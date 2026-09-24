"""Rank UAM/REH crossings and UAM/REH junctions from C1/C2 replicas.

Run this script on the machine holding the raw logs. Only CSV/JSON summaries
need to be copied back; STATELOG files are read one at a time in a stream.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from src.uam_dashboard.capacity import (
    _buffered_route_groups,
    _official_route_groups,
    _official_uam_route_groups,
    _uam_reh_crossing_features,
)
from src.uam_dashboard.config import DEFAULT_REH_XML_PATH, DEFAULT_UAM_CSV_PATH, EXTENDED_LOG_COLUMNS, LOG_COLUMNS
from src.uam_dashboard.run_config import load_run_selection
from src.uam_dashboard.reh_parser import load_reh_network
from src.uam_dashboard.topology import network_junction_features, reh_junction_features
from src.uam_dashboard.uam_corridor_parser import load_uam_corridor_network


SCENARIO_RE = re.compile(r"(?:^|[_-])(C[12])(?:[_-]|$)", re.IGNORECASE)
EARTH_RADIUS_M = 6371000.0


def discover_logs(root: Path) -> list[tuple[str, Path]]:
    found = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".log", ".csv"} and "STATELOG" in path.name.upper():
            match = SCENARIO_RE.search(path.stem)
            if match:
                found.append((match.group(1).upper(), path))
    return found


def manifest_logs(path: Path) -> list[tuple[str, Path]]:
    found = []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            scenario = row["scenario"].strip().upper()
            if scenario not in {"C1", "C2"}:
                raise ValueError(f"Invalid scenario {scenario!r}; expected C1 or C2")
            log = Path(row["path"].strip())
            if not log.is_absolute():
                log = path.parent / log
            found.append((scenario, log))
    return found


def state_rows(path: Path):
    """Yield time, id, 3D position and flown distance from STATELOGs."""
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
        for line_number, line in enumerate(stream, 1):
            parts = [part.strip() for part in line.split(",")]
            if len(parts) < len(LOG_COLUMNS):
                continue
            try:
                simt = float(parts[0])
            except ValueError:
                continue
            names = EXTENDED_LOG_COLUMNS if len(parts) >= len(EXTENDED_LOG_COLUMNS) else LOG_COLUMNS
            try:
                fields = dict(zip(names, parts))
                row = (simt, fields["id"], float(fields["lat"]), float(fields["lon"]), float(fields["alt"]), float(fields["distflown"]))
            except ValueError as exc:
                raise ValueError(f"Invalid STATELOG row in {path}:{line_number}") from exc
            if not all(math.isfinite(value) for value in (row[0], row[2], row[3], row[4], row[5])):
                raise ValueError(f"Non-finite STATELOG value in {path}:{line_number}")
            yield row


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    a = math.sin(math.radians(lat2 - lat1) / 2) ** 2
    a += math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def crossing_index(features: list[dict], radius_m: float):
    # Approximate 250 m cells; exact capture is checked by haversine below.
    cell_deg = radius_m / 111000.0
    grid = defaultdict(list)
    for index, feature in enumerate(features):
        if feature["properties"].get("altitude_m") is None:
            continue
        lon, lat = feature["geometry"]["coordinates"]
        lat_cell = math.floor(lat / cell_deg)
        lon_span = radius_m / (111000.0 * max(0.1, math.cos(math.radians(lat))))
        lo = math.floor((lon - lon_span) / cell_deg)
        hi = math.floor((lon + lon_span) / cell_deg)
        for y in range(lat_cell - 1, lat_cell + 2):
            for x in range(lo, hi + 1):
                grid[y, x].append(index)
    return grid, cell_deg


def process_replica(path: Path, features: list[dict], radius_m: float, window_s: int,
                    gap_s: float, reset_m: float, jump_m: float) -> list[dict]:
    grid, cell_deg = crossing_index(features, radius_m)
    states = {}  # aircraft -> (time, lat, lon, distflown, instance number)
    seen = set()  # one passage per crossing and flight instance
    counts = defaultdict(lambda: defaultdict(int))
    start = end = None
    samples = 0
    for simt, aircraft, lat, lon, altitude, distance in state_rows(path):
        if start is None:
            start = simt
        if end is not None and simt < end:
            raise ValueError(f"STATELOG must be ordered by simt: {path}")
        end = simt
        samples += 1
        previous = states.get(aircraft)
        instance = 0 if previous is None else previous[4]
        if previous is not None and (
            simt - previous[0] > gap_s or distance + reset_m < previous[3]
            or haversine(previous[1], previous[2], lat, lon) > jump_m
        ):
            instance += 1
        states[aircraft] = (simt, lat, lon, distance, instance)
        cell = math.floor(lat / cell_deg), math.floor(lon / cell_deg)
        for index in grid.get(cell, ()):
            key = index, aircraft, instance
            if key in seen:
                continue
            point_lon, point_lat = features[index]["geometry"]["coordinates"]
            point_altitude = features[index]["properties"]["altitude_m"]
            if math.hypot(haversine(lat, lon, point_lat, point_lon), altitude - point_altitude) <= radius_m:
                seen.add(key)
                counts[index][int((simt - start) // window_s)] += 1
    if not samples:
        raise ValueError(f"No valid STATELOG samples in {path}")
    windows = int((end - start) // window_s) + 1
    rows = []
    for index, feature in enumerate(features):
        bins = counts[index]
        operations = sum(bins.values())
        altitude_available = feature["properties"].get("altitude_m") is not None
        rows.append({
            "waypoint_id": feature["properties"]["resource_id"],
            "criterion": feature["properties"].get("criterion", "uam_reh_crossing"),
            "network_degree": feature["properties"].get("network_degree"),
            "altitude_m": feature["properties"].get("altitude_m"),
            "operations": operations if altitude_available else None,
            "mean_throughput_per_hour": operations / (windows * window_s / 3600) if altitude_available else None,
            "peak_throughput_per_hour": max(bins.values(), default=0) * 3600 / window_s if altitude_available else None,
            "window_count": windows,
            "sample_count": samples,
        })
    return rows


def write_csv(path: Path, rows: list[dict]):
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--logs-root", type=Path, help="Recursively discover C1/C2 STATELOG files")
    source.add_argument("--manifest", type=Path, help="CSV with scenario,path columns")
    source.add_argument("--config", type=Path, help="JSON selecting a validated P100 orchestrator run")
    parser.add_argument("--reh-xml", type=Path, default=DEFAULT_REH_XML_PATH)
    parser.add_argument("--uam-csv", type=Path, default=DEFAULT_UAM_CSV_PATH)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--dashboard-assets", type=Path, help="Also publish waypoint ranking JS in this dashboard assets directory")
    parser.add_argument("--capture-radius-m", type=float, default=250.0)
    parser.add_argument("--window-seconds", type=int, default=900)
    parser.add_argument("--gap-seconds", type=float, default=300.0)
    parser.add_argument("--reset-distance-m", type=float, default=250.0)
    parser.add_argument("--jump-m", type=float, default=5000.0)
    parser.add_argument("--workers", type=int, default=1, help="Parallel replica processes (default: 1)")
    args = parser.parse_args()
    if args.capture_radius_m <= 0 or args.window_seconds <= 0 or args.workers <= 0:
        parser.error("capture radius, window and workers must be positive")
    if args.config:
        selection = load_run_selection(args.config)
        logs = [(path.parent.name, path) for path in selection.log_paths]
        args.output_dir = args.output_dir or Path("docs/assets/data/critical_waypoints")
        args.dashboard_assets = args.dashboard_assets or Path("docs/assets")
    else:
        logs = manifest_logs(args.manifest) if args.manifest else discover_logs(args.logs_root)
        if args.output_dir is None:
            parser.error("--output-dir is required without --config")
    if not logs or {scenario for scenario, _ in logs} != {"C1", "C2"}:
        parser.error("At least one C1 and one C2 STATELOG are required")
    for _, path in logs:
        if not path.is_file():
            parser.error(f"Missing log: {path}")

    reh = load_reh_network(args.reh_xml)["segments"]
    uam = load_uam_corridor_network(args.uam_csv)["routes"]
    crossing_features = _uam_reh_crossing_features(
        _buffered_route_groups(_official_uam_route_groups(uam), 250.0), _official_route_groups(reh)
    )
    junction_features = network_junction_features(uam)
    reh_junctions = reh_junction_features(reh)
    for feature in crossing_features:
        feature["properties"]["criterion"] = "uam_reh_crossing"
        feature["properties"]["network_degree"] = None
    for feature in junction_features:
        feature["properties"]["criterion"] = "uam_junction"
    for feature in reh_junctions:
        feature["properties"]["criterion"] = "reh_junction"
    features = crossing_features + junction_features + reh_junctions
    if not features:
        parser.error("No UAM/REH crossings or degree > 2 network junctions found")
    print(f"{len(crossing_features)} crossings; {len(junction_features)} UAM junctions; "
          f"{len(reh_junctions)} REH junctions; "
          f"{len(logs)} replicas", file=sys.stderr)
    replica_rows = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(
            process_replica, path, features, args.capture_radius_m, args.window_seconds,
            args.gap_seconds, args.reset_distance_m, args.jump_m,
        ) for _, path in logs]
        for (scenario, path), future in zip(logs, futures):
            for row in future.result():
                replica_rows.append({"scenario": scenario, "replica": f"{scenario}/{path.name}", **row})
            print(f"Completed {scenario}: {path}", file=sys.stderr, flush=True)

    by_scenario = defaultdict(list)
    for scenario, _ in logs:
        by_scenario[scenario].append(1)
    replica_counts = {scenario: len(items) for scenario, items in by_scenario.items()}
    grouped = defaultdict(list)
    for row in replica_rows:
        grouped[row["scenario"], row["waypoint_id"]].append(row)
    summary = []
    for scenario in ("C1", "C2"):
        for feature in features:
            properties = feature["properties"]
            waypoint_id = properties["resource_id"]
            rows = grouped[scenario, waypoint_id]
            altitude_available = properties.get("altitude_m") is not None
            lon, lat = feature["geometry"]["coordinates"]
            summary.append({
                "scenario": scenario,
                "waypoint_id": waypoint_id,
                "label": properties["label"],
                "criterion": properties["criterion"],
                "network_degree": properties["network_degree"],
                "latitude": lat,
                "longitude": lon,
                "altitude_m": properties.get("altitude_m"),
                "replica_count": len(rows),
                "mean_operations_per_replica": sum(r["operations"] for r in rows) / len(rows) if altitude_available else None,
                "mean_throughput_per_hour": sum(r["mean_throughput_per_hour"] for r in rows) / len(rows) if altitude_available else None,
                "mean_peak_throughput_per_hour": sum(r["peak_throughput_per_hour"] for r in rows) / len(rows) if altitude_available else None,
                "uam_route_ids": ";".join(properties["uam_route_ids"]),
                "reh_resource_ids": ";".join(properties["reh_resource_ids"]),
            })
    summary.sort(key=lambda row: (row["scenario"], -row["mean_throughput_per_hour"] if row["mean_throughput_per_hour"] is not None else float("inf"),
                                  -row["mean_peak_throughput_per_hour"] if row["mean_peak_throughput_per_hour"] is not None else float("inf"), row["waypoint_id"]))
    ranks = defaultdict(int)
    for row in summary:
        if row["mean_throughput_per_hour"] is not None:
            ranks[row["scenario"]] += 1
            row["rank"] = ranks[row["scenario"]]
        else:
            row["rank"] = None
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "critical_waypoints.csv", summary)
    write_csv(args.output_dir / "waypoints_by_replica.csv", replica_rows)
    if args.dashboard_assets is not None:
        args.dashboard_assets.mkdir(parents=True, exist_ok=True)
        (args.dashboard_assets / "waypoint_rankings.js").write_text(
            "window.__UAM_WAYPOINT_RANKINGS__ = " + json.dumps(summary, ensure_ascii=False, separators=(",", ":")) + ";\n",
            encoding="utf-8",
        )
    (args.output_dir / "crossing_waypoints.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": crossing_features}, ensure_ascii=False), encoding="utf-8"
    )
    (args.output_dir / "critical_waypoints.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False), encoding="utf-8"
    )
    (args.output_dir / "run_metadata.json").write_text(json.dumps({
        "source_run": selection.run_dir.name if args.config else None,
        "replica_counts": replica_counts,
        "crossing_count": len(crossing_features),
        "uam_reh_crossing_count": len(crossing_features),
        "uam_junction_count": len(junction_features),
        "reh_junction_count": len(reh_junctions),
        "capture_radius_m": args.capture_radius_m,
        "window_seconds": args.window_seconds,
        "workers": args.workers,
        "ranking": "descending mean of per-replica mean hourly throughput",
        "critical_waypoint_definition": [
            "3D overlap of UAM corridor volume and official REH polygon/altitude envelope",
            "planned UAM waypoint or geometric node incident to at least 3 distinct edges",
            "official REH fix incident to at least 3 distinct centerline edges",
        ],
        "altitude_reference": "metres MSL; REH feet converted to metres",
        "junctions_without_complete_altitude": sum(feature["properties"].get("altitude_m") is None for feature in junction_features + reh_junctions),
        "logs": [{"scenario": scenario, "file": path.name} for scenario, path in logs],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Results: {args.output_dir}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
