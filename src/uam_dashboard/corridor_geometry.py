"""Dissolve map footprints and audit true UAM centerline junctions.

No source route is edited and no new capacity resource is declared. Horizontal
buffer overlap alone never establishes connectivity between flight levels.
"""
from __future__ import annotations

import hashlib
from collections import defaultdict
from shapely.geometry import LineString, Point, mapping, shape
from shapely.ops import unary_union
from shapely.strtree import STRtree
from .capacity import _buffered_route_groups, _official_uam_route_groups


def _key(lon, lat, altitude, dimensions):
    # Millimetre-scale numerical precision only; no proximity snapping.
    return (round(lon, 8), round(lat, 8), round(altitude, 3), *dimensions)


def _intersection_points(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type == "Point":
        return [geometry]
    if geometry.geom_type == "LineString":
        return [Point(geometry.coords[0]), Point(geometry.coords[-1])]
    return [p for part in getattr(geometry, "geoms", []) for p in _intersection_points(part)]


def uam_geometry(routes: list[dict]) -> dict:
    """Union projected footprints; node intersecting centerlines in 3D.

    Coincident segments share an edge, including reversed OD routes. Partial
    overlaps split at both endpoints. Crossings connect only when interpolated
    altitudes agree at millimetre precision and dimensions agree. No proximity snapping.
    """
    corridors = _buffered_route_groups(_official_uam_route_groups(routes), 250.)
    dissolved = unary_union([shape(c["buffer_geometry"]) for c in corridors])
    footprints = list(dissolved.geoms) if dissolved.geom_type == "MultiPolygon" else ([dissolved] if not dissolved.is_empty else [])
    features = [{"type": "Feature", "properties": {
        "resource_id": f"UAM-FOOTPRINT-{i}", "label": "Rede UAM · área consolidada",
        "projection_only": True, "source_route_count": len(routes),
        "buffer_method": "union_of_metric_route_buffers",
        "altitude_min_m": min(a for r in routes for a in r["altitudes_m"]),
        "altitude_max_m": max(a for r in routes for a in r["altitudes_m"]),
        "widths_m": sorted({r["width_m"] for r in routes}),
        "heights_m": sorted({r["height_m"] for r in routes}),
    }, "geometry": mapping(polygon)} for i, polygon in enumerate(footprints, 1)]
    unique = {}
    named = defaultdict(set)
    terminals = set()
    occurrences = 0
    for route in routes:
        points = route["points"]
        dimensions = (route["height_m"], route["width_m"])
        keys = [_key(p["lon"], p["lat"], p["altitude_m"], dimensions) for p in points]
        for p, key in zip(points, keys):
            if p["type"].casefold() == "waypoint": named[key].add(p["name"])
            if p["type"].casefold() in {"vertiport", "airport"}: terminals.add(key)
        for a, b in zip(keys, keys[1:]):
            if a[:2] == b[:2]: continue
            occurrences += 1
            key = tuple(sorted((a, b)))
            unique.setdefault(key, {"ends": key, "routes": set()})["routes"].add(route["label"])
    edges = list(unique.values())
    lines = [LineString([e["ends"][0][:2], e["ends"][1][:2]]) for e in edges]
    splits = [{0., 1.} for _ in edges]
    tree = STRtree(lines)
    separated = 0
    for i, line in enumerate(lines):
        a, b = edges[i]["ends"]
        for j in tree.query(line):
            j = int(j)
            if j <= i: continue
            c, d = edges[j]["ends"]
            intersection = line.intersection(lines[j])
            if intersection.is_empty: continue
            points = _intersection_points(intersection)
            # Collinear projections can meet in 3D between their endpoints
            # when one segment climbs/descends relative to the other.
            if intersection.geom_type == "LineString" and len(points) == 2 and a[3:] == c[3:]:
                differences = []
                for point in points:
                    t = line.project(point, normalized=True)
                    u = lines[j].project(point, normalized=True)
                    differences.append(a[2] + t * (b[2] - a[2]) - c[2] - u * (d[2] - c[2]))
                if differences[0] * differences[1] < 0:
                    fraction = differences[0] / (differences[0] - differences[1])
                    points.append(LineString(points).interpolate(fraction, normalized=True))
            for point in points:
                t = line.project(point, normalized=True)
                u = lines[j].project(point, normalized=True)
                z = a[2] + t * (b[2] - a[2])
                other_z = c[2] + u * (d[2] - c[2])
                if round(z, 3) == round(other_z, 3) and a[3:] == c[3:]:
                    splits[i].add(t)
                    splits[j].add(u)
                else: separated += 1
    adjacency = defaultdict(set)
    provenance = defaultdict(set)
    merged = {}
    for i, edge in enumerate(edges):
        a, b = edge["ends"]
        vertices = [_key(a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]),
                         a[2] + t * (b[2] - a[2]), a[3:]) for t in sorted(splits[i])]
        for left, right in zip(vertices, vertices[1:]):
            if left == right: continue
            adjacency[left].add(right)
            adjacency[right].add(left)
            provenance[left].update(edge["routes"])
            provenance[right].update(edge["routes"])
            merged.setdefault(tuple(sorted((left, right))), set()).update(edge["routes"])
    junctions = []
    for key, neighbors in sorted(adjacency.items()):
        if len(neighbors) < 3 or key in terminals: continue
        junctions.append({"type": "Feature", "properties": {
            "resource_id": "UAM-GJ-" + hashlib.sha256(repr(key).encode()).hexdigest()[:16],
            "label": " / ".join(sorted(named[key])) or "Junção geométrica UAM",
            "network_degree": len(neighbors), "altitude_m": key[2],
            "height_m": key[3], "width_m": key[4], "route_labels": sorted(provenance[key]),
            "status": "geometric_diagnostic_only", "capacity_resource": False,
            "method": "noded_unique_3d_centerlines_no_proximity_snap",
        }, "geometry": {"type": "Point", "coordinates": list(key[:3])}})
    centerlines = [{"type": "Feature", "properties": {"route_labels": sorted(labels)},
                   "geometry": {"type": "LineString", "coordinates": [list(a[:3]), list(b[:3])]}}
                  for (a, b), labels in sorted(merged.items())]
    return {
        "projection": {"type": "FeatureCollection", "properties": {
            "projection": "dissolved_horizontal_footprint_not_3d_connectivity", "route_count": len(routes)}, "features": features},
        "junctions": {"type": "FeatureCollection", "features": junctions},
        "centerlines": {"type": "FeatureCollection", "features": centerlines},
        "audit": {"route_count": len(routes), "segment_occurrences": occurrences,
                  "unique_original_segments": len(edges), "duplicate_segment_occurrences": occurrences - len(edges),
                  "noded_unique_segments": len(merged), "geometric_junctions": len(junctions),
                  "separated_intersection_checks": separated,
                  "rules": "union footprints for map only; 3D centerlines connect at equal altitude rounded to 1mm, same dimensions; no proximity snap; no capacity or source-route change"},
    }
