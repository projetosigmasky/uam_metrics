from __future__ import annotations

import argparse
import json
import shutil
import re
from pathlib import Path
from typing import Any

from src.uam_dashboard.config import DashboardConfig, SAO_PAULO_CENTER
from src.uam_dashboard.exports import conflicts_geojson, heatmap_points, timeline_records, tracks_geojson
from src.uam_dashboard.log_parser import load_state_log
from src.uam_dashboard.metrics import (
    active_aircraft_series,
    build_summary,
    detect_lowc_events,
    efficiency_metrics,
    environment_metrics,
    flight_instance_frame,
)
from src.uam_dashboard.metric_catalog import metric_catalog_payload
from src.uam_dashboard.plots import (
    plot_active_aircraft,
    plot_altitude_histogram,
    plot_route_distance_histogram,
    plot_separation_histogram,
    plot_severity_histogram,
)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_js_bundle(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    path.write_text(f"window.__UAM_DASHBOARD_DATA__ = {serialized};\n", encoding="utf-8")


def copy_static_assets(output_dir: Path) -> None:
    source = Path("web")
    if not source.exists():
        raise FileNotFoundError("Static source folder not found: web")

    for item in source.iterdir():
        destination = output_dir / item.name
        if item.is_dir():
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(item, destination)
        else:
            shutil.copy2(item, destination)


def slugify(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
    return value.strip("._")[:96] or "statelog"


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def average_dashboard(run_dashboards: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(run_dashboards)
    if count == 1:
        return run_dashboards[0]

    return {
        "source_log": f"Media de {count} STATELOGs",
        "map_center": SAO_PAULO_CENTER,
        "summary": {
            "records": int(sum(d["summary"]["records"] for d in run_dashboards)),
            "aircraft_count": mean([d["summary"]["aircraft_count"] for d in run_dashboards]),
            "sim_start_s": mean([d["summary"]["sim_start_s"] for d in run_dashboards]),
            "sim_end_s": mean([d["summary"]["sim_end_s"] for d in run_dashboards]),
            "duration_min": mean([d["summary"]["duration_min"] for d in run_dashboards]),
            "mean_simultaneous_aircraft": mean(
                [d["summary"]["mean_simultaneous_aircraft"] for d in run_dashboards]
            ),
            "peak_simultaneous_aircraft": mean(
                [d["summary"]["peak_simultaneous_aircraft"] for d in run_dashboards]
            ),
            "bounds": {
                "min_lat": min(d["summary"]["bounds"]["min_lat"] for d in run_dashboards),
                "max_lat": max(d["summary"]["bounds"]["max_lat"] for d in run_dashboards),
                "min_lon": min(d["summary"]["bounds"]["min_lon"] for d in run_dashboards),
                "max_lon": max(d["summary"]["bounds"]["max_lon"] for d in run_dashboards),
            },
        },
        "efficiency": {
            "mean_flight_time_min": mean([d["efficiency"]["mean_flight_time_min"] for d in run_dashboards]),
            "median_flight_time_min": mean([d["efficiency"]["median_flight_time_min"] for d in run_dashboards]),
            "p95_flight_time_min": mean([d["efficiency"]["p95_flight_time_min"] for d in run_dashboards]),
            "mean_distance_nm": mean([d["efficiency"]["mean_distance_nm"] for d in run_dashboards]),
            "median_distance_nm": mean([d["efficiency"]["median_distance_nm"] for d in run_dashboards]),
            "p95_distance_nm": mean([d["efficiency"]["p95_distance_nm"] for d in run_dashboards]),
            "total_distance_km": sum(d["efficiency"]["total_distance_km"] for d in run_dashboards),
            "total_flight_hours": sum(d["efficiency"]["total_flight_hours"] for d in run_dashboards),
            "mean_great_circle_distance_nm": mean(
                [d["efficiency"]["mean_great_circle_distance_nm"] for d in run_dashboards]
            ),
            "mean_route_efficiency_pct": mean(
                [d["efficiency"]["mean_route_efficiency_pct"] for d in run_dashboards]
            ),
            "mean_route_extension_pct": mean(
                [d["efficiency"]["mean_route_extension_pct"] for d in run_dashboards]
            ),
            "route_extension_sample_count": int(
                sum(d["efficiency"]["route_extension_sample_count"] for d in run_dashboards)
            ),
            "route_proxy_excluded_count": int(
                sum(d["efficiency"]["route_proxy_excluded_count"] for d in run_dashboards)
            ),
            "route_reference_min_m": run_dashboards[0]["efficiency"]["route_reference_min_m"],
        },
        "environment": {
            "low_altitude_threshold_ft": run_dashboards[0]["environment"]["low_altitude_threshold_ft"],
            "low_altitude_threshold_m": run_dashboards[0]["environment"]["low_altitude_threshold_m"],
            "low_altitude_reference_mode": run_dashboards[0]["environment"]["low_altitude_reference_mode"],
            "low_altitude_reference_samples": run_dashboards[0]["environment"]["low_altitude_reference_samples"],
            "flight_instance_gap_seconds": run_dashboards[0]["environment"]["flight_instance_gap_seconds"],
            "flight_instance_reset_distance_m": run_dashboards[0]["environment"][
                "flight_instance_reset_distance_m"
            ],
            "flight_instance_jump_m": run_dashboards[0]["environment"]["flight_instance_jump_m"],
            "low_altitude_share_pct": mean([d["environment"]["low_altitude_share_pct"] for d in run_dashboards]),
            "mean_altitude_m": mean([d["environment"]["mean_altitude_m"] for d in run_dashboards]),
            "median_altitude_m": mean([d["environment"]["median_altitude_m"] for d in run_dashboards]),
            "mean_altitude_agl_proxy_m": mean(
                [d["environment"]["mean_altitude_agl_proxy_m"] for d in run_dashboards]
            ),
            "median_altitude_agl_proxy_m": mean(
                [d["environment"]["median_altitude_agl_proxy_m"] for d in run_dashboards]
            ),
            "mean_origin_altitude_m": mean([d["environment"]["mean_origin_altitude_m"] for d in run_dashboards]),
            "median_origin_altitude_m": mean(
                [d["environment"]["median_origin_altitude_m"] for d in run_dashboards]
            ),
            "flight_instance_count": mean([d["environment"]["flight_instance_count"] for d in run_dashboards]),
        },
        "safety": {
            "lowc_events": mean([d["safety"]["lowc_events"] for d in run_dashboards]),
            "nmac_events": mean([d["safety"]["nmac_events"] for d in run_dashboards]),
            "lowc_horizontal_m": run_dashboards[0]["safety"]["lowc_horizontal_m"],
            "lowc_vertical_m": run_dashboards[0]["safety"]["lowc_vertical_m"],
            "nmac_horizontal_m": run_dashboards[0]["safety"]["nmac_horizontal_m"],
            "nmac_vertical_m": run_dashboards[0]["safety"]["nmac_vertical_m"],
            "sample_seconds": run_dashboards[0]["safety"]["sample_seconds"],
            "same_altitude_band_m": run_dashboards[0]["safety"]["same_altitude_band_m"],
            "separation_samples": int(sum(d["safety"]["separation_samples"] for d in run_dashboards)),
            "lowc_per_100_operations": mean([d["safety"]["lowc_per_100_operations"] for d in run_dashboards]),
            "lowc_per_flight_hour": mean([d["safety"]["lowc_per_flight_hour"] for d in run_dashboards]),
            "lowc_per_1000_km": mean([d["safety"]["lowc_per_1000_km"] for d in run_dashboards]),
            "nmac_per_100_operations": mean([d["safety"]["nmac_per_100_operations"] for d in run_dashboards]),
            "nmac_per_flight_hour": mean([d["safety"]["nmac_per_flight_hour"] for d in run_dashboards]),
            "nmac_per_1000_km": mean([d["safety"]["nmac_per_1000_km"] for d in run_dashboards]),
            "monitored_pair_samples": int(sum(d["safety"]["monitored_pair_samples"] for d in run_dashboards)),
            "min_severity_ratio": min(d["safety"]["min_severity_ratio"] for d in run_dashboards),
            "p05_severity_ratio": mean([d["safety"]["p05_severity_ratio"] for d in run_dashboards]),
            "median_severity_ratio": mean([d["safety"]["median_severity_ratio"] for d in run_dashboards]),
            "p95_severity_ratio": mean([d["safety"]["p95_severity_ratio"] for d in run_dashboards]),
            "total_time_below_threshold_s": sum(
                d["safety"]["total_time_below_threshold_s"] for d in run_dashboards
            ),
            "mean_time_below_threshold_s": mean(
                [d["safety"]["mean_time_below_threshold_s"] for d in run_dashboards]
            ),
            "max_time_below_threshold_s": max(
                d["safety"]["max_time_below_threshold_s"] for d in run_dashboards
            ),
            "mac_probability_low": run_dashboards[0]["safety"]["mac_probability_low"],
            "mac_probability_nominal": run_dashboards[0]["safety"]["mac_probability_nominal"],
            "mac_probability_high": run_dashboards[0]["safety"]["mac_probability_high"],
            "expected_mac_low": mean([d["safety"]["expected_mac_low"] for d in run_dashboards]),
            "expected_mac_nominal": mean([d["safety"]["expected_mac_nominal"] for d in run_dashboards]),
            "expected_mac_high": mean([d["safety"]["expected_mac_high"] for d in run_dashboards]),
        },
        "charts": run_dashboards[0]["charts"],
        "metric_catalog": metric_catalog_payload(),
    }


def comparison_payload(runs: list[dict[str, Any]], average: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for run in runs:
        d = run["dashboard"]
        rows.append(
            {
                "name": run["name"],
                "records": d["summary"]["records"],
                "aircraft": d["summary"]["aircraft_count"],
                "peak": d["summary"]["peak_simultaneous_aircraft"],
                "duration_min": d["summary"]["duration_min"],
                "flight_time_min": d["efficiency"]["mean_flight_time_min"],
                "distance_nm": d["efficiency"]["mean_distance_nm"],
                "route_efficiency_pct": d["efficiency"]["mean_route_efficiency_pct"],
                "route_extension_pct": d["efficiency"]["mean_route_extension_pct"],
                "low_altitude_pct": d["environment"]["low_altitude_share_pct"],
                "lowc_events": d["safety"]["lowc_events"],
                "nmac_events": d["safety"]["nmac_events"],
                "lowc_per_flight_hour": d["safety"]["lowc_per_flight_hour"],
                "min_severity_ratio": d["safety"]["min_severity_ratio"],
            }
        )

    rows.append(
        {
            "name": "Media",
            "records": average["summary"]["records"],
            "aircraft": average["summary"]["aircraft_count"],
            "peak": average["summary"]["peak_simultaneous_aircraft"],
            "duration_min": average["summary"]["duration_min"],
            "flight_time_min": average["efficiency"]["mean_flight_time_min"],
            "distance_nm": average["efficiency"]["mean_distance_nm"],
            "route_efficiency_pct": average["efficiency"]["mean_route_efficiency_pct"],
            "route_extension_pct": average["efficiency"]["mean_route_extension_pct"],
            "low_altitude_pct": average["environment"]["low_altitude_share_pct"],
            "lowc_events": average["safety"]["lowc_events"],
            "nmac_events": average["safety"]["nmac_events"],
            "lowc_per_flight_hour": average["safety"]["lowc_per_flight_hour"],
            "min_severity_ratio": average["safety"]["min_severity_ratio"],
            "is_average": True,
        }
    )
    return {"run_count": len(runs), "rows": rows}


def analyze_log(log_path: Path, config: DashboardConfig, charts_dir: Path, run_index: int) -> dict[str, Any]:
    chart_prefix = f"{run_index + 1:02d}_{slugify(log_path.stem)}"
    print(f"Loading log: {log_path}")
    df = load_state_log(log_path)

    print("Computing metrics and sampled LoWC events...")
    series = active_aircraft_series(df)
    efficiency = efficiency_metrics(df)
    environment = environment_metrics(
        df,
        config.low_altitude_ft,
        reference_mode=config.low_altitude_reference_mode,
        reference_samples=config.low_altitude_reference_samples,
        instance_gap_seconds=config.flight_instance_gap_seconds,
        instance_reset_distance_m=config.flight_instance_reset_distance_m,
        instance_jump_m=config.flight_instance_jump_m,
    )
    lowc_events, separation_samples, safety = detect_lowc_events(
        df,
        horizontal_threshold_m=config.lowc_horizontal_m,
        vertical_threshold_m=config.lowc_vertical_m,
        nmac_horizontal_threshold_m=config.nmac_horizontal_m,
        nmac_vertical_threshold_m=config.nmac_vertical_m,
        sample_seconds=config.conflict_sample_seconds,
        same_altitude_band_m=config.same_altitude_band_m,
        aircraft_count=int(df["id"].nunique()),
        total_flight_hours=efficiency["total_flight_hours"],
        total_distance_km=efficiency["total_distance_km"],
        mac_probability_bands=config.mac_probability_bands,
    )
    altitude_plot_df = df
    altitude_plot_column = "alt"
    altitude_plot_title = "Distribuicao de altitude"
    altitude_plot_xlabel = "Altitude MSL (m)"
    if config.low_altitude_reference_mode == "origin_agl_proxy":
        altitude_plot_df = flight_instance_frame(
            df,
            gap_seconds=config.flight_instance_gap_seconds,
            reset_distance_m=config.flight_instance_reset_distance_m,
            jump_m=config.flight_instance_jump_m,
            reference_samples=config.low_altitude_reference_samples,
        )
        altitude_plot_column = "alt_agl_proxy_m"
        altitude_plot_title = "Distribuicao de altitude relativa"
        altitude_plot_xlabel = "Altitude acima da origem (m)"

    print("Rendering chart images...")
    chart_paths = {
        "active_aircraft": f"assets/charts/{chart_prefix}_active_aircraft.png",
        "separation_histogram": f"assets/charts/{chart_prefix}_separation_histogram.png",
        "altitude_histogram": f"assets/charts/{chart_prefix}_altitude_histogram.png",
        "distance_histogram": f"assets/charts/{chart_prefix}_distance_histogram.png",
        "severity_histogram": f"assets/charts/{chart_prefix}_severity_histogram.png",
    }
    plot_active_aircraft(series, charts_dir / Path(chart_paths["active_aircraft"]).name)
    plot_separation_histogram(
        separation_samples,
        config.lowc_horizontal_m,
        charts_dir / Path(chart_paths["separation_histogram"]).name,
    )
    plot_altitude_histogram(
        altitude_plot_df,
        config.low_altitude_ft * 0.3048,
        charts_dir / Path(chart_paths["altitude_histogram"]).name,
        altitude_column=altitude_plot_column,
        title=altitude_plot_title,
        xlabel=altitude_plot_xlabel,
    )
    plot_route_distance_histogram(df, charts_dir / Path(chart_paths["distance_histogram"]).name)
    plot_severity_histogram(lowc_events, charts_dir / Path(chart_paths["severity_histogram"]).name)

    summary = build_summary(df)
    dashboard = {
        "source_log": log_path.name,
        "map_center": SAO_PAULO_CENTER,
        "summary": summary,
        "efficiency": efficiency,
        "environment": environment,
        "safety": safety,
        "charts": chart_paths,
        "metric_catalog": metric_catalog_payload(),
    }

    return {
        "id": chart_prefix,
        "name": log_path.name,
        "dashboard": dashboard,
        "tracks": tracks_geojson(df, config.track_sample_stride),
        "conflicts": conflicts_geojson(lowc_events),
        "heatmap": heatmap_points(df, config.heatmap_sample_stride),
        "timeline": timeline_records(series),
    }


def build_dashboard(config: DashboardConfig) -> None:
    output_dir = config.output_dir
    print("Copying HTML/CSS/JS...")
    copy_static_assets(output_dir)

    charts_dir = output_dir / "assets" / "charts"
    data_dir = output_dir / "assets" / "data"
    charts_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    runs = [analyze_log(log_path, config, charts_dir, index) for index, log_path in enumerate(config.log_paths)]
    dashboard = average_dashboard([run["dashboard"] for run in runs])
    comparison = comparison_payload(runs, dashboard)
    primary = runs[0]

    print("Writing static data files...")
    write_json(data_dir / "dashboard.json", dashboard)
    write_json(data_dir / "comparison.json", comparison)
    write_json(data_dir / "tracks.geojson", primary["tracks"])
    write_json(data_dir / "conflicts.geojson", primary["conflicts"])
    write_json(data_dir / "heatmap_points.json", primary["heatmap"])
    write_json(data_dir / "timeline.json", primary["timeline"])
    runs_dir = data_dir / "runs"
    for run in runs:
        write_json(runs_dir / f"{run['id']}.json", run)

    write_js_bundle(
        output_dir / "assets" / "data_bundle.js",
        {
            "dashboard": dashboard,
            "tracks": primary["tracks"],
            "conflicts": primary["conflicts"],
            "heatmap": primary["heatmap"],
            "timeline": primary["timeline"],
            "runs": runs,
            "comparison": comparison,
            "metric_catalog": metric_catalog_payload(),
        },
    )

    print(f"Dashboard ready at: {output_dir / 'index.html'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a static UAM KPI/KPA dashboard.")
    parser.add_argument("logs", nargs="*", default=None, help="One or more STATELOG files.")
    parser.add_argument("--output", default="docs", help="Output folder for GitHub Pages.")
    parser.add_argument("--data-dir", default="data", help="Folder searched when no log is passed.")
    parser.add_argument("--low-altitude-ft", type=float, default=1500.0)
    parser.add_argument("--low-altitude-reference-mode", choices=["origin_agl_proxy", "msl"], default="origin_agl_proxy")
    parser.add_argument("--low-altitude-reference-samples", type=int, default=5)
    parser.add_argument("--flight-instance-gap-seconds", type=float, default=300.0)
    parser.add_argument("--flight-instance-reset-distance-m", type=float, default=250.0)
    parser.add_argument("--flight-instance-jump-m", type=float, default=5000.0)
    parser.add_argument("--lowc-horizontal-m", type=float, default=500.0)
    parser.add_argument("--lowc-vertical-m", type=float, default=30.0)
    parser.add_argument("--nmac-horizontal-m", type=float, default=150.0)
    parser.add_argument("--nmac-vertical-m", type=float, default=30.0)
    parser.add_argument("--conflict-sample-seconds", type=int, default=10)
    return parser.parse_args()


def find_default_logs(data_dir: Path) -> tuple[Path, ...]:
    logs = sorted(data_dir.glob("STATELOG*.log"))
    if not logs:
        logs = sorted(Path(".").glob("STATELOG*.log"))
    if not logs:
        raise FileNotFoundError("No STATELOG*.log file found. Pass the log path explicitly.")
    return tuple(logs)


def main() -> None:
    args = parse_args()
    data_dir = Path(args.data_dir)
    log_paths = tuple(Path(log) for log in args.logs) if args.logs else find_default_logs(data_dir)
    config = DashboardConfig(
        log_paths=log_paths,
        output_dir=Path(args.output),
        data_dir=data_dir,
        low_altitude_ft=args.low_altitude_ft,
        low_altitude_reference_mode=args.low_altitude_reference_mode,
        low_altitude_reference_samples=args.low_altitude_reference_samples,
        flight_instance_gap_seconds=args.flight_instance_gap_seconds,
        flight_instance_reset_distance_m=args.flight_instance_reset_distance_m,
        flight_instance_jump_m=args.flight_instance_jump_m,
        lowc_horizontal_m=args.lowc_horizontal_m,
        lowc_vertical_m=args.lowc_vertical_m,
        nmac_horizontal_m=args.nmac_horizontal_m,
        nmac_vertical_m=args.nmac_vertical_m,
        conflict_sample_seconds=args.conflict_sample_seconds,
    )
    build_dashboard(config)


if __name__ == "__main__":
    main()
