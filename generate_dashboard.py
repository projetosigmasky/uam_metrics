from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from src.uam_dashboard.config import DashboardConfig, SAO_PAULO_CENTER
from src.uam_dashboard.exports import conflicts_geojson, heatmap_points, timeline_records, tracks_geojson
from src.uam_dashboard.log_parser import load_state_log
from src.uam_dashboard.metrics import (
    active_aircraft_series,
    build_summary,
    detect_lowc_events,
    efficiency_metrics,
    environment_metrics,
)
from src.uam_dashboard.plots import (
    plot_active_aircraft,
    plot_altitude_histogram,
    plot_route_distance_histogram,
    plot_separation_histogram,
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


def build_dashboard(config: DashboardConfig) -> None:
    output_dir = config.output_dir
    print("Copying HTML/CSS/JS...")
    copy_static_assets(output_dir)

    charts_dir = output_dir / "assets" / "charts"
    data_dir = output_dir / "assets" / "data"
    charts_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading log: {config.log_path}")
    df = load_state_log(config.log_path)

    print("Computing metrics and sampled LoWC events...")
    series = active_aircraft_series(df)
    lowc_events, separation_samples = detect_lowc_events(
        df,
        horizontal_threshold_m=config.lowc_horizontal_m,
        vertical_threshold_m=config.lowc_vertical_m,
        sample_seconds=config.conflict_sample_seconds,
        same_altitude_band_m=config.same_altitude_band_m,
    )

    print("Rendering chart images...")
    plot_active_aircraft(series, charts_dir / "active_aircraft.png")
    plot_separation_histogram(separation_samples, config.lowc_horizontal_m, charts_dir / "separation_histogram.png")
    plot_altitude_histogram(df, config.low_altitude_ft * 0.3048, charts_dir / "altitude_histogram.png")
    plot_route_distance_histogram(df, charts_dir / "distance_histogram.png")

    print("Writing static data files...")
    summary = build_summary(df)
    tracks = tracks_geojson(df, config.track_sample_stride)
    conflicts = conflicts_geojson(lowc_events)
    heatmap = heatmap_points(df, config.heatmap_sample_stride)
    timeline = timeline_records(series)
    dashboard = {
        "source_log": config.log_path.name,
        "map_center": SAO_PAULO_CENTER,
        "summary": summary,
        "efficiency": efficiency_metrics(df),
        "environment": environment_metrics(df, config.low_altitude_ft),
        "safety": {
            "lowc_events": int(len(lowc_events)),
            "lowc_horizontal_m": float(config.lowc_horizontal_m),
            "lowc_vertical_m": float(config.lowc_vertical_m),
            "sample_seconds": int(config.conflict_sample_seconds),
            "separation_samples": int(len(separation_samples)),
        },
        "charts": {
            "active_aircraft": "assets/charts/active_aircraft.png",
            "separation_histogram": "assets/charts/separation_histogram.png",
            "altitude_histogram": "assets/charts/altitude_histogram.png",
            "distance_histogram": "assets/charts/distance_histogram.png",
        },
    }
    write_json(data_dir / "dashboard.json", dashboard)
    write_json(data_dir / "tracks.geojson", tracks)
    write_json(data_dir / "conflicts.geojson", conflicts)
    write_json(data_dir / "heatmap_points.json", heatmap)
    write_json(data_dir / "timeline.json", timeline)
    write_js_bundle(
        output_dir / "assets" / "data_bundle.js",
        {
            "dashboard": dashboard,
            "tracks": tracks,
            "conflicts": conflicts,
            "heatmap": heatmap,
            "timeline": timeline,
        },
    )

    print(f"Dashboard ready at: {output_dir / 'index.html'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a static UAM KPI/KPA dashboard.")
    parser.add_argument("log", nargs="?", default=None, help="Path to a STATELOG file.")
    parser.add_argument("--output", default="docs", help="Output folder for GitHub Pages.")
    parser.add_argument("--low-altitude-ft", type=float, default=1500.0)
    parser.add_argument("--lowc-horizontal-m", type=float, default=500.0)
    parser.add_argument("--lowc-vertical-m", type=float, default=30.0)
    parser.add_argument("--conflict-sample-seconds", type=int, default=10)
    return parser.parse_args()


def find_default_log() -> Path:
    logs = sorted(Path("data").glob("STATELOG*.log"))
    if not logs:
        logs = sorted(Path(".").glob("STATELOG*.log"))
    if not logs:
        raise FileNotFoundError("No STATELOG*.log file found. Pass the log path explicitly.")
    return logs[-1]


def main() -> None:
    args = parse_args()
    log_path = Path(args.log) if args.log else find_default_log()
    config = DashboardConfig(
        log_path=log_path,
        output_dir=Path(args.output),
        low_altitude_ft=args.low_altitude_ft,
        lowc_horizontal_m=args.lowc_horizontal_m,
        lowc_vertical_m=args.lowc_vertical_m,
        conflict_sample_seconds=args.conflict_sample_seconds,
    )
    build_dashboard(config)


if __name__ == "__main__":
    main()
