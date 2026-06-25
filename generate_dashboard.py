from __future__ import annotations

import argparse
import json
import shutil
import re
from pathlib import Path
from typing import Any

from src.uam_dashboard.capacity import capacity_metrics
from src.uam_dashboard.config import DashboardConfig, SAO_PAULO_CENTER
from src.uam_dashboard.experiment import experiment_metadata, experiment_sort_key
from src.uam_dashboard.exports import conflicts_geojson, heatmap_points, planned_routes_geojson, tracks_geojson
from src.uam_dashboard.log_parser import load_state_log
from src.uam_dashboard.metrics import (
    active_aircraft_series,
    airborne_delay_metrics,
    build_summary,
    detect_lowc_events,
    efficiency_metrics,
    total_delay_metrics,
    trajectory_conformity,
)
from src.uam_dashboard.metric_catalog import metric_catalog_payload
from src.uam_dashboard.plots import (
    plot_active_aircraft,
    plot_altitude_histogram,
    plot_route_distance_histogram,
    plot_separation_histogram,
    plot_severity_histogram,
    plot_trajectory_conformity,
)
from src.uam_dashboard.scenario_parser import ground_delay_metrics, load_bluesky_scenario


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
            "mean_horizontal_inefficiency_pct": mean(
                [d["efficiency"]["mean_horizontal_inefficiency_pct"] for d in run_dashboards]
            ),
            "trajectory_conformity": _average_conformity(run_dashboards),
            "ground_delay": _average_ground_delay(run_dashboards),
            "airborne_delay": _average_airborne_delay(run_dashboards),
            "total_delay": _average_total_delay(run_dashboards),
        },
        "capacity": _average_capacity(run_dashboards),
        "safety": {
            "lowc_events": mean([d["safety"]["lowc_events"] for d in run_dashboards]),
            "nmac_events": mean([d["safety"]["nmac_events"] for d in run_dashboards]),
            "lowc_horizontal_m": run_dashboards[0]["safety"]["lowc_horizontal_m"],
            "nmac_horizontal_m": run_dashboards[0]["safety"]["nmac_horizontal_m"],
            "sample_seconds": run_dashboards[0]["safety"]["sample_seconds"],
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
            "mac_beta": run_dashboards[0]["safety"]["mac_beta"],
            "mac_probability_given_nmac": run_dashboards[0]["safety"]["mac_probability_given_nmac"],
            "expected_mac": mean([d["safety"]["expected_mac"] for d in run_dashboards]),
            "expected_mac_rate_per_flight_hour": mean(
                [d["safety"]["expected_mac_rate_per_flight_hour"] for d in run_dashboards]
            ),
            "expected_mac_per_100k_flight_hours": mean(
                [d["safety"]["expected_mac_per_100k_flight_hours"] for d in run_dashboards]
            ),
            "tls_target_per_flight_hour": run_dashboards[0]["safety"]["tls_target_per_flight_hour"],
            "tls_epsilon": run_dashboards[0]["safety"]["tls_epsilon"],
            "tls_margin": mean([d["safety"]["tls_margin"] for d in run_dashboards]),
            "tls_compliant": all(d["safety"]["tls_compliant"] for d in run_dashboards),
        },
        "charts": run_dashboards[0]["charts"],
        "metric_catalog": metric_catalog_payload(),
    }


def _average_conformity(run_dashboards: list[dict[str, Any]]) -> dict[str, Any]:
    conformities = [
        dashboard["efficiency"]["trajectory_conformity"]
        for dashboard in run_dashboards
        if dashboard["efficiency"].get("trajectory_conformity", {}).get("available")
    ]
    if not conformities:
        return {"available": False}
    return {
        "available": True,
        "tolerance_m": conformities[0]["tolerance_m"],
        "planned_instances": int(sum(item["planned_instances"] for item in conformities)),
        "matched_instances": int(sum(item["matched_instances"] for item in conformities)),
        "spatial_adherence_pct": mean([item["spatial_adherence_pct"] for item in conformities]),
        "mean_deviation_m": mean([item["mean_deviation_m"] for item in conformities]),
        "p95_deviation_m": mean([item["p95_deviation_m"] for item in conformities]),
        "max_deviation_m": max(item["max_deviation_m"] for item in conformities),
        "mean_trajectory_conformity_ratio": mean(
            [item["mean_trajectory_conformity_ratio"] for item in conformities]
        ),
        "median_trajectory_conformity_ratio": mean(
            [item["median_trajectory_conformity_ratio"] for item in conformities]
        ),
        "p95_trajectory_conformity_ratio": mean(
            [item["p95_trajectory_conformity_ratio"] for item in conformities]
        ),
        "mean_additional_distance_m": mean(
            [item["mean_additional_distance_m"] for item in conformities]
        ),
        "total_additional_distance_m": sum(
            item["total_additional_distance_m"] for item in conformities
        ),
        "mean_planned_horizontal_inefficiency_ratio": mean(
            [item["mean_planned_horizontal_inefficiency_ratio"] for item in conformities]
        ),
        "mean_executed_horizontal_inefficiency_ratio": mean(
            [item["mean_executed_horizontal_inefficiency_ratio"] for item in conformities]
        ),
        "executed_samples": int(sum(item["executed_samples"] for item in conformities)),
    }


def _average_ground_delay(run_dashboards: list[dict[str, Any]]) -> dict[str, Any]:
    values = [
        dashboard["efficiency"]["ground_delay"]
        for dashboard in run_dashboards
        if dashboard["efficiency"].get("ground_delay", {}).get("available")
    ]
    if not values:
        return {"available": False}
    return {
        "available": True,
        "matched_flights": int(sum(item["matched_flights"] for item in values)),
        "mean_ground_delay_s": mean([item["mean_ground_delay_s"] for item in values]),
        "median_ground_delay_s": mean([item["median_ground_delay_s"] for item in values]),
        "p95_ground_delay_s": mean([item["p95_ground_delay_s"] for item in values]),
        "max_ground_delay_s": max(item["max_ground_delay_s"] for item in values),
    }


def _average_airborne_delay(run_dashboards: list[dict[str, Any]]) -> dict[str, Any]:
    values = [
        dashboard["efficiency"]["airborne_delay"]
        for dashboard in run_dashboards
        if dashboard["efficiency"].get("airborne_delay", {}).get("available")
    ]
    if not values:
        return {"available": False}
    return {
        "available": True,
        "matched_flights": int(sum(item["matched_flights"] for item in values)),
        "mean_airborne_delay_s": mean([item["mean_airborne_delay_s"] for item in values]),
        "median_airborne_delay_s": mean([item["median_airborne_delay_s"] for item in values]),
        "p95_airborne_delay_s": mean([item["p95_airborne_delay_s"] for item in values]),
        "max_airborne_delay_s": max(item["max_airborne_delay_s"] for item in values),
        "total_airborne_delay_s": sum(item["total_airborne_delay_s"] for item in values),
    }


def _average_total_delay(run_dashboards: list[dict[str, Any]]) -> dict[str, Any]:
    values = [
        dashboard["efficiency"]["total_delay"]
        for dashboard in run_dashboards
        if dashboard["efficiency"].get("total_delay", {}).get("available")
    ]
    if not values:
        return {"available": False}
    return {
        "available": True,
        "mean_total_delay_s": mean([item["mean_total_delay_s"] for item in values]),
        "mean_ground_component_s": mean([item["mean_ground_component_s"] for item in values]),
        "mean_airborne_component_s": mean([item["mean_airborne_component_s"] for item in values]),
        "ground_available": all(item["ground_available"] for item in values),
        "airborne_available": all(item["airborne_available"] for item in values),
    }


def _average_capacity(run_dashboards: list[dict[str, Any]]) -> dict[str, Any]:
    capacities = [
        dashboard.get("capacity", {})
        for dashboard in run_dashboards
        if dashboard.get("capacity", {}).get("available")
    ]
    if not capacities:
        return {"available": False}
    density_values = [item["density"] for item in capacities if item.get("density", {}).get("available")]
    complexity_values = [
        item["complexity"] for item in capacities if item.get("complexity", {}).get("available")
    ]
    first = capacities[0]
    return {
        "available": True,
        "window_seconds": first["window_seconds"],
        "capacity_percentile": first["capacity_percentile"],
        "corridor_width_m": first["corridor_width_m"],
        "density": {
            "available": bool(density_values),
            "corridor_area_km2": mean([item["corridor_area_km2"] for item in density_values]),
            "mean_simultaneous_aircraft": mean(
                [item["mean_simultaneous_aircraft"] for item in density_values]
            ),
            "peak_simultaneous_aircraft": max(
                [item["peak_simultaneous_aircraft"] for item in density_values], default=0
            ),
            "air_traffic_density_per_km2": mean(
                [item["air_traffic_density_per_km2"] for item in density_values]
            ),
            "hotspot_density_per_km2": mean([item["hotspot_density_per_km2"] for item in density_values]),
        },
        "throughput": first["throughput"],
        "complexity": {
            "available": bool(complexity_values),
            "planned_route_count": mean([item["planned_route_count"] for item in complexity_values]),
            "planned_waypoint_count": mean([item["planned_waypoint_count"] for item in complexity_values]),
            "planned_route_crossings": mean([item["planned_route_crossings"] for item in complexity_values]),
            "trajectory_group_count": mean([item["trajectory_group_count"] for item in complexity_values]),
            "repeated_trajectory_group_count": mean(
                [item["repeated_trajectory_group_count"] for item in complexity_values]
            ),
            "lowc_event_count": mean([item["lowc_event_count"] for item in complexity_values]),
        },
    }


def comparison_payload(runs: list[dict[str, Any]], average: dict[str, Any]) -> dict[str, Any]:
    by_day: dict[str, list[dict[str, Any]]] = {}
    for index, run in enumerate(runs):
        d = run["dashboard"]
        metadata = run["metadata"]
        row = {
            "run_index": index,
            **metadata,
            "name": run["name"],
            "aircraft": d["summary"]["aircraft_count"],
            "peak": d["summary"]["peak_simultaneous_aircraft"],
            "flight_time_min": d["efficiency"]["mean_flight_time_min"],
            "distance_nm": d["efficiency"]["mean_distance_nm"],
            "horizontal_inefficiency_pct": d["efficiency"]["mean_horizontal_inefficiency_pct"],
            "trajectory_conformity_pct": (
                d["efficiency"]["trajectory_conformity"].get("mean_trajectory_conformity_ratio", 0.0)
                * 100.0
            ),
            "spatial_adherence_pct": d["efficiency"]["trajectory_conformity"].get("spatial_adherence_pct"),
            "ground_delay_s": d["efficiency"]["ground_delay"].get("mean_ground_delay_s"),
            "airborne_delay_s": d["efficiency"]["airborne_delay"].get("mean_airborne_delay_s"),
            "total_delay_s": d["efficiency"]["total_delay"].get("mean_total_delay_s"),
            "lowc_events": d["safety"]["lowc_events"],
            "nmac_events": d["safety"]["nmac_events"],
            "expected_mac": d["safety"]["expected_mac"],
            "expected_mac_rate_per_flight_hour": d["safety"]["expected_mac_rate_per_flight_hour"],
            "expected_mac_per_100k_flight_hours": d["safety"]["expected_mac_per_100k_flight_hours"],
            "tls_margin": d["safety"]["tls_margin"],
            "tls_compliant": d["safety"]["tls_compliant"],
            "lowc_per_flight_hour": d["safety"]["lowc_per_flight_hour"],
            "lowc_per_100_operations": d["safety"]["lowc_per_100_operations"],
            "min_severity_ratio": d["safety"]["min_severity_ratio"],
        }
        by_day.setdefault(metadata["day_key"], []).append(row)

    days = []
    variant_order = {"disturbed_mvp": 0, "disturbed_off": 1, "nominal_mvp": 2, "nominal_off": 3}
    for rows in by_day.values():
        rows.sort(key=lambda row: variant_order.get(row["variant_key"], 99))
        risk_reference = next(
            (row for row in rows if row["mvp_enabled"] is False and row["disturbed"] is False),
            None,
        )
        off_references = {
            row["disturbed"]: row
            for row in rows
            if row["mvp_enabled"] is False
        }
        for row in rows:
            row["risk_ratio_vs_reference"] = _ratio_or_none(
                row["expected_mac_per_100k_flight_hours"],
                risk_reference["expected_mac_per_100k_flight_hours"] if risk_reference else None,
            )
            reference = off_references.get(row["disturbed"])
            row["flight_time_delta_vs_off_min"] = _difference_or_none(
                row["flight_time_min"],
                reference["flight_time_min"] if reference else None,
            )
            row["distance_delta_vs_off_nm"] = _difference_or_none(
                row["distance_nm"],
                reference["distance_nm"] if reference else None,
            )
        days.append({"day_key": rows[0]["day_key"], "day_label": rows[0]["day_label"], "rows": rows})

    days.sort(key=lambda day: min(row["rank"] or 999 for row in day["rows"]))
    return {"run_count": len(runs), "day_count": len(days), "days": days}


def _ratio_or_none(value: float | None, reference: float | None) -> float | None:
    if value is None or reference is None or reference <= 0:
        return None
    return float(value / reference)


def _difference_or_none(value: float | None, reference: float | None) -> float | None:
    if value is None or reference is None:
        return None
    return float(value - reference)


def analyze_log(log_path: Path, config: DashboardConfig, charts_dir: Path, run_index: int) -> dict[str, Any]:
    chart_prefix = f"{run_index + 1:02d}_{slugify(log_path.stem)}"
    print(f"Loading log: {log_path}")
    df = load_state_log(log_path)

    print("Computing metrics and sampled LoWC events...")
    series = active_aircraft_series(df)
    efficiency = efficiency_metrics(
        df,
        gap_seconds=config.flight_instance_gap_seconds,
        reset_distance_m=config.flight_instance_reset_distance_m,
        jump_m=config.flight_instance_jump_m,
    )
    scenario_path = find_matching_scenario(log_path, config.scenario_paths)
    planned_flights = load_bluesky_scenario(scenario_path) if scenario_path else []
    metadata = experiment_metadata(log_path)
    nominal_scenario = find_nominal_scenario(metadata, config.scenario_paths)
    nominal_flights = load_bluesky_scenario(nominal_scenario) if nominal_scenario else None
    efficiency["ground_delay"] = ground_delay_metrics(planned_flights, nominal_flights)
    reference_log_path = find_reference_off_log(metadata, config.log_paths)
    reference_df = load_state_log(reference_log_path) if reference_log_path else None
    efficiency["airborne_delay"] = airborne_delay_metrics(
        df,
        reference_df,
        gap_seconds=config.flight_instance_gap_seconds,
        reset_distance_m=config.flight_instance_reset_distance_m,
        jump_m=config.flight_instance_jump_m,
    )
    efficiency["total_delay"] = total_delay_metrics(
        efficiency["ground_delay"],
        efficiency["airborne_delay"],
    )
    conformity, conformity_by_instance = trajectory_conformity(
        df,
        planned_flights,
        tolerance_m=config.conformity_tolerance_m,
        gap_seconds=config.flight_instance_gap_seconds,
        reset_distance_m=config.flight_instance_reset_distance_m,
        jump_m=config.flight_instance_jump_m,
    )
    efficiency["trajectory_conformity"] = conformity
    lowc_events, separation_samples, safety = detect_lowc_events(
        df,
        horizontal_threshold_m=config.lowc_horizontal_m,
        nmac_horizontal_threshold_m=config.nmac_horizontal_m,
        sample_seconds=config.conflict_sample_seconds,
        aircraft_count=int(df["id"].nunique()),
        total_flight_hours=efficiency["total_flight_hours"],
        total_distance_km=efficiency["total_distance_km"],
        mac_beta=config.mac_beta,
        mac_probability_given_nmac=config.mac_probability_given_nmac,
        tls_target_per_flight_hour=config.tls_target_per_flight_hour,
        tls_epsilon=config.tls_epsilon,
    )

    print("Rendering chart images...")
    chart_paths = {
        "active_aircraft": f"assets/charts/{chart_prefix}_active_aircraft.png",
        "separation_histogram": f"assets/charts/{chart_prefix}_separation_histogram.png",
        "altitude_histogram": f"assets/charts/{chart_prefix}_altitude_histogram.png",
        "distance_histogram": f"assets/charts/{chart_prefix}_distance_histogram.png",
        "severity_histogram": f"assets/charts/{chart_prefix}_severity_histogram.png",
        "trajectory_conformity": f"assets/charts/{chart_prefix}_trajectory_conformity.png",
    }
    plot_active_aircraft(series, charts_dir / Path(chart_paths["active_aircraft"]).name)
    plot_separation_histogram(
        separation_samples,
        config.lowc_horizontal_m,
        charts_dir / Path(chart_paths["separation_histogram"]).name,
    )
    plot_altitude_histogram(
        df,
        None,
        charts_dir / Path(chart_paths["altitude_histogram"]).name,
        title="Distribuicao de altitude",
        xlabel="Altitude MSL (m)",
    )
    plot_route_distance_histogram(df, charts_dir / Path(chart_paths["distance_histogram"]).name)
    plot_severity_histogram(lowc_events, charts_dir / Path(chart_paths["severity_histogram"]).name)
    plot_trajectory_conformity(
        conformity_by_instance,
        charts_dir / Path(chart_paths["trajectory_conformity"]).name,
    )
    tracks = tracks_geojson(
        df,
        config.track_sample_stride,
        instance_gap_seconds=config.flight_instance_gap_seconds,
        instance_reset_distance_m=config.flight_instance_reset_distance_m,
        instance_jump_m=config.flight_instance_jump_m,
        shape_points=config.trajectory_shape_points,
        cluster_distance_m=config.trajectory_cluster_distance_m,
        endpoint_tolerance_m=config.trajectory_endpoint_tolerance_m,
        conformity_by_instance=conformity_by_instance,
    )
    planned_routes = planned_routes_geojson(
        planned_flights,
        conformity_by_instance,
        config.conformity_tolerance_m,
    )
    capacity = capacity_metrics(
        df,
        planned_flights,
        tracks,
        conformity_by_instance,
        lowc_event_count=len(lowc_events),
        corridor_width_m=config.conformity_tolerance_m,
        window_seconds=config.capacity_window_seconds,
        capacity_percentile=config.capacity_reference_percentile,
        gap_seconds=config.flight_instance_gap_seconds,
        reset_distance_m=config.flight_instance_reset_distance_m,
        jump_m=config.flight_instance_jump_m,
    )

    summary = build_summary(df)
    dashboard = {
        "source_log": log_path.name,
        "metadata": metadata,
        "map_center": SAO_PAULO_CENTER,
        "summary": summary,
        "efficiency": efficiency,
        "safety": safety,
        "capacity": capacity,
        "charts": chart_paths,
        "metric_catalog": metric_catalog_payload(),
    }

    return {
        "id": chart_prefix,
        "name": log_path.name,
        "metadata": metadata,
        "dashboard": dashboard,
        "tracks": tracks,
        "planned_routes": planned_routes,
        "conflicts": conflicts_geojson(lowc_events),
        "heatmap": heatmap_points(df, config.heatmap_sample_stride),
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
    write_json(data_dir / "planned_routes.geojson", primary["planned_routes"])
    write_json(data_dir / "conflicts.geojson", primary["conflicts"])
    write_json(data_dir / "heatmap_points.json", primary["heatmap"])
    runs_dir = data_dir / "runs"
    for run in runs:
        write_json(runs_dir / f"{run['id']}.json", run)

    write_js_bundle(
        output_dir / "assets" / "data_bundle.js",
        {
            "dashboard": dashboard,
            "tracks": primary["tracks"],
            "planned_routes": primary["planned_routes"],
            "conflicts": primary["conflicts"],
            "heatmap": primary["heatmap"],
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
    parser.add_argument("--scenario-dir", default="data/scenarios", help="Folder searched for BlueSky SCN files.")
    parser.add_argument("--scenarios", nargs="*", default=None, help="BlueSky SCN files used as planned routes.")
    parser.add_argument("--flight-instance-gap-seconds", type=float, default=300.0)
    parser.add_argument("--flight-instance-reset-distance-m", type=float, default=250.0)
    parser.add_argument("--flight-instance-jump-m", type=float, default=5000.0)
    parser.add_argument("--lowc-horizontal-m", type=float, default=500.0)
    parser.add_argument("--nmac-horizontal-m", type=float, default=150.0)
    parser.add_argument("--mac-beta", type=float, default=5.038e-3)
    parser.add_argument("--mac-probability-given-nmac", type=float, default=0.005)
    parser.add_argument("--tls-target-per-flight-hour", type=float, default=9.4e-6)
    parser.add_argument("--tls-epsilon", type=float, default=1e-15)
    parser.add_argument("--conflict-sample-seconds", type=int, default=10)
    parser.add_argument("--trajectory-shape-points", type=int, default=12)
    parser.add_argument("--trajectory-cluster-distance-m", type=float, default=1200.0)
    parser.add_argument("--trajectory-endpoint-tolerance-m", type=float, default=2500.0)
    parser.add_argument("--conformity-tolerance-m", type=float, default=250.0)
    parser.add_argument("--capacity-window-seconds", type=int, default=3600)
    parser.add_argument("--capacity-reference-percentile", type=float, default=0.95)
    return parser.parse_args()


def find_default_logs(data_dir: Path) -> tuple[Path, ...]:
    logs = sorted(data_dir.glob("logs/*.log"), key=experiment_sort_key)
    if not logs:
        logs = sorted(data_dir.glob("STATELOG*.log"))
    if not logs:
        logs = sorted(Path(".").glob("STATELOG*.log"))
    if not logs:
        raise FileNotFoundError("No STATELOG*.log file found. Pass the log path explicitly.")
    return tuple(logs)


def find_scenarios(scenario_dir: Path, explicit: list[str] | None) -> tuple[Path, ...]:
    if explicit:
        return tuple(Path(path) for path in explicit)
    return tuple(sorted(scenario_dir.glob("*.scn"))) if scenario_dir.exists() else ()


def find_matching_scenario(log_path: Path, scenario_paths: tuple[Path, ...]) -> Path | None:
    log_stem = log_path.stem.lower()
    matches = [path for path in scenario_paths if path.stem.lower() in log_stem]
    return max(matches, key=lambda path: len(path.stem)) if matches else None


def find_nominal_scenario(metadata: dict[str, Any], scenario_paths: tuple[Path, ...]) -> Path | None:
    if not metadata.get("disturbed"):
        return find(
            scenario_paths,
            lambda path: experiment_metadata(path)["day_key"] == metadata["day_key"]
            and experiment_metadata(path)["mvp_enabled"] == metadata["mvp_enabled"]
            and experiment_metadata(path)["disturbed"] is False,
        )
    return find(
        scenario_paths,
        lambda path: experiment_metadata(path)["day_key"] == metadata["day_key"]
        and experiment_metadata(path)["mvp_enabled"] == metadata["mvp_enabled"]
        and experiment_metadata(path)["disturbed"] is False,
    )


def find_reference_off_log(metadata: dict[str, Any], log_paths: tuple[Path, ...]) -> Path | None:
    if metadata.get("day_key") is None or metadata.get("disturbed") is None:
        return None
    return find(
        log_paths,
        lambda path: experiment_metadata(path)["day_key"] == metadata["day_key"]
        and experiment_metadata(path)["mvp_enabled"] is False
        and experiment_metadata(path)["disturbed"] == metadata["disturbed"],
    )


def find(paths: tuple[Path, ...], predicate: Any) -> Path | None:
    return next((path for path in paths if predicate(path)), None)


def main() -> None:
    args = parse_args()
    data_dir = Path(args.data_dir)
    log_paths = tuple(Path(log) for log in args.logs) if args.logs else find_default_logs(data_dir)
    scenario_paths = find_scenarios(Path(args.scenario_dir), args.scenarios)
    config = DashboardConfig(
        log_paths=log_paths,
        scenario_paths=scenario_paths,
        output_dir=Path(args.output),
        data_dir=data_dir,
        flight_instance_gap_seconds=args.flight_instance_gap_seconds,
        flight_instance_reset_distance_m=args.flight_instance_reset_distance_m,
        flight_instance_jump_m=args.flight_instance_jump_m,
        lowc_horizontal_m=args.lowc_horizontal_m,
        nmac_horizontal_m=args.nmac_horizontal_m,
        mac_beta=args.mac_beta,
        mac_probability_given_nmac=args.mac_probability_given_nmac,
        tls_target_per_flight_hour=args.tls_target_per_flight_hour,
        tls_epsilon=args.tls_epsilon,
        conflict_sample_seconds=args.conflict_sample_seconds,
        trajectory_shape_points=args.trajectory_shape_points,
        trajectory_cluster_distance_m=args.trajectory_cluster_distance_m,
        trajectory_endpoint_tolerance_m=args.trajectory_endpoint_tolerance_m,
        conformity_tolerance_m=args.conformity_tolerance_m,
        capacity_window_seconds=args.capacity_window_seconds,
        capacity_reference_percentile=args.capacity_reference_percentile,
    )
    build_dashboard(config)


if __name__ == "__main__":
    main()
