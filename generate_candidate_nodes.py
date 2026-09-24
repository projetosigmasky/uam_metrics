"""Refresh dashboard candidate nodes from UAM CSV and official REH XML only."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.uam_dashboard.topology import write_candidate_node_assets


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uam-csv", type=Path, required=True)
    parser.add_argument("--reh-xml", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("docs"))
    args = parser.parse_args()
    write_candidate_node_assets(args.output_dir, args.uam_csv, args.reh_xml)


if __name__ == "__main__":
    main()
