from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .config import FEET_TO_METERS, METERS_PER_NM, ROUTE_REFERENCE_MIN_M


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


def efficiency_metrics(df: pd.DataFrame) -> dict[str, Any]:
    grouped = df.groupby("id", sort=True)
    durations_s = grouped["simt"].max() - grouped["simt"].min()
    distances_m = grouped["distflown"].max()

    route_efficiencies = []
    route_extensions = []
    great_circle_distances_m = []
    route_proxy_excluded_count = 0
    for _, group in grouped:
        first = group.iloc[0]
        last = group.iloc[-1]
        straight_m = haversine_m(first["lat"], first["lon"], last["lat"], last["lon"])
        flown_m = float(group["distflown"].max())
        great_circle_distances_m.append(float(straight_m))
        if flown_m > 0:
            route_efficiencies.append(float(straight_m / flown_m))
        if straight_m >= ROUTE_REFERENCE_MIN_M and flown_m > 0:
            route_extensions.append(float((flown_m / straight_m - 1.0) * 100.0))
        elif flown_m > 0:
            route_proxy_excluded_count += 1

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
        "mean_route_extension_pct": float(np.mean(route_extensions)) if route_extensions else 0.0,
        "route_extension_sample_count": int(len(route_extensions)),
        "route_proxy_excluded_count": int(route_proxy_excluded_count),
        "route_reference_min_m": float(ROUTE_REFERENCE_MIN_M),
    }


def flight_instance_frame(
    df: pd.DataFrame,
    gap_seconds: float,
    reset_distance_m: float,
    jump_m: float,
    reference_samples: int,
) -> pd.DataFrame:
    """Return rows annotated with flight instances and origin altitude references."""

    annotated_groups: list[pd.DataFrame] = []
    reference_samples = max(1, int(reference_samples))

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

    annotated = pd.concat(annotated_groups, ignore_index=True).sort_values(["simt", "id"]).reset_index(drop=True)
    origin_altitudes = (
        annotated.groupby("flight_instance", sort=True)
        .head(reference_samples)
        .groupby("flight_instance")["alt"]
        .median()
    )
    annotated["origin_alt_m"] = annotated["flight_instance"].map(origin_altitudes)
    annotated["alt_agl_proxy_m"] = annotated["alt"] - annotated["origin_alt_m"]
    return annotated


def environment_metrics(
    df: pd.DataFrame,
    low_altitude_ft: float,
    reference_mode: str = "origin_agl_proxy",
    reference_samples: int = 5,
    instance_gap_seconds: float = 300.0,
    instance_reset_distance_m: float = 250.0,
    instance_jump_m: float = 5000.0,
) -> dict[str, Any]:
    threshold_m = low_altitude_ft * FEET_TO_METERS
    reference_mode = reference_mode or "origin_agl_proxy"

    if reference_mode == "msl":
        annotated = df.copy()
        annotated["flight_instance"] = annotated["id"]
        annotated["origin_alt_m"] = 0.0
        annotated["alt_agl_proxy_m"] = annotated["alt"]
        altitude_for_low_share = annotated["alt"]
    else:
        annotated = flight_instance_frame(
            df,
            gap_seconds=instance_gap_seconds,
            reset_distance_m=instance_reset_distance_m,
            jump_m=instance_jump_m,
            reference_samples=reference_samples,
        )
        altitude_for_low_share = annotated["alt_agl_proxy_m"]

    low_altitude_share = float((altitude_for_low_share < threshold_m).mean() * 100.0) if len(annotated) else 0.0
    origin_altitudes = annotated.groupby("flight_instance")["origin_alt_m"].first() if len(annotated) else pd.Series(dtype=float)
    return {
        "low_altitude_threshold_ft": float(low_altitude_ft),
        "low_altitude_threshold_m": float(threshold_m),
        "low_altitude_reference_mode": reference_mode,
        "low_altitude_reference_samples": int(reference_samples),
        "flight_instance_gap_seconds": float(instance_gap_seconds),
        "flight_instance_reset_distance_m": float(instance_reset_distance_m),
        "flight_instance_jump_m": float(instance_jump_m),
        "low_altitude_share_pct": low_altitude_share,
        "mean_altitude_m": float(df["alt"].mean()),
        "median_altitude_m": float(df["alt"].median()),
        "mean_altitude_agl_proxy_m": float(annotated["alt_agl_proxy_m"].mean()) if len(annotated) else 0.0,
        "median_altitude_agl_proxy_m": float(annotated["alt_agl_proxy_m"].median()) if len(annotated) else 0.0,
        "mean_origin_altitude_m": float(origin_altitudes.mean()) if len(origin_altitudes) else 0.0,
        "median_origin_altitude_m": float(origin_altitudes.median()) if len(origin_altitudes) else 0.0,
        "flight_instance_count": int(annotated["flight_instance"].nunique()) if len(annotated) else 0,
    }


def active_aircraft_series(df: pd.DataFrame) -> pd.DataFrame:
    series = df.groupby("simt")["id"].nunique().reset_index(name="aircraft")
    series["hour"] = series["simt"] / 3600.0
    return series


def detect_lowc_events(
    df: pd.DataFrame,
    horizontal_threshold_m: float,
    vertical_threshold_m: float,
    nmac_horizontal_threshold_m: float,
    nmac_vertical_threshold_m: float,
    sample_seconds: int,
    same_altitude_band_m: float,
    aircraft_count: int,
    total_flight_hours: float,
    total_distance_km: float,
    mac_probability_bands: tuple[float, float, float],
) -> tuple[pd.DataFrame, list[float], dict[str, Any]]:
    """Detect sampled Loss of Well Clear events and compute safety rates."""

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
        pairs["dist_v_m"] = np.abs(pairs["alt_a"].to_numpy() - pairs["alt_b"].to_numpy())

        same_band = pairs[pairs["dist_v_m"] < same_altitude_band_m]
        if not same_band.empty:
            separation_samples.extend(same_band["dist_h_m"].tolist())

        lowc = same_band[
            (same_band["dist_h_m"] < horizontal_threshold_m)
            & (same_band["dist_v_m"] < vertical_threshold_m)
        ]
        for _, row in lowc.iterrows():
            severity_ratio = min(
                _safe_rate(float(row["dist_h_m"]), horizontal_threshold_m),
                _safe_rate(float(row["dist_v_m"]), vertical_threshold_m),
            )
            pair_samples.append(
                {
                    "simt": float(simt),
                    "id_a": str(row["id_a"]),
                    "id_b": str(row["id_b"]),
                    "lat": float((row["lat_a"] + row["lat_b"]) / 2),
                    "lon": float((row["lon_a"] + row["lon_b"]) / 2),
                    "dist_h_m": float(row["dist_h_m"]),
                    "dist_v_m": float(row["dist_v_m"]),
                    "severity_ratio": float(severity_ratio),
                    "is_nmac": bool(
                        row["dist_h_m"] < nmac_horizontal_threshold_m
                        and row["dist_v_m"] < nmac_vertical_threshold_m
                    ),
                }
            )

    events = _collapse_lowc_samples(pair_samples, sample_seconds)
    safety = _safety_summary(
        events,
        pair_sample_count=len(separation_samples),
        aircraft_count=aircraft_count,
        total_flight_hours=total_flight_hours,
        total_distance_km=total_distance_km,
        horizontal_threshold_m=horizontal_threshold_m,
        vertical_threshold_m=vertical_threshold_m,
        nmac_horizontal_threshold_m=nmac_horizontal_threshold_m,
        nmac_vertical_threshold_m=nmac_vertical_threshold_m,
        sample_seconds=sample_seconds,
        same_altitude_band_m=same_altitude_band_m,
        mac_probability_bands=mac_probability_bands,
    )
    return pd.DataFrame(events), separation_samples, safety


def _collapse_lowc_samples(samples: list[dict[str, Any]], sample_seconds: int) -> list[dict[str, Any]]:
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
                events.append(_summarize_lowc_event(current, sample_seconds))
                current = []
            current.append(sample)

        if current:
            events.append(_summarize_lowc_event(current, sample_seconds))

    events.sort(key=lambda item: item["simt"])
    return events


def _summarize_lowc_event(samples: list[dict[str, Any]], sample_seconds: int) -> dict[str, Any]:
    most_severe = min(samples, key=lambda item: item["severity_ratio"])
    return {
        "simt": float(most_severe["simt"]),
        "start_simt": float(samples[0]["simt"]),
        "end_simt": float(samples[-1]["simt"]),
        "duration_s": float(len(samples) * sample_seconds),
        "sample_count": int(len(samples)),
        "id_a": most_severe["id_a"],
        "id_b": most_severe["id_b"],
        "lat": float(most_severe["lat"]),
        "lon": float(most_severe["lon"]),
        "dist_h_m": float(most_severe["dist_h_m"]),
        "dist_v_m": float(most_severe["dist_v_m"]),
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
    vertical_threshold_m: float,
    nmac_horizontal_threshold_m: float,
    nmac_vertical_threshold_m: float,
    sample_seconds: int,
    same_altitude_band_m: float,
    mac_probability_bands: tuple[float, float, float],
) -> dict[str, Any]:
    lowc_count = len(events)
    nmac_count = sum(1 for event in events if event["is_nmac"])
    severities = [event["severity_ratio"] for event in events]
    durations = [event["duration_s"] for event in events]
    mac_low, mac_nominal, mac_high = mac_probability_bands

    return {
        "lowc_events": int(lowc_count),
        "nmac_events": int(nmac_count),
        "lowc_horizontal_m": float(horizontal_threshold_m),
        "lowc_vertical_m": float(vertical_threshold_m),
        "nmac_horizontal_m": float(nmac_horizontal_threshold_m),
        "nmac_vertical_m": float(nmac_vertical_threshold_m),
        "sample_seconds": int(sample_seconds),
        "same_altitude_band_m": float(same_altitude_band_m),
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
        "mac_probability_low": float(mac_low),
        "mac_probability_nominal": float(mac_nominal),
        "mac_probability_high": float(mac_high),
        "expected_mac_low": float(nmac_count * mac_low),
        "expected_mac_nominal": float(nmac_count * mac_nominal),
        "expected_mac_high": float(nmac_count * mac_high),
    }
