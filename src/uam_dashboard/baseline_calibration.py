"""Native-passage calibration of the four nominal baselines.

All statistics use physical resources, epoch-aligned full windows and independent
replications as bootstrap clusters. No operational capacity is inferred here.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import multiprocessing
import os
import re
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import numpy as np

BASELINES = ("C1.1", "C1.2", "C2.1", "C2.2")
WINDOWS = (300, 900, 3600)
POLICIES = ("positive", "all")
DEFAULT_CRITERIA = {
    "minimum_replications": 30, "confirmation_window": 15,
    "confidence_level": .95, "relative_tolerance": .05,
    "absolute_tolerance_per_hour": 0., "bootstrap_samples": 1000, "seed": 1729,
}

_worker_criteria = None
_worker_weights = None


def validate_workers(workers: int) -> None:
    if type(workers) is not int or workers < 1:
        raise ValueError("workers must be a positive integer")


@contextmanager
def _worker_environment():
    """Spawn numerical workers with one BLAS/OpenMP thread per process."""
    names = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
             "BLIS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS")
    previous = {name: os.environ.get(name) for name in names}
    try:
        os.environ.update(dict.fromkeys(names, "1"))
        yield
    finally:
        for name, value in previous.items():
            if value is None: os.environ.pop(name, None)
            else: os.environ[name] = value


def _initialize_waypoint_worker(criteria, weights):
    global _worker_criteria, _worker_weights
    _worker_criteria, _worker_weights = criteria, weights


def _run_waypoint_worker(task):
    return _analyze_waypoint(task, _worker_criteria, _worker_weights)


def fingerprint(path: Path) -> dict:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {"path": str(path.resolve()), "sha256": digest.hexdigest()}


def resolve_path(value: str, root: Path) -> Path:
    path = Path(value).expanduser()
    return (path if path.is_absolute() else root / path).resolve()


def validate_completed_run(run_dir: Path) -> None:
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    records = summary.get("scenarios", [])
    if summary.get("error") or summary.get("stopped") or not records or any(r.get("status") != "completed" for r in records):
        raise ValueError(f"Run incomplete or failed: {run_dir}")
    lifecycle = run_dir / "lifecycle.json"
    if lifecycle.exists() and json.loads(lifecycle.read_text(encoding="utf-8")).get("status") != "completed":
        raise ValueError(f"Run lifecycle incomplete: {run_dir}")


def load_manifest(path: Path) -> tuple[dict, list[dict]]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    expected = manifest.get("expected_replicas", 50)
    if type(expected) is not int or expected < 1:
        raise ValueError("expected_replicas must be a positive integer")
    entries = manifest.get("replicas", [])
    keys = [(r["scenario"], r["replication"]) for r in entries]
    required = {(code, n) for code in BASELINES for n in range(1, expected + 1)}
    if any(type(n) is not int for _, n in keys) or len(keys) != len(set(keys)) or set(keys) != required:
        raise ValueError("Require exactly the configured replications of C1.1, C1.2, C2.1, C2.2; no duplicates or missing replicas")
    checked = set()
    selected_logs, selected_configs = set(), set()
    result = []
    for item in entries:
        entry = dict(item)
        for field in ("scenario_config", "run_dir", "events_file", "statelog"):
            if entry.get(field): entry[field] = resolve_path(entry[field], path.parent)
        run = entry["run_dir"]
        if run not in checked:
            validate_completed_run(run)
            checked.add(run)
        method = entry.get("passage_source", "native")
        if method not in ("native", "geometric"):
            raise ValueError("passage_source must be native or geometric")
        log = entry.get("events_file" if method == "native" else "statelog")
        if log is None or not log.is_file() or not log.is_relative_to((run / "output").resolve()):
            raise ValueError("Passage/STATELOG must exist inside the completed run's output directory")
        if log in selected_logs or entry["scenario_config"] in selected_configs:
            raise ValueError("Each replication must have a distinct log and scenario configuration")
        selected_logs.add(log); selected_configs.add(entry["scenario_config"])
        named = re.search(r"produto2_(C[12][._][12])_p100_r(\d+)(?:[_.]|$)", log.name, re.I)
        if named and (named[1].upper().replace("_", "."), int(named[2])) != (entry["scenario"], entry["replication"]):
            raise ValueError("Passage filename does not match scenario/replication")
        if method == "geometric" and not manifest.get("allow_geometric_estimate", False):
            raise ValueError("Geometric estimation requires allow_geometric_estimate=true")
        entry["passage_source"] = method
        result.append(entry)
    for code in BASELINES:
        if len({r["passage_source"] for r in result if r["scenario"] == code}) != 1:
            raise ValueError(f"Do not pool native and geometric passages within {code}")
    return manifest, sorted(result, key=lambda r: (r["scenario"], r["replication"]))


def full_window_counts(times: list[float], start: float, end: float, window: int) -> tuple[list[int], dict]:
    """Only [k*w, (k+1)*w) fully inside [start,end) is observed."""
    if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end) or window not in WINDOWS:
        raise ValueError("Invalid observation interval/window")
    first, stop = math.ceil(start / window), math.floor(end / window)
    counts = [0] * max(0, stop - first)
    excluded = 0
    for time in times:
        if not math.isfinite(time) or not start <= time <= end:
            raise ValueError("Passage outside declared completed observation interval")
        bucket = math.floor(time / window)
        if first <= bucket < stop: counts[bucket - first] += 1
        else: excluded += 1
    return counts, {"full_windows": len(counts), "excluded_partial_seconds": end - start - len(counts) * window,
                    "excluded_passages": excluded, "first_window_start_s": first * window}


def read_replica(entry: dict, radius_m: float = 250.) -> dict:
    config = json.loads(entry["scenario_config"].read_text(encoding="utf-8"))
    product = config["product2"]
    if product.get("scenario") != entry["scenario"] or product["replication"]["index"] != entry["replication"]:
        raise ValueError("Scenario configuration does not match manifest scenario/replication")
    if product.get("traffic_management") != "none":
        raise ValueError("Calibration only accepts unmanaged baselines")
    catalog = product["resource_manifest"]
    if catalog.get("capacity_key") != "physical_point_track":
        raise ValueError("Require physical_point_track resource identity")
    eligible = {rid: r for rid, r in catalog["resources"].items() if r.get("eligible") is True}
    if not eligible: raise ValueError("No eligible physical waypoints")
    for rid, resource in eligible.items():
        if resource.get("resource_id") != rid or resource.get("kind") != "named_reh":
            raise ValueError("Eligible resource identity/kind mismatch")
    start = float(entry.get("observation_start_s", 0))
    end = float(entry.get("observation_end_s", config["simulation_duration_sec"]))
    if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end <= float(config["simulation_duration_sec"])):
        raise ValueError("Observation interval exceeds completed scenario duration")
    events = {rid: [] for rid in eligible}
    passage_events = []
    provenance = {"scenario_config": fingerprint(entry["scenario_config"]), "passage_source": entry["passage_source"],
                  "run_dir": str(entry["run_dir"]), "observation_start_s": start, "observation_end_s": end}
    if entry["passage_source"] == "native":
        expected = {(flight, visit["route_index"]): visit["resource_id"]
                    for flight, visits in catalog["flights"].items() for visit in visits if visit["eligible"]}
        seen = set()
        with entry["events_file"].open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if not {"time_s", "flight_id", "resource_id", "occurrence"} <= set(reader.fieldnames or []):
                raise ValueError("Invalid WPPASS header")
            for row in reader:
                key = row["flight_id"], int(row["occurrence"])
                rid = row["resource_id"]
                if key in seen or expected.get(key) != rid or rid not in eligible:
                    raise ValueError("Duplicate, unknown or mismatched native passage occurrence")
                time = float(row["time_s"])
                if not math.isfinite(time) or not 0 <= time <= float(config["simulation_duration_sec"]):
                    raise ValueError("Invalid native passage time")
                seen.add(key)
                if start <= time <= end:
                    events[rid].append(time)
                    passage_events.append({"waypoint_id": rid, "time_s": time, "flight_id": row["flight_id"],
                                           "occurrence": key[1], "flight_instance": None})
        if seen != set(expected):
            raise ValueError(f"Incomplete WPPASS: {len(seen)}/{len(expected)} planned eligible occurrences")
        provenance["events_file"] = fingerprint(entry["events_file"])
        provenance["validated_native_occurrences"] = len(seen)
    else:
        from critical_waypoints import process_replica
        features = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
                     "properties": {"resource_id": rid, "network": r["network"], "altitude_m": r["altitude_ft"] * .3048}}
                    for rid, r in eligible.items()]
        rows = process_replica(entry["statelog"], features, radius_m, 300, 300., 250., 5000.)
        # STATELOG coverage is narrower than the declared simulation interval.
        from critical_waypoints import state_rows
        first = last = None
        for row in state_rows(entry["statelog"]):
            if first is None: first = row[0]
            last = row[0]
        start, end = max(start, first), min(end, last)
        if start >= end: raise ValueError("No observed STATELOG interval")
        for row in rows:
            events[row["waypoint_id"]] = [e["time_s"] for e in row["passage_events"] if start <= e["time_s"] <= end]
            passage_events.extend({"waypoint_id": row["waypoint_id"], "time_s": event["time_s"],
                                   "flight_id": event["aircraft"], "occurrence": None,
                                   "flight_instance": event["flight_instance"]}
                                  for event in row["passage_events"] if start <= event["time_s"] <= end)
        provenance.update(statelog=fingerprint(entry["statelog"]), radius_m=radius_m,
                          gap_seconds=300, reset_distance_m=250, jump_m=5000,
                          observation_start_s=start, observation_end_s=end,
                          ambiguous_encounters=sum(r["ambiguous_encounters"] for r in rows))
    return {"scenario": entry["scenario"], "replication": entry["replication"], "resources": eligible,
            "events": events, "start": start, "end": end, "provenance": provenance,
            "passage_events": passage_events,
            "seeds": {k: product["replication"].get(k) for k in ("seed", "helicopter_seed", "evtol_seed")}}


def quantile_hist(hist: np.ndarray, q: float = .95) -> np.ndarray:
    """NumPy 'higher' percentile from integer-count histograms, including batches."""
    hist = np.atleast_2d(hist)
    totals = hist.sum(axis=1)
    ranks = np.ceil(q * np.maximum(totals - 1, 0))
    values = (np.cumsum(hist, axis=1) > ranks[:, None]).argmax(axis=1).astype(float)
    values[totals == 0] = np.nan
    return values


def estimate(counts: list[list[int]], window: int, policy: str, criteria: dict, weights: dict) -> dict:
    max_count = max((max(row, default=0) for row in counts), default=0)
    hist = np.array([np.bincount(row, minlength=max_count + 1) for row in counts], dtype=np.int64)
    if policy == "positive": hist[:, 0] = 0
    factor = 3600 / window
    trace = []
    consecutive = 0
    confirmed = None
    mean_consecutive = 0
    mean_confirmed = None
    cumulative = hist.cumsum(axis=0)
    for n, pooled in enumerate(cumulative, 1):
        windows = int(pooled.sum())
        p95 = float(quantile_hist(pooled)[0]) * factor if windows else None
        # An unused resource cannot establish capacity or convergence.
        used = bool(pooled[1:].sum())
        value = p95 if used else None
        ci = None
        mean_ci = None
        met = False
        mean_met = False
        mean_rate = float(np.dot(pooled, np.arange(len(pooled))) / windows * factor) if windows else None
        if n >= criteria["minimum_replications"] and used and all(len(row) for row in counts[:n]):
            boot_hist = weights[n] @ hist[:n]
            boot = quantile_hist(boot_hist) * factor
            # Sparse resamples with no positive windows do not provide evidence.
            if np.isfinite(boot).all():
                alpha = (1 - criteria["confidence_level"]) / 2
                ci = [float(x) for x in np.quantile(boot, [alpha, 1 - alpha])]
                boot_mean = (boot_hist @ np.arange(hist.shape[1])) / boot_hist.sum(axis=1) * factor
                mean_ci = [float(x) for x in np.quantile(boot_mean, [alpha, 1 - alpha])]
                tolerance = max(criteria["absolute_tolerance_per_hour"], abs(value) * criteria["relative_tolerance"])
                met = max(value - ci[0], ci[1] - value) <= tolerance
                mean_tolerance = max(criteria["absolute_tolerance_per_hour"], abs(mean_rate) * criteria["relative_tolerance"])
                mean_met = max(mean_rate - mean_ci[0], mean_ci[1] - mean_rate) <= mean_tolerance
        consecutive = consecutive + 1 if met else 0
        mean_consecutive = mean_consecutive + 1 if mean_met else 0
        if confirmed is None and consecutive >= criteria["confirmation_window"]: confirmed = n
        if mean_confirmed is None and mean_consecutive >= criteria["confirmation_window"]: mean_confirmed = n
        trace.append({"replicas": n, "p95_per_hour": value, "mean_per_hour": mean_rate,
                      "ci95": ci, "mean_ci95": mean_ci, "criterion_met": bool(met), "mean_criterion_met": bool(mean_met)})
    last = trace[-1]
    sufficient = all(len(row) for row in counts)
    return {"p95_per_hour": last["p95_per_hour"] if sufficient else None,
            "p95_operations_per_window": last["p95_per_hour"] / factor if sufficient and last["p95_per_hour"] is not None else None,
            "mean_per_hour": last["mean_per_hour"] if sufficient else None, "peak_per_hour": max_count * factor if sufficient else None,
            "window_count": int(hist.sum()), "positive_window_count": int(hist[:, 1:].sum()),
            "replicas_with_full_windows": sum(bool(row) for row in counts),
            "status": "insufficient_full_windows" if not sufficient else "observed" if last["p95_per_hour"] is not None else "no_observed_use",
            "ci95": last["ci95"], "confirmed_at_n": confirmed,
            "mean_ci95": last["mean_ci95"], "mean_confirmed_at_n": mean_confirmed,
            "mean_stable_at_final": bool(mean_confirmed is not None and mean_consecutive >= criteria["confirmation_window"]),
            "stable_at_final": bool(confirmed is not None and consecutive >= criteria["confirmation_window"]),
            "convergence": trace}


def _analyze_waypoint(task: tuple, criteria: dict, weights_by_scenario: dict) -> tuple:
    scenario, metadata, observations = task
    record = {**metadata, "estimates": {}, "coverage": {}}
    for window in WINDOWS:
        per_replica = []
        coverage = []
        for replication, start, end, times in observations:
            counts, audit = full_window_counts(times, start, end, window)
            per_replica.append(counts)
            coverage.append({"replication": replication, **audit})
        record["coverage"][str(window)] = coverage
        for policy in POLICIES:
            record["estimates"][f"{window}:{policy}"] = estimate(
                per_replica, window, policy, criteria, weights_by_scenario[scenario]
            )
    return scenario, record


def analyze(replicas: list[dict], criteria: dict | None = None, workers: int = 1) -> tuple:
    validate_workers(workers)
    criteria = {**DEFAULT_CRITERIA, **(criteria or {})}
    for key in ("minimum_replications", "confirmation_window", "bootstrap_samples", "seed"):
        if type(criteria[key]) is not int or criteria[key] < (0 if key == "seed" else 1): raise ValueError(f"Invalid {key}")
    if criteria["bootstrap_samples"] < 100 or not 0 < criteria["confidence_level"] < 1:
        raise ValueError("Require bootstrap_samples>=100 and 0<confidence_level<1")
    for key in ("relative_tolerance", "absolute_tolerance_per_hour"):
        if not math.isfinite(criteria[key]) or criteria[key] < 0: raise ValueError(f"Invalid {key}")
    result = {"schema_version": 1, "windows_seconds": list(WINDOWS), "epoch_seconds": 0,
              "quantile_method": "higher", "capacity_key": "physical_point_track", "operational_capacity_proven": False,
              "criteria": criteria, "uncertainty_method": "percentile_bootstrap_replication_clusters",
              "scenarios": {}}
    rng = np.random.default_rng(criteria["seed"])
    weights_by_scenario = {}
    tasks = []
    for scenario in BASELINES:
        rows = sorted((r for r in replicas if r["scenario"] == scenario), key=lambda r: r["replication"])
        if not rows: raise ValueError(f"Missing {scenario}")
        catalog = {}
        for row in rows:
            for rid, resource in row["resources"].items():
                if rid in catalog and any(catalog[rid].get(k) != resource.get(k) for k in ("lat", "lon", "altitude_ft", "network", "reh_id")):
                    raise ValueError(f"Physical resource identity changed: {rid}")
                catalog[rid] = resource
        weights = {n: rng.multinomial(n, np.full(n, 1/n), size=criteria["bootstrap_samples"]).astype(float)
                   for n in range(criteria["minimum_replications"], len(rows) + 1)}
        weights_by_scenario[scenario] = weights
        output = {"replica_count": len(rows), "passage_source": rows[0]["provenance"]["passage_source"],
                  "provenance": [{"replication": r["replication"], **r["provenance"]} for r in rows], "resources": []}
        print(f"Calibrating {scenario}: {len(rows)} replicas, {len(catalog)} physical waypoints", flush=True)
        for rid, resource in sorted(catalog.items()):
            metadata = {"waypoint_id": rid, "label": resource.get("reh_name") or resource.get("source_waypoint_name") or rid,
                        "network": resource.get("network"), "lat": resource["lat"], "lon": resource["lon"],
                        "altitude_ft": resource.get("altitude_ft")}
            observations = [(row["replication"], row["start"], row["end"], row["events"].get(rid, [])) for row in rows]
            tasks.append((scenario, metadata, observations))
        result["scenarios"][scenario] = output
    # Pairing is checked on requested-demand seeds, never assumed by scenario name alone.
    for stage in ("1", "2"):
        left = [r for r in replicas if r["scenario"] == f"C1.{stage}"]
        right = {r["replication"]: r for r in replicas if r["scenario"] == f"C2.{stage}"}
        if any(r["seeds"] != right[r["replication"]]["seeds"] or any(v is None for v in r["seeds"].values()) for r in left):
            raise ValueError(f"Baseline seeds are not paired for stage {stage}")
    worker_count = min(workers, len(tasks))
    print(f"Analyzing {len(tasks)} physical waypoints with {worker_count} worker processes...", flush=True)

    def collect(results):
        # executor.map preserves input order, independent of completion order.
        for completed, (scenario, record) in enumerate(results, 1):
            result["scenarios"][scenario]["resources"].append(record)
            if completed % 50 == 0 or completed == len(tasks):
                print(f"Completed {completed}/{len(tasks)} physical waypoints", flush=True)

    if worker_count == 1:
        collect(_analyze_waypoint(task, criteria, weights_by_scenario) for task in tasks)
    else:
        # The bootstrap draws are generated once above, in the same order as the
        # serial implementation, and initialized once per worker. Tasks contain
        # only one waypoint's observations, never entire logs or replica catalogs.
        with _worker_environment():
            with ProcessPoolExecutor(
                max_workers=worker_count,
                mp_context=multiprocessing.get_context("spawn"),
                initializer=_initialize_waypoint_worker,
                initargs=(criteria, weights_by_scenario),
            ) as pool:
                collect(pool.map(_run_waypoint_worker, tasks, chunksize=1))
    return result, iter_windows(replicas), iter_passages(replicas)


def iter_passages(replicas):
    for row in replicas:
        for event in row["passage_events"]:
            yield {"scenario": row["scenario"], "replication": row["replication"], **event}


def iter_windows(replicas):
    # Sparse audit: coverage in calibration.json defines the omitted zero bins.
    for row in replicas:
        for rid, times in row["events"].items():
            for window in WINDOWS:
                counts, audit = full_window_counts(times, row["start"], row["end"], window)
                for index, count in enumerate(counts):
                    if count:
                        yield {"scenario": row["scenario"], "replication": row["replication"], "waypoint_id": rid,
                               "window_seconds": window, "window_start_s": audit["first_window_start_s"] + index * window,
                               "operations": count, "throughput_per_hour": count * 3600/window}


def iter_replica_metrics(replicas):
    catalogs = {code: set().union(*(set(r["resources"]) for r in replicas if r["scenario"] == code)) for code in BASELINES}
    for row in replicas:
        for rid in sorted(catalogs[row["scenario"]]):
            for window in WINDOWS:
                counts, coverage = full_window_counts(row["events"].get(rid, []), row["start"], row["end"], window)
                for policy in POLICIES:
                    selected = [count for count in counts if count > 0 or policy == "all"]
                    yield {"scenario": row["scenario"], "replication": row["replication"], "waypoint_id": rid,
                           "window_seconds": window, "zero_policy": policy, "window_count": len(selected),
                           "operations_in_full_windows": sum(counts), "positive_window_count": sum(c > 0 for c in counts),
                           "mean_per_hour": float(np.mean(selected)) * 3600/window if selected else None,
                           "p95_per_hour": float(np.quantile(selected, .95, method="higher")) * 3600/window if any(selected) else None,
                           **coverage}


def write_csv(path: Path, rows) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        iterator = iter(rows)
        first = next(iterator, None)
        if first is None: return
        writer = csv.DictWriter(stream, fieldnames=list(first))
        writer.writeheader(); writer.writerow(first); writer.writerows(iterator)


def write_charts(result: dict, destination: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator
    values = [e["p95_per_hour"] for s in result["scenarios"].values() for r in s["resources"]
              for e in r["estimates"].values() if e["p95_per_hour"] is not None and e["status"] == "observed"]
    upper = max(values, default=12.)
    edges = np.linspace(0, max(12., (math.floor(upper / 12) + 1) * 12), 21)
    result["histogram_edges_per_hour"] = edges.tolist()
    for code, scenario in result["scenarios"].items():
        scenario["charts"] = {}
        for policy in POLICIES:
            for kind in ("histogram", "cdf"):
                fig, axes = plt.subplots(1, 3, figsize=(14, 4), sharex=True, sharey=True)
                for window, ax in zip(WINDOWS, axes):
                    estimates = [r["estimates"][f"{window}:{policy}"] for r in scenario["resources"]]
                    x = sorted(e["p95_per_hour"] for e in estimates if e["status"] == "observed")
                    if kind == "histogram":
                        ax.hist(x, bins=edges, color="#2563eb", edgecolor="white")
                        ax.yaxis.set_major_locator(MaxNLocator(integer=True))
                    elif x:
                        ax.step([0, *x, edges[-1]], [0, *(np.arange(1, len(x)+1) / len(x) * 100), 100],
                                where="post", color="#0f766e")
                        ax.set_ylim(0, 100)
                    else:
                        ax.text(.5, .5, "Sem estimativas", transform=ax.transAxes, ha="center")
                    noun = "waypoint com estimativa" if len(x) == 1 else "waypoints com estimativa"
                    ax.set_title(f"{window//60} min · {len(x)} {noun}")
                    ax.set_xlabel("Referência empírica P95 (operações/h)")
                    ax.set_xlim(edges[0], edges[-1]); ax.grid(axis="y", alpha=.2)
                axes[0].set_ylabel("Quantidade de waypoints" if kind == "histogram" else "Waypoints acumulados (%)")
                fig.suptitle(f"{code} · {'Janelas positivas' if policy == 'positive' else 'Todas as janelas completas'}")
                fig.tight_layout()
                filename = f"{code}_{policy}_{kind}.png"
                fig.savefig(destination / filename, dpi=150); plt.close(fig)
                scenario["charts"][f"{policy}:{kind}"] = f"assets/data/baseline_calibration/{filename}"


def publish(result: dict, window_rows, passage_rows, output_dir: Path, audit_dir: Path | None = None, replicas=None) -> None:
    destination = output_dir / "assets/data/baseline_calibration"
    destination.mkdir(parents=True, exist_ok=True)
    write_charts(result, destination)
    if audit_dir is not None:
        audit_dir.mkdir(parents=True, exist_ok=True)
        write_csv(audit_dir / "positive_windows.csv", window_rows)
        write_csv(audit_dir / "passages.csv", passage_rows)
    comparisons, convergence = [], []
    for code, scenario in result["scenarios"].items():
        for resource in scenario["resources"]:
            for key, estimate_ in resource["estimates"].items():
                window, policy = key.split(":")
                base = {"scenario": code, "waypoint_id": resource["waypoint_id"], "label": resource["label"],
                        "window_seconds": int(window), "zero_policy": policy}
                comparisons.append({**base, **{k: v for k, v in estimate_.items() if k not in ("convergence", "ci95", "mean_ci95")},
                                    "ci_lower": estimate_["ci95"][0] if estimate_["ci95"] else None,
                                    "ci_upper": estimate_["ci95"][1] if estimate_["ci95"] else None,
                                    "mean_ci_lower": estimate_["mean_ci95"][0] if estimate_["mean_ci95"] else None,
                                    "mean_ci_upper": estimate_["mean_ci95"][1] if estimate_["mean_ci95"] else None})
                convergence.extend({**base, **{k: v for k, v in point.items() if k not in ("ci95", "mean_ci95")},
                                    "ci_lower": point["ci95"][0] if point["ci95"] else None,
                                    "ci_upper": point["ci95"][1] if point["ci95"] else None,
                                    "mean_ci_lower": point["mean_ci95"][0] if point["mean_ci95"] else None,
                                    "mean_ci_upper": point["mean_ci95"][1] if point["mean_ci95"] else None} for point in estimate_["convergence"])
    write_csv(destination / "comparison.csv", comparisons)
    write_csv(destination / "convergence.csv", convergence)
    if replicas is not None: write_csv(destination / "replica_metrics.csv", iter_replica_metrics(replicas))
    # Avoid repeating field names hundreds of thousands of times in the static
    # bundle. CSV exports remain explicit, and column metadata makes JSON lossless.
    trace_columns = ["replicas", "p95_per_hour", "mean_per_hour", "ci95", "mean_ci95", "criterion_met", "mean_criterion_met"]
    coverage_columns = ["replication", "full_windows", "excluded_partial_seconds", "excluded_passages", "first_window_start_s"]
    result["trace_columns"] = trace_columns
    result["coverage_columns"] = coverage_columns
    for scenario in result["scenarios"].values():
        for resource in scenario["resources"]:
            for estimate_ in resource["estimates"].values():
                estimate_["convergence"] = [[point[key] for key in trace_columns] for point in estimate_["convergence"]]
            resource["coverage"] = {window: [[point[key] for key in coverage_columns] for point in points]
                                    for window, points in resource["coverage"].items()}
    serialized = json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    (destination / "calibration.json").write_text(serialized, encoding="utf-8")
    (output_dir / "assets/baseline_calibration_data.js").write_text("window.__BASELINE_CALIBRATION__=" + serialized + ";\n", encoding="utf-8")
