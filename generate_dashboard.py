from __future__ import annotations

import argparse
import copy
import json
import shutil
import re
import math
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from src.uam_dashboard.capacity import capacity_metrics
from src.uam_dashboard.aggregation import average_resource_group
from src.uam_dashboard.replica_analysis import summarize_replica, aggregate_summaries, stability_payload, plot_aggregates, metric_value, metric_audit, KPI_PATHS, SCHEMA_VERSION
from src.uam_dashboard.config import DEFAULT_REH_XML_PATH, DashboardConfig, SAO_PAULO_CENTER
from src.uam_dashboard.experiment import experiment_metadata, experiment_sort_key, log_experiment_metadata, matching_scenario
from src.uam_dashboard.exports import (
    conflicts_geojson,
    heatmap_points,
    density_grid,
    merge_density_grids,
    planned_routes_geojson,
    trajectory_3d_payload,
    tracks_geojson,
)
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
from src.uam_dashboard.metric_catalog import SOURCE_VERSION, metric_catalog_payload, write_metric_catalog_asset
from src.uam_dashboard.reh_parser import load_reh_network
from src.uam_dashboard.run_config import load_run_selection
from src.uam_dashboard.scenario_parser import (
    annotate_aircraft_metadata,
    load_bluesky_scenario,
)
from src.uam_dashboard.topology import write_candidate_node_assets
from src.uam_dashboard.topology import candidate_node_collection
from src.uam_dashboard.corridor_geometry import uam_geometry
from src.uam_dashboard.named_waypoints import source_record
from src.uam_dashboard.named_waypoints import uam_selection_inventory
from generate_crossing_waypoints import write_crossing_waypoint_asset
from generate_uam_projection import write_uam_projection_asset
from src.uam_dashboard.uam_corridor_parser import load_uam_corridor_network


def write_json(path: Path, payload: object, *, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=None if compact else 2,
                               separators=(",", ":") if compact else None), encoding="utf-8")


def write_js_bundle(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    path.write_text(f"window.__UAM_DASHBOARD_DATA__ = {serialized};\n", encoding="utf-8")


def scenario_candidate_nodes(routes, segments, csv, reh_xml):
    collection = candidate_node_collection(routes, segments)
    inventory = [f for f in uam_selection_inventory(routes, segments) if f["properties"]["network"] == "UAM"]
    sources = {"uam": source_record(csv) if csv and routes else None,
               "reh": source_record(reh_xml) if reh_xml else None}
    collection["properties"].update(sources=sources, uam_named_inventory_count=len(inventory),
                                    uam_excluded_count=sum(not f["properties"]["capacity_eligible"] for f in inventory))
    for feature in collection["features"]:
        feature["properties"]["source"] = sources[feature["properties"]["network"].lower()]
    return collection


def copy_static_assets(output_dir: Path) -> None:
    source = Path("web")
    if not source.exists():
        raise FileNotFoundError("Static source folder not found: web")
    output_dir.mkdir(parents=True, exist_ok=True)

    for item in source.iterdir():
        if item.name == "calibration.html":
            continue
        destination = output_dir / item.name
        if item.is_dir():
            # Preserve generated audit data, including offline calibration.
            shutil.copytree(item, destination, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("baseline_calibration*"))
        else:
            shutil.copy2(item, destination)
    (output_dir / "calibration.html").unlink(missing_ok=True)


def slugify(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
    return value.strip("._")[:96] or "statelog"


def mean(values: list[float | None]) -> float | None:
    valid = [v for v in values if v is not None and math.isfinite(v)]
    return sum(valid) / len(valid) if valid else None


def average_dashboard(run_dashboards: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(run_dashboards)
    if count == 1:
        return run_dashboards[0]

    return {
        "source_log": f"Media de {count} STATELOGs",
        "metric_catalog_version": SOURCE_VERSION,
        "map_center": SAO_PAULO_CENTER,
        "summary": {
            "records": mean([d["summary"]["records"] for d in run_dashboards]),
            "aircraft_count": mean([d["summary"]["aircraft_count"] for d in run_dashboards]),
            "operation_count": mean([d["summary"]["operation_count"] for d in run_dashboards]),
            "fleet_mix": run_dashboards[0]["summary"].get("fleet_mix", {}),
            "kinematics": run_dashboards[0]["summary"].get("kinematics", {}),
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
            "total_distance_km": mean([d["efficiency"]["total_distance_km"] for d in run_dashboards]),
            "total_flight_hours": mean([d["efficiency"]["total_flight_hours"] for d in run_dashboards]),
            "mean_great_circle_distance_nm": mean(
                [d["efficiency"]["mean_great_circle_distance_nm"] for d in run_dashboards]
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
            "lowc_vertical_m": run_dashboards[0]["safety"].get("lowc_vertical_m"),
            "nmac_horizontal_m": run_dashboards[0]["safety"]["nmac_horizontal_m"],
            "nmac_vertical_m": run_dashboards[0]["safety"].get("nmac_vertical_m"),
            "conflict_definition": run_dashboards[0]["safety"].get("conflict_definition"),
            "operation_count": mean([d["safety"].get("operation_count", 0) for d in run_dashboards]),
            "events_by_vehicle_pair": run_dashboards[0]["safety"].get("events_by_vehicle_pair", {}),
            "sample_seconds": run_dashboards[0]["safety"]["sample_seconds"],
            "separation_samples": mean([d["safety"]["separation_samples"] for d in run_dashboards]),
            "lowc_per_100_operations": mean([d["safety"]["lowc_per_100_operations"] for d in run_dashboards]),
            "lowc_per_flight_hour": mean([d["safety"]["lowc_per_flight_hour"] for d in run_dashboards]),
            "nmac_per_100_operations": mean([d["safety"]["nmac_per_100_operations"] for d in run_dashboards]),
            "nmac_per_flight_hour": mean([d["safety"]["nmac_per_flight_hour"] for d in run_dashboards]),
            "monitored_pair_samples": mean([d["safety"]["monitored_pair_samples"] for d in run_dashboards]),
            "min_severity_ratio": mean([d["safety"]["min_severity_ratio"] for d in run_dashboards]),
            "p05_severity_ratio": mean([d["safety"]["p05_severity_ratio"] for d in run_dashboards]),
            "median_severity_ratio": mean([d["safety"]["median_severity_ratio"] for d in run_dashboards]),
            "p95_severity_ratio": mean([d["safety"]["p95_severity_ratio"] for d in run_dashboards]),
            "total_time_below_threshold_s": mean(
                [d["safety"]["total_time_below_threshold_s"] for d in run_dashboards]
            ),
            "mean_time_below_threshold_s": mean(
                [d["safety"]["mean_time_below_threshold_s"] for d in run_dashboards]
            ),
            "max_time_below_threshold_s": mean(
                [d["safety"]["max_time_below_threshold_s"] for d in run_dashboards]
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
            "tls_margin": run_dashboards[0]["safety"]["tls_target_per_flight_hour"] / (
                mean([d["safety"]["expected_mac_rate_per_flight_hour"] for d in run_dashboards])
                + run_dashboards[0]["safety"]["tls_epsilon"]
            ),
            "tls_compliant": mean(
                [d["safety"]["expected_mac_rate_per_flight_hour"] for d in run_dashboards]
            ) <= run_dashboards[0]["safety"]["tls_target_per_flight_hour"],
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
        "planned_instances": mean([item["planned_instances"] for item in conformities]),
        "matched_instances": mean([item["matched_instances"] for item in conformities]),
        "mean_deviation_m": mean([item["mean_deviation_m"] for item in conformities]),
        "p95_deviation_m": mean([item["p95_deviation_m"] for item in conformities]),
        "max_deviation_m": mean([item["max_deviation_m"] for item in conformities]),
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
        "total_additional_distance_m": mean(
            [item["total_additional_distance_m"] for item in conformities]
        ),
        "mean_planned_horizontal_inefficiency_ratio": mean(
            [item["mean_planned_horizontal_inefficiency_ratio"] for item in conformities]
        ),
        "mean_executed_horizontal_inefficiency_ratio": mean(
            [item["mean_executed_horizontal_inefficiency_ratio"] for item in conformities]
        ),
        "executed_samples": mean([item["executed_samples"] for item in conformities]),
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
        "matched_flights": mean([item["matched_flights"] for item in values]),
        "mean_ground_delay_s": mean([item["mean_ground_delay_s"] for item in values]),
        "median_ground_delay_s": mean([item["median_ground_delay_s"] for item in values]),
        "p95_ground_delay_s": mean([item["p95_ground_delay_s"] for item in values]),
        "max_ground_delay_s": mean([item["max_ground_delay_s"] for item in values]),
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
        "matched_flights": mean([item["matched_flights"] for item in values]),
        "mean_airborne_delay_s": mean([item["mean_airborne_delay_s"] for item in values]),
        "median_airborne_delay_s": mean([item["median_airborne_delay_s"] for item in values]),
        "p95_airborne_delay_s": mean([item["p95_airborne_delay_s"] for item in values]),
        "max_airborne_delay_s": mean([item["max_airborne_delay_s"] for item in values]),
        "total_airborne_delay_s": mean([item["total_airborne_delay_s"] for item in values]),
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
    crossings = copy.deepcopy(first.get("complexity", {}).get("crossings", {"type": "FeatureCollection", "features": []}))
    crossing_samples = [
        {feature["properties"]["resource_id"]: feature["properties"] for feature in item.get("complexity", {}).get("crossings", {}).get("features", [])}
        for item in capacities
    ]
    for feature in crossings.get("features", []):
        properties = feature["properties"]
        resource_id = properties["resource_id"]
        for field in ("operations", "mean_throughput_per_hour", "peak_throughput_per_hour", "capacity_reference_per_hour"):
            properties[field] = mean([sample.get(resource_id, {}).get(field, 0) or 0 for sample in crossing_samples])
        capacity_reference = properties["capacity_reference_per_hour"]
        properties["utilization_peak"] = properties["peak_throughput_per_hour"] / capacity_reference if capacity_reference > 0 else None
        properties["replica_count"] = len(capacities)
    return {
        "available": True,
        "replica_count": len(capacities),
        "window_seconds": first["window_seconds"],
        "capacity_percentile": first["capacity_percentile"],
        "corridor_width_m": first["corridor_width_m"],
        "crossing_capture_radius_m": first.get("crossing_capture_radius_m", 250.0),
        "geometry_source": first.get("geometry_source", "scenario_route_buffers"),
        "uam_geometry_source": first.get("uam_geometry_source", "scenario_route_buffers"),
        "official_reh_segment_count": first.get("official_reh_segment_count", 0),
        "density": {
            "available": bool(density_values),
            "corridor_area_km2": mean([item["corridor_area_km2"] for item in density_values]),
            "mean_simultaneous_aircraft": mean(
                [item["mean_simultaneous_aircraft"] for item in density_values]
            ),
            "peak_simultaneous_aircraft": mean(
                [item["peak_simultaneous_aircraft"] for item in density_values]
            ),
            "air_traffic_density_per_km2": mean(
                [item["air_traffic_density_per_km2"] for item in density_values]
            ),
            "hotspot_density_per_km2": mean([item["hotspot_density_per_km2"] for item in density_values]),
            "hotspots": first.get("density", {}).get("hotspots", {"type": "FeatureCollection", "features": []}),
        },
        "throughput": {
            resource_type: average_resource_group([item.get("throughput", {}).get(resource_type, {}) for item in capacities])
            for resource_type in first["throughput"]
        },
        "complexity": {
            "available": bool(complexity_values),
            "crossing_definition": first.get("complexity", {}).get("crossing_definition"),
            "geometry_dimension": first.get("complexity", {}).get("geometry_dimension", "3D"),
            "uam_corridor_count": mean([item.get("uam_corridor_count", 0) for item in complexity_values]),
            "reh_segment_count": mean([item.get("reh_segment_count", 0) for item in complexity_values]),
            "planned_route_count": mean([item["planned_route_count"] for item in complexity_values]),
            "planned_waypoint_count": mean([item["planned_waypoint_count"] for item in complexity_values]),
            "planned_route_crossings": mean([item["planned_route_crossings"] for item in complexity_values]),
            "trajectory_group_count": mean([item["trajectory_group_count"] for item in complexity_values]),
            "repeated_trajectory_group_count": mean(
                [item["repeated_trajectory_group_count"] for item in complexity_values]
            ),
            "lowc_event_count": mean([item["lowc_event_count"] for item in complexity_values]),
            "crossings": crossings,
            "crossing_capacity": average_resource_group([item.get("complexity", {}).get("crossing_capacity", {}) for item in capacities]),
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
    variant_order = {"c1": 0, "c2": 1, "disturbed_mvp": 2, "disturbed_off": 3, "nominal_mvp": 4, "nominal_off": 5}
    for rows in by_day.values():
        rows.sort(key=lambda row: variant_order.get(row["variant_key"], 99))
        if rows[0].get("experiment_family") != "produto2":
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
            if row.get("experiment_family") == "produto2":
                risk_reference = next((ref for ref in rows if ref["variant_key"] == row["reference_variant_key"]), None)
            row["is_reference"] = risk_reference is row
            row["risk_ratio_vs_reference"] = _ratio_or_none(
                row["expected_mac_per_100k_flight_hours"],
                risk_reference["expected_mac_per_100k_flight_hours"] if risk_reference else None,
            )
            reference = risk_reference if row.get("experiment_family") == "produto2" else off_references.get(row["disturbed"])
            row["flight_time_delta_vs_reference_min"] = _difference_or_none(
                row["flight_time_min"],
                reference["flight_time_min"] if reference else None,
            )
            row["distance_delta_vs_reference_nm"] = _difference_or_none(
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


def analyze_log(log_path: Path, config: DashboardConfig, charts_dir: Path, run_index: int, render_charts: bool = True) -> dict[str, Any]:
    chart_prefix = f"{run_index + 1:02d}_{slugify(log_path.stem)}"
    print(f"Loading log: {log_path}")
    df = load_state_log(log_path)

    print("Computing metrics and sampled LoWC events...")
    scenario_path = find_matching_scenario(log_path, config.scenario_paths)
    planned_flights = load_bluesky_scenario(scenario_path) if scenario_path else []
    df = annotate_aircraft_metadata(df, planned_flights)
    series = active_aircraft_series(df)
    efficiency = efficiency_metrics(
        df,
        gap_seconds=config.flight_instance_gap_seconds,
        reset_distance_m=config.flight_instance_reset_distance_m,
        jump_m=config.flight_instance_jump_m,
    )
    reh_network = load_reh_network(config.reh_xml_path) if config.reh_xml_path else None
    reh_segments = reh_network["segments"] if reh_network else []
    metadata = log_experiment_metadata(log_path, config.scenario_paths)
    selected_csv = config.uam_corridor_csv_by_scenario.get(metadata.get("scenario_key"), config.uam_corridor_csv_path)
    uam_network = (
        load_uam_corridor_network(selected_csv)
        if selected_csv and (metadata.get("airspace") == "dedicated_uam" or metadata.get("scenario_key") == "C2")
        else None
    )
    if uam_network and metadata.get("network_stage"):
        expected_vertiports = {"1": 6, "2": 12}[metadata["network_stage"]]
        if len(uam_network["vertiports"]) != expected_vertiports:
            raise ValueError(f"Wrong corridor network for {metadata['scenario_key']}: {selected_csv}")
    efficiency["ground_delay"] = {
        "available": False,
        "reason": "requer horários solicitado (S_f) e autorizado/reprogramado (R_f)",
    }
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
        reh_segments=reh_segments,
    )
    efficiency["trajectory_conformity"] = conformity
    lowc_events, separation_samples, safety = detect_lowc_events(
        df,
        horizontal_threshold_m=config.lowc_horizontal_m,
        nmac_horizontal_threshold_m=config.nmac_horizontal_m,
        sample_seconds=config.conflict_sample_seconds,
        detection_horizon_seconds=0.0,
        aircraft_count=int(df["id"].nunique()),
        total_flight_hours=efficiency["total_flight_hours"],
        total_distance_km=efficiency["total_distance_km"],
        mac_beta=config.mac_beta,
        mac_probability_given_nmac=config.mac_probability_given_nmac,
        tls_target_per_flight_hour=config.tls_target_per_flight_hour,
        tls_epsilon=config.tls_epsilon,
        lowc_vertical_threshold_m=config.lowc_vertical_m,
        nmac_vertical_threshold_m=config.nmac_vertical_m,
        operation_count=efficiency["flight_instances"],
    )

    chart_paths = {
        "active_aircraft": f"assets/charts/{chart_prefix}_active_aircraft.png",
        "separation_histogram": f"assets/charts/{chart_prefix}_separation_histogram.png",
        "altitude_histogram": f"assets/charts/{chart_prefix}_altitude_histogram.png",
        "distance_histogram": f"assets/charts/{chart_prefix}_distance_histogram.png",
        "severity_histogram": f"assets/charts/{chart_prefix}_severity_histogram.png",
        "trajectory_conformity": f"assets/charts/{chart_prefix}_trajectory_conformity.png",
    }
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
        reh_segments=reh_segments,
        official_uam_routes=uam_network["routes"] if uam_network else None,
        crossing_capture_radius_m=config.crossing_capture_radius_m,
    )

    summary = build_summary(df, operation_count=efficiency["flight_instances"])
    dashboard = {
        "source_log": log_path.name,
        "metric_catalog_version": SOURCE_VERSION,
        "metadata": metadata,
        "map_center": SAO_PAULO_CENTER,
        "summary": summary,
        "efficiency": efficiency,
        "safety": safety,
        "capacity": capacity,
        "charts": chart_paths,
        "metric_catalog": metric_catalog_payload(),
    }

    dashboard["replica_summary"] = summarize_replica(df, series, separation_samples, lowc_events, conformity_by_instance, config)
    grid = density_grid(df, config.heatmap_grid_degrees)
    if not render_charts:
        return {"dashboard": dashboard, "density_grid": grid}

    return {
        "id": chart_prefix,
        "name": log_path.name,
        "metadata": metadata,
        "dashboard": dashboard,
        "density_grid": grid,
        "tracks": tracks,
        "planned_routes": planned_routes,
        "official_reh": reh_network["geojson"] if reh_network else {
            "type": "FeatureCollection",
            "properties": {"segment_count": 0, "geometry_reference": "unavailable"},
            "features": [],
        },
        "conflicts": conflicts_geojson(lowc_events),
        "heatmap": heatmap_points(df, config.heatmap_sample_stride),
        "trajectory_3d": trajectory_3d_payload(
            df, config.visualization_3d_sample_seconds,
            config.flight_instance_gap_seconds, config.flight_instance_reset_distance_m,
            config.flight_instance_jump_m, config.visualization_3d_ground_msl_ft,
        ) if render_charts else None,
    }


def build_dashboard(config: DashboardConfig) -> None:
    output_dir = config.output_dir
    for log_path in config.log_paths:
        metadata = log_experiment_metadata(log_path, config.scenario_paths)
        if metadata["experiment_family"] == "produto2" and metadata["day_key"] != "produto2_p100":
            raise ValueError(
                f"{log_path} pertence a {metadata['day_label']}. "
                "Esta fase publica somente réplicas de demanda P100."
            )
        if re.fullmatch(r"C\d+(?:[._]\d+)*", log_path.parent.name, re.IGNORECASE) and matching_scenario(log_path, config.scenario_paths) is None:
            raise ValueError(
                f"Não foi possível associar {log_path} a um único cenário SCN. "
                "Confira a demanda P100, a réplica e --scenario-dir, "
                "ou informe --scenarios explicitamente."
            )
    print("Copying HTML/CSS/JS...")
    copy_static_assets(output_dir)
    write_candidate_node_assets(output_dir, config.uam_corridor_csv_path, config.reh_xml_path)
    if config.uam_corridor_csv_path:
        write_crossing_waypoint_asset(config.uam_corridor_csv_path, config.reh_xml_path, output_dir)
        write_uam_projection_asset(config.uam_corridor_csv_path, output_dir)
    write_metric_catalog_asset(output_dir)

    charts_dir = output_dir / "assets" / "charts"
    data_dir = output_dir / "assets" / "data"
    charts_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    # Keep only per-replica metrics in memory. Geometry, timelines and charts
    # are published from one representative replica per scenario. Charts use compact
    # per-replica summaries; inference retains the individual estimates. The heatmap
    # merges every position sample from all replicas on a common grid, preventing
    # a 50-replica GitHub Pages bundle from duplicating large tracks 50 times.
    dashboards_by_group: dict[tuple[str, str, bool | None], list[tuple[int, dict[str, Any]]]] = {}
    grids_by_group: dict[tuple, list] = {}
    representatives: dict[tuple[str, str, bool | None], dict[str, Any]] = {}
    group_order: list[tuple[str, str, bool | None]] = []
    tasks = []
    for index, log_path in enumerate(sorted(config.log_paths, key=lambda path: (
            experiment_sort_key(path), log_experiment_metadata(path, config.scenario_paths).get("replica") or 0, str(path)))):
        metadata = log_experiment_metadata(log_path, config.scenario_paths)
        group_key = (
            str(metadata.get("day_key")),
            str(metadata.get("scenario_key") or log_path.stem),
            metadata.get("mvp_enabled"),
        )
        representative = group_key not in group_order
        if representative:
            group_order.append(group_key)
        tasks.append((index, log_path, group_key, representative))

    def record_result(index: int, group_key: tuple[str, str, bool | None], representative: bool, run: dict[str, Any]) -> None:
        dashboards_by_group.setdefault(group_key, []).append((index, run["dashboard"]))
        grids_by_group.setdefault(group_key, []).append(run.pop("density_grid"))
        if representative:
            representatives[group_key] = run

    worker_count = min(config.workers, len(tasks))
    if worker_count < 1:
        raise ValueError("At least one STATELOG and one worker are required")
    print(f"Analyzing {len(tasks)} STATELOGs with {worker_count} worker processes...", flush=True)
    if worker_count == 1:
        for index, log_path, group_key, representative in tasks:
            record_result(index, group_key, representative, analyze_log(log_path, config, charts_dir, index, representative))
    else:
        with ProcessPoolExecutor(max_workers=worker_count) as pool:
            futures = {
                pool.submit(analyze_log, log_path, config, charts_dir, index, representative): (index, log_path, group_key, representative)
                for index, log_path, group_key, representative in tasks
            }
            for completed, future in enumerate(as_completed(futures), 1):
                index, log_path, group_key, representative = futures.pop(future)
                record_result(index, group_key, representative, future.result())
                print(f"Completed {completed}/{len(tasks)}: {log_path.name}", flush=True)
    runs = []
    for group_key in group_order:
        run = representatives[group_key]
        count = len(dashboards_by_group[group_key])
        if count > 1:
            run["dashboard"] = average_dashboard([
                dashboard for _, dashboard in sorted(dashboards_by_group[group_key])
            ])
            run["dashboard"]["source_log"] = f"Média de {count} réplicas ({run['metadata'].get('scenario_key', group_key[1])})"
            run["metadata"] = {**run["metadata"], "variant_label": f"{run['metadata']['variant_label']} · média de {count} réplicas"}
        individuals = [d for _, d in sorted(dashboards_by_group[group_key])]
        run["aggregate_analysis"] = aggregate_summaries([d.pop("replica_summary") for d in individuals])
        run["stability"] = stability_payload(individuals)
        # Preserve all individual scalar metrics in an audit file, outside the browser bundle.
        write_json(data_dir / "replica_metrics" / f"{run['id']}.json", {
            "schema_version": SCHEMA_VERSION, "replicas": [
                metric_audit(d) for d in individuals]}, compact=True)
        run["dashboard"] = copy.deepcopy(run["dashboard"])
        for path in sorted({p for paths in KPI_PATHS.values() for p in paths} - {"safety.tls_margin"}):
            values = [metric_value(d, path) for d in individuals]
            valid = [v for v in values if v is not None]
            parent = run["dashboard"]
            for part in path.split(".")[:-1]:
                parent = parent.setdefault(part, {})
            parent[path.split(".")[-1]] = mean(valid) if valid else None
        run["analysis_schema_version"] = SCHEMA_VERSION
        run["dashboard"].pop("replica_summary", None)
        run["dashboard"]["chart_aggregation_version"] = SCHEMA_VERSION
        run["dashboard"]["replica_count"] = count
        plot_aggregates(run["aggregate_analysis"], run["dashboard"]["charts"], charts_dir)
        run["replica_count"] = count
        run["representative_log"] = run["name"]
        run["density"] = merge_density_grids(grids_by_group[group_key], config.heatmap_grid_degrees)
        runs.append(run)
    # One intensity scale for all scenarios: replica count never amplifies color.
    density_max = max((cell[2] for run in runs for cell in run["density"]["cells"]), default=1.) or 1.
    geometry_cache = {}
    reh_segments = load_reh_network(config.reh_xml_path)["segments"] if config.reh_xml_path else []
    for run in runs:
        run["heatmap"] = [[lat, lon, count / density_max] for lat, lon, count in run["density"].pop("cells")]
        run["density"]["shared_scale_max_mean_records"] = density_max
        code = run["metadata"].get("scenario_key")
        csv = config.uam_corridor_csv_by_scenario.get(code, config.uam_corridor_csv_path)
        dedicated = run["metadata"].get("airspace") == "dedicated_uam" or code == "C2"
        if csv and dedicated:
            if csv not in geometry_cache:
                routes = load_uam_corridor_network(csv)["routes"]
                geometry = uam_geometry(routes)
                geometry["audit"]["source"] = source_record(csv)
                nodes = scenario_candidate_nodes(routes, reh_segments, csv, config.reh_xml_path)
                geometry_cache[csv] = (geometry, nodes)
            geometry, nodes = geometry_cache[csv]
            run["uam_projection"] = geometry["projection"]
            run["uam_junctions"] = geometry["junctions"]
            run["uam_centerlines"] = geometry["centerlines"]
            run["uam_geometry_audit"] = geometry["audit"]
            run["candidate_nodes"] = nodes
        else:
            run["uam_projection"] = {"type": "FeatureCollection", "features": []}
            run["uam_junctions"] = {"type": "FeatureCollection", "features": []}
            run["uam_centerlines"] = {"type": "FeatureCollection", "features": []}
            run["candidate_nodes"] = scenario_candidate_nodes([], reh_segments, None, config.reh_xml_path)
    dashboard = average_dashboard([run["dashboard"] for run in runs])
    comparison = comparison_payload(runs, dashboard)
    primary = runs[0]

    print("Writing static data files...")
    write_json(data_dir / "dashboard.json", dashboard)
    write_json(data_dir / "comparison.json", comparison)
    write_json(data_dir / "tracks.geojson", primary["tracks"])
    write_json(data_dir / "planned_routes.geojson", primary["planned_routes"])
    write_json(data_dir / "official_reh.geojson", primary["official_reh"])
    write_json(data_dir / "conflicts.geojson", primary["conflicts"])
    write_json(data_dir / "heatmap_points.json", primary["heatmap"])
    write_json(data_dir / "trajectory_3d.json", primary["trajectory_3d"])
    runs_dir = data_dir / "runs"
    for run in runs:
        write_json(runs_dir / f"{run['id']}.json", run)

    write_js_bundle(
        output_dir / "assets" / "data_bundle.js",
        {
            "dashboard": dashboard,
            "tracks": primary["tracks"],
            "planned_routes": primary["planned_routes"],
            "official_reh": primary["official_reh"],
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
    parser.add_argument("--config", default=None, help="JSON selecting an orchestrator RUN; default: run_config.json when no logs are passed.")
    parser.add_argument("--workers", type=int, default=None, help="Worker processes for per-replica metrics; overrides the JSON setting.")
    parser.add_argument("--output", default="docs", help="Output folder for GitHub Pages.")
    parser.add_argument("--data-dir", default="data", help="Folder searched when no log is passed.")
    parser.add_argument("--scenario-dir", default="data/scenarios", help="Folder searched for BlueSky SCN files.")
    parser.add_argument("--scenarios", nargs="*", default=None, help="BlueSky SCN files used as planned routes.")
    parser.add_argument(
        "--reh-xml",
        default=None,
        help="WFS/GML XML with the official Sao Paulo REH polygons.",
    )
    parser.add_argument(
        "--uam-corridor-csv",
        default=None,
        help="Product II corridor CSV belonging to the selected scenario; vertiport set is validated.",
    )
    parser.add_argument("--flight-instance-gap-seconds", type=float, default=300.0)
    parser.add_argument("--flight-instance-reset-distance-m", type=float, default=250.0)
    parser.add_argument("--flight-instance-jump-m", type=float, default=5000.0)
    parser.add_argument("--lowc-horizontal-m", type=float, default=500.0)
    parser.add_argument("--lowc-vertical-m", type=float, default=137.16)
    parser.add_argument("--nmac-horizontal-m", type=float, default=152.0)
    parser.add_argument("--nmac-vertical-m", type=float, default=30.0)
    parser.add_argument("--mac-beta", type=float, default=0.005)
    parser.add_argument("--mac-probability-given-nmac", type=float, default=5.038e-3)
    parser.add_argument("--tls-target-per-flight-hour", type=float, default=8.9e-6)
    parser.add_argument("--tls-epsilon", type=float, default=1e-15)
    parser.add_argument("--conflict-sample-seconds", type=int, default=1)
    parser.add_argument("--visualization-3d-sample-seconds", type=int, default=5)
    parser.add_argument("--visualization-3d-ground-msl-ft", type=float, default=2621.0)
    parser.add_argument("--conflict-detection-horizon-seconds", type=float, default=60.0)
    parser.add_argument("--trajectory-shape-points", type=int, default=12)
    parser.add_argument("--trajectory-cluster-distance-m", type=float, default=1200.0)
    parser.add_argument("--trajectory-endpoint-tolerance-m", type=float, default=2500.0)
    parser.add_argument("--conformity-tolerance-m", type=float, default=250.0)
    parser.add_argument("--capacity-window-seconds", type=int, default=900)
    parser.add_argument("--capacity-reference-percentile", type=float, default=0.95)
    parser.add_argument("--crossing-capture-radius-m", type=float, default=250.0)
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
    return tuple(sorted(scenario_dir.rglob("*.scn"))) if scenario_dir.exists() else ()


def find_reh_xml(explicit: str | None) -> Path:
    path = Path(explicit) if explicit else DEFAULT_REH_XML_PATH
    if not path.is_file():
        raise FileNotFoundError(
            f"REH XML not found: {path}. Restore the versioned file in data/xml/"
            " or pass --reh-xml."
        )
    return path


def find_uam_corridor_csv(data_dir: Path, explicit: str | None) -> Path | None:
    if explicit:
        path = Path(explicit)
        if not path.exists():
            raise FileNotFoundError(f"UAM corridor CSV not found: {path}")
        return path

    candidate = data_dir / "corridors" / "scenario_horizontal_3000ft_expanded_displaced.csv"
    return candidate if candidate.exists() else None


def find_matching_scenario(log_path: Path, scenario_paths: tuple[Path, ...]) -> Path | None:
    return matching_scenario(log_path, scenario_paths)


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
    # C1 and C2 are alternative airspace/vehicle scenarios, not an evaluated
    # run plus a no-deconfliction reference of the same configuration.
    if metadata.get("experiment_family") == "produto2":
        return None
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
    selection = None
    data_dir = Path(args.data_dir)
    if args.config and args.logs:
        raise ValueError("Pass either --config or positional STATELOG paths, not both")
    config_path = Path(args.config or "run_config.json")
    if args.config or (not args.logs and config_path.is_file()):
        selection = load_run_selection(config_path)
        log_paths = selection.log_paths
        scenario_paths = selection.scenario_paths
        worker_count = args.workers if args.workers is not None else selection.dashboard_workers
        print(f"Using orchestrator RUN: {selection.run_dir}")
    else:
        log_paths = tuple(Path(log) for log in args.logs) if args.logs else find_default_logs(data_dir)
        scenario_paths = find_scenarios(Path(args.scenario_dir), args.scenarios)
        worker_count = args.workers if args.workers is not None else 1
    if worker_count < 1:
        raise ValueError("--workers must be a positive integer")
    reh_xml_path = find_reh_xml(args.reh_xml)
    if selection and args.uam_corridor_csv and selection.uam_corridor_csv_path and Path(args.uam_corridor_csv).resolve() != selection.uam_corridor_csv_path.resolve():
        raise ValueError("--uam-corridor-csv differs from validated run config; update the config explicitly")
    selected_csv = args.uam_corridor_csv or (str(selection.uam_corridor_csv_path) if selection and selection.uam_corridor_csv_path else None)
    if selection and selection.uam_corridor_csv_path is None:
        raise ValueError("Run config must select uam_corridor_csv explicitly for its scenario")
    uam_corridor_csv_path = find_uam_corridor_csv(data_dir, selected_csv)
    config = DashboardConfig(
        log_paths=log_paths,
        workers=worker_count,
        scenario_paths=scenario_paths,
        output_dir=Path(args.output),
        data_dir=data_dir,
        reh_xml_path=reh_xml_path,
        uam_corridor_csv_path=uam_corridor_csv_path,
        uam_corridor_csv_by_scenario=selection.uam_corridor_csv_by_scenario if selection else {},
        flight_instance_gap_seconds=args.flight_instance_gap_seconds,
        flight_instance_reset_distance_m=args.flight_instance_reset_distance_m,
        flight_instance_jump_m=args.flight_instance_jump_m,
        lowc_horizontal_m=args.lowc_horizontal_m,
        lowc_vertical_m=args.lowc_vertical_m,
        nmac_horizontal_m=args.nmac_horizontal_m,
        nmac_vertical_m=args.nmac_vertical_m,
        mac_beta=args.mac_beta,
        mac_probability_given_nmac=args.mac_probability_given_nmac,
        tls_target_per_flight_hour=args.tls_target_per_flight_hour,
        tls_epsilon=args.tls_epsilon,
        conflict_sample_seconds=args.conflict_sample_seconds,
        visualization_3d_sample_seconds=args.visualization_3d_sample_seconds,
        visualization_3d_ground_msl_ft=args.visualization_3d_ground_msl_ft,
        trajectory_shape_points=args.trajectory_shape_points,
        trajectory_cluster_distance_m=args.trajectory_cluster_distance_m,
        trajectory_endpoint_tolerance_m=args.trajectory_endpoint_tolerance_m,
        conformity_tolerance_m=args.conformity_tolerance_m,
        capacity_window_seconds=args.capacity_window_seconds,
        capacity_reference_percentile=args.capacity_reference_percentile,
        crossing_capture_radius_m=args.crossing_capture_radius_m,
    )
    build_dashboard(config)


if __name__ == "__main__":
    main()
