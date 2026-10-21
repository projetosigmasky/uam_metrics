"""Export dissolved UAM footprints and audited 3D centerline junctions."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from src.uam_dashboard.corridor_geometry import uam_geometry
from src.uam_dashboard.named_waypoints import source_record
from src.uam_dashboard.uam_corridor_parser import load_uam_corridor_network


def write_uam_projection_asset(uam_csv: Path, output_dir: Path) -> int:
    geometry = uam_geometry(load_uam_corridor_network(uam_csv)["routes"])
    geometry["audit"]["source"] = source_record(uam_csv)
    assets = output_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "uam_projection.js").write_text(
        "window.__UAM_CORRIDOR_PROJECTION__ = " + json.dumps(geometry["projection"], ensure_ascii=False, separators=(",", ":")) + ";\n"
        + "window.__UAM_GEOMETRIC_JUNCTIONS__ = " + json.dumps(geometry["junctions"], ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    audit_path = assets / "data/uam_geometry_audit.json"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(geometry, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(geometry["projection"]["features"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uam-csv", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("docs"))
    args = parser.parse_args()
    print(f"{write_uam_projection_asset(args.uam_csv, args.output_dir)} dissolved UAM footprint components")


if __name__ == "__main__":
    main()
