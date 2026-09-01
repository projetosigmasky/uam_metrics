from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


REQUIRED_COLUMNS = {
    "route", "id", "name", "lat", "lon", "type", "altitude", "height", "width"
}
PARALLEL_RE = re.compile(r"\s+\(Parallel\s+(?P<track>\d+)\)$", re.IGNORECASE)


def load_uam_corridor_network(path: str | Path) -> dict[str, Any]:
    """Load the six-vertiport Product II dedicated UAM corridor export."""

    source_path = Path(path)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    vertiports: set[str] = set()
    with source_path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        missing = REQUIRED_COLUMNS.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(
                f"UAM corridor CSV is missing required columns: {', '.join(sorted(missing))}"
            )
        for row in reader:
            route_name = str(row["route"]).strip()
            point_type = str(row["type"]).strip()
            point_name = str(row["name"]).strip()
            if point_type.casefold() == "vertiport":
                vertiports.add(point_name)
            grouped[route_name].append(
                {
                    "id": int(row["id"]),
                    "name": point_name,
                    "type": point_type,
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                    "altitude_m": float(row["altitude"]),
                    "height_m": float(row["height"]),
                    "width_m": float(row["width"]),
                }
            )

    if not grouped:
        raise ValueError(f"UAM corridor CSV contains no routes: {source_path}")
    expected_vertiports = {f"VP-{index:03d}" for index in range(1, 7)}
    if vertiports != expected_vertiports:
        raise ValueError(
            "The current dashboard scope requires exactly Product II vertiports VP-001 through VP-006."
        )

    routes = []
    for index, (route_name, points) in enumerate(grouped.items(), start=1):
        points.sort(key=lambda point: point["id"])
        widths = {point["width_m"] for point in points}
        heights = {point["height_m"] for point in points}
        if len(widths) != 1 or len(heights) != 1:
            raise ValueError(f"Route {route_name!r} has inconsistent width or height values.")
        width_m = widths.pop()
        parallel_match = PARALLEL_RE.search(route_name)
        routes.append(
            {
                "resource_id": f"UAM{index:03d}",
                "label": route_name,
                "route_name": route_name,
                "od_pair": PARALLEL_RE.sub("", route_name),
                "parallel_track": int(parallel_match.group("track")) if parallel_match else None,
                "coordinates": [[point["lat"], point["lon"]] for point in points],
                "altitudes_m": [point["altitude_m"] for point in points],
                "height_m": heights.pop(),
                "width_m": width_m,
                "semi_width_m": width_m / 2.0,
                "waypoint_count": len(points),
                "points": points,
                "geometry_source": "product2_uam_corridor_csv_6_vertiports",
            }
        )

    return {
        "source": str(source_path),
        "scope": "product2_6_vertiports",
        "units": "metres",
        "vertiports": sorted(vertiports),
        "route_count": len(routes),
        "od_pair_count": len({route["od_pair"] for route in routes}),
        "routes": routes,
    }
