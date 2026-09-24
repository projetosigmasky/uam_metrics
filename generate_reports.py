"""Build the P100 dashboard and the C1/C2 waypoint ranking from one RUN."""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

from src.uam_dashboard.run_config import load_run_selection


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("run_config.json"))
    parser.add_argument("--workers", type=int, default=None, help="Override both worker counts from the JSON")
    args = parser.parse_args()
    if args.workers is not None and args.workers <= 0:
        parser.error("--workers must be positive")
    repository = Path(__file__).resolve().parent
    config_path = args.config.resolve()
    selection = load_run_selection(config_path)
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
    for name in ("data_bundle.js", "waypoint_rankings.js"):
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
    print("Dashboard and waypoint ranking ready in docs/", flush=True)


if __name__ == "__main__":
    main()
