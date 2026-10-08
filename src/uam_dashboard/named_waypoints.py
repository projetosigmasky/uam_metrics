"""Capacity resources: named fixes only; exact exported positions, no proximity merge."""
from __future__ import annotations
import hashlib
import json
import math
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from .capacity import _reh_vertical_interval_m


def normalize_name(value):
    text = ''.join(c for c in unicodedata.normalize('NFKD', str(value).strip()) if not unicodedata.combining(c))
    return re.sub(r'[^A-Z0-9]+', '_', text.upper()).strip('_')


def source_record(path):
    path = Path(path)
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return {'file': path.name, 'sha256': digest.hexdigest()}


def named_waypoint_inventory(routes, segments):
    nodes = {}
    def add(network, name, lat, lon, vertical, route, label, dimensions=None):
        normalized = normalize_name(name)
        if lat is not None and lon is not None and not all(math.isfinite(float(v)) for v in (lat,lon)):
            raise ValueError("Non-finite named waypoint coordinate")
        if not normalized or normalized in {'NONE', 'NULL', 'NAN'} or lat is None or lon is None:
            return
        key = (network, normalized, float(lat), float(lon), vertical, dimensions)
        node = nodes.setdefault(key, {'names': set(), 'routes': set(), 'labels': set()})
        node['names'].add(str(name).strip()); node['routes'].add(str(route)); node['labels'].add(str(label))
    for route in routes:
        for point in route['points']:
            if str(point['type']).strip().casefold() == 'waypoint':
                alt = point.get('altitude_m')
                half = point.get('height_m', 0) / 2
                vertical = (alt - half, alt + half) if alt is not None else None
                add('UAM', point['name'], point['lat'], point['lon'], vertical, route['resource_id'], route['label'], (point.get('height_m'), point.get('width_m')))
    # REH positions retain all incident altitude envelopes; unknown inputs disable 3D counting.
    reh = defaultdict(list)
    for segment in segments:
        for fix in segment.get('explicit_fixes', []):
            if normalize_name(fix['name']) and fix['lat'] is not None and fix['lon'] is not None:
                reh[normalize_name(fix['name']), fix['lat'], fix['lon']].append((fix, segment))
    for items in reh.values():
        intervals = [_reh_vertical_interval_m(segment) for _, segment in items]
        valid = all(i is not None and all(math.isfinite(v) for v in i) and i[0] <= i[1] for i in intervals)
        vertical = tuple(sorted(set(intervals))) if valid else None
        for fix, segment in items:
            add('REH', fix['name'], fix['lat'], fix['lon'], vertical, segment['resource_id'], segment['label'])
    features = []
    for key, node in sorted(nodes.items(), key=lambda item: repr(item[0])):
        network, normalized, lat, lon, vertical, dimensions = key
        identifier = network + '-WP-' + hashlib.sha256(json.dumps(key, ensure_ascii=False).encode()).hexdigest()[:20]
        intervals = ([list(vertical)] if network == 'UAM' else [list(v) for v in vertical]) if vertical is not None else []
        altitude = sum(vertical)/2 if network == 'UAM' and vertical else None
        p = {'resource_id': identifier, 'label': sorted(node['names'])[0], 'node_name': sorted(node['names'])[0],
             'original_names': sorted(node['names']), 'normalized_name': normalized, 'network': network,
             'criterion': network.lower() + '_named_waypoint', 'network_degree': None,
             'altitude_m': altitude, 'vertical_intervals_m': intervals,
             'altitude_status': 'known_envelopes' if intervals else 'unknown_or_invalid_envelope',
             'dimensions_m': dimensions, 'uam_route_ids': sorted(node['routes']) if network == 'UAM' else [],
             'reh_resource_ids': sorted(node['routes']) if network == 'REH' else [],
             'uam_route_labels': sorted(node['labels']) if network == 'UAM' else [],
             'reh_labels': sorted(node['labels']) if network == 'REH' else [],
             'status': 'geometry_only_pending_recomputation', 'method': 'explicit_named_export_position'}
        features.append({'type': 'Feature', 'properties': p, 'geometry': {'type': 'Point', 'coordinates': [lon, lat]}})
    groups = defaultdict(list)
    for feature in features:
        p = feature['properties']; groups[p['network'], p['normalized_name']].append(p['resource_id'])
    for feature in features:
        p = feature['properties']; members = groups[p['network'], p['normalized_name']]
        p.update(name_group_id=p['network'] + ':' + p['normalized_name'], name_position_count=len(members), name_position_ids=members,
                 grouping_rule='name index only; exact coordinates/levels/dimensions remain independent; no analytical name total')
    return features


# Explicit spelling/abbreviation equivalences only. No unrestricted fuzzy matching.
REH_NAME_ALIASES = {
    "AVENIDA_MORUMBI": {"MORUMBI"},
    "MORUMBI": {"AVENIDA_MORUMBI"},
    "VD_ANTARTICA": {"VIADUTO_ANTARTICA"},
    "VD_SAO_CARLOS": {"VIADUTO_SAO_CARLOS"},
    "VD_GRANDE_SAO_PAULO": {"VIADUTO_GRANDE_SAO_PAULO"},
}
CAPACITY_SELECTION_VERSION = "reh-uam-junctions-v3"
REH_REFERENCE_MAX_DISTANCE_M = 500.0
TERMINAL_TYPES = {"vertiport", "airport"}


def _physical_key(point):
    return (float(point["lat"]), float(point["lon"]), point.get("altitude_m"),
            point.get("height_m"), point.get("width_m"))


def _distance_m(left, right):
    lat1, lon1 = left
    lat2, lon2 = right
    angle = math.sin(math.radians(lat2-lat1)/2)**2
    angle += math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(math.radians(lon2-lon1)/2)**2
    return 2*6371000*math.asin(min(1., math.sqrt(angle)))


def uam_selection_inventory(routes, segments, reference_max_distance_m=REH_REFERENCE_MAX_DISTANCE_M):
    """Audit named positions, topology and terminal use without merging positions.

    Degree counts exact distinct undirected physical edges, including geometric
    vertices as neighbors but never as capacity resources. A terminal gateway is
    the first/last named Waypoint after/before an Airport or Vertiport; geometric
    shaping points between it and the terminal do not change that role.
    """
    inventory = named_waypoint_inventory(routes, segments)
    adjacency = defaultdict(set)
    usages = defaultdict(lambda: {"terminal_gateway": set(), "interior": set()})
    for route in routes:
        points = route["points"]
        keys = [_physical_key(point) for point in points]
        for left, right in zip(keys, keys[1:]):
            if left != right:
                adjacency[left].add(right)
                adjacency[right].add(left)
        named_indices = [i for i, p in enumerate(points) if str(p["type"]).strip().casefold() == "waypoint" and normalize_name(p["name"])]
        gateways = set()
        if named_indices:
            if str(points[0]["type"]).casefold() in TERMINAL_TYPES:
                gateways.add(named_indices[0])
            if str(points[-1]["type"]).casefold() in TERMINAL_TYPES:
                gateways.add(named_indices[-1])
        for i in named_indices:
            usages[(keys[i], normalize_name(points[i]["name"]))]["terminal_gateway" if i in gateways else "interior"].add(str(route["resource_id"]))
    # Preserve the original REH topology rule: distinct undirected neighbors,
    # endpoints joined at six decimal places. Resource identities remain exact.
    reh_adjacency = defaultdict(set)
    for segment in segments:
        coordinates = segment.get("coordinates", [])
        if len(coordinates) < 2:
            continue
        left = tuple(round(float(v), 6) for v in coordinates[0][:2])
        right = tuple(round(float(v), 6) for v in coordinates[-1][:2])
        if left != right:
            reh_adjacency[left].add(right)
            reh_adjacency[right].add(left)
    # All explicit named fixes remain available as UAM reference landmarks.
    reh = [f for f in inventory if f["properties"]["network"] == "REH"]
    for feature in inventory:
        p = feature["properties"]
        p["analysis_method_version"] = CAPACITY_SELECTION_VERSION
        if p["network"] == "REH":
            key = tuple(round(float(v), 6) for v in reversed(feature["geometry"]["coordinates"][:2]))
            degree = len(reh_adjacency[key])
            p.update(network_degree=degree, capacity_eligible=degree >= 3,
                     selection_reasons=[] if degree >= 3 else ["fewer_than_three_distinct_reh_edges"],
                     selection_rule="reh_degree_at_least_3_distinct_undirected_edges_round6")
            continue
        lon, lat = feature["geometry"]["coordinates"]
        height, width = p["dimensions_m"]
        key = (lat, lon, p["altitude_m"], height, width)
        p["network_degree"] = len(adjacency[key])
        p["distinct_edge_neighbors"] = [list(k) for k in sorted(adjacency[key], key=repr)]
        usage = usages[(key, p["normalized_name"])]
        p["terminal_route_ids"] = sorted(usage["terminal_gateway"])
        p["interior_route_ids"] = sorted(usage["interior"])
        p["terminal_only"] = not bool(usage["interior"])
        names = {p["normalized_name"]} | REH_NAME_ALIASES.get(p["normalized_name"], set())
        matches = []
        for ref in reh:
            q = ref["properties"]
            if q["normalized_name"] not in names:
                continue
            ref_lon, ref_lat = ref["geometry"]["coordinates"]
            matches.append((_distance_m((lat,lon),(ref_lat,ref_lon)), q))
        matches.sort(key=lambda item: (item[0], item[1]["resource_id"]))
        reasons = []
        if p["network_degree"] < 3: reasons.append("fewer_than_three_distinct_physical_edges")
        if p["terminal_only"]: reasons.append("terminal_gateway_only")
        p["reh_reference"] = None
        if not matches:
            reasons.append("no_explicit_reh_name_or_documented_alias")
        else:
            distance, q = matches[0]
            p["reh_reference"] = {"resource_id": q["resource_id"], "label": q["label"],
                "horizontal_distance_m": distance, "max_distance_m": reference_max_distance_m,
                "match_method": "normalized_exact_name" if q["normalized_name"] == p["normalized_name"] else "documented_alias",
                "coordinates": next(f["geometry"]["coordinates"] for f in reh if f["properties"]["resource_id"] == q["resource_id"])}
            if distance > reference_max_distance_m:
                reasons.append("reh_reference_outside_distance_threshold")
            elif len(matches) > 1 and abs(matches[1][0]-distance) < .001:
                reasons.append("ambiguous_reh_reference")
        p.update(capacity_eligible=not reasons, selection_reasons=reasons,
                 selection_rule="uam_degree_at_least_3_and_reh_reference_within_500m_and_nonterminal_use")
    return inventory


def named_waypoint_features(routes, segments):
    inventory = uam_selection_inventory(routes, segments)
    features = [f for f in inventory if f["properties"]["capacity_eligible"]]
    groups = defaultdict(list)
    for feature in features:
        groups[feature["properties"]["name_group_id"]].append(feature["properties"]["resource_id"])
    for feature in features:
        p = feature["properties"]
        p["name_all_position_count"] = p["name_position_count"]
        p["name_position_ids"] = groups[p["name_group_id"]]
        p["name_position_count"] = len(p["name_position_ids"])
    return features
