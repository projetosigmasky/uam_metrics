from __future__ import annotations

import csv
import re
import math
from collections import defaultdict
from pathlib import Path
from typing import Any


REQUIRED_COLUMNS = {
    "route", "id", "name", "lat", "lon", "type", "altitude", "height", "width"
}
PARALLEL_RE = re.compile(r"\s+\(Parallel\s+(?P<track>\d+)\)$", re.IGNORECASE)


def load_uam_corridor_network(path: str | Path, expected_vertiports: set[str] | None = None) -> dict[str, Any]:
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
    if not vertiports or any(not re.fullmatch(r"VP-\d{3}", name) for name in vertiports):
        raise ValueError("Vertiports must have nonempty VP-NNN identifiers")
    if expected_vertiports is not None and vertiports != expected_vertiports:
        raise ValueError(f"Expected vertiports {sorted(expected_vertiports)}, found {sorted(vertiports)}")
    for route_name, points in grouped.items():
        if not route_name or len(points) < 2 or len({p["id"] for p in points}) != len(points):
            raise ValueError(f"Invalid route or duplicate point ids: {route_name!r}")
        for point in points:
            if not all(math.isfinite(point[k]) for k in ("lat", "lon", "altitude_m", "height_m", "width_m")) or not (-90 <= point["lat"] <= 90 and -180 <= point["lon"] <= 180) or min(point["height_m"], point["width_m"]) <= 0:
                raise ValueError(f"Invalid corridor coordinate/dimensions in {route_name!r}")

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
                "geometry_source": "product2_uam_corridor_csv",
            }
        )

    return {
        "source": str(source_path),
        "scope": f"product2_{len(vertiports)}_vertiports",
        "units": "metres",
        "vertiports": sorted(vertiports),
        "route_count": len(routes),
        "od_pair_count": len({route["od_pair"] for route in routes}),
        "routes": routes,
    }
