from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


LOG_COLUMNS = ["simt", "id", "lat", "lon", "distflown", "alt", "cas", "tas", "gs"]
EXTENDED_LOG_COLUMNS = [
    "simt",
    "id",
    "lat",
    "lon",
    "distflown",
    "alt",
    "hdg",
    "trk",
    "cas",
    "tas",
    "gs",
    "vs",
]
METERS_PER_NM = 1852.0
SAO_PAULO_CENTER = [-23.5505, -46.6333]


@dataclass(frozen=True)
class DashboardConfig:
    """Analysis settings used by the static dashboard generator."""

    log_paths: tuple[Path, ...]
    scenario_paths: tuple[Path, ...] = ()
    output_dir: Path = Path("docs")
    data_dir: Path = Path("data")
    flight_instance_gap_seconds: float = 300.0
    flight_instance_reset_distance_m: float = 250.0
    flight_instance_jump_m: float = 5000.0
    lowc_horizontal_m: float = 500.0
    nmac_horizontal_m: float = 150.0
    mac_beta: float = 5.038e-3
    mac_probability_given_nmac: float = 0.005
    tls_target_per_flight_hour: float = 9.4e-6
    tls_epsilon: float = 1e-15
    conflict_sample_seconds: int = 10
    track_sample_stride: int = 20
    trajectory_shape_points: int = 12
    trajectory_cluster_distance_m: float = 1200.0
    trajectory_endpoint_tolerance_m: float = 2500.0
    conformity_tolerance_m: float = 250.0
    capacity_window_seconds: int = 3600
    capacity_reference_percentile: float = 0.95
    heatmap_sample_stride: int = 10
