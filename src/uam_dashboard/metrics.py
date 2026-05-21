from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .config import FEET_TO_METERS, METERS_PER_NM


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


def efficiency_metrics(df: pd.DataFrame) -> dict[str, Any]:
    grouped = df.groupby("id", sort=True)
    durations_s = grouped["simt"].max() - grouped["simt"].min()
    distances_m = grouped["distflown"].max()

    route_efficiencies = []
    for _, group in grouped:
        first = group.iloc[0]
        last = group.iloc[-1]
        straight_m = haversine_m(first["lat"], first["lon"], last["lat"], last["lon"])
        flown_m = float(group["distflown"].max())
        if flown_m > 0:
            route_efficiencies.append(float(straight_m / flown_m))

    return {
        "mean_flight_time_min": float(durations_s.mean() / 60.0),
        "median_flight_time_min": float(durations_s.median() / 60.0),
        "mean_distance_nm": float(distances_m.mean() / METERS_PER_NM),
        "median_distance_nm": float(distances_m.median() / METERS_PER_NM),
        "mean_route_efficiency_pct": float(np.mean(route_efficiencies) * 100.0)
        if route_efficiencies
        else 0.0,
    }


def environment_metrics(df: pd.DataFrame, low_altitude_ft: float) -> dict[str, Any]:
    threshold_m = low_altitude_ft * FEET_TO_METERS
    low_altitude_share = float((df["alt"] < threshold_m).mean() * 100.0) if len(df) else 0.0
    return {
        "low_altitude_threshold_ft": float(low_altitude_ft),
        "low_altitude_threshold_m": float(threshold_m),
        "low_altitude_share_pct": low_altitude_share,
        "mean_altitude_m": float(df["alt"].mean()),
        "median_altitude_m": float(df["alt"].median()),
    }


def active_aircraft_series(df: pd.DataFrame) -> pd.DataFrame:
    series = df.groupby("simt")["id"].nunique().reset_index(name="aircraft")
    series["hour"] = series["simt"] / 3600.0
    return series


def detect_lowc_events(
    df: pd.DataFrame,
    horizontal_threshold_m: float,
    vertical_threshold_m: float,
    sample_seconds: int,
    same_altitude_band_m: float,
) -> tuple[pd.DataFrame, list[float]]:
    """Detect sampled Loss of Well Clear events and return nearby separations."""

    if sample_seconds <= 0:
        sample_seconds = 1

    sampled = df[np.isclose(df["simt"] % sample_seconds, 0)]
    events: list[dict[str, Any]] = []
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
            events.append(
                {
                    "simt": float(simt),
                    "id_a": row["id_a"],
                    "id_b": row["id_b"],
                    "lat": float((row["lat_a"] + row["lat_b"]) / 2),
                    "lon": float((row["lon_a"] + row["lon_b"]) / 2),
                    "dist_h_m": float(row["dist_h_m"]),
                    "dist_v_m": float(row["dist_v_m"]),
                }
            )

    return pd.DataFrame(events), separation_samples
