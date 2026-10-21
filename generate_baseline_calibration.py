"""Calibrate C1.1/C1.2/C2.1/C2.2 from a validated manifest, without rerunning BlueSky."""
from __future__ import annotations

import argparse
import math
from pathlib import Path

from src.uam_dashboard.baseline_calibration import analyze, fingerprint, load_manifest, publish, read_replica, validate_workers


def generate(manifest_path: Path, output_dir: Path, audit_dir: Path | None = None, workers: int | None = None) -> dict:
    if workers is not None: validate_workers(workers)
    manifest, entries = load_manifest(manifest_path)
    worker_count = manifest.get("workers", 1) if workers is None else workers
    validate_workers(worker_count)
    replicas = []
    radius = float(manifest.get("capture_radius_m", 250))
    if radius <= 0 or not math.isfinite(radius): raise ValueError("Invalid capture_radius_m")
    for index, entry in enumerate(entries, 1):
        print(f"Reading {index}/{len(entries)}: {entry['scenario']} r{entry['replication']:03d}", flush=True)
        replicas.append(read_replica(entry, radius))
    print("Computing pooled P95 and replication-cluster bootstrap...", flush=True)
    result, windows, passages = analyze(replicas, manifest.get("stability"), workers=worker_count)
    result["manifest"] = fingerprint(manifest_path)
    # Publish only after every replica and its native occurrences were validated.
    publish(result, windows, passages, output_dir, audit_dir, replicas)
    # Retain numerical evidence and plots; capacity calibration has no public UI.
    (output_dir / "calibration.html").unlink(missing_ok=True)
    print(f"Calibration data ready: {output_dir / 'assets/data/baseline_calibration'}", flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", default=Path("docs"), type=Path)
    parser.add_argument("--audit-dir", type=Path, help="Optional server-side sparse windows and passage CSVs")
    parser.add_argument("--workers", type=int, help="Waypoint worker processes; overrides manifest workers (default: 1)")
    args = parser.parse_args()
    if args.workers is not None and args.workers < 1: parser.error("--workers must be positive")
    generate(args.manifest.resolve(), args.output_dir.resolve(), args.audit_dir, workers=args.workers)


if __name__ == "__main__": main()
