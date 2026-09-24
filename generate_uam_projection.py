"""Export the 2D footprint of the versioned UAM corridor CSV for the map."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.uam_dashboard.capacity import _buffered_route_groups, _official_uam_route_groups
from src.uam_dashboard.uam_corridor_parser import load_uam_corridor_network


def write_uam_projection_asset(uam_csv: Path, output_dir: Path) -> int:
    routes = _official_uam_route_groups(load_uam_corridor_network(uam_csv)["routes"])
    corridors = _buffered_route_groups(routes, 250.0)
    features = []
    for corridor in corridors:
        features.append({
            "type": "Feature",
            "properties": {
                "resource_id": corridor["resource_id"],
                "label": corridor["label"],
                "od_pair": corridor["od_pair"],
                "parallel_track": corridor["parallel_track"],
                "width_m": corridor["width_m"],
                "height_m": corridor["height_m"],
                "altitude_min_m": min(corridor["altitudes_m"]),
                "altitude_max_m": max(corridor["altitudes_m"]),
                "geometry_source": corridor["geometry_source"],
            },
            "geometry": {"type": "Polygon", "coordinates": corridor["polygons"]},
        })
    collection = {
        "type": "FeatureCollection",
        "properties": {"source": uam_csv.name, "projection": "horizontal_footprint_of_3d_uam_corridors", "route_count": len(features)},
        "features": features,
    }
    assets = output_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "uam_projection.js").write_text(
        "window.__UAM_CORRIDOR_PROJECTION__ = " + json.dumps(collection, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )
    return len(features)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uam-csv", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("docs"))
    args = parser.parse_args()
    print(f"{write_uam_projection_asset(args.uam_csv, args.output_dir)} UAM corridor projections")


if __name__ == "__main__":
    main()
