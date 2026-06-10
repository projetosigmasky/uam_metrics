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
    low_altitude_reference_mode: str = "origin_agl_proxy"
    low_altitude_reference_samples: int = 5
    flight_instance_gap_seconds: float = 300.0
    flight_instance_reset_distance_m: float = 250.0
    flight_instance_jump_m: float = 5000.0
    lowc_horizontal_m: float = 500.0
    lowc_vertical_m: float = 30.0
    nmac_horizontal_m: float = 150.0
    nmac_vertical_m: float = 30.0
    mac_probability_bands: tuple[float, float, float] = (0.001, 0.01, 0.05)
    conflict_sample_seconds: int = 10
    same_altitude_band_m: float = 150.0
    track_sample_stride: int = 20
    trajectory_shape_points: int = 12
    trajectory_cluster_distance_m: float = 1200.0
    trajectory_endpoint_tolerance_m: float = 2500.0
    heatmap_sample_stride: int = 10
