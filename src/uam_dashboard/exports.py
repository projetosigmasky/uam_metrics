from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .config import FEET_TO_METERS, METERS_PER_NM
from .metrics import flight_instance_frame, haversine_m


def _trajectory_signature(group: pd.DataFrame, shape_points: int) -> np.ndarray:
    coordinates = group[["lat", "lon"]].to_numpy(dtype=float)
    if len(coordinates) == 1:
        return np.repeat(coordinates, shape_points, axis=0)

    segment_distances = haversine_m(
        coordinates[:-1, 0],
        coordinates[:-1, 1],
        coordinates[1:, 0],
        coordinates[1:, 1],
    )
    cumulative = np.concatenate(([0.0], np.cumsum(segment_distances)))
    if cumulative[-1] <= 0:
        return np.repeat(coordinates[:1], shape_points, axis=0)

    target = np.linspace(0.0, cumulative[-1], max(2, shape_points))
    return np.column_stack(
        [
            np.interp(target, cumulative, coordinates[:, 0]),
            np.interp(target, cumulative, coordinates[:, 1]),
        ]
    )


def _signature_distance_m(left: np.ndarray, right: np.ndarray) -> float:
    distances = haversine_m(left[:, 0], left[:, 1], right[:, 0], right[:, 1])
    return float(np.mean(distances))


def _trajectory_clusters(
    instances: list[dict[str, Any]],
    cluster_distance_m: float,
    endpoint_tolerance_m: float,
) -> list[list[int]]:
    clusters: list[list[int]] = []

    for instance_index, instance in enumerate(instances):
        signature = instance["signature"]
        assigned = False

        for cluster in clusters:
            representative = instances[cluster[0]]["signature"]
            start_distance = float(
                haversine_m(signature[0, 0], signature[0, 1], representative[0, 0], representative[0, 1])
            )
            end_distance = float(
                haversine_m(signature[-1, 0], signature[-1, 1], representative[-1, 0], representative[-1, 1])
            )
            if start_distance > endpoint_tolerance_m or end_distance > endpoint_tolerance_m:
                continue
            if _signature_distance_m(signature, representative) <= cluster_distance_m:
                cluster.append(instance_index)
                assigned = True
                break

        if not assigned:
            clusters.append([instance_index])

    return clusters


def tracks_geojson(
    df: pd.DataFrame,
    sample_stride: int,
    instance_gap_seconds: float,
    instance_reset_distance_m: float,
    instance_jump_m: float,
    shape_points: int,
    cluster_distance_m: float,
    endpoint_tolerance_m: float,
    conformity_by_instance: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    stride = max(1, sample_stride)
    annotated = flight_instance_frame(
        df,
        gap_seconds=instance_gap_seconds,
        reset_distance_m=instance_reset_distance_m,
        jump_m=instance_jump_m,
    )
    instances: list[dict[str, Any]] = []

    for flight_instance, group in annotated.groupby("flight_instance", sort=True):
        group = group.sort_values("simt")
        sampled = group.iloc[::stride]
        if len(sampled) < 2:
            sampled = group

        coordinates = [
            [float(row.lon), float(row.lat), float(row.alt)]
            for row in sampled.itertuples(index=False)
        ]
        if len(coordinates) < 2:
            continue
        instances.append(
            {
                "flight_instance": str(flight_instance),
                "aircraft_id": str(group["id"].iloc[0]),
                "group": group,
                "signature": _trajectory_signature(group, shape_points),
                "coordinates": coordinates,
            }
        )

    clusters = _trajectory_clusters(instances, cluster_distance_m, endpoint_tolerance_m)
    max_frequency = max((len(cluster) for cluster in clusters), default=1)

    for cluster_index, cluster in enumerate(clusters, start=1):
        frequency = len(cluster)
        volume_ratio = frequency / max_frequency
        volume_class = "high" if volume_ratio >= 0.67 else "medium" if volume_ratio >= 0.34 else "low"
        for instance_index in cluster:
            instance = instances[instance_index]
            group = instance["group"]
            conformity = (conformity_by_instance or {}).get(instance["flight_instance"], {})
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "id": instance["aircraft_id"],
                        "vehicle_type": str(group["vehicle_type"].iloc[0]) if "vehicle_type" in group else "desconhecido",
                        "aircraft_model": str(group["aircraft_model"].iloc[0]) if "aircraft_model" in group else "DESCONHECIDO",
                        "flight_instance": instance["flight_instance"],
                        "trajectory_group": f"T{cluster_index:03d}",
                        "frequency": int(frequency),
                        "volume_ratio": float(volume_ratio),
                        "volume_class": volume_class,
                        "samples": int(len(group)),
                        "distance_nm": float(group["distflown"].max() / METERS_PER_NM),
                        "duration_min": float((group["simt"].max() - group["simt"].min()) / 60.0),
                        "min_alt_m": float(group["alt"].min()),
                        "max_alt_m": float(group["alt"].max()),
                        **conformity,
                    },
                    "geometry": {"type": "LineString", "coordinates": instance["coordinates"]},
                }
            )

    features.sort(key=lambda feature: feature["properties"]["frequency"])
    return {
        "type": "FeatureCollection",
        "properties": {
            "trajectory_count": len(features),
            "trajectory_group_count": len(clusters),
            "max_frequency": max_frequency,
            "cluster_distance_m": float(cluster_distance_m),
            "endpoint_tolerance_m": float(endpoint_tolerance_m),
            "shape_points": int(shape_points),
        },
        "features": features,
    }


def conflicts_geojson(events: pd.DataFrame) -> dict[str, Any]:
    features = []
    if events.empty:
        return {
            "type": "FeatureCollection",
            "properties": {"mac_timestamp_available": False},
            "features": features,
        }

    for row in events.itertuples(index=False):
        is_mac = bool(getattr(row, "is_mac", False))
        event_class = "mac" if is_mac else "nmac" if bool(row.is_nmac) else "lowc"
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "simt": float(row.simt),
                    "start_simt": float(row.start_simt),
                    "end_simt": float(row.end_simt),
                    "detection_simt": float(row.detection_simt),
                    "time_to_conflict_s": float(row.time_to_conflict_s),
                    "duration_s": float(row.duration_s),
                    "id_a": str(row.id_a),
                    "id_b": str(row.id_b),
                    "dist_h_m": float(row.dist_h_m),
                    "dist_v_m": float(row.dist_v_m),
                    "horizontal_ratio": float(row.horizontal_ratio),
                    "vertical_ratio": float(row.vertical_ratio),
                    "vehicle_type_a": str(row.vehicle_type_a),
                    "vehicle_type_b": str(row.vehicle_type_b),
                    "vehicle_pair": str(row.vehicle_pair),
                    "severity_ratio": float(row.severity_ratio),
                    "is_nmac": bool(row.is_nmac),
                    "is_mac": is_mac,
                    "event_class": event_class,
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(row.lon), float(row.lat), float(row.alt)],
                },
            }
        )

    return {
        "type": "FeatureCollection",
        "properties": {
            "mac_timestamp_available": any(
                feature["properties"]["event_class"] == "mac" for feature in features
            )
        },
        "features": features,
    }


def trajectory_3d_payload(
    df: pd.DataFrame,
    sample_seconds: int,
    instance_gap_seconds: float,
    instance_reset_distance_m: float,
    instance_jump_m: float,
    ground_plane_msl_ft: float = 2621.0,
) -> dict[str, Any]:
    """Create a compact, globally aligned time series for the canvas 3D viewer."""

    interval = max(1, int(sample_seconds))
    annotated = flight_instance_frame(
        df,
        gap_seconds=instance_gap_seconds,
        reset_distance_m=instance_reset_distance_m,
        jump_m=instance_jump_m,
    )
    sampled = annotated[np.isclose(annotated["simt"] % interval, 0)].copy()
    if sampled.empty:
        sampled = annotated.iloc[::interval].copy()

    tracks: list[dict[str, Any]] = []
    for flight_instance, group in sampled.groupby("flight_instance", sort=True):
        group = group.sort_values("simt")
        points = [
            [
                int(row.simt) if float(row.simt).is_integer() else round(float(row.simt), 3),
                round(float(row.lon), 6),
                round(float(row.lat), 6),
                round(float(row.alt), 1),
            ]
            for row in group.itertuples(index=False)
        ]
        tracks.append(
            {
                "flight_instance": str(flight_instance),
                "id": str(group["id"].iloc[0]),
                "vehicle_type": str(group["vehicle_type"].iloc[0]) if "vehicle_type" in group else "desconhecido",
                "aircraft_model": str(group["aircraft_model"].iloc[0]) if "aircraft_model" in group else "DESCONHECIDO",
                "points": points,
            }
        )

    return {
        "sample_seconds": interval,
        "sim_start_s": float(sampled["simt"].min()),
        "sim_end_s": float(sampled["simt"].max()),
        "bounds": {
            "min_lat": float(sampled["lat"].min()),
            "max_lat": float(sampled["lat"].max()),
            "min_lon": float(sampled["lon"].min()),
            "max_lon": float(sampled["lon"].max()),
        },
        "altitude_bounds_m": [float(sampled["alt"].min()), float(sampled["alt"].max())],
        "ground_plane_msl_ft": float(ground_plane_msl_ft),
        "ground_plane_msl_m": float(ground_plane_msl_ft * FEET_TO_METERS),
        "track_count": len(tracks),
        "point_count": int(len(sampled)),
        "tracks": tracks,
    }


def planned_routes_geojson(
    planned_flights: list[dict[str, Any]],
    conformity_by_instance: dict[str, dict[str, Any]],
    tolerance_m: float,
) -> dict[str, Any]:
    features = []
    conformity_by_planned = {
        values["planned_flight_instance"]: values
        for values in conformity_by_instance.values()
        if "planned_flight_instance" in values
    }
    for flight in planned_flights:
        conformity = conformity_by_planned.get(flight["flight_instance"], {})
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "id": flight["aircraft_id"],
                    "flight_instance": flight["flight_instance"],
                    "start_time": flight["start_time"],
                    "scenario": flight["scenario"],
                    "waypoint_count": len(flight["coordinates"]),
                    **conformity,
                },
                "geometry": {"type": "LineString", "coordinates": flight["coordinates"]},
            }
        )
    return {
        "type": "FeatureCollection",
        "properties": {
            "planned_instance_count": len(features),
            "conformity_tolerance_m": float(tolerance_m),
        },
        "features": features,
    }


def heatmap_points(df: pd.DataFrame, sample_stride: int) -> list[list[float]]:
    sampled = df.iloc[:: max(1, sample_stride)]
    return [[float(row.lat), float(row.lon), 0.28] for row in sampled.itertuples(index=False)]
