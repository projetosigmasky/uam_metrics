from __future__ import annotations

from typing import Any

import pandas as pd

from .config import METERS_PER_NM


def tracks_geojson(df: pd.DataFrame, sample_stride: int) -> dict[str, Any]:
    features = []
    stride = max(1, sample_stride)

    for aircraft_id, group in df.groupby("id", sort=True):
        sampled = group.iloc[::stride]
        if len(sampled) < 2:
            sampled = group

        coordinates = [
            [float(row.lon), float(row.lat), float(row.alt)]
            for row in sampled.itertuples(index=False)
        ]
        if len(coordinates) < 2:
            continue

        features.append(
            {
                "type": "Feature",
                "properties": {
                    "id": str(aircraft_id),
                    "samples": int(len(group)),
                    "distance_nm": float(group["distflown"].max() / METERS_PER_NM),
                    "duration_min": float((group["simt"].max() - group["simt"].min()) / 60.0),
                    "min_alt_m": float(group["alt"].min()),
                    "max_alt_m": float(group["alt"].max()),
                },
                "geometry": {"type": "LineString", "coordinates": coordinates},
            }
        )

    return {"type": "FeatureCollection", "features": features}


def conflicts_geojson(events: pd.DataFrame) -> dict[str, Any]:
    features = []
    if events.empty:
        return {"type": "FeatureCollection", "features": features}

    for row in events.itertuples(index=False):
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "simt": float(row.simt),
                    "id_a": str(row.id_a),
                    "id_b": str(row.id_b),
                    "dist_h_m": float(row.dist_h_m),
                    "dist_v_m": float(row.dist_v_m),
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(row.lon), float(row.lat)],
                },
            }
        )

    return {"type": "FeatureCollection", "features": features}


def heatmap_points(df: pd.DataFrame, sample_stride: int) -> list[list[float]]:
    sampled = df.iloc[:: max(1, sample_stride)]
    return [[float(row.lat), float(row.lon), 0.65] for row in sampled.itertuples(index=False)]


def timeline_records(series: pd.DataFrame) -> list[dict[str, float]]:
    return [
        {"simt": float(row.simt), "hour": float(row.hour), "aircraft": int(row.aircraft)}
        for row in series.itertuples(index=False)
    ]
