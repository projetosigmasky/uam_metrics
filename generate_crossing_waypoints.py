"""Generate altitude-confirmed UAM/REH crossing candidates for the dashboard."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.uam_dashboard.capacity import _buffered_route_groups, _official_route_groups, _official_uam_route_groups, _uam_reh_crossing_features
from src.uam_dashboard.reh_parser import load_reh_network
from src.uam_dashboard.uam_corridor_parser import load_uam_corridor_network


def write_crossing_waypoint_asset(uam_csv: Path, reh_xml: Path, output_dir: Path) -> int:
    uam = _official_uam_route_groups(load_uam_corridor_network(uam_csv)["routes"])
    reh = _official_route_groups(load_reh_network(reh_xml)["segments"])
    features = _uam_reh_crossing_features(_buffered_route_groups(uam, 250.0), reh)
    collection = {"type": "FeatureCollection", "properties": {"geometry_dimension": "3D", "status": "geometric_candidates_pending_replica_throughput"}, "features": features}
    assets = output_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "crossing_waypoints_3d.js").write_text("window.__UAM_CROSSINGS_3D__ = " + json.dumps(collection, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    return len(features)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uam-csv", type=Path, required=True)
    parser.add_argument("--reh-xml", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("docs"))
    args = parser.parse_args()
    count = write_crossing_waypoint_asset(args.uam_csv, args.reh_xml, args.output_dir)
    print(f"{count} altitude-confirmed crossing candidates")


if __name__ == "__main__":
    main()
