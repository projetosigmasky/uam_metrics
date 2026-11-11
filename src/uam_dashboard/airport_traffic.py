"""eVTOL x airport traffic: a safety analysis separate from the simulated-traffic one.

The airport traffic is a fixed background: Flightradar24 tracks of the SBSP
peak day (data/airport_traffic). It is not simulated in BlueSky and does not
react to the simulated flights. Its positions are linearly interpolated to whole
seconds on the scenario clock (seconds from 00:00 UTC) and compared with the
STATELOG positions of the **eVTOLs** at the same instant. Helicopters are not
paired with the airport traffic, and the existing ``safety`` block (pairs between
simulated aircraft) is left unchanged.

Event definition, collapse, severity and the MAC/TLS formulas are those of
``detect_lowc_events``/``_safety_summary``; rates use eVTOL operations and eVTOL
flight hours (same flight-instance rule as the efficiency metrics).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .metrics import _collapse_lowc_samples, _safe_rate, _safety_summary, efficiency_metrics, haversine_m

FEET_TO_METERS = 0.3048
DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "airport_traffic"
DEFAULT_AIRPORT_TRAFFIC_PATH = DATA_DIR / "fr24_sbsp_peak_20221201.csv.gz"
EVTOL_TYPE = "eVTOL"
AIRPORT_VEHICLE_TYPE = "aviao_aeroporto"
ID_PREFIX = "FR24:"
PROXIMITY_HORIZONTAL_M = 5000.0
EVENT_TABLES = ("events_by_airport", "events_by_airport_movement", "events_by_vehicle_pair")
DESCRIPTIVE_KEYS = ("available", "source", "definition", "thresholds", "reason")


def traffic_metadata(path: str | Path) -> dict[str, Any]:
    sidecar = Path(path).with_suffix("").with_suffix(".json")
    if not sidecar.exists():
        return {"csv": Path(path).name}
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    return {key: data.get(key) for key in ("source", "content", "peak_rule", "peak_day_local", "sim_time_origin_utc",
                                           "airports", "flights", "rows", "csv", "csv_sha256", "altitude")}


@lru_cache(maxsize=2)
def load_airport_traffic(path: str, max_gap_seconds: float = 60.0) -> pd.DataFrame:
    """Return airport traffic at whole seconds: simt, fr24_id, lat, lon, alt (m) and labels.

    Consecutive FR24 points of a flight are joined by straight-line interpolation
    when they are at most ``max_gap_seconds`` apart; longer gaps stay empty.
    """
    raw = pd.read_csv(path, dtype={"fr24_id": str, "callsign": str, "equip": str, "airport": str, "movement": str},
                      keep_default_na=False)
    raw = raw.drop_duplicates(["fr24_id", "sim_time_s"]).sort_values(["fr24_id", "sim_time_s"]).reset_index(drop=True)
    t = raw["sim_time_s"].to_numpy(dtype=np.int64)
    same = raw["fr24_id"].to_numpy()[1:] == raw["fr24_id"].to_numpy()[:-1]
    gap = np.diff(t)
    joined = same & (gap > 0) & (gap <= max_gap_seconds)
    start = np.flatnonzero(joined)
    counts = gap[joined]
    offsets = np.arange(counts.sum()) - np.repeat(np.cumsum(counts) - counts, counts)
    left = np.repeat(start, counts)
    fraction = offsets / np.repeat(counts, counts)
    lat, lon, alt = (raw[c].to_numpy(dtype=float) for c in ("lat", "lon", "alt_ft"))
    alt = alt * FEET_TO_METERS
    interpolated = pd.DataFrame({
        "row": left,
        "simt": t[left] + offsets,
        "lat": lat[left] + (lat[left + 1] - lat[left]) * fraction,
        "lon": lon[left] + (lon[left + 1] - lon[left]) * fraction,
        "alt": alt[left] + (alt[left + 1] - alt[left]) * fraction,
    })
    # Points that do not start a joined interval (segment ends, isolated points).
    ends = np.setdiff1d(np.arange(len(raw)), start)
    tail = pd.DataFrame({"row": ends, "simt": t[ends], "lat": lat[ends], "lon": lon[ends], "alt": alt[ends]})
    frame = pd.concat([interpolated, tail], ignore_index=True)
    labels = raw[["fr24_id", "callsign", "equip", "airport", "movement"]]
    frame = pd.concat([frame.drop(columns="row").reset_index(drop=True),
                       labels.iloc[frame["row"].to_numpy()].reset_index(drop=True)], axis=1)
    return frame.drop_duplicates(["fr24_id", "simt"]).sort_values(["simt", "fr24_id"]).reset_index(drop=True)


def _no_event_severity(summary: dict[str, Any]) -> dict[str, Any]:
    # No event means no observed severity (not the 0.0 sentinel of _safety_summary).
    if not summary["lowc_events"]:
        for key in ("min_severity_ratio", "p05_severity_ratio", "median_severity_ratio", "p95_severity_ratio"):
            summary[key] = None
    return summary


def evtol_airport_safety(
    df: pd.DataFrame,
    traffic: pd.DataFrame,
    *,
    lowc_horizontal_m: float,
    lowc_vertical_m: float,
    nmac_horizontal_m: float,
    nmac_vertical_m: float,
    sample_seconds: int,
    gap_seconds: float,
    reset_distance_m: float,
    jump_m: float,
    mac_beta: float,
    mac_probability_given_nmac: float,
    tls_target_per_flight_hour: float,
    tls_epsilon: float,
    source: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return eVTOL x airport-traffic events and the ``evtol_airport_safety`` payload."""

    thresholds = {"lowc_horizontal_m": float(lowc_horizontal_m), "lowc_vertical_m": float(lowc_vertical_m),
                  "nmac_horizontal_m": float(nmac_horizontal_m), "nmac_vertical_m": float(nmac_vertical_m)}
    definition = ("eVTOL x background FR24 airport traffic (interpolated to 1 s); helicopters excluded; "
                  "rates per eVTOL operation and eVTOL flight hour")
    evtols = df[df["vehicle_type"].astype(str) == EVTOL_TYPE] if "vehicle_type" in df.columns else df.iloc[:0]
    if evtols.empty:
        return [], {"available": False, "reason": "scenario without eVTOL", "source": source or {},
                    "definition": definition, "thresholds": thresholds}
    exposure = efficiency_metrics(evtols, gap_seconds=gap_seconds, reset_distance_m=reset_distance_m, jump_m=jump_m)

    sample_seconds = max(int(sample_seconds), 1)
    sim = evtols[np.isclose(evtols["simt"] % sample_seconds, 0)]
    sim = pd.DataFrame({"simt": np.rint(sim["simt"].to_numpy()).astype(np.int64), "id": sim["id"].astype(str).to_numpy(),
                        "lat": sim["lat"].to_numpy(float), "lon": sim["lon"].to_numpy(float),
                        "alt": sim["alt"].to_numpy(float)})
    window = traffic[traffic["simt"].between(sim["simt"].min(), sim["simt"].max())]
    margin_deg = PROXIMITY_HORIZONTAL_M / 111_000.0
    near = window[window["alt"].between(sim["alt"].min() - lowc_vertical_m, sim["alt"].max() + lowc_vertical_m)
                  & window["lat"].between(sim["lat"].min() - margin_deg, sim["lat"].max() + margin_deg)
                  & window["lon"].between(sim["lon"].min() - margin_deg, sim["lon"].max() + margin_deg)]
    pairs = sim.merge(near, on="simt", suffixes=("", "_fr"))
    horizontal = haversine_m(pairs["lat"].to_numpy(), pairs["lon"].to_numpy(),
                             pairs["lat_fr"].to_numpy(), pairs["lon_fr"].to_numpy()) if len(pairs) else np.array([])
    vertical = np.abs(pairs["alt"].to_numpy() - pairs["alt_fr"].to_numpy()) if len(pairs) else np.array([])
    co_altitude = vertical < lowc_vertical_m
    proximity = co_altitude & (horizontal < PROXIMITY_HORIZONTAL_M)
    lowc = co_altitude & (horizontal < lowc_horizontal_m)

    samples = []
    pair_type = " - ".join(sorted((EVTOL_TYPE, AIRPORT_VEHICLE_TYPE)))
    for index in np.flatnonzero(lowc):
        row = pairs.iloc[index]
        h, v = float(horizontal[index]), float(vertical[index])
        h_ratio, v_ratio = _safe_rate(h, lowc_horizontal_m), _safe_rate(v, lowc_vertical_m)
        samples.append({
            "simt": float(row["simt"]), "id_a": str(row["id"]), "id_b": ID_PREFIX + str(row["fr24_id"]),
            "vehicle_type_a": EVTOL_TYPE, "vehicle_type_b": AIRPORT_VEHICLE_TYPE, "vehicle_pair": pair_type,
            "lat": float((row["lat"] + row["lat_fr"]) / 2), "lon": float((row["lon"] + row["lon_fr"]) / 2),
            "alt": float((row["alt"] + row["alt_fr"]) / 2), "dist_h_m": h, "dist_v_m": v,
            "horizontal_ratio": float(h_ratio), "vertical_ratio": float(v_ratio),
            "severity_ratio": float(min(h_ratio, v_ratio)),
            "is_nmac": bool(h < nmac_horizontal_m and v < nmac_vertical_m),
        })
    events = _collapse_lowc_samples(samples, sample_seconds, 0.0)
    labels = near.drop_duplicates("fr24_id").set_index("fr24_id")[["callsign", "equip", "airport", "movement"]]
    for event in events:
        fr24_id = event["id_b"][len(ID_PREFIX):]
        event.update(fr24_id=fr24_id, **labels.loc[fr24_id].to_dict())

    summary = _no_event_severity(_safety_summary(
        events, pair_sample_count=int(proximity.sum()), aircraft_count=exposure["flight_instances"],
        total_flight_hours=exposure["total_flight_hours"], total_distance_km=exposure["total_distance_km"],
        horizontal_threshold_m=lowc_horizontal_m, nmac_horizontal_threshold_m=nmac_horizontal_m,
        lowc_vertical_threshold_m=lowc_vertical_m, nmac_vertical_threshold_m=nmac_vertical_m,
        sample_seconds=sample_seconds, detection_horizon_seconds=0.0, mac_beta=mac_beta,
        mac_probability_given_nmac=mac_probability_given_nmac,
        tls_target_per_flight_hour=tls_target_per_flight_hour, tls_epsilon=tls_epsilon))
    by_airport: dict[str, dict[str, int]] = {}
    by_movement: dict[str, dict[str, int]] = {}
    for event in events:
        for table, key in ((by_airport, event["airport"]), (by_movement, f"{event['airport']}/{event['movement']}")):
            item = table.setdefault(str(key), {"lowc_events": 0, "nmac_events": 0})
            item["lowc_events"] += 1
            item["nmac_events"] += int(event["is_nmac"])
    payload = {
        "available": True,
        "source": source or {},
        "definition": definition,
        "thresholds": thresholds,
        **summary,
        "evtol_operations": int(exposure["flight_instances"]),
        "evtol_flight_hours": float(exposure["total_flight_hours"]),
        "events_by_airport": by_airport,
        "events_by_airport_movement": by_movement,
        "airport_flights_with_lowc": int(len({e["fr24_id"] for e in events})),
        "evtol_flights_with_lowc": int(len({e["id_a"] for e in events})),
        "min_horizontal_m_co_altitude": float(horizontal[co_altitude].min()) if co_altitude.any() else None,
        "pair_samples_within_5km_co_altitude": int(proximity.sum()),
        "airport_flights_in_time_window": int(window["fr24_id"].nunique()),
        "airport_flights_within_5km_co_altitude": int(pairs.loc[proximity, "fr24_id"].nunique()) if len(pairs) else 0,
    }
    return events, payload


def average_evtol_airport(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    """Mean of the per-replica payloads; absent event classes count as zero events."""

    valid = [p for p in payloads if p and p.get("available")]
    if not valid:
        first = next((p for p in payloads if p), {})
        return {key: first[key] for key in DESCRIPTIVE_KEYS if key in first} | {"available": False}

    def mean_tree(items: list[Any]) -> Any:
        present = [item for item in items if item is not None]
        if not present:
            return None
        first = present[0]
        if isinstance(first, (bool, int, float)):
            return float(np.mean(present))
        if isinstance(first, dict):
            return {key: mean_tree([item.get(key) for item in present]) for key in sorted({k for i in present for k in i})}
        return first

    result = {key: valid[0][key] for key in DESCRIPTIVE_KEYS if key in valid[0]}
    numeric = mean_tree([{k: v for k, v in p.items() if k not in DESCRIPTIVE_KEYS} for p in valid])
    for table in EVENT_TABLES:
        keys = sorted({k for p in valid for k in p.get(table, {})})
        numeric[table] = {k: {m: float(np.mean([p.get(table, {}).get(k, {}).get(m, 0) for p in valid]))
                              for m in ("lowc_events", "nmac_events")} for k in keys}
    # TLS keeps the card formula: target / (mean rate + epsilon).
    rate = numeric["expected_mac_rate_per_flight_hour"]
    numeric["tls_margin"] = numeric["tls_target_per_flight_hour"] / (rate + numeric["tls_epsilon"])
    numeric["tls_compliant"] = bool(rate <= numeric["tls_target_per_flight_hour"])
    return result | numeric | {"replica_count": len(valid)}
