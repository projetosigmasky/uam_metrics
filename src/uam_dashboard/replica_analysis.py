"""Compact worker summaries and deterministic, equal-replica inference.

No trajectories or pooled flights are needed by the parent process/browser.
Fixed-width bins have the same origin and width in every scenario.
"""
from __future__ import annotations

import math
import numpy as np

from .metrics import flight_instance_frame

SCHEMA_VERSION = 1
CRITERIA = dict(minimum_replications=30, confirmation_window=15,
                confidence_level=.95, relative_tolerance=.05,
                absolute_tolerance=0., bootstrap_samples=1000, seed=1729)
# key: width, percentage (otherwise mean sample/event counts), x-axis unit
BINS = {
    "altitude_histogram": (25., False, "Altitude MSL (m)"),
    "separation_histogram": (100., True, "Separação horizontal (m), amostras de pares < 5.000 m"),
    "severity_histogram": (.05, False, "Razão mínima de severidade por evento LoWC (inclui NMAC)"),
    "distance_histogram": (2., True, "Distância executada por instância de voo (NM)"),
    "trajectory_conformity": (5., True, "Distância adicional em relação ao plano (%)"),
}


def metric_audit(dashboard):
    """Keep individual estimates, without duplicating spatial feature catalogs."""
    def compact(value):
        if isinstance(value, dict):
            return {k: compact(v) for k, v in value.items()
                    if k not in ("features", "geometry", "coordinates", "polygons", "map_target", "hotspots", "crossings")}
        if isinstance(value, list):
            return [compact(v) for v in value]
        return value
    return compact({k: v for k, v in dashboard.items() if k not in ("charts", "metric_catalog")})


def histogram(values, width):
    clean = np.asarray(list(values), dtype=float)
    clean = clean[np.isfinite(clean)]
    keys, counts = np.unique(np.floor(clean / width).astype(np.int64), return_counts=True)
    return {"counts": {str(k): int(v) for k, v in zip(keys, counts)}, "valid_count": len(clean)}


def summarize_replica(df, series, separations, events, conformity, config):
    instances = flight_instance_frame(df, config.flight_instance_gap_seconds,
                                     config.flight_instance_reset_distance_m, config.flight_instance_jump_m)
    distances = instances.groupby("flight_instance")["distflown"].agg(["min", "max"])
    values = {
        "altitude_histogram": df.alt,
        "separation_histogram": [x for x in separations if x < 5000],
        "severity_histogram": events.severity_ratio.clip(upper=1.) if not events.empty else [],
        "distance_histogram": (distances["max"] - distances["min"]) / 1852.,
        "trajectory_conformity": [x["trajectory_conformity_ratio"] * 100 for x in conformity.values()
                                  if x.get("trajectory_conformity_ratio") is not None],
    }
    times = np.sort(df.simt.unique())
    return {
        "active": series[["simt", "aircraft"]].values.tolist(),
        "histograms": {k: histogram(v, BINS[k][0]) for k, v in values.items()},
        "coverage": {"start_s": float(times[0]), "end_s": float(times[-1]),
                     "observed_timestamps": len(times),
                     "median_cadence_s": float(np.median(np.diff(times))) if len(times) > 1 else None,
                     "position_records": len(df), "flight_instances": len(distances),
                     "matched_flights": len(values["trajectory_conformity"])},
    }


def aggregate_summaries(rows):
    charts = {}
    times = sorted({t for row in rows for t, _ in row["active"]})
    indexed = [dict(row["active"]) for row in rows]
    charts["active_aircraft"] = {"x": times, "mean": [], "lower": [], "upper": [], "valid_replicas": [],
                                  "xlabel": "Tempo de simulação (s)", "ylabel": "Aeronaves", "total_replicas": len(rows)}
    for t in times:
        values = [r[t] for r in indexed if t in r]
        for field, value in zip(("mean", "lower", "upper", "valid_replicas"),
                                (float(np.mean(values)), min(values), max(values), len(values))):
            charts["active_aircraft"][field].append(value)
    for key, (width, percent, xlabel) in BINS.items():
        hist = [row["histograms"][key] for row in rows]
        # A successful detection with no events is an observed zero vector.
        valid = [h for h in hist if h["valid_count"] or key == "severity_histogram"]
        indices = sorted({int(i) for h in hist for i in h["counts"]}) or [0]
        matrix = np.array([[h["counts"].get(str(i), 0) * (100 / h["valid_count"] if percent else 1)
                            for i in indices] for h in valid])
        charts[key] = {"x": [(i + .5) * width for i in indices], "bin_width": width,
                       "mean": matrix.mean(axis=0).tolist() if len(valid) else [],
                       "lower": matrix.min(axis=0).tolist() if len(valid) else [],
                       "upper": matrix.max(axis=0).tolist() if len(valid) else [],
                       "valid_replicas": len(valid), "total_replicas": len(rows),
                       "counts_per_replica": [h["valid_count"] for h in hist],
                       "xlabel": xlabel, "ylabel": "Percentual médio por réplica (%)" if percent else
                       "Eventos médios por réplica" if key == "severity_histogram" else "Registros médios por réplica"}
    return {"schema_version": SCHEMA_VERSION, "replica_count": len(rows), "charts": charts,
            "coverage": [row["coverage"] for row in rows],
            "dispersion": "minimum_maximum_between_valid_replicas_not_confidence_interval",
            "time_alignment": "exact_simulation_timestamp_no_interpolation_missing_excluded",
            "altitude_unit": "raw_position_records_mean_per_replica_no_cadence_normalization"}


def cumulative_mean(values, criteria=None, transform=None, denominators=None):
    """Percentile bootstrap of replica estimates, never of pooled flight samples.

    Missing observations break confirmation. Constant samples cannot establish
    statistical precision (especially zero-event samples); report descriptively.
    """
    c = {**CRITERIA, **(criteria or {})}
    trace, valid, valid_denominators, consecutive = [], [], [], 0
    first_confirmed = None
    mean, constant = None, False
    for n, raw in enumerate(values, 1):
        observed = isinstance(raw, (int, float)) and not isinstance(raw, bool) and math.isfinite(raw)
        if denominators is not None:
            denominator = denominators[n-1]
            observed = observed and isinstance(denominator, (int, float)) and math.isfinite(denominator) and denominator >= 0
        if observed:
            valid.append(float(raw))
            if denominators is not None:
                valid_denominators.append(float(denominator))
        mean = float(np.mean(valid)) if valid else None
        if denominators is not None:
            mean = mean / np.mean(valid_denominators) if valid_denominators and np.mean(valid_denominators) > 0 else None
        if transform is not None and mean is not None:
            mean = float(transform(mean))
        ci, met = None, False
        constant = bool(valid) and min(valid) == max(valid) and (denominators is None or min(valid_denominators) == max(valid_denominators))
        if len(valid) >= 2 and not constant and mean is not None:
            rng = np.random.default_rng(c["seed"] + n)
            indices = rng.integers(0, len(valid), (c["bootstrap_samples"], len(valid)))
            samples = np.asarray(valid)[indices].mean(axis=1)
            if denominators is not None:
                den = np.asarray(valid_denominators)[indices].mean(axis=1)
                samples = np.divide(samples, den, out=np.full_like(samples, np.nan), where=den>0)
            if transform is not None:
                samples = transform(samples)
            if np.isfinite(samples).all():
                alpha = (1 - c["confidence_level"]) / 2
                ci = np.quantile(samples, [alpha, 1 - alpha]).tolist()
                tolerance = max(c["absolute_tolerance"], abs(mean) * c["relative_tolerance"])
                met = observed and len(valid) >= c["minimum_replications"] and max(mean-ci[0], ci[1]-mean) <= tolerance
        consecutive = consecutive + 1 if met else 0
        if consecutive >= c["confirmation_window"] and first_confirmed is None:
            first_confirmed = n
        trace.append(dict(replicas=n, valid_count=len(valid), mean=mean, ci95=ci, criterion_met=bool(met)))
    stable = consecutive >= c["confirmation_window"]
    return dict(trace=trace, valid_count=len(valid), total_count=len(values), criteria=c,
                status="unavailable" if not valid or mean is None else "constant_observed_no_inference" if constant
                else "confirmed" if stable else "not_confirmed",
                stable_from_n=len(values)-consecutive+1 if stable else None,
                confirmed_at_n=len(values)-consecutive+c["confirmation_window"] if stable else None,
                first_confirmed_at_n=first_confirmed)


# Every numeric card, including duplicate overview/safety/efficiency displays.
KPI_PATHS = {
    "overview": ["summary.aircraft_count", "summary.records", "summary.peak_simultaneous_aircraft", "summary.duration_min",
                 "efficiency.mean_flight_time_min", "efficiency.mean_distance_nm", "safety.lowc_events", "safety.nmac_events",
                 "safety.lowc_per_flight_hour", "safety.expected_mac_per_100k_flight_hours",
                 "safety.lowc_horizontal_m", "safety.lowc_vertical_m", "safety.nmac_horizontal_m", "safety.nmac_vertical_m"],
    "safety": ["safety.min_severity_ratio", "safety.expected_mac_per_100k_flight_hours", "safety.tls_margin",
               "safety.total_time_below_threshold_s", "safety.sample_seconds"],
    "efficiency": ["efficiency.mean_flight_time_min", "efficiency.mean_distance_nm", "efficiency.mean_horizontal_inefficiency_pct",
                   "efficiency.trajectory_conformity.mean_trajectory_conformity_ratio", "efficiency.trajectory_conformity.spatial_adherence_pct",
                   "efficiency.ground_delay.mean_ground_delay_s", "efficiency.airborne_delay.mean_airborne_delay_s",
                   "efficiency.total_delay.mean_total_delay_s"],
    "capacity": ["capacity.density.air_traffic_density_per_km2", "capacity.density.hotspot_density_per_km2",
                 "capacity.density.corridor_area_km2", "capacity.complexity.planned_route_count",
                 "capacity.complexity.uam_corridor_count", "capacity.complexity.reh_segment_count",
                 "capacity.complexity.trajectory_group_count", "capacity.complexity.repeated_trajectory_group_count",
                 "capacity.complexity.lowc_event_count"],
}


def metric_value(dashboard, path):
    value = dashboard
    for part in path.split("."):
        if not isinstance(value, dict) or value.get("available") is False:
            return None
        value = value.get(part)
    # Existing no-event severity sentinel is not an observed severity.
    if path == "safety.min_severity_ratio" and not dashboard["safety"]["lowc_events"]:
        return None
    if (path.startswith("safety.") and ("flight_hour" in path or path == "safety.tls_margin")
            and dashboard["efficiency"]["total_flight_hours"] <= 0):
        return None
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def stability_payload(dashboards):
    result = {"schema_version": SCHEMA_VERSION, "method": "percentile_bootstrap_equal_replica_means", "criteria": CRITERIA,
              "replicas": [{"index": d["metadata"].get("replica"), "file": d["source_log"]} for d in dashboards], "panels": {}}
    for panel, paths in KPI_PATHS.items():
        result["panels"][panel] = {}
        for path in paths:
            values = [metric_value(d, path) for d in dashboards]
            analysis = cumulative_mean(values)
            if path in ("safety.sample_seconds", "capacity.density.corridor_area_km2", "capacity.complexity.planned_route_count",
                        "capacity.complexity.uam_corridor_count", "capacity.complexity.reh_segment_count",
                        "safety.lowc_horizontal_m", "safety.lowc_vertical_m", "safety.nmac_horizontal_m", "safety.nmac_vertical_m"):
                analysis = {"status": "configuration_or_geometry_no_inference", "total_count": len(values),
                            "valid_count": sum(v is not None for v in values), "trace": []}
            if path == "safety.tls_margin":
                # Card is TLS / (mean rate + epsilon), not mean of replica margins.
                rates = [metric_value(d, "safety.expected_mac_rate_per_flight_hour") for d in dashboards]
                target = dashboards[0]["safety"]["tls_target_per_flight_hour"]
                eps = dashboards[0]["safety"]["tls_epsilon"]
                analysis = cumulative_mean(rates, transform=lambda value: target / (value + eps))
                analysis["estimand"] = "TLS/(cumulative_mean_MAC_rate+epsilon); criterion_on_transformed_interval"
            result["panels"][panel][path] = {**analysis, "values": values}
    result["panels"]["capacity"]["Junções geométricas 3D"] = {
        "status": "configuration_or_geometry_no_inference", "trace": [], "valid_count": len(dashboards), "total_count": len(dashboards)}
    from .aggregation import average_resource_group
    for group_key in ("od_pairs", "trajectory_groups", "planned_reh"):
        groups = [d["capacity"].get("throughput", {}).get(group_key, {}) for d in dashboards]
        combined = average_resource_group(groups)
        for resource in combined["top_resources"]:
            rid = resource["resource_id"]
            fields = {}
            for field, label in (("operations", "Operações"), ("peak_throughput_per_hour", "Pico (ops/h)"),
                                 ("capacity_reference_per_hour", "Referência P95 (ops/h)")):
                values = []
                for group in groups:
                    entry = next((r for r in group.get("resources", group.get("top_resources", [])) if r["resource_id"] == rid), None)
                    # Same estimand as average_resource_group: completed replica,
                    # unused resource contributes zero; unavailable group is missing.
                    values.append(entry.get(field) if entry else 0. if group.get("available") else None)
                fields[field] = values
                key = f"{group_key} · {resource['label']} · {label}"
                result["panels"]["capacity"][key] = {**cumulative_mean(values), "values": values}
            # Utilization is a ratio of mean peak / mean reference, not a mean of ratios.
            result["panels"]["capacity"][f"{group_key} · {resource['label']} · Utilização (razão)"] = {
                **cumulative_mean(fields["peak_throughput_per_hour"], denominators=fields["capacity_reference_per_hour"]),
                "estimand": "ratio_of_mean_peak_to_mean_reference_same_replica_bootstrap",
                "values": fields["peak_throughput_per_hour"], "denominators": fields["capacity_reference_per_hour"]}
    return result


def plot_aggregates(payload, paths, charts_dir):
    from .plots import _set_style
    import matplotlib.pyplot as plt
    _set_style()
    for key, data in payload["charts"].items():
        fig, ax = plt.subplots(figsize=(10.5, 4.2))
        if data["mean"]:
            x = np.asarray(data["x"])
            if key == "active_aircraft":
                x = x / 3600
                ax.plot(x, data["mean"], color="#2563eb", label="Média das réplicas com observação")
                ax.set_xlabel("Tempo de simulação (h)")
                ax.fill_between(x, data["lower"], data["upper"], color="#93c5fd", alpha=.35,
                                label="Mínimo–máximo entre réplicas (não IC)")
            else:
                ax.bar(x, data["mean"], width=data["bin_width"] * .9, color="#0f766e", alpha=.8, label="Média por réplica")
                ax.set_xlabel(data["xlabel"])
                # Discrete ranges do not interpolate across empty classes.
                ax.errorbar(x, data["mean"], yerr=[np.asarray(data["mean"])-data["lower"],
                            np.asarray(data["upper"])-data["mean"]], fmt="none", capsize=4,
                            color="#60a5fa", alpha=.7, label="Mínimo–máximo entre réplicas (não IC)")
            valid = data["valid_replicas"]
            if isinstance(valid, list):
                title = f"{min(valid)}–{max(valid)} de {payload['replica_count']} réplicas válidas por instante"
            else:
                title = f"{valid}/{payload['replica_count']} réplicas válidas"
            ax.set_title(title)
            ax.legend(fontsize=8)
        else:
            ax.text(.5, .5, "Indisponível: nenhuma observação válida", ha="center", transform=ax.transAxes)
        ax.set_ylabel(data["ylabel"])
        ax.grid(axis="y", alpha=.25)
        fig.tight_layout()
        fig.savefig(charts_dir / paths[key].split("/")[-1], dpi=150)
        plt.close(fig)
