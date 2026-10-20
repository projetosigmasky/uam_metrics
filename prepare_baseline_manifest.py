"""Match nominal source JSONs to completed Lessonia runs, with no positional guesses."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from src.uam_dashboard.baseline_calibration import BASELINES, load_manifest, validate_completed_run


def identity(name: str):
    match = re.search(r"(?:^|_)produto2_(C[12][._][12])_p100_r(\d+)(?:[_.]|$)", name, re.I)
    return (match[1].upper().replace("_", "."), int(match[2])) if match else None


def prepare(scenario_root: Path, runs: list[Path], expected: int = 50) -> dict:
    configs, events = {}, {}
    required = {(code, n) for code in BASELINES for n in range(1, expected + 1)}
    for path in sorted(scenario_root.rglob("*.json")):
        key = identity(path.stem)
        if key not in required: continue
        if key in configs: raise ValueError(f"Ambiguous scenario configs: {key}")
        configs[key] = path.resolve()
    for run in runs:
        run = run.expanduser().resolve()
        validate_completed_run(run)
        for path in sorted((run / "output").rglob("WPPASS*.csv")):
            key = identity(path.stem)
            if key not in required: continue
            if key in events: raise ValueError(f"Multiple WPPASS files for {key}; select one completed batch")
            events[key] = run, path.resolve()
    if set(configs) != required or set(events) != required:
        raise ValueError(f"Missing configurations: {sorted(required-set(configs))}; missing WPPASS: {sorted(required-set(events))}")
    return {"schema_version": 1, "expected_replicas": expected, "replicas": [
        {"scenario": code, "replication": n, "scenario_config": str(configs[code, n]),
         "run_dir": str(events[code, n][0]), "events_file": str(events[code, n][1]), "passage_source": "native"}
        for code, n in sorted(required)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario-root", required=True, type=Path)
    parser.add_argument("--run-dirs", nargs="+", required=True, type=Path)
    parser.add_argument("--expected-replicas", type=int, default=50)
    parser.add_argument("--output", type=Path, default=Path("baseline_manifest.local.json"))
    args = parser.parse_args()
    if args.expected_replicas < 1: parser.error("expected-replicas must be positive")
    manifest = prepare(args.scenario_root.expanduser(), args.run_dirs, args.expected_replicas)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Path fields are absolute, so validation does not depend on temporary locations.
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        candidate = Path(directory) / "manifest.json"
        candidate.write_text(json.dumps(manifest), encoding="utf-8")
        load_manifest(candidate)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Validated {len(manifest['replicas'])} replicas: {args.output}")


if __name__ == "__main__": main()
