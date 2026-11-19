"""Observed occupancy of the simulator's nominal Congonhas grid (all modelled altitudes)."""
import json
from functools import lru_cache
from pathlib import Path

import shapely
from shapely.geometry import shape


@lru_cache(maxsize=1)
def model_grid():
    path = Path(__file__).resolve().parents[2] / "data" / "circea_grid.geojson"
    return json.loads(path.read_text(encoding="utf-8"))


def occupancy_sample(frame):
    """Count simultaneous flight instances at observed timestamps; never fill gaps."""
    rows = frame[["flight_instance", "simt", "lon", "lat"]].dropna()
    # One simultaneous snapshot per observed second even when logging faster
    # than 1 Hz. Empty seconds have unknown occupancy and do not add exposure.
    timestamps = rows.simt.drop_duplicates().sort_values()
    snapshots = timestamps[~(timestamps // 1).duplicated()]
    rows = rows[rows.simt.isin(snapshots)]
    times = len(snapshots)
    cells = {}
    for feature in model_grid()["features"]:
        polygon = shape(feature["geometry"])
        inside = shapely.intersects_xy(polygon, rows.lon.to_numpy(), rows.lat.to_numpy())
        occupancy = rows.loc[inside].groupby("simt").flight_instance.nunique()
        props = feature["properties"]
        cells[props["resource_id"]] = {
            "at_limit": int((occupancy >= props["capacity"]).sum()),
            "peak": int(occupancy.max()) if len(occupancy) else 0,
        }
    return {"observations": int(times), "cells": cells}


def merge_occupancy(samples):
    samples = [s for s in samples if s["observations"]]
    if not samples:
        return None
    observations = sum(s["observations"] for s in samples)
    return dict(observations=observations, replicas=len(samples), cells={
        key: dict(at_limit=sum(s["cells"][key]["at_limit"] for s in samples),
                  peak=max(s["cells"][key]["peak"] for s in samples))
        for key in samples[0]["cells"]
    })
