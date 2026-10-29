"""Resolve and validate orchestrator runs for dashboard generation."""

from __future__ import annotations

import json
import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path

from src.uam_dashboard.experiment import log_experiment_metadata, matching_scenario, scenario_stage, scenario_airspace
from .scenario_catalog import NOMINAL_CODES


@dataclass(frozen=True)
class RunSelection:
    run_dir: Path
    log_paths: tuple[Path, ...]
    scenario_paths: tuple[Path, ...]
    dashboard_workers: int
    ranking_workers: int
    uam_corridor_csv_path: Path | None = None
    uam_corridor_csv_by_scenario: dict[str, Path] = field(default_factory=dict)
    source_runs: dict[str, str] = field(default_factory=dict)
    unavailable_scenarios: tuple[str, ...] = ()


def load_run_selection(config_path: Path) -> RunSelection:
    settings = json.loads(config_path.read_text(encoding="utf-8"))
    if settings.get("run_name") == "auto":
        return discover_nominal_runs(settings, config_path)
    return _load_single_run(settings, config_path)


def discover_nominal_runs(settings: dict, config_path: Path) -> RunSelection:
    """Choose the newest complete, validated run for each nominal variant.

    Never pool replicas from different runs or substitute older micro IDs.
    """
    root = Path(settings.get("runs_root", "~/runs")).expanduser()
    codes = settings.get("scenario_codes", list(NOMINAL_CODES))
    if not codes or len(codes) != len(set(codes)) or set(codes) - set(NOMINAL_CODES):
        raise ValueError("Automatic discovery requires distinct canonical nominal scenario_codes")
    if not root.is_dir():
        raise FileNotFoundError(f"Runs directory not found: {root}")
    candidates = sorted((p for p in root.iterdir() if p.is_dir() and (p / "summary.json").is_file()),
                        key=lambda p: p.name, reverse=True)
    selections = {}
    rejected = []
    pinned = settings.get("scenario_runs")
    if pinned is not None and (not isinstance(pinned, dict) or set(pinned) != set(codes)):
        raise ValueError("scenario_runs must select exactly one run for every requested scenario")
    if pinned is not None and any(not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name)
                                  for name in pinned.values()):
        raise ValueError("scenario_runs values must be run directory names")
    for code in codes:
        for run in ([root / pinned[code]] if pinned is not None else candidates):
            if not any((run / "output" / name).is_dir() for name in (code, code.replace(".", "_"))):
                continue
            try:
                selections[code] = _load_single_run(dict(settings, run_name=run.name, scenario_codes=[code]), config_path)
            except (ValueError, OSError) as error:
                rejected.append(f"{run.name}/{code}: {error}")
                continue
            break
    missing = tuple(code for code in codes if code not in selections)
    if not selections or (missing and (pinned is not None or settings.get("require_all_scenarios", False))):
        raise ValueError(f"No complete selection; unavailable scenarios: {', '.join(missing)}. " + " | ".join(rejected))
    if missing:
        warnings.warn("Nominal scenarios awaiting complete results: " + ", ".join(missing), stacklevel=2)
    for message in rejected:
        warnings.warn("Skipped " + message, stacklevel=2)
    first = next(iter(selections.values()))
    for code, selected in selections.items():
        print(f"{code}: {selected.run_dir.name} ({len(selected.log_paths)} replicas)", flush=True)
    return RunSelection(root, tuple(p for s in selections.values() for p in s.log_paths),
                        tuple(p for s in selections.values() for p in s.scenario_paths),
                        first.dashboard_workers, first.ranking_workers, first.uam_corridor_csv_path,
                        {code: s.uam_corridor_csv_by_scenario[code] for code, s in selections.items()},
                        {code: s.run_dir.name for code, s in selections.items()}, missing)


def _load_single_run(settings: dict, config_path: Path) -> RunSelection:
    run_name = settings.get("run_name")
    if not isinstance(run_name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", run_name) or run_name in {".", ".."}:
        raise ValueError("run_name must be one run directory name, without path separators")
    runs_root = Path(settings.get("runs_root", "~/runs")).expanduser()
    run_dir = runs_root / run_name
    summary_path = run_dir / "summary.json"
    if not summary_path.is_file():
        raise ValueError(f"Run has no completion summary: {run_dir}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    records = summary.get("scenarios", [])
    if summary.get("error") or summary.get("stopped") or not records or any(item.get("status") != "completed" for item in records):
        raise ValueError(f"Run is incomplete or failed: {run_dir}")
    lifecycle_path = run_dir / "lifecycle.json"
    if lifecycle_path.is_file() and json.loads(lifecycle_path.read_text(encoding="utf-8")).get("status") != "completed":
        raise ValueError(f"Run lifecycle is not completed: {run_dir}")
    scenario_dir = run_dir / "scenario"
    if not scenario_dir.is_dir():
        raise FileNotFoundError(f"Orchestrator scenario directory not found: {scenario_dir}")
    scenario_paths = tuple(sorted(scenario_dir.rglob("*.scn")))
    if not scenario_paths:
        raise FileNotFoundError(f"No SCN files found in {scenario_dir}")

    expected = settings.get("expected_replicas_per_scenario", 50)
    if not isinstance(expected, int) or isinstance(expected, bool) or expected <= 0:
        raise ValueError("expected_replicas_per_scenario must be a positive integer")
    dashboard_workers = settings.get("dashboard_workers", 1)
    ranking_workers = settings.get("ranking_workers", 1)
    for name, value in (("dashboard_workers", dashboard_workers), ("ranking_workers", ranking_workers)):
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ValueError(f"{name} must be a positive integer")
    log_paths = []
    scenario_codes = settings.get("scenario_codes") or sorted({
        p.name.upper().replace("_", ".") for p in (run_dir / "output").iterdir()
        if p.is_dir() and re.fullmatch(r"C\d+(?:[._]\d+)*", p.name, re.I)
    })
    if not scenario_codes or len(set(scenario_codes)) != len(scenario_codes) or any(not re.fullmatch(r"C\d+(?:\.\d+)*", code) for code in scenario_codes):
        raise ValueError("scenario_codes must contain distinct scenario identifiers")
    for scenario_key in scenario_codes:
        output_dir = run_dir / "output" / scenario_key
        if not output_dir.is_dir():
            output_dir = run_dir / "output" / scenario_key.replace(".", "_")
        if not output_dir.is_dir():
            raise FileNotFoundError(f"Orchestrator output directory not found: {output_dir}")
        selected = sorted(
            path for path in output_dir.iterdir()
            if path.is_file() and path.name.upper().startswith("STATELOG") and path.suffix.lower() in {".log", ".csv"}
        )
        if len(selected) != expected:
            raise ValueError(f"{scenario_key}: expected {expected} STATELOGs, found {len(selected)} in {output_dir}")
        log_paths.extend(selected)

    matched_scenarios = []
    for log_path in log_paths:
        metadata = log_experiment_metadata(log_path, scenario_paths)
        if (metadata.get("day_key"), metadata.get("scenario_key"), metadata.get("mvp_enabled")) != (
            "produto2_p100", log_path.parent.name.upper().replace("_", "."), False
        ):
            raise ValueError(f"Expected a P100/off replica of {log_path.parent.name}: {log_path}")
        scenario = matching_scenario(log_path, scenario_paths)
        if scenario is None:
            raise ValueError(f"No unique P100 SCN matched STATELOG: {log_path}")
        matched_scenarios.append(scenario)
    if len(set(matched_scenarios)) != len(log_paths):
        raise ValueError("Each STATELOG must match a distinct SCN from the same orchestrator run")
    for code in scenario_codes:
        if "." not in code:
            continue
        replica_numbers = {log_experiment_metadata(log, scenario_paths).get("replica")
                           for log in log_paths if log.parent.name.upper().replace("_", ".") == code}
        if replica_numbers != set(range(1, expected + 1)):
            raise ValueError(f"{code}: require exactly replicas 1..{expected}, found {sorted(replica_numbers, key=repr)}")
    def resolve_corridor(value):
        path = Path(value).expanduser()
        return path if path.is_absolute() else config_path.resolve().parent / path
    by_stage = settings.get("uam_corridor_csv_by_stage", {})
    by_scenario = {code: resolve_corridor(value) for code, value in settings.get("uam_corridor_csv_by_scenario", {}).items()}
    for code in scenario_codes:
        stage = scenario_stage(code)
        if code not in by_scenario and stage in by_stage:
            by_scenario[code] = resolve_corridor(by_stage[stage])
    if by_scenario:
        missing = set(scenario_codes) - set(by_scenario)
        if missing: raise ValueError(f"Select a corridor CSV explicitly for: {sorted(missing)}")
        from .uam_corridor_parser import load_uam_corridor_network
        from .corridor_validation import validate_c2_corridor_scenarios
        for code in scenario_codes:
            network = load_uam_corridor_network(by_scenario[code])
            stage = scenario_stage(code)
            if stage and len(network["vertiports"]) != {"1": 6, "2": 12}[stage]:
                raise ValueError(f"Wrong vertiport count for {code}: {by_scenario[code]}")
            if scenario_airspace(code) == "dedicated_uam":
                validate_c2_corridor_scenarios([s for log, s in zip(log_paths, matched_scenarios)
                                               if log_experiment_metadata(log, scenario_paths)["scenario_key"] == code], network["routes"])
        return RunSelection(run_dir, tuple(log_paths), tuple(matched_scenarios), dashboard_workers, ranking_workers,
                            by_scenario[scenario_codes[0]], by_scenario,
                            {code: run_dir.name for code in scenario_codes})
    if any("." in code for code in scenario_codes):
        raise ValueError("Dotted scenarios require uam_corridor_csv_by_stage or uam_corridor_csv_by_scenario")
    corridor = settings.get("uam_corridor_csv")
    corridor_path = Path(corridor).expanduser() if corridor else None
    if corridor_path is not None:
        if not corridor_path.is_absolute(): corridor_path = config_path.resolve().parent / corridor_path
        from .uam_corridor_parser import load_uam_corridor_network
        expected = settings.get("expected_vertiports")
        load_uam_corridor_network(corridor_path, set(expected) if expected else None)
        from .corridor_validation import validate_c2_corridor_scenarios
        c2_scenarios = [scenario for log, scenario in zip(log_paths, matched_scenarios) if log.parent.name == "C2"]
        validate_c2_corridor_scenarios(c2_scenarios, load_uam_corridor_network(corridor_path)["routes"])
        if settings.get("uam_corridor_sha256"):
            import hashlib
            if hashlib.sha256(corridor_path.read_bytes()).hexdigest() != settings["uam_corridor_sha256"]:
                raise ValueError("Corridor source hash differs from run configuration")
    return RunSelection(run_dir, tuple(log_paths), scenario_paths, dashboard_workers, ranking_workers, corridor_path)
