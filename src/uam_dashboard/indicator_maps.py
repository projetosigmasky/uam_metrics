"""Compact map layers accumulated from matching SCNs and STATELOGs."""
from collections import defaultdict

import numpy as np

from .exports import _trajectory_signature
from .metrics import haversine_m

GRID_DEGREES = 0.01
GRID_WINDOW_S = 300
ENDPOINT_TOLERANCE_M = 1_000


def summarize_indicator_maps(instances, planned_flights, conformity, shape_points):
    shape_points = max(2, shape_points)
    plans = {plan["flight_instance"]: plan["coordinates"] for plan in planned_flights}
    routes = {}
    od_times = defaultdict(list)
    for instance, group in instances.groupby("flight_instance", sort=False):
        match = conformity.get(instance)
        if not match or len(group) < 2:
            continue
        coords = plans[match["planned_flight_instance"]]
        ends = [(group.iloc[0], coords[0]), (group.iloc[-1], coords[-1])]
        if any(haversine_m(row.lat, row.lon, lat, lon) > ENDPOINT_TOLERANCE_M
               for row, (lon, lat) in ends):
            continue
        duration = float(group.simt.iloc[-1] - group.simt.iloc[0])
        if duration <= 0:
            continue

        # Group by planned horizontal geometry (about 11 m precision) and by
        # direction. Equal-distance samples preserve the average route shape.
        route = tuple((round(lon, 4), round(lat, 4)) for lon, lat in coords)
        row = routes.setdefault(route, [0, np.zeros((shape_points, 2)), 0., 0.])
        row[0] += 1
        row[1] += _trajectory_signature(group, shape_points)[:, ::-1]
        row[2] += max(0., match["executed_horizontal_inefficiency_ratio"])
        row[3] += max(0., match["trajectory_conformity_ratio"])
        od_times[route[0], route[-1]].append(duration)

    cells = {}
    complete_windows = int((instances.simt.max() - instances.simt.min()) // GRID_WINDOW_S)
    if complete_windows:
        # Count distinct observed flight instances per cell and full window.
        # An instance may appear in multiple cells/windows, once in each.
        bucket = ((instances.simt - instances.simt.min()) // GRID_WINDOW_S).astype(int)
        positions = instances.loc[bucket < complete_windows, ["flight_instance", "lat", "lon"]].copy()
        positions["window"] = bucket
        positions[["lat", "lon"]] = np.floor(positions[["lat", "lon"]] / GRID_DEGREES).astype(int)
        by_window = positions.drop_duplicates().groupby(["lat", "lon", "window"]).size()
        cells = by_window.groupby(level=[0, 1]).max().to_dict()
    return routes, od_times, cells, bool(complete_windows)


def _feature(geometry, coordinates, **properties):
    return dict(type="Feature", geometry=dict(type=geometry, coordinates=coordinates), properties=properties)


class IndicatorMaps:
    """Merge worker results without keeping their trajectory samples in memory."""

    def __init__(self):
        self.routes = {}
        self.od_times = defaultdict(list)
        self.cells = defaultdict(int)
        self.grid_replicas = 0

    def add(self, summary):
        routes, od_times, cells, valid_grid = summary
        for key, (count, coordinates, hfe, conformity) in routes.items():
            row = self.routes.setdefault(key, [0, np.zeros_like(coordinates), 0., 0.])
            row[0] += count
            row[1] += coordinates
            row[2] += hfe
            row[3] += conformity
        for od, durations in od_times.items():
            self.od_times[od].extend(durations)
        for key, peak in cells.items():
            self.cells[key] += peak
        self.grid_replicas += valid_grid

    def payload(self):
        planned, executed, od_pairs = [], [], []
        for index, (route, (count, coordinates, hfe, conformity)) in enumerate(sorted(self.routes.items()), 1):
            properties = dict(route_id=f"R{index:03}", flights=count,
                              horizontal_excess_pct=round(100 * hfe / count, 4),
                              conformity_excess_pct=round(100 * conformity / count, 4))
            planned.append(_feature("LineString", route, **properties))
            executed.append(_feature("LineString", (coordinates / count).round(6).tolist(), **properties))
        for index, (od, durations) in enumerate(sorted(self.od_times.items()), 1):
            if od[0] == od[1]:
                continue  # No drawable connection when origin equals destination.
            q1, q3 = np.percentile(durations, [25, 75])
            count = len(durations)
            origin, destination = od
            # Offset the display line so opposite directions remain selectable.
            lon_delta, lat_delta = np.subtract(destination, origin)
            bend = (round((origin[0] + destination[0]) / 2 - lat_delta * .12, 6),
                    round((origin[1] + destination[1]) / 2 + lon_delta * .12, 6))
            od_pairs.append(_feature("LineString", [origin, bend, destination], od_id=f"OD{index:03}", flights=count,
                                     iqr_s=round(float(q3 - q1), 2) if count >= 2 else None,
                                     std_s=round(float(np.std(durations, ddof=1)), 2) if count >= 2 else None))
        return dict(schema_version=1,
                    planned_routes=dict(type="FeatureCollection", features=planned),
                    mean_tracks=dict(type="FeatureCollection", features=executed),
                    od_pairs=dict(type="FeatureCollection", features=od_pairs),
                    capacity_grid=dict(cell_degrees=GRID_DEGREES, window_s=GRID_WINDOW_S,
                                       replicas=self.grid_replicas,
                                       cells=[[int(lat), int(lon), round(peak / self.grid_replicas, 3)]
                                              for (lat, lon), peak in sorted(self.cells.items())]))
