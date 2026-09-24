"""Resolve and validate one orchestrator run for dashboard generation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from src.uam_dashboard.experiment import log_experiment_metadata, matching_scenario


@dataclass(frozen=True)
class RunSelection:
    run_dir: Path
    log_paths: tuple[Path, ...]
    scenario_paths: tuple[Path, ...]


def load_run_selection(config_path: Path) -> RunSelection:
    settings = json.loads(config_path.read_text(encoding="utf-8"))
    run_name = settings.get("run_name")
    if not isinstance(run_name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", run_name) or run_name in {".", ".."}:
        raise ValueError("run_name must be one run directory name, without path separators")
    runs_root = Path(settings.get("runs_root", "~/bluesky-orchestrator/runs")).expanduser()
    run_dir = runs_root / run_name
    scenario_dir = run_dir / "scenario"
    if not scenario_dir.is_dir():
        raise FileNotFoundError(f"Orchestrator scenario directory not found: {scenario_dir}")
    scenario_paths = tuple(sorted(scenario_dir.rglob("*.scn")))
    if not scenario_paths:
        raise FileNotFoundError(f"No SCN files found in {scenario_dir}")

    expected = settings.get("expected_replicas_per_scenario", 50)
    if not isinstance(expected, int) or isinstance(expected, bool) or expected <= 0:
        raise ValueError("expected_replicas_per_scenario must be a positive integer")
    log_paths = []
    for scenario_key in ("C1", "C2"):
        output_dir = run_dir / "output" / scenario_key
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
            "produto2_p100", log_path.parent.name, False
        ):
            raise ValueError(f"Expected a P100/off replica of {log_path.parent.name}: {log_path}")
        scenario = matching_scenario(log_path, scenario_paths)
        if scenario is None:
            raise ValueError(f"No unique P100 SCN matched STATELOG: {log_path}")
        matched_scenarios.append(scenario)
    if len(set(matched_scenarios)) != len(log_paths):
        raise ValueError("Each STATELOG must match a distinct SCN from the same orchestrator run")
    return RunSelection(run_dir, tuple(log_paths), scenario_paths)
