from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

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


def build_summary(df: pd.DataFrame) -> dict[str, Any]:
    active_by_second = df.groupby("simt")["id"].nunique()
    duration_seconds = float(df["simt"].max() - df["simt"].min()) if not df.empty else 0.0

    return {
        "records": int(len(df)),
        "aircraft_count": int(df["id"].nunique()),
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
    if not ground_available and not airborne_available:
        return {"available": False}

    mean_ground_s = float(ground_delay.get("mean_ground_delay_s", 0.0)) if ground_available else 0.0
    mean_airborne_s = float(airborne_delay.get("mean_airborne_delay_s", 0.0)) if airborne_available else 0.0
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
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Compare executed samples with the closest point of their planned polyline."""

    annotated = flight_instance_frame(df, gap_seconds, reset_distance_m, jump_m)
    by_instance: dict[str, dict[str, Any]] = {}
    unused_planned = set(range(len(planned_flights)))
    all_deviations: list[float] = []
    conformity_ratios: list[float] = []
    additional_distances_m: list[float] = []
    planned_horizontal_inefficiencies: list[float] = []
    executed_horizontal_inefficiencies: list[float] = []
    conforming_samples = 0
    matched_instances = 0

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
        all_deviations.extend(deviations.tolist())
        inside = int(np.sum(deviations <= tolerance_m))
        conforming_samples += inside
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
            "start_time_delta_s": abs(float(planned["start_simt"]) - start_simt),
            "spatial_adherence_pct": float(inside / len(deviations) * 100.0),
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
    summary = {
        "available": bool(total_samples),
        "tolerance_m": float(tolerance_m),
        "planned_instances": int(len(planned_flights)),
        "matched_instances": int(matched_instances),
        "spatial_adherence_pct": _safe_rate(conforming_samples, total_samples, 100.0),
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
) -> tuple[pd.DataFrame, list[float], dict[str, Any]]:
    """Detect sampled horizontal Loss of Well Clear events and compute safety rates."""

    if sample_seconds <= 0:
        sample_seconds = 1

    sampled = df[np.isclose(df["simt"] % sample_seconds, 0)]
    pair_samples: list[dict[str, Any]] = []
    separation_samples: list[float] = []

    for simt, group in sampled.groupby("simt", sort=True):
        if len(group) < 2:
            continue

        pairs = group.merge(group, how="cross", suffixes=("_a", "_b"))
        pairs = pairs[pairs["id_a"] < pairs["id_b"]]
        if pairs.empty:
            continue

        pairs["dist_h_m"] = haversine_m(
            pairs["lat_a"].to_numpy(),
            pairs["lon_a"].to_numpy(),
            pairs["lat_b"].to_numpy(),
            pairs["lon_b"].to_numpy(),
        )
        separation_samples.extend(pairs["dist_h_m"].tolist())

        lowc = pairs[pairs["dist_h_m"] < horizontal_threshold_m]
        for _, row in lowc.iterrows():
            horizontal_ratio = _safe_rate(float(row["dist_h_m"]), horizontal_threshold_m)
            pair_samples.append(
                {
                    "simt": float(simt),
                    "id_a": str(row["id_a"]),
                    "id_b": str(row["id_b"]),
                    "lat": float((row["lat_a"] + row["lat_b"]) / 2),
                    "lon": float((row["lon_a"] + row["lon_b"]) / 2),
                    "dist_h_m": float(row["dist_h_m"]),
                    "horizontal_ratio": float(horizontal_ratio),
                    "severity_ratio": float(horizontal_ratio),
                    "is_nmac": bool(row["dist_h_m"] < nmac_horizontal_threshold_m),
                }
            )

    events = _collapse_lowc_samples(pair_samples, sample_seconds, detection_horizon_seconds)
    safety = _safety_summary(
        events,
        pair_sample_count=len(separation_samples),
        aircraft_count=aircraft_count,
        total_flight_hours=total_flight_hours,
        total_distance_km=total_distance_km,
        horizontal_threshold_m=horizontal_threshold_m,
        nmac_horizontal_threshold_m=nmac_horizontal_threshold_m,
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
        "lat": float(most_severe["lat"]),
        "lon": float(most_severe["lon"]),
        "dist_h_m": float(most_severe["dist_h_m"]),
        "horizontal_ratio": float(most_severe["horizontal_ratio"]),
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

    return {
        "lowc_events": int(lowc_count),
        "nmac_events": int(nmac_count),
        "lowc_horizontal_m": float(horizontal_threshold_m),
        "nmac_horizontal_m": float(nmac_horizontal_threshold_m),
        "sample_seconds": int(sample_seconds),
        "conflict_detection_horizon_s": float(detection_horizon_seconds),
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
