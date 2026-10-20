"""Calibrate C1.1/C1.2/C2.1/C2.2 from a validated manifest, without rerunning BlueSky."""
from __future__ import annotations

import argparse
import json
import hashlib
import math
import re
import shutil
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
    root = Path(__file__).resolve().parent
    for name in ("baseline_calibration.js", "baseline_calibration.css"):
        destination = output_dir / "assets" / name
        source = root / "web/assets" / name
        if source.resolve() != destination.resolve(): shutil.copy2(source, destination)
    source = root / "web/calibration.html"
    destination = output_dir / "calibration.html"
    if source.resolve() != destination.resolve(): shutil.copy2(source, destination)
    for html_path in (destination, output_dir / "index.html"):
        if not html_path.exists(): continue
        html = html_path.read_text(encoding="utf-8")
        for name in ("baseline_calibration.js", "baseline_calibration.css", "baseline_calibration_data.js"):
            digest = hashlib.sha256((output_dir / "assets" / name).read_bytes()).hexdigest()[:12]
            html = re.sub(rf'assets/{re.escape(name)}(?:\?v=[^"\s]+)?', f"assets/{name}?v={digest}", html)
        html_path.write_text(html, encoding="utf-8")
    print(f"Calibration ready: {destination}", flush=True)
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
