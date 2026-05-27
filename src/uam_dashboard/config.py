from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


LOG_COLUMNS = ["simt", "id", "lat", "lon", "distflown", "alt", "cas", "tas", "gs"]
METERS_PER_NM = 1852.0
FEET_TO_METERS = 0.3048
SAO_PAULO_CENTER = [-23.5505, -46.6333]


@dataclass(frozen=True)
class DashboardConfig:
    """Analysis settings used by the static dashboard generator."""

    log_paths: tuple[Path, ...]
    output_dir: Path = Path("docs")
    data_dir: Path = Path("data")
    low_altitude_ft: float = 1500.0
    lowc_horizontal_m: float = 500.0
    lowc_vertical_m: float = 30.0
    conflict_sample_seconds: int = 10
    same_altitude_band_m: float = 150.0
    track_sample_stride: int = 20
    heatmap_sample_stride: int = 10
