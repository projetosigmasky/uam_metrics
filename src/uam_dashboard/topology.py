"""Topology features derived from UAM and official REH centerlines."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .reh_parser import load_reh_network
from .uam_corridor_parser import load_uam_corridor_network


ELIGIBLE_NODE_TYPES = {"waypoint", "geometric node"}


def _coordinate_key(point: dict[str, Any]) -> tuple[float, float]:
    # Six decimal places are roughly 0.1 m here: enough to absorb CSV noise
    # without conflating the two displaced parallel tracks.
    return round(float(point["lat"]), 6), round(float(point["lon"]), 6)


def network_junction_features(routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return planned waypoints incident to at least three distinct edges.

    Routes may reuse the same physical segment. Edges are therefore undirected
    coordinate pairs in a set, and an edge contributes only once to node degree.
    """
    adjacency: dict[tuple[float, float], set[tuple[float, float]]] = defaultdict(set)
    node_points: dict[tuple[float, float], list[dict[str, Any]]] = defaultdict(list)
    node_routes: dict[tuple[float, float], set[str]] = defaultdict(set)
    for route in routes:
        points = route["points"]
        keys = [_coordinate_key(point) for point in points]
        for key, point in zip(keys, points):
            node_points[key].append(point)
            node_routes[key].add(str(route["resource_id"]))
        for left, right in zip(keys, keys[1:]):
            if left != right:
                adjacency[left].add(right)
                adjacency[right].add(left)

    junctions = []
    for key, neighbors in sorted(adjacency.items()):
        if len(neighbors) <= 2:
            continue
        points = node_points[key]
        eligible = [point for point in points if str(point["type"]).casefold() in ELIGIBLE_NODE_TYPES]
        if not eligible:
            continue
        chosen = eligible[0]
        junctions.append({
            "type": "Feature",
            "properties": {
                "method": "uam_network_distinct_edge_degree",
                "geometry_dimension": "2D",
                "node_name": str(chosen["name"]),
                "node_type": str(chosen["type"]),
                "network_degree": len(neighbors),
                "uam_route_ids": sorted(node_routes[key]),
                "uam_route_labels": sorted({
                    str(route["label"]) for route in routes
                    if str(route["resource_id"]) in node_routes[key]
                }),
                "reh_resource_ids": [],
                "reh_labels": [],
            },
            "geometry": {
                "type": "Point",
                "coordinates": [float(chosen["lon"]), float(chosen["lat"])],
            },
        })
    for index, feature in enumerate(junctions, 1):
        feature["properties"]["resource_id"] = f"XJUNCTION{index:03d}"
        feature["properties"]["label"] = feature["properties"]["node_name"]
    return junctions


def reh_junction_features(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return official REH fixes incident to three or more distinct segments.

    Each official REH segment has a centerline between its two fixes. Shared
    endpoints are joined by position at six decimal places; polygon vertices
    are intentionally excluded because they describe boundaries, not fixes.
    """
    adjacency: dict[tuple[float, float], set[tuple[float, float]]] = defaultdict(set)
    node_segments: dict[tuple[float, float], set[str]] = defaultdict(set)
    node_labels: dict[tuple[float, float], set[str]] = defaultdict(set)
    segment_labels = {str(segment["resource_id"]): str(segment["label"]) for segment in segments}
    for segment in segments:
        coordinates = segment.get("coordinates", [])
        if len(coordinates) < 2:
            continue
        left = round(float(coordinates[0][0]), 6), round(float(coordinates[0][1]), 6)
        right = round(float(coordinates[-1][0]), 6), round(float(coordinates[-1][1]), 6)
        if left == right:
            continue
        adjacency[left].add(right)
        adjacency[right].add(left)
        for key, name in ((left, segment.get("fix_a_name")), (right, segment.get("fix_b_name"))):
            node_segments[key].add(str(segment["resource_id"]))
            if name:
                node_labels[key].add(str(name))

    junctions = []
    for (lat, lon), neighbors in sorted(adjacency.items()):
        if len(neighbors) <= 2:
            continue
        key = lat, lon
        names = sorted(node_labels[key])
        label = names[0] if names else f"Fix REH {lat:.6f}, {lon:.6f}"
        segment_ids = sorted(node_segments[key])
        junctions.append({
            "type": "Feature",
            "properties": {
                "method": "reh_centerline_distinct_edge_degree",
                "geometry_dimension": "2D",
                "node_name": label,
                "node_type": "REH fix",
                "network_degree": len(neighbors),
                "uam_route_ids": [],
                "uam_route_labels": [],
                "reh_resource_ids": segment_ids,
                "reh_labels": [segment_labels[identifier] for identifier in segment_ids],
            },
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
        })
    for index, feature in enumerate(junctions, 1):
        feature["properties"]["resource_id"] = f"XREH{index:03d}"
        feature["properties"]["label"] = feature["properties"]["node_name"]
    return junctions


def candidate_node_collection(
    uam_routes: list[dict[str, Any]], reh_segments: list[dict[str, Any]]
) -> dict[str, Any]:
    """Expose geometric candidates without assigning simulated criticality."""
    uam_features = network_junction_features(uam_routes)
    reh_features = reh_junction_features(reh_segments)
    for feature in uam_features:
        feature["properties"]["criterion"] = "uam_junction"
        feature["properties"]["status"] = "candidate"
    for feature in reh_features:
        feature["properties"]["criterion"] = "reh_junction"
        feature["properties"]["status"] = "candidate"
    return {
        "type": "FeatureCollection",
        "properties": {
            "uam_junction_count": len(uam_features),
            "reh_junction_count": len(reh_features),
            "definition": "degree greater than two using distinct undirected centerline edges",
            "status": "geometric_candidates_pending_replica_throughput",
        },
        "features": uam_features + reh_features,
    }


def write_candidate_node_assets(
    output_dir: Path, uam_csv: Path | None, reh_xml: Path | None
) -> dict[str, Any]:
    uam_routes = load_uam_corridor_network(uam_csv)["routes"] if uam_csv else []
    reh_segments = load_reh_network(reh_xml)["segments"] if reh_xml else []
    collection = candidate_node_collection(uam_routes, reh_segments)
    data_path = output_dir / "assets" / "data" / "candidate_nodes.geojson"
    js_path = output_dir / "assets" / "candidate_nodes.js"
    data_path.parent.mkdir(parents=True, exist_ok=True)
    js_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text(json.dumps(collection, ensure_ascii=False, indent=2), encoding="utf-8")
    serialized = json.dumps(collection, ensure_ascii=False, separators=(",", ":"))
    js_path.write_text(f"window.__UAM_CANDIDATE_NODES__ = {serialized};\n", encoding="utf-8")
    return collection
