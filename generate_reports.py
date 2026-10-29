"""Build the P100 dashboard and waypoint ranking for the selected scenarios."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

from src.uam_dashboard.run_config import load_run_selection


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("run_config.json"))
    parser.add_argument("--workers", type=int, default=None, help="Worker processes for replica metrics and waypoint reports")
    parser.add_argument("--run-id", help="Select a completed run and save run_config.local.json")
    parser.add_argument("--runs-root", type=Path, help="Run directory root, default ~/runs when selecting a run")
    parser.add_argument("--scenario-codes", nargs="+", help="Restrict selection to these scenario identifiers")
    parser.add_argument("--baseline-manifest", type=Path, help="Compute offline native throughput calibration only; does not regenerate the STATELOG dashboard")
    parser.add_argument("--audit-dir", type=Path, help="Optional server-side passage/window CSVs for baseline calibration")
    args = parser.parse_args()
    if args.workers is not None and args.workers <= 0:
        parser.error("--workers must be positive")
    if args.baseline_manifest is not None:
        if args.run_id is not None or args.runs_root is not None or args.scenario_codes is not None or args.config != Path("run_config.json"):
            parser.error("--baseline-manifest uses its own completed run paths; do not combine with legacy run/config selection")
        from generate_baseline_calibration import generate
        generate(args.baseline_manifest.resolve(), Path(__file__).resolve().parent / "docs", args.audit_dir, workers=args.workers)
        return
    if args.audit_dir is not None:
        parser.error("--audit-dir requires --baseline-manifest")
    repository = Path(__file__).resolve().parent
    config_path = args.config.resolve()
    if args.run_id is not None or args.runs_root is not None or args.scenario_codes is not None:
        settings = json.loads(config_path.read_text(encoding="utf-8"))
        settings.pop("scenario_runs", None)
        if args.run_id is not None:
            settings["run_name"] = args.run_id
        if args.runs_root is not None:
            settings["runs_root"] = str(args.runs_root)
        if args.scenario_codes is not None:
            settings["scenario_codes"] = args.scenario_codes
        # Relative geometry paths refer to the original config, including during
        # provisional validation in a temporary directory.
        def absolute_corridor(value):
            path = Path(value).expanduser()
            return str(path if path.is_absolute() else config_path.parent / path)
        if settings.get("uam_corridor_csv"):
            settings["uam_corridor_csv"] = absolute_corridor(settings["uam_corridor_csv"])
        for key in ("uam_corridor_csv_by_stage", "uam_corridor_csv_by_scenario"):
            if key in settings:
                settings[key] = {code: absolute_corridor(value) for code, value in settings[key].items()}
        destination = repository / "run_config.local.json"
        # Validate before persisting a new selection or changing report files.
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            provisional = Path(directory) / "selection.json"
            provisional.write_text(json.dumps(settings), encoding="utf-8")
            load_run_selection(provisional)
        destination.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
        config_path = destination
    selection = load_run_selection(config_path)
    settings = json.loads(config_path.read_text(encoding="utf-8"))
    if settings.get("run_name") == "auto" and not settings.get("scenario_runs"):
        # Freeze discovery once so a run finishing during dashboard computation
        # cannot change the sources subsequently used by the waypoint ranking.
        settings.update(scenario_codes=list(selection.source_runs), scenario_runs=selection.source_runs,
                        unavailable_scenarios=list(selection.unavailable_scenarios))
        for key in ("uam_corridor_csv_by_stage", "uam_corridor_csv_by_scenario"):
            settings[key] = {code: str(path if (path := Path(value).expanduser()).is_absolute()
                                      else config_path.parent / path)
                             for code, value in settings.get(key, {}).items()}
        config_path = repository / "run_config.local.json"
        config_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    if selection.uam_corridor_csv_path is None:
        raise ValueError("Set uam_corridor_csv in the run configuration before generating reports")
    print(f"Generating P100 reports from {selection.run_dir}", flush=True)
    dashboard_command = [sys.executable, str(repository / "generate_dashboard.py"), "--config", str(config_path)]
    if args.workers is not None:
        dashboard_command.extend(("--workers", str(args.workers)))
    subprocess.run(dashboard_command, cwd=repository, check=True)
    subprocess.run(
        [sys.executable, str(repository / "critical_waypoints.py"), "--config", str(config_path),
         "--workers", str(args.workers if args.workers is not None else selection.ranking_workers)],
        cwd=repository, check=True,
    )
    index_path = repository / "docs" / "index.html"
    html = index_path.read_text(encoding="utf-8")
    for name in ("data_bundle.js", "waypoint_rankings.js", "candidate_nodes.js", "dashboard.js", "dashboard.css", "uam_projection.js", "crossing_waypoints_3d.js", "scenario_catalog.js"):
        asset = repository / "docs" / "assets" / name
        digest = hashlib.sha256(asset.read_bytes()).hexdigest()[:12]
        html, replacements = re.subn(
            rf"(assets/{re.escape(name)}\?v=)[^\"]+",
            lambda match: match.group(1) + digest,
            html,
        )
        if replacements != 1:
            raise ValueError(f"Expected one cache version for {name} in {index_path}")
    index_path.write_text(html, encoding="utf-8")
    from src.uam_dashboard.publication import check_publication
    check_publication(repository / "docs")
    print("Dashboard and waypoint ranking ready in docs/", flush=True)


if __name__ == "__main__":
    main()
