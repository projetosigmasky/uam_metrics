from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .metrics import (
    _point_to_polyline_distances_m,
    _polyline_distance_m,
    flight_instance_frame,
    haversine_m,
)
from .reh_parser import points_in_polygons


def capacity_metrics(
    df: pd.DataFrame,
    planned_flights: list[dict[str, Any]],
    tracks: dict[str, Any],
    conformity_by_instance: dict[str, dict[str, Any]],
    lowc_event_count: int,
    corridor_width_m: float,
    window_seconds: int,
    capacity_percentile: float,
    gap_seconds: float,
    reset_distance_m: float,
    jump_m: float,
    reh_segments: list[dict[str, Any]] | None = None,
    official_uam_routes: list[dict[str, Any]] | None = None,
    crossing_capture_radius_m: float = 250.0,
) -> dict[str, Any]:
    """Compute capacity proxies and 2D UAM-corridor/REH crossing resources."""

    annotated = flight_instance_frame(df, gap_seconds, reset_distance_m, jump_m)
    instances = _flight_instances(annotated)
    scenario_route_groups, planned_to_scenario_route = _planned_route_groups(
        planned_flights, route_prefix="SCN"
    )
    if official_uam_routes:
        uam_route_groups = _official_uam_route_groups(official_uam_routes)
        uam_geometry_source = "product2_uam_corridor_csv_6_vertiports"
    else:
        uam_route_groups, _ = _planned_route_groups(
            [flight for flight in planned_flights if flight.get("vehicle_type") == "eVTOL"],
            route_prefix="UAM",
        )
        uam_geometry_source = "scenario_route_buffers"
    uam_corridors = _buffered_route_groups(uam_route_groups, corridor_width_m)
    if reh_segments:
        route_groups = _official_route_groups(reh_segments)
        planned_to_route = _planned_to_official_routes(planned_flights, route_groups)
        geometry_source = "official_reh_polygons"
    else:
        route_groups = scenario_route_groups
        planned_to_route = {
            key: [value] for key, value in planned_to_scenario_route.items()
        }
        geometry_source = "scenario_route_buffers"
    density = _corridor_density(df, route_groups, corridor_width_m)
    throughput = _throughput_metrics(
        instances,
        tracks,
        conformity_by_instance,
        planned_to_route,
        {route["resource_id"]: route["label"] for route in route_groups},
        window_seconds,
        capacity_percentile,
    )
    complexity = _complexity_components(
        uam_corridors,
        _official_route_groups(reh_segments or []),
        annotated,
        tracks,
        lowc_event_count,
        window_seconds,
        capacity_percentile,
        crossing_capture_radius_m,
    )
    throughput["crossing_waypoints"] = _crossing_throughput(complexity)
    return {
        "available": bool(instances),
        "window_seconds": int(window_seconds),
        "capacity_percentile": float(capacity_percentile),
        "corridor_width_m": float(corridor_width_m),
        "crossing_capture_radius_m": float(crossing_capture_radius_m),
        "geometry_source": geometry_source,
        "uam_geometry_source": uam_geometry_source,
        "official_reh_segment_count": int(len(reh_segments or [])),
        "density": density,
        "throughput": throughput,
        "complexity": complexity,
    }


def _official_uam_route_groups(routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            **route,
            "coordinates": np.asarray(route["coordinates"], dtype=float),
            "waypoint_count": int(route.get("waypoint_count", len(route["coordinates"]))),
        }
        for route in routes
    ]


def _official_route_groups(reh_segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            **segment,
            "coordinates": np.asarray(segment["coordinates"], dtype=float),
            "waypoint_count": len(segment["coordinates"]),
        }
        for segment in reh_segments
    ]


def _planned_to_official_routes(
    planned_flights: list[dict[str, Any]],
    route_groups: list[dict[str, Any]],
) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for flight in planned_flights:
        coordinates = np.asarray(
            [[coordinate[1], coordinate[0]] for coordinate in flight["coordinates"]],
            dtype=float,
        )
        sampled = _densify_polyline(coordinates, 100.0)
        matched = [
            route["resource_id"]
            for route in route_groups
            if np.any(points_in_polygons(sampled, route.get("polygons", [])))
        ]
        mapping[flight["flight_instance"]] = matched
    return mapping


def _densify_polyline(polyline: np.ndarray, spacing_m: float) -> np.ndarray:
    if len(polyline) < 2:
        return polyline
    samples = [polyline[0]]
    for start, end in zip(polyline[:-1], polyline[1:]):
        length_m = float(
            _polyline_distance_m(np.asarray([start, end], dtype=float))
        )
        steps = max(1, int(np.ceil(length_m / max(spacing_m, 1.0))))
        samples.extend(start + (end - start) * (index / steps) for index in range(1, steps + 1))
    return np.asarray(samples, dtype=float)


def _flight_instances(annotated: pd.DataFrame) -> list[dict[str, Any]]:
    instances: list[dict[str, Any]] = []
    for flight_instance, group in annotated.groupby("flight_instance", sort=True):
        group = group.sort_values("simt")
        first = group.iloc[0]
        last = group.iloc[-1]
        instances.append(
            {
                "flight_instance": str(flight_instance),
                "aircraft_id": str(first["id"]),
                "start_s": float(group["simt"].min()),
                "end_s": float(group["simt"].max()),
                "origin": (float(first["lat"]), float(first["lon"])),
                "destination": (float(last["lat"]), float(last["lon"])),
            }
        )
    return instances


def _planned_route_groups(
    planned_flights: list[dict[str, Any]],
    route_prefix: str = "REH",
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    grouped: dict[tuple[tuple[float, float], ...], dict[str, Any]] = {}
    planned_to_route: dict[str, str] = {}

    for flight in planned_flights:
        signature = tuple((round(float(lon), 4), round(float(lat), 4)) for lon, lat in flight["coordinates"])
        if signature not in grouped:
            route_id = f"{route_prefix}{len(grouped) + 1:03d}"
            coordinates = np.asarray([[lat, lon] for lon, lat in flight["coordinates"]], dtype=float)
            grouped[signature] = {
                "resource_id": route_id,
                "label": route_id,
                "coordinates": coordinates,
                "flight_instances": [],
                "waypoint_count": len(flight["coordinates"]),
            }
        grouped[signature]["flight_instances"].append(flight["flight_instance"])
        planned_to_route[flight["flight_instance"]] = grouped[signature]["resource_id"]

    return list(grouped.values()), planned_to_route


def _buffered_route_groups(
    route_groups: list[dict[str, Any]], corridor_width_m: float
) -> list[dict[str, Any]]:
    buffered = []
    for route in route_groups:
        semi_width_m = float(route.get("semi_width_m", corridor_width_m))
        ring = _corridor_polygon_coordinates(route["coordinates"], semi_width_m)
        buffered.append(
            {
                **route,
                "polygons": [ring],
                "area_m2": _corridor_area_m2(route["coordinates"], semi_width_m),
                "semi_width_m": semi_width_m,
                "resource_type": "uam_corridor",
            }
        )
    return buffered


def _corridor_density(
    df: pd.DataFrame,
    route_groups: list[dict[str, Any]],
    corridor_width_m: float,
) -> dict[str, Any]:
    if not route_groups or df.empty:
        return {
            "available": False,
            "corridor_area_km2": 0.0,
            "mean_simultaneous_aircraft": 0.0,
            "peak_simultaneous_aircraft": 0,
            "air_traffic_density_per_km2": 0.0,
            "hotspot_density_per_km2": 0.0,
            "hotspots": {"type": "FeatureCollection", "features": []},
        }

    area_m2 = sum(_route_area_m2(route, corridor_width_m) for route in route_groups)
    area_km2 = area_m2 / 1_000_000.0
    if area_km2 <= 0:
        return {"available": False, "corridor_area_km2": 0.0}

    points = df[["lat", "lon"]].to_numpy(dtype=float)
    inside_any = np.zeros(len(points), dtype=bool)
    route_masks = []
    for route in route_groups:
        route_mask = _route_inside_mask(points, route, corridor_width_m)
        route_masks.append(route_mask)
        inside_any |= route_mask

    corridor_samples = df.loc[inside_any, ["simt", "id"]]
    simultaneous = corridor_samples.groupby("simt")["id"].nunique()
    if simultaneous.empty:
        mean_simultaneous = 0.0
        peak_simultaneous = 0
    else:
        mean_simultaneous = float(simultaneous.mean())
        peak_simultaneous = int(simultaneous.max())

    hotspot_density = 0.0
    hotspot_features = []
    for route, route_mask in zip(route_groups, route_masks):
        route_samples = df.loc[route_mask, ["simt", "id"]]
        route_simultaneous = route_samples.groupby("simt")["id"].nunique()
        route_area_km2 = _route_area_m2(route, corridor_width_m) / 1_000_000.0
        route_density = 0.0
        route_peak = 0
        route_mean = 0.0
        if route_area_km2 > 0 and not route_simultaneous.empty:
            route_mean = float(route_simultaneous.mean())
            route_peak = int(route_simultaneous.max())
            route_density = route_mean / route_area_km2
            hotspot_density = max(hotspot_density, route_density)
        hotspot_features.append(
            {
                "type": "Feature",
                "properties": {
                    "resource_id": route["resource_id"],
                    "label": route["label"],
                    "reh_name": route.get("name", route["label"]),
                    "section": route.get("section", ""),
                    "route_type": route.get("route_type", ""),
                    "semi_width_m": route.get("semi_width_m"),
                    "mean_simultaneous_aircraft": route_mean,
                    "peak_simultaneous_aircraft": route_peak,
                    "corridor_area_km2": float(route_area_km2),
                    "air_traffic_density_per_km2": float(route_density),
                    "sample_count": int(len(route_samples)),
                },
                "geometry": _route_geometry(route, corridor_width_m),
            }
        )

    hotspot_features.sort(
        key=lambda feature: feature["properties"]["air_traffic_density_per_km2"],
        reverse=True,
    )
    for feature in hotspot_features:
        density = feature["properties"]["air_traffic_density_per_km2"]
        feature["properties"]["density_ratio"] = float(density / hotspot_density) if hotspot_density > 0 else 0.0

    return {
        "available": True,
        "corridor_area_km2": float(area_km2),
        "mean_simultaneous_aircraft": mean_simultaneous,
        "peak_simultaneous_aircraft": peak_simultaneous,
        "air_traffic_density_per_km2": float(mean_simultaneous / area_km2),
        "hotspot_density_per_km2": float(hotspot_density),
        "hotspots": {"type": "FeatureCollection", "features": hotspot_features},
    }


def _route_inside_mask(
    points: np.ndarray,
    route: dict[str, Any],
    corridor_width_m: float,
) -> np.ndarray:
    if route.get("polygons"):
        return points_in_polygons(points, route["polygons"])
    deviations = _point_to_polyline_distances_m(points, route["coordinates"])
    return deviations <= corridor_width_m


def _route_area_m2(route: dict[str, Any], corridor_width_m: float) -> float:
    if route.get("area_m2") is not None:
        return float(route["area_m2"])
    return _corridor_area_m2(route["coordinates"], corridor_width_m)


def _route_geometry(route: dict[str, Any], corridor_width_m: float) -> dict[str, Any]:
    if route.get("polygons"):
        return {
            "type": "MultiPolygon",
            "coordinates": [[ring] for ring in route["polygons"]],
        }
    return {
        "type": "Polygon",
        "coordinates": [_corridor_polygon_coordinates(route["coordinates"], corridor_width_m)],
    }


def _corridor_area_m2(polyline: np.ndarray, corridor_width_m: float) -> float:
    length_m = _polyline_distance_m(polyline)
    return float(length_m * 2.0 * corridor_width_m + np.pi * corridor_width_m**2)


def _corridor_polygon_coordinates(polyline: np.ndarray, corridor_width_m: float) -> list[list[float]]:
    if len(polyline) < 2:
        lat = float(polyline[0, 0]) if len(polyline) else 0.0
        lon = float(polyline[0, 1]) if len(polyline) else 0.0
        return [[lon, lat], [lon, lat], [lon, lat], [lon, lat]]

    reference_lat = float(np.mean(polyline[:, 0]))
    xy = _project_with_reference(polyline, reference_lat)
    left_offsets = []
    right_offsets = []
    for index, point in enumerate(xy):
        if index == 0:
            direction = xy[1] - point
        elif index == len(xy) - 1:
            direction = point - xy[index - 1]
        else:
            before = point - xy[index - 1]
            after = xy[index + 1] - point
            direction = before / max(float(np.linalg.norm(before)), 1.0) + after / max(float(np.linalg.norm(after)), 1.0)
        norm = float(np.linalg.norm(direction))
        normal = np.asarray([0.0, 1.0]) if norm <= 0 else np.asarray([-direction[1], direction[0]]) / norm
        left_offsets.append(point + normal * corridor_width_m)
        right_offsets.append(point - normal * corridor_width_m)

    polygon_xy = np.vstack([left_offsets, right_offsets[::-1], left_offsets[:1]])
    return [_unproject_xy(point, reference_lat) for point in polygon_xy]


def _throughput_metrics(
    instances: list[dict[str, Any]],
    tracks: dict[str, Any],
    conformity_by_instance: dict[str, dict[str, Any]],
    planned_to_route: dict[str, list[str]],
    route_labels: dict[str, str],
    window_seconds: int,
    capacity_percentile: float,
) -> dict[str, Any]:
    track_group_by_instance = {
        feature["properties"]["flight_instance"]: feature["properties"]["trajectory_group"]
        for feature in tracks.get("features", [])
    }
    resources = {
        "od_pairs": [],
        "trajectory_groups": [],
        "planned_reh": [],
    }

    for instance in instances:
        origin = instance["origin"]
        destination = instance["destination"]
        resources["od_pairs"].append(
            {
                "resource_id": _od_pair_id(origin, destination),
                "label": _od_pair_label(origin, destination),
                "time_s": instance["start_s"],
                "map_target": {
                    "type": "od_pair",
                    "coordinates": [
                        [float(origin[1]), float(origin[0])],
                        [float(destination[1]), float(destination[0])],
                    ],
                },
            }
        )
        group = track_group_by_instance.get(instance["flight_instance"])
        if group:
            resources["trajectory_groups"].append(
                {
                    "resource_id": group,
                    "label": group,
                    "time_s": instance["start_s"],
                    "map_target": {"type": "trajectory_group", "resource_id": group},
                }
            )
        planned = conformity_by_instance.get(instance["flight_instance"], {}).get("planned_flight_instance")
        route_ids = planned_to_route.get(planned, [])
        for route_id in route_ids:
            resources["planned_reh"].append(
                {
                    "resource_id": route_id,
                    "label": route_labels.get(route_id, route_id),
                    "time_s": instance["start_s"],
                    "map_target": {"type": "reh_segment", "resource_id": route_id},
                }
            )

    return {
        resource_type: _resource_throughput(items, window_seconds, capacity_percentile)
        for resource_type, items in resources.items()
    }


def _resource_throughput(
    items: list[dict[str, Any]],
    window_seconds: int,
    capacity_percentile: float,
) -> dict[str, Any]:
    if not items:
        return {
            "available": False,
            "capacity_reference_per_hour": 0.0,
            "top_resources": [],
            "resource_count": 0,
        }

    start_s = min(item["time_s"] for item in items)
    window_hours = max(window_seconds, 1) / 3600.0
    counts: dict[tuple[str, int], int] = {}
    labels: dict[str, str] = {}
    totals: dict[str, int] = {}
    map_targets: dict[str, dict[str, Any]] = {}
    for item in items:
        window_index = int((item["time_s"] - start_s) // max(window_seconds, 1))
        key = (item["resource_id"], window_index)
        counts[key] = counts.get(key, 0) + 1
        labels[item["resource_id"]] = item["label"]
        totals[item["resource_id"]] = totals.get(item["resource_id"], 0) + 1
        if item.get("map_target"):
            map_targets[item["resource_id"]] = item["map_target"]

    throughputs = [count / window_hours for count in counts.values()]
    capacity = float(np.quantile(throughputs, capacity_percentile)) if throughputs else 0.0
    summaries = []
    for resource_id, total in totals.items():
        resource_values = [
            count / window_hours
            for (item_resource_id, _), count in counts.items()
            if item_resource_id == resource_id
        ]
        peak = max(resource_values) if resource_values else 0.0
        mean = float(np.mean(resource_values)) if resource_values else 0.0
        summaries.append(
            {
                "resource_id": resource_id,
                "label": labels[resource_id],
                "operations": int(total),
                "mean_throughput_per_hour": mean,
                "peak_throughput_per_hour": float(peak),
                "utilization_peak": float(peak / capacity) if capacity > 0 else 0.0,
                "utilization_mean": float(mean / capacity) if capacity > 0 else 0.0,
                "map_target": map_targets.get(resource_id),
            }
        )

    summaries.sort(key=lambda item: (item["peak_throughput_per_hour"], item["operations"]), reverse=True)
    return {
        "available": True,
        "capacity_reference_per_hour": capacity,
        "resource_count": len(totals),
        "top_resources": summaries[:5],
    }


def _complexity_components(
    uam_corridors: list[dict[str, Any]],
    reh_routes: list[dict[str, Any]],
    annotated: pd.DataFrame,
    tracks: dict[str, Any],
    lowc_event_count: int,
    window_seconds: int,
    capacity_percentile: float,
    crossing_capture_radius_m: float,
) -> dict[str, Any]:
    trajectory_groups = tracks.get("properties", {}).get("trajectory_group_count", 0)
    repeated_groups = len(
        {
            feature["properties"]["trajectory_group"]
            for feature in tracks.get("features", [])
            if feature["properties"].get("frequency", 0) > 1
        }
    )
    crossings = _uam_reh_crossing_features(uam_corridors, reh_routes)
    crossing_capacity = _annotate_crossing_criticality(
        crossings,
        annotated,
        window_seconds,
        capacity_percentile,
        crossing_capture_radius_m,
    )
    return {
        "available": bool(uam_corridors and reh_routes),
        "crossing_definition": "sobreposicao horizontal 2D entre corredor UAM planejado e poligono REH oficial",
        "geometry_dimension": "2D",
        "uam_corridor_count": int(len(uam_corridors)),
        "reh_segment_count": int(len(reh_routes)),
        "planned_route_count": int(len(reh_routes)),
        "planned_waypoint_count": int(sum(route["waypoint_count"] for route in uam_corridors)),
        "planned_route_crossings": int(len(crossings)),
        "trajectory_group_count": int(trajectory_groups),
        "repeated_trajectory_group_count": int(repeated_groups),
        "lowc_event_count": int(lowc_event_count),
        "crossings": {"type": "FeatureCollection", "features": crossings},
        "crossing_capacity": crossing_capacity,
    }


def _uam_reh_crossing_features(
    uam_corridors: list[dict[str, Any]],
    reh_routes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return virtual crossing waypoints for UAM corridor/official REH overlaps."""
    if not uam_corridors or not reh_routes:
        return []
    all_lats = [
        coordinate[1]
        for route in (*uam_corridors, *reh_routes)
        for ring in route.get("polygons", [])
        for coordinate in ring
    ]
    reference_lat = float(np.mean(all_lats))
    by_location: dict[tuple[int, int], dict[str, Any]] = {}
    for uam_route in uam_corridors:
        for reh_route in reh_routes:
            overlap_points = _polygon_overlap_points(uam_route, reh_route, reference_lat)
            if not overlap_points:
                continue
            point = np.mean(np.asarray(overlap_points, dtype=float), axis=0)
            key = (round(float(point[0]) / 20.0), round(float(point[1]) / 20.0))
            feature = by_location.get(key)
            if feature is None:
                feature = {
                    "type": "Feature",
                    "properties": {
                        "method": "uam_buffer_official_reh_overlap",
                        "geometry_dimension": "2D",
                        "uam_route_ids": [],
                        "uam_route_labels": [],
                        "reh_resource_ids": [],
                        "reh_labels": [],
                    },
                    "geometry": {
                        "type": "Point",
                        "coordinates": _unproject_xy(point, reference_lat),
                    },
                }
                by_location[key] = feature
            properties = feature["properties"]
            for target, value in (
                ("uam_route_ids", uam_route["resource_id"]),
                ("uam_route_labels", uam_route["label"]),
                ("reh_resource_ids", reh_route["resource_id"]),
                ("reh_labels", reh_route["label"]),
            ):
                if value not in properties[target]:
                    properties[target].append(value)

    features = sorted(
        by_location.values(),
        key=lambda feature: tuple(feature["geometry"]["coordinates"]),
    )
    for index, feature in enumerate(features, start=1):
        crossing_id = f"XUAMREH{index:03d}"
        feature["properties"]["resource_id"] = crossing_id
        feature["properties"]["label"] = f"Cruzamento UAM × REH {index:03d}"
    return features


def _annotate_crossing_criticality(
    crossings: list[dict[str, Any]],
    annotated: pd.DataFrame,
    window_seconds: int,
    capacity_percentile: float,
    capture_radius_m: float,
) -> dict[str, Any]:
    if not crossings or annotated.empty:
        return {
            "available": False,
            "capture_radius_m": float(capture_radius_m),
            "top_resources": [],
        }

    start_s = float(annotated["simt"].min())
    end_s = float(annotated["simt"].max())
    window_count = max(1, int(np.floor((end_s - start_s) / max(window_seconds, 1))) + 1)
    window_hours = max(window_seconds, 1) / 3600.0
    summaries = []
    points = annotated[["lat", "lon"]].to_numpy(dtype=float)
    for feature in crossings:
        lon, lat = feature["geometry"]["coordinates"]
        distances = haversine_m(points[:, 0], points[:, 1], lat, lon)
        nearby = annotated.loc[distances <= capture_radius_m]
        passages: list[float] = []
        if not nearby.empty:
            passages = [
                float(group["simt"].min())
                for _, group in nearby.groupby("flight_instance", sort=False)
            ]
        counts = np.zeros(window_count, dtype=float)
        for passage_time in passages:
            index = min(
                window_count - 1,
                max(0, int((passage_time - start_s) // max(window_seconds, 1))),
            )
            counts[index] += 1.0
        throughputs = counts / window_hours
        p95 = float(np.quantile(throughputs, capacity_percentile))
        peak = float(np.max(throughputs)) if len(throughputs) else 0.0
        mean = float(np.mean(throughputs)) if len(throughputs) else 0.0
        utilization_peak = float(peak / p95) if p95 > 0 else 0.0
        properties = feature["properties"]
        properties.update(
            {
                "capture_radius_m": float(capture_radius_m),
                "operations": int(len(passages)),
                "mean_throughput_per_hour": mean,
                "peak_throughput_per_hour": peak,
                "operational_limit_p95_per_hour": p95,
                "utilization_peak": utilization_peak,
            }
        )
        summaries.append(
            {
                "resource_id": properties["resource_id"],
                "label": properties["label"],
                "operations": int(len(passages)),
                "mean_throughput_per_hour": mean,
                "peak_throughput_per_hour": peak,
                "capacity_reference_per_hour": p95,
                "utilization_peak": utilization_peak,
                "utilization_mean": float(mean / p95) if p95 > 0 else 0.0,
                "map_target": {
                    "type": "crossing_waypoint",
                    "resource_id": properties["resource_id"],
                    "coordinates": feature["geometry"]["coordinates"],
                },
            }
        )
    summaries.sort(
        key=lambda item: (
            item["utilization_peak"],
            item["capacity_reference_per_hour"],
            item["operations"],
        ),
        reverse=True,
    )
    return {
        "available": True,
        "capacity_percentile": float(capacity_percentile),
        "capture_radius_m": float(capture_radius_m),
        "resource_count": len(summaries),
        "top_resources": summaries[:5],
    }


def _crossing_throughput(complexity: dict[str, Any]) -> dict[str, Any]:
    crossing_capacity = complexity.get("crossing_capacity", {})
    if not crossing_capacity.get("available"):
        return {
            "available": False,
            "capacity_reference_per_hour": 0.0,
            "top_resources": [],
            "resource_count": 0,
        }
    top_resources = crossing_capacity.get("top_resources", [])
    references = [item["capacity_reference_per_hour"] for item in top_resources]
    return {
        **crossing_capacity,
        "capacity_reference_per_hour": max(references, default=0.0),
    }


def _route_crossing_features(route_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not route_groups:
        return []
    if any(route.get("polygons") for route in route_groups):
        return _official_corridor_crossing_features(route_groups)

    reference_lat = float(
        np.mean([point[0] for route in route_groups for point in route["coordinates"]])
    )
    segments = []
    for route in route_groups:
        xy = _project_with_reference(route["coordinates"], reference_lat)
        for segment_index, (start, end) in enumerate(zip(xy[:-1], xy[1:])):
            segments.append((route["resource_id"], segment_index, start, end))

    route_labels = {route["resource_id"]: route["label"] for route in route_groups}

    crossings = []
    seen_coordinates: set[tuple[int, int]] = set()
    for left_index, (route_a, segment_a, a1, a2) in enumerate(segments):
        for route_b, segment_b, b1, b2 in segments[left_index + 1 :]:
            if route_a == route_b:
                continue
            if _share_endpoint(a1, a2, b1, b2):
                continue
            if _segments_intersect(a1, a2, b1, b2):
                point = _segment_intersection(a1, a2, b1, b2)
                if point is None:
                    continue
                key = (round(float(point[0])), round(float(point[1])))
                if key in seen_coordinates:
                    continue
                seen_coordinates.add(key)
                lon_lat = _unproject_xy(point, reference_lat)
                crossings.append(
                    {
                        "type": "Feature",
                        "properties": {
                            "route_a": route_a,
                            "route_b": route_b,
                            "route_a_label": route_labels.get(route_a, route_a),
                            "route_b_label": route_labels.get(route_b, route_b),
                            "segment_a": int(segment_a),
                            "segment_b": int(segment_b),
                        },
                        "geometry": {"type": "Point", "coordinates": lon_lat},
                    }
                )
    return crossings


def _official_corridor_crossing_features(
    route_groups: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    reference_lat = float(
        np.mean(
            [coordinate[1] for route in route_groups for ring in route.get("polygons", []) for coordinate in ring]
        )
    )
    crossings = []
    seen_coordinates: set[tuple[int, int]] = set()

    for left_index, route_a in enumerate(route_groups):
        for route_b in route_groups[left_index + 1 :]:
            if _routes_share_endpoint(route_a, route_b):
                continue
            overlap_points = _polygon_overlap_points(route_a, route_b, reference_lat)
            if not overlap_points:
                continue
            point = np.mean(np.asarray(overlap_points, dtype=float), axis=0)
            key = (round(float(point[0]) / 20.0), round(float(point[1]) / 20.0))
            if key in seen_coordinates:
                continue
            seen_coordinates.add(key)
            crossings.append(
                {
                    "type": "Feature",
                    "properties": {
                        "route_a": route_a["resource_id"],
                        "route_b": route_b["resource_id"],
                        "route_a_label": route_a["label"],
                        "route_b_label": route_b["label"],
                        "method": "official_polygon_overlap",
                    },
                    "geometry": {
                        "type": "Point",
                        "coordinates": _unproject_xy(point, reference_lat),
                    },
                }
            )
    return crossings


def _polygon_overlap_points(
    route_a: dict[str, Any],
    route_b: dict[str, Any],
    reference_lat: float,
) -> list[np.ndarray]:
    points: list[np.ndarray] = []
    polygons_a = route_a.get("polygons", [])
    polygons_b = route_b.get("polygons", [])

    for ring_a in polygons_a:
        lat_lon_a = np.asarray([[coordinate[1], coordinate[0]] for coordinate in ring_a], dtype=float)
        inside_b = points_in_polygons(lat_lon_a, polygons_b)
        points.extend(_project_with_reference(lat_lon_a[inside_b], reference_lat))
        xy_a = _project_with_reference(lat_lon_a, reference_lat)
        for ring_b in polygons_b:
            lat_lon_b = np.asarray([[coordinate[1], coordinate[0]] for coordinate in ring_b], dtype=float)
            xy_b = _project_with_reference(lat_lon_b, reference_lat)
            for a1, a2 in zip(xy_a[:-1], xy_a[1:]):
                for b1, b2 in zip(xy_b[:-1], xy_b[1:]):
                    if _segments_intersect(a1, a2, b1, b2):
                        intersection = _segment_intersection(a1, a2, b1, b2)
                        if intersection is not None:
                            points.append(intersection)

    for ring_b in polygons_b:
        lat_lon_b = np.asarray([[coordinate[1], coordinate[0]] for coordinate in ring_b], dtype=float)
        inside_a = points_in_polygons(lat_lon_b, polygons_a)
        points.extend(_project_with_reference(lat_lon_b[inside_a], reference_lat))
    return points


def _routes_share_endpoint(route_a: dict[str, Any], route_b: dict[str, Any]) -> bool:
    coordinates_a = np.asarray(route_a.get("coordinates", []), dtype=float)
    coordinates_b = np.asarray(route_b.get("coordinates", []), dtype=float)
    if len(coordinates_a) < 2 or len(coordinates_b) < 2:
        return False
    reference_lat = float(np.mean(np.concatenate((coordinates_a[:, 0], coordinates_b[:, 0]))))
    xy_a = _project_with_reference(coordinates_a[[0, -1]], reference_lat)
    xy_b = _project_with_reference(coordinates_b[[0, -1]], reference_lat)
    return any(float(np.linalg.norm(left - right)) < 15.0 for left in xy_a for right in xy_b)


def _project(coordinates: np.ndarray) -> np.ndarray:
    if len(coordinates) == 0:
        return np.asarray([], dtype=float)
    reference_lat = float(np.mean(coordinates[:, 0]))
    return _project_with_reference(coordinates, reference_lat)


def _project_with_reference(coordinates: np.ndarray, reference_lat: float) -> np.ndarray:
    if len(coordinates) == 0:
        return np.asarray([], dtype=float)
    meters_per_degree_lat = 111_320.0
    meters_per_degree_lon = meters_per_degree_lat * np.cos(np.radians(reference_lat))
    return np.column_stack(
        (coordinates[:, 1] * meters_per_degree_lon, coordinates[:, 0] * meters_per_degree_lat)
    )


def _unproject_xy(point: np.ndarray, reference_lat: float) -> list[float]:
    meters_per_degree_lat = 111_320.0
    meters_per_degree_lon = meters_per_degree_lat * np.cos(np.radians(reference_lat))
    lon = float(point[0] / meters_per_degree_lon)
    lat = float(point[1] / meters_per_degree_lat)
    return [lon, lat]


def _segments_intersect(a1: np.ndarray, a2: np.ndarray, b1: np.ndarray, b2: np.ndarray) -> bool:
    def orientation(p: np.ndarray, q: np.ndarray, r: np.ndarray) -> float:
        return float((q[1] - p[1]) * (r[0] - q[0]) - (q[0] - p[0]) * (r[1] - q[1]))

    o1 = orientation(a1, a2, b1)
    o2 = orientation(a1, a2, b2)
    o3 = orientation(b1, b2, a1)
    o4 = orientation(b1, b2, a2)
    return (o1 * o2 < 0) and (o3 * o4 < 0)


def _segment_intersection(
    a1: np.ndarray,
    a2: np.ndarray,
    b1: np.ndarray,
    b2: np.ndarray,
) -> np.ndarray | None:
    da = a2 - a1
    db = b2 - b1
    denominator = float(da[0] * db[1] - da[1] * db[0])
    if abs(denominator) < 1e-9:
        return None
    delta = b1 - a1
    t = float((delta[0] * db[1] - delta[1] * db[0]) / denominator)
    return a1 + t * da


def _share_endpoint(a1: np.ndarray, a2: np.ndarray, b1: np.ndarray, b2: np.ndarray) -> bool:
    return any(
        float(np.linalg.norm(left - right)) < 10.0
        for left in (a1, a2)
        for right in (b1, b2)
    )


def _od_pair_id(origin: tuple[float, float], destination: tuple[float, float]) -> str:
    return (
        f"{origin[0]:.4f},{origin[1]:.4f}"
        f"->{destination[0]:.4f},{destination[1]:.4f}"
    )


def _od_pair_label(origin: tuple[float, float], destination: tuple[float, float]) -> str:
    return (
        f"{origin[0]:.3f},{origin[1]:.3f}"
        f" -> {destination[0]:.3f},{destination[1]:.3f}"
    )
