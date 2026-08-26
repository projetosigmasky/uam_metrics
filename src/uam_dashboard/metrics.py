from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .reh_parser import points_in_reh_network

from .config import METERS_PER_NM


def haversine_m(lat1: Any, lon1: Any, lat2: Any, lon2: Any) -> Any:
    """Return the great-circle distance in meters."""

    earth_radius_m = 6371000.0
    phi1 = np.radians(lat1)
    phi2 = np.radians(lat2)
    dphi = np.radians(np.asarray(lat2) - np.asarray(lat1))
    dlambda = np.radians(np.asarray(lon2) - np.asarray(lon1))
    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda / 2) ** 2
    return 2 * earth_radius_m * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def build_summary(df: pd.DataFrame, operation_count: int | None = None) -> dict[str, Any]:
    active_by_second = df.groupby("simt")["id"].nunique()
    duration_seconds = float(df["simt"].max() - df["simt"].min()) if not df.empty else 0.0

    fleet_mix = {}
    if "vehicle_type" in df.columns:
        fleet_mix = {
            str(vehicle_type): int(group["id"].nunique())
            for vehicle_type, group in df.groupby("vehicle_type", sort=True)
        }
    kinematics = {
        "min_alt_m": float(df["alt"].min()),
        "mean_alt_m": float(df["alt"].mean()),
        "max_alt_m": float(df["alt"].max()),
    }
    for column in ("cas", "tas", "gs", "vs", "hdg", "trk"):
        if column in df.columns:
            kinematics[f"mean_{column}"] = float(df[column].mean())
            kinematics[f"min_{column}"] = float(df[column].min())
            kinematics[f"max_{column}"] = float(df[column].max())

    return {
        "records": int(len(df)),
        "aircraft_count": int(df["id"].nunique()),
        "operation_count": int(operation_count if operation_count is not None else df["id"].nunique()),
        "fleet_mix": fleet_mix,
        "kinematics": kinematics,
        "sim_start_s": float(df["simt"].min()),
        "sim_end_s": float(df["simt"].max()),
        "duration_min": duration_seconds / 60.0,
        "mean_simultaneous_aircraft": float(active_by_second.mean()),
        "peak_simultaneous_aircraft": int(active_by_second.max()),
        "bounds": {
            "min_lat": float(df["lat"].min()),
            "max_lat": float(df["lat"].max()),
            "min_lon": float(df["lon"].min()),
            "max_lon": float(df["lon"].max()),
        },
    }


def _percentile(values: pd.Series | list[float], q: float) -> float:
    clean = pd.Series(values, dtype="float64").replace([np.inf, -np.inf], np.nan).dropna()
    return float(clean.quantile(q)) if len(clean) else 0.0


def _safe_rate(numerator: float, denominator: float, scale: float = 1.0) -> float:
    return float((numerator / denominator) * scale) if denominator > 0 else 0.0


def efficiency_metrics(
    df: pd.DataFrame,
    gap_seconds: float = 300.0,
    reset_distance_m: float = 250.0,
    jump_m: float = 5000.0,
) -> dict[str, Any]:
    annotated = flight_instance_frame(df, gap_seconds, reset_distance_m, jump_m)
    grouped = annotated.groupby("flight_instance", sort=True)
    durations_s = grouped["simt"].max() - grouped["simt"].min()
    distances_m = grouped["distflown"].max() - grouped["distflown"].min()

    route_efficiencies = []
    horizontal_inefficiencies = []
    great_circle_distances_m = []
    for _, group in grouped:
        first = group.iloc[0]
        last = group.iloc[-1]
        straight_m = haversine_m(first["lat"], first["lon"], last["lat"], last["lon"])
        flown_m = float(group["distflown"].max() - group["distflown"].min())
        great_circle_distances_m.append(float(straight_m))
        if flown_m > 0:
            route_efficiencies.append(float(straight_m / flown_m))
        if straight_m > 0:
            horizontal_inefficiencies.append(float((flown_m - straight_m) / straight_m))

    return {
        "mean_flight_time_min": float(durations_s.mean() / 60.0),
        "median_flight_time_min": float(durations_s.median() / 60.0),
        "p95_flight_time_min": _percentile(durations_s / 60.0, 0.95),
        "mean_distance_nm": float(distances_m.mean() / METERS_PER_NM),
        "median_distance_nm": float(distances_m.median() / METERS_PER_NM),
        "p95_distance_nm": _percentile(distances_m / METERS_PER_NM, 0.95),
        "total_distance_km": float(distances_m.sum() / 1000.0),
        "total_flight_hours": float(durations_s.sum() / 3600.0),
        "mean_great_circle_distance_nm": float(np.mean(great_circle_distances_m) / METERS_PER_NM)
        if great_circle_distances_m
        else 0.0,
        "mean_route_efficiency_pct": float(np.mean(route_efficiencies) * 100.0)
        if route_efficiencies
        else 0.0,
        "mean_horizontal_inefficiency_pct": float(np.mean(horizontal_inefficiencies) * 100.0)
        if horizontal_inefficiencies
        else 0.0,
        "flight_instances": int(len(durations_s)),
    }


def airborne_delay_metrics(
    df: pd.DataFrame,
    reference_df: pd.DataFrame | None,
    gap_seconds: float,
    reset_distance_m: float,
    jump_m: float,
) -> dict[str, Any]:
    """Return airborne delay against a same-route no-deconfliction reference log."""

    if reference_df is None or reference_df.empty:
        return {"available": False}

    observed = _flight_duration_by_instance(df, gap_seconds, reset_distance_m, jump_m)
    reference = _flight_duration_by_instance(reference_df, gap_seconds, reset_distance_m, jump_m)
    delays = []

    for flight_instance, duration_s in observed.items():
        reference_duration_s = reference.get(flight_instance)
        if reference_duration_s is None:
            continue
        delays.append(max(0.0, float(duration_s - reference_duration_s)))

    if not delays:
        return {"available": False}

    return {
        "available": True,
        "matched_flights": int(len(delays)),
        "mean_airborne_delay_s": float(np.mean(delays)),
        "median_airborne_delay_s": float(np.median(delays)),
        "p95_airborne_delay_s": float(np.quantile(delays, 0.95)),
        "max_airborne_delay_s": float(np.max(delays)),
        "total_airborne_delay_s": float(np.sum(delays)),
    }


def total_delay_metrics(ground_delay: dict[str, Any], airborne_delay: dict[str, Any]) -> dict[str, Any]:
    """Combine ground and airborne delay summaries as a per-flight average."""

    ground_available = bool(ground_delay.get("available"))
    airborne_available = bool(airborne_delay.get("available"))
    if not ground_available or not airborne_available:
        return {
            "available": False,
            "ground_available": ground_available,
            "airborne_available": airborne_available,
            "reason": "atraso total requer simultaneamente os componentes de solo e de voo",
        }

    mean_ground_s = float(ground_delay["mean_ground_delay_s"])
    mean_airborne_s = float(airborne_delay["mean_airborne_delay_s"])
    return {
        "available": True,
        "mean_total_delay_s": mean_ground_s + mean_airborne_s,
        "mean_ground_component_s": mean_ground_s,
        "mean_airborne_component_s": mean_airborne_s,
        "ground_available": ground_available,
        "airborne_available": airborne_available,
    }


def _flight_duration_by_instance(
    df: pd.DataFrame,
    gap_seconds: float,
    reset_distance_m: float,
    jump_m: float,
) -> dict[str, float]:
    annotated = flight_instance_frame(df, gap_seconds, reset_distance_m, jump_m)
    grouped = annotated.groupby("flight_instance", sort=True)
    durations = grouped["simt"].max() - grouped["simt"].min()
    return {str(index): float(value) for index, value in durations.items()}


def flight_instance_frame(
    df: pd.DataFrame,
    gap_seconds: float,
    reset_distance_m: float,
    jump_m: float,
) -> pd.DataFrame:
    """Return rows annotated with inferred flight instances."""

    annotated_groups: list[pd.DataFrame] = []

    for aircraft_id, group in df.sort_values(["id", "simt"]).groupby("id", sort=True):
        group = group.copy()
        instance_numbers: list[int] = []
        instance_number = 0
        previous = None

        for row in group.itertuples(index=False):
            if previous is not None:
                time_gap = float(row.simt - previous.simt)
                distance_reset = float(row.distflown + reset_distance_m < previous.distflown)
                horizontal_jump_m = float(haversine_m(previous.lat, previous.lon, row.lat, row.lon))
                if time_gap > gap_seconds or distance_reset or horizontal_jump_m > jump_m:
                    instance_number += 1

            instance_numbers.append(instance_number)
            previous = row

        group["flight_instance"] = [f"{aircraft_id}#{number}" for number in instance_numbers]
        annotated_groups.append(group)

    if not annotated_groups:
        return df.copy()

    return pd.concat(annotated_groups, ignore_index=True).sort_values(["simt", "id"]).reset_index(drop=True)


def trajectory_conformity(
    df: pd.DataFrame,
    planned_flights: list[dict[str, Any]],
    tolerance_m: float,
    gap_seconds: float,
    reset_distance_m: float,
    jump_m: float,
    reh_segments: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Compare execution with its plan and, when available, official REH polygons."""

    annotated = flight_instance_frame(df, gap_seconds, reset_distance_m, jump_m)
    by_instance: dict[str, dict[str, Any]] = {}
    unused_planned = set(range(len(planned_flights)))
    all_deviations: list[float] = []
    conformity_ratios: list[float] = []
    additional_distances_m: list[float] = []
    planned_horizontal_inefficiencies: list[float] = []
    executed_horizontal_inefficiencies: list[float] = []
    conforming_samples = 0
    planned_line_conforming_samples = 0
    matched_instances = 0
    adherence_by_vehicle_type: dict[str, dict[str, int]] = {}

    for flight_instance, group in annotated.groupby("flight_instance", sort=True):
        aircraft_id = str(group["id"].iloc[0])
        start_simt = float(group["simt"].min())
        candidates = [
            index
            for index in unused_planned
            if planned_flights[index]["aircraft_id"] == aircraft_id
        ]
        if not candidates:
            continue
        planned_index = min(
            candidates,
            key=lambda index: abs(float(planned_flights[index]["start_simt"]) - start_simt),
        )
        planned = planned_flights[planned_index]
        unused_planned.remove(planned_index)
        planned_coordinates = np.asarray(
            [[coord[1], coord[0]] for coord in planned["coordinates"]],
            dtype=float,
        )
        deviations = _point_to_polyline_distances_m(
            group[["lat", "lon"]].to_numpy(dtype=float),
            planned_coordinates,
        )
        if not len(deviations):
            continue

        matched_instances += 1
        vehicle_type = str(group["vehicle_type"].iloc[0]) if "vehicle_type" in group else "desconhecido"
        all_deviations.extend(deviations.tolist())
        planned_line_inside = int(np.sum(deviations <= tolerance_m))
        planned_line_conforming_samples += planned_line_inside
        if reh_segments:
            official_inside_mask = points_in_reh_network(
                group[["lat", "lon"]].to_numpy(dtype=float),
                reh_segments,
            )
            inside = int(np.sum(official_inside_mask))
        else:
            inside = planned_line_inside
        conforming_samples += inside
        vehicle_adherence = adherence_by_vehicle_type.setdefault(
            vehicle_type,
            {"matched_instances": 0, "executed_samples": 0, "conforming_samples": 0},
        )
        vehicle_adherence["matched_instances"] += 1
        vehicle_adherence["executed_samples"] += int(len(deviations))
        vehicle_adherence["conforming_samples"] += inside
        planned_distance_m = _polyline_distance_m(planned_coordinates)
        executed_distance_m = float(group["distflown"].max() - group["distflown"].min())
        additional_distance_m = executed_distance_m - planned_distance_m
        conformity_ratio = _safe_rate(additional_distance_m, planned_distance_m)
        first = group.iloc[0]
        last = group.iloc[-1]
        great_circle_distance_m = float(haversine_m(first["lat"], first["lon"], last["lat"], last["lon"]))
        planned_hfe = _safe_rate(planned_distance_m - great_circle_distance_m, great_circle_distance_m)
        executed_hfe = _safe_rate(executed_distance_m - great_circle_distance_m, great_circle_distance_m)
        conformity_ratios.append(conformity_ratio)
        additional_distances_m.append(additional_distance_m)
        planned_horizontal_inefficiencies.append(planned_hfe)
        executed_horizontal_inefficiencies.append(executed_hfe)
        by_instance[str(flight_instance)] = {
            "planned_flight_instance": planned["flight_instance"],
            "planned_start_time": planned["start_time"],
            "vehicle_type": vehicle_type,
            "aircraft_model": str(group["aircraft_model"].iloc[0]) if "aircraft_model" in group else "DESCONHECIDO",
            "start_time_delta_s": abs(float(planned["start_simt"]) - start_simt),
            "spatial_adherence_pct": float(inside / len(deviations) * 100.0),
            "planned_line_adherence_pct": float(planned_line_inside / len(deviations) * 100.0),
            "adherence_reference": "official_reh_polygons" if reh_segments else "planned_line_tolerance",
            "mean_deviation_m": float(np.mean(deviations)),
            "p95_deviation_m": _percentile(deviations.tolist(), 0.95),
            "max_deviation_m": float(np.max(deviations)),
            "planned_distance_m": float(planned_distance_m),
            "executed_distance_m": float(executed_distance_m),
            "additional_distance_m": float(additional_distance_m),
            "trajectory_conformity_ratio": float(conformity_ratio),
            "planned_horizontal_inefficiency_ratio": float(planned_hfe),
            "executed_horizontal_inefficiency_ratio": float(executed_hfe),
            "executed_samples": int(len(deviations)),
        }

    total_samples = len(all_deviations)
    adherence_by_type_payload = {
        vehicle_type: {
            **values,
            "spatial_adherence_pct": _safe_rate(
                values["conforming_samples"], values["executed_samples"], 100.0
            ),
        }
        for vehicle_type, values in adherence_by_vehicle_type.items()
    }
    summary = {
        "available": bool(total_samples),
        "tolerance_m": float(tolerance_m),
        "planned_instances": int(len(planned_flights)),
        "matched_instances": int(matched_instances),
        "spatial_adherence_pct": _safe_rate(conforming_samples, total_samples, 100.0),
        "spatial_adherence_scope": "todas as aeronaves",
        "spatial_adherence_by_vehicle_type": adherence_by_type_payload,
        "planned_line_adherence_pct": _safe_rate(
            planned_line_conforming_samples,
            total_samples,
            100.0,
        ),
        "adherence_reference": "official_reh_polygons" if reh_segments else "planned_line_tolerance",
        "official_reh_segment_count": int(len(reh_segments or [])),
        "mean_deviation_m": float(np.mean(all_deviations)) if all_deviations else 0.0,
        "p95_deviation_m": _percentile(all_deviations, 0.95),
        "max_deviation_m": max(all_deviations) if all_deviations else 0.0,
        "mean_trajectory_conformity_ratio": float(np.mean(conformity_ratios))
        if conformity_ratios
        else 0.0,
        "median_trajectory_conformity_ratio": float(np.median(conformity_ratios))
        if conformity_ratios
        else 0.0,
        "p95_trajectory_conformity_ratio": _percentile(conformity_ratios, 0.95),
        "mean_additional_distance_m": float(np.mean(additional_distances_m))
        if additional_distances_m
        else 0.0,
        "total_additional_distance_m": float(np.sum(additional_distances_m))
        if additional_distances_m
        else 0.0,
        "mean_planned_horizontal_inefficiency_ratio": float(np.mean(planned_horizontal_inefficiencies))
        if planned_horizontal_inefficiencies
        else 0.0,
        "mean_executed_horizontal_inefficiency_ratio": float(np.mean(executed_horizontal_inefficiencies))
        if executed_horizontal_inefficiencies
        else 0.0,
        "executed_samples": int(total_samples),
    }
    return summary, by_instance


def _polyline_distance_m(polyline: np.ndarray) -> float:
    if len(polyline) < 2:
        return 0.0
    return float(
        np.sum(
            haversine_m(
                polyline[:-1, 0],
                polyline[:-1, 1],
                polyline[1:, 0],
                polyline[1:, 1],
            )
        )
    )


def _point_to_polyline_distances_m(points: np.ndarray, polyline: np.ndarray) -> np.ndarray:
    if len(points) == 0 or len(polyline) < 2:
        return np.asarray([], dtype=float)

    reference_lat = float(np.mean(polyline[:, 0]))
    meters_per_degree_lat = 111_320.0
    meters_per_degree_lon = meters_per_degree_lat * np.cos(np.radians(reference_lat))
    points_xy = np.column_stack((points[:, 1] * meters_per_degree_lon, points[:, 0] * meters_per_degree_lat))
    line_xy = np.column_stack(
        (polyline[:, 1] * meters_per_degree_lon, polyline[:, 0] * meters_per_degree_lat)
    )

    minimum = np.full(len(points_xy), np.inf)
    for start, end in zip(line_xy[:-1], line_xy[1:]):
        segment = end - start
        length_squared = float(np.dot(segment, segment))
        if length_squared <= 0:
            distances = np.linalg.norm(points_xy - start, axis=1)
        else:
            projection = np.clip(((points_xy - start) @ segment) / length_squared, 0.0, 1.0)
            closest = start + projection[:, None] * segment
            distances = np.linalg.norm(points_xy - closest, axis=1)
        minimum = np.minimum(minimum, distances)
    return minimum


def active_aircraft_series(df: pd.DataFrame) -> pd.DataFrame:
    series = df.groupby("simt")["id"].nunique().reset_index(name="aircraft")
    series["hour"] = series["simt"] / 3600.0
    return series


def detect_lowc_events(
    df: pd.DataFrame,
    horizontal_threshold_m: float,
    nmac_horizontal_threshold_m: float,
    sample_seconds: int,
    detection_horizon_seconds: float,
    aircraft_count: int,
    total_flight_hours: float,
    total_distance_km: float,
    mac_beta: float,
    mac_probability_given_nmac: float,
    tls_target_per_flight_hour: float,
    tls_epsilon: float,
    lowc_vertical_threshold_m: float | None = None,
    nmac_vertical_threshold_m: float | None = None,
    operation_count: int | None = None,
) -> tuple[pd.DataFrame, list[float], dict[str, Any]]:
    """Detect sampled 3D Loss of Well Clear events and compute safety rates.

    When a vertical threshold is ``None``, the corresponding event remains a
    horizontal-only diagnostic for backwards compatibility.
    """

    if sample_seconds <= 0:
        sample_seconds = 1

    sampled = df[np.isclose(df["simt"] % sample_seconds, 0)]
    pair_samples: list[dict[str, Any]] = []
    separation_samples: list[float] = []

    for simt, group in sampled.groupby("simt", sort=True):
        size = len(group)
        if size < 2:
            continue
        left, right = np.triu_indices(size, 1)
        lat = group["lat"].to_numpy(dtype=float)
        lon = group["lon"].to_numpy(dtype=float)
        alt = group["alt"].to_numpy(dtype=float)
        ids = group["id"].astype(str).to_numpy()
        vehicle_types = (
            group["vehicle_type"].astype(str).to_numpy()
            if "vehicle_type" in group.columns
            else np.repeat("desconhecido", size)
        )
        horizontal = haversine_m(lat[left], lon[left], lat[right], lon[right])
        vertical = np.abs(alt[left] - alt[right])
        separation_samples.extend(horizontal.tolist())
        lowc_mask = horizontal < horizontal_threshold_m
        if lowc_vertical_threshold_m is not None:
            lowc_mask &= vertical < lowc_vertical_threshold_m

        for pair_index in np.flatnonzero(lowc_mask):
            a = int(left[pair_index])
            b = int(right[pair_index])
            dist_h_m = float(horizontal[pair_index])
            dist_v_m = float(vertical[pair_index])
            horizontal_ratio = _safe_rate(dist_h_m, horizontal_threshold_m)
            vertical_ratio = (
                _safe_rate(dist_v_m, lowc_vertical_threshold_m)
                if lowc_vertical_threshold_m is not None
                else 0.0
            )
            nmac = dist_h_m < nmac_horizontal_threshold_m
            if nmac_vertical_threshold_m is not None:
                nmac = nmac and dist_v_m < nmac_vertical_threshold_m
            type_a = str(vehicle_types[a])
            type_b = str(vehicle_types[b])
            pair_samples.append(
                {
                    "simt": float(simt),
                    "id_a": str(ids[a]),
                    "id_b": str(ids[b]),
                    "vehicle_type_a": type_a,
                    "vehicle_type_b": type_b,
                    "vehicle_pair": " - ".join(sorted((type_a, type_b))),
                    "lat": float((lat[a] + lat[b]) / 2),
                    "lon": float((lon[a] + lon[b]) / 2),
                    "alt": float((alt[a] + alt[b]) / 2),
                    "dist_h_m": dist_h_m,
                    "dist_v_m": dist_v_m,
                    "horizontal_ratio": float(horizontal_ratio),
                    "vertical_ratio": float(vertical_ratio),
                    "severity_ratio": float(max(horizontal_ratio, vertical_ratio)),
                    "is_nmac": bool(nmac),
                }
            )

    events = _collapse_lowc_samples(pair_samples, sample_seconds, detection_horizon_seconds)
    safety = _safety_summary(
        events,
        pair_sample_count=len(separation_samples),
        aircraft_count=int(operation_count if operation_count is not None else aircraft_count),
        total_flight_hours=total_flight_hours,
        total_distance_km=total_distance_km,
        horizontal_threshold_m=horizontal_threshold_m,
        nmac_horizontal_threshold_m=nmac_horizontal_threshold_m,
        lowc_vertical_threshold_m=lowc_vertical_threshold_m,
        nmac_vertical_threshold_m=nmac_vertical_threshold_m,
        sample_seconds=sample_seconds,
        detection_horizon_seconds=detection_horizon_seconds,
        mac_beta=mac_beta,
        mac_probability_given_nmac=mac_probability_given_nmac,
        tls_target_per_flight_hour=tls_target_per_flight_hour,
        tls_epsilon=tls_epsilon,
    )
    return pd.DataFrame(events), separation_samples, safety


def _collapse_lowc_samples(
    samples: list[dict[str, Any]],
    sample_seconds: int,
    detection_horizon_seconds: float,
) -> list[dict[str, Any]]:
    if not samples:
        return []

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for sample in samples:
        key = tuple(sorted((sample["id_a"], sample["id_b"])))
        grouped.setdefault(key, []).append(sample)

    events: list[dict[str, Any]] = []
    max_gap_s = sample_seconds * 1.5
    for pair_samples in grouped.values():
        pair_samples.sort(key=lambda item: item["simt"])
        current: list[dict[str, Any]] = []

        for sample in pair_samples:
            if current and sample["simt"] - current[-1]["simt"] > max_gap_s:
                events.append(_summarize_lowc_event(current, sample_seconds, detection_horizon_seconds))
                current = []
            current.append(sample)

        if current:
            events.append(_summarize_lowc_event(current, sample_seconds, detection_horizon_seconds))

    events.sort(key=lambda item: item["simt"])
    return events


def _summarize_lowc_event(
    samples: list[dict[str, Any]],
    sample_seconds: int,
    detection_horizon_seconds: float,
) -> dict[str, Any]:
    most_severe = min(samples, key=lambda item: item["severity_ratio"])
    start_simt = float(samples[0]["simt"])
    return {
        "simt": float(most_severe["simt"]),
        "start_simt": start_simt,
        "end_simt": float(samples[-1]["simt"]),
        "detection_simt": max(0.0, start_simt - float(detection_horizon_seconds)),
        "time_to_conflict_s": float(detection_horizon_seconds),
        "duration_s": float(len(samples) * sample_seconds),
        "sample_count": int(len(samples)),
        "id_a": most_severe["id_a"],
        "id_b": most_severe["id_b"],
        "vehicle_type_a": most_severe["vehicle_type_a"],
        "vehicle_type_b": most_severe["vehicle_type_b"],
        "vehicle_pair": most_severe["vehicle_pair"],
        "lat": float(most_severe["lat"]),
        "lon": float(most_severe["lon"]),
        "alt": float(most_severe["alt"]),
        "dist_h_m": float(most_severe["dist_h_m"]),
        "dist_v_m": float(most_severe["dist_v_m"]),
        "horizontal_ratio": float(most_severe["horizontal_ratio"]),
        "vertical_ratio": float(most_severe["vertical_ratio"]),
        "severity_ratio": float(most_severe["severity_ratio"]),
        "is_nmac": bool(any(sample["is_nmac"] for sample in samples)),
    }


def _safety_summary(
    events: list[dict[str, Any]],
    pair_sample_count: int,
    aircraft_count: int,
    total_flight_hours: float,
    total_distance_km: float,
    horizontal_threshold_m: float,
    nmac_horizontal_threshold_m: float,
    lowc_vertical_threshold_m: float | None,
    nmac_vertical_threshold_m: float | None,
    sample_seconds: int,
    detection_horizon_seconds: float,
    mac_beta: float,
    mac_probability_given_nmac: float,
    tls_target_per_flight_hour: float,
    tls_epsilon: float,
) -> dict[str, Any]:
    lowc_count = len(events)
    nmac_count = sum(1 for event in events if event["is_nmac"])
    severities = [event["severity_ratio"] for event in events]
    durations = [event["duration_s"] for event in events]
    time_to_conflict_values = [event["time_to_conflict_s"] for event in events]
    expected_mac = float(nmac_count * mac_beta * mac_probability_given_nmac)
    expected_mac_rate_per_flight_hour = _safe_rate(expected_mac, total_flight_hours)
    tls_margin = float(tls_target_per_flight_hour / (expected_mac_rate_per_flight_hour + tls_epsilon))
    events_by_vehicle_pair: dict[str, dict[str, int]] = {}
    for event in events:
        pair = str(event.get("vehicle_pair", "desconhecido"))
        item = events_by_vehicle_pair.setdefault(pair, {"lowc_events": 0, "nmac_events": 0})
        item["lowc_events"] += 1
        item["nmac_events"] += int(bool(event["is_nmac"]))

    return {
        "lowc_events": int(lowc_count),
        "nmac_events": int(nmac_count),
        "lowc_horizontal_m": float(horizontal_threshold_m),
        "lowc_vertical_m": (
            float(lowc_vertical_threshold_m) if lowc_vertical_threshold_m is not None else None
        ),
        "nmac_horizontal_m": float(nmac_horizontal_threshold_m),
        "nmac_vertical_m": (
            float(nmac_vertical_threshold_m) if nmac_vertical_threshold_m is not None else None
        ),
        "conflict_definition": "3D retangular" if lowc_vertical_threshold_m is not None else "somente horizontal",
        "operation_count": int(aircraft_count),
        "events_by_vehicle_pair": events_by_vehicle_pair,
        "sample_seconds": int(sample_seconds),
        "conflict_detection_horizon_s": float(detection_horizon_seconds),
        "time_to_conflict_source": "horizonte configurado; nao observado no STATELOG",
        "separation_samples": int(pair_sample_count),
        "lowc_per_100_operations": _safe_rate(lowc_count, aircraft_count, 100.0),
        "lowc_per_flight_hour": _safe_rate(lowc_count, total_flight_hours),
        "lowc_per_1000_km": _safe_rate(lowc_count, total_distance_km, 1000.0),
        "nmac_per_100_operations": _safe_rate(nmac_count, aircraft_count, 100.0),
        "nmac_per_flight_hour": _safe_rate(nmac_count, total_flight_hours),
        "nmac_per_1000_km": _safe_rate(nmac_count, total_distance_km, 1000.0),
        "monitored_pair_samples": int(pair_sample_count),
        "min_severity_ratio": min(severities) if severities else 0.0,
        "p05_severity_ratio": _percentile(severities, 0.05),
        "median_severity_ratio": _percentile(severities, 0.50),
        "p95_severity_ratio": _percentile(severities, 0.95),
        "total_time_below_threshold_s": float(sum(durations)),
        "mean_time_below_threshold_s": float(np.mean(durations)) if durations else 0.0,
        "max_time_below_threshold_s": max(durations) if durations else 0.0,
        "mean_time_to_conflict_s": float(np.mean(time_to_conflict_values))
        if time_to_conflict_values
        else 0.0,
        "min_time_to_conflict_s": min(time_to_conflict_values) if time_to_conflict_values else 0.0,
        "mac_beta": float(mac_beta),
        "mac_probability_given_nmac": float(mac_probability_given_nmac),
        "expected_mac": expected_mac,
        "expected_mac_rate_per_flight_hour": expected_mac_rate_per_flight_hour,
        "expected_mac_per_100k_flight_hours": _safe_rate(expected_mac, total_flight_hours, 100000.0),
        "tls_target_per_flight_hour": float(tls_target_per_flight_hour),
        "tls_epsilon": float(tls_epsilon),
        "tls_margin": tls_margin,
        "tls_compliant": bool(expected_mac_rate_per_flight_hour <= tls_target_per_flight_hour),
    }
