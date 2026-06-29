from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .metrics import (
    _point_to_polyline_distances_m,
    _polyline_distance_m,
    flight_instance_frame,
)


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
) -> dict[str, Any]:
    """Compute capacity proxies based on REH corridors and observed resources."""

    annotated = flight_instance_frame(df, gap_seconds, reset_distance_m, jump_m)
    instances = _flight_instances(annotated)
    route_groups, planned_to_route = _planned_route_groups(planned_flights)
    density = _corridor_density(df, route_groups, corridor_width_m)
    throughput = _throughput_metrics(
        instances,
        tracks,
        conformity_by_instance,
        planned_to_route,
        window_seconds,
        capacity_percentile,
    )
    complexity = _complexity_components(route_groups, tracks, lowc_event_count)
    return {
        "available": bool(instances),
        "window_seconds": int(window_seconds),
        "capacity_percentile": float(capacity_percentile),
        "corridor_width_m": float(corridor_width_m),
        "density": density,
        "throughput": throughput,
        "complexity": complexity,
    }


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
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    grouped: dict[tuple[tuple[float, float], ...], dict[str, Any]] = {}
    planned_to_route: dict[str, str] = {}

    for flight in planned_flights:
        signature = tuple((round(float(lon), 4), round(float(lat), 4)) for lon, lat in flight["coordinates"])
        if signature not in grouped:
            route_id = f"REH{len(grouped) + 1:03d}"
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

    area_m2 = sum(_corridor_area_m2(route["coordinates"], corridor_width_m) for route in route_groups)
    area_km2 = area_m2 / 1_000_000.0
    if area_km2 <= 0:
        return {"available": False, "corridor_area_km2": 0.0}

    points = df[["lat", "lon"]].to_numpy(dtype=float)
    inside_any = np.zeros(len(points), dtype=bool)
    for route in route_groups:
        deviations = _point_to_polyline_distances_m(points, route["coordinates"])
        inside_any |= deviations <= corridor_width_m

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
    for route in route_groups:
        deviations = _point_to_polyline_distances_m(points, route["coordinates"])
        route_samples = df.loc[deviations <= corridor_width_m, ["simt", "id"]]
        route_simultaneous = route_samples.groupby("simt")["id"].nunique()
        route_area_km2 = _corridor_area_m2(route["coordinates"], corridor_width_m) / 1_000_000.0
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
                    "mean_simultaneous_aircraft": route_mean,
                    "peak_simultaneous_aircraft": route_peak,
                    "corridor_area_km2": float(route_area_km2),
                    "air_traffic_density_per_km2": float(route_density),
                    "sample_count": int(len(route_samples)),
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [_corridor_polygon_coordinates(route["coordinates"], corridor_width_m)],
                },
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
    planned_to_route: dict[str, str],
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
        resources["od_pairs"].append(
            {
                "resource_id": _od_pair_id(instance["origin"], instance["destination"]),
                "label": _od_pair_label(instance["origin"], instance["destination"]),
                "time_s": instance["start_s"],
            }
        )
        group = track_group_by_instance.get(instance["flight_instance"])
        if group:
            resources["trajectory_groups"].append(
                {"resource_id": group, "label": group, "time_s": instance["start_s"]}
            )
        planned = conformity_by_instance.get(instance["flight_instance"], {}).get("planned_flight_instance")
        route_id = planned_to_route.get(planned)
        if route_id:
            resources["planned_reh"].append(
                {"resource_id": route_id, "label": route_id, "time_s": instance["start_s"]}
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
    for item in items:
        window_index = int((item["time_s"] - start_s) // max(window_seconds, 1))
        key = (item["resource_id"], window_index)
        counts[key] = counts.get(key, 0) + 1
        labels[item["resource_id"]] = item["label"]
        totals[item["resource_id"]] = totals.get(item["resource_id"], 0) + 1

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
    route_groups: list[dict[str, Any]],
    tracks: dict[str, Any],
    lowc_event_count: int,
) -> dict[str, Any]:
    trajectory_groups = tracks.get("properties", {}).get("trajectory_group_count", 0)
    repeated_groups = len(
        {
            feature["properties"]["trajectory_group"]
            for feature in tracks.get("features", [])
            if feature["properties"].get("frequency", 0) > 1
        }
    )
    crossings = _route_crossing_features(route_groups)
    return {
        "available": bool(route_groups),
        "planned_route_count": int(len(route_groups)),
        "planned_waypoint_count": int(sum(route["waypoint_count"] for route in route_groups)),
        "planned_route_crossings": int(len(crossings)),
        "trajectory_group_count": int(trajectory_groups),
        "repeated_trajectory_group_count": int(repeated_groups),
        "lowc_event_count": int(lowc_event_count),
        "crossings": {"type": "FeatureCollection", "features": crossings},
    }


def _route_crossing_features(route_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not route_groups:
        return []
    reference_lat = float(
        np.mean([point[0] for route in route_groups for point in route["coordinates"]])
    )
    segments = []
    for route in route_groups:
        xy = _project_with_reference(route["coordinates"], reference_lat)
        for segment_index, (start, end) in enumerate(zip(xy[:-1], xy[1:])):
            segments.append((route["resource_id"], segment_index, start, end))

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
                            "segment_a": int(segment_a),
                            "segment_b": int(segment_b),
                        },
                        "geometry": {"type": "Point", "coordinates": lon_lat},
                    }
                )
    return crossings


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
