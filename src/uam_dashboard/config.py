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
FEET_TO_METERS = 0.3048
SAO_PAULO_CENTER = [-23.5505, -46.6333]


@dataclass(frozen=True)
class DashboardConfig:
    """Analysis settings used by the static dashboard generator."""

    log_paths: tuple[Path, ...]
    scenario_paths: tuple[Path, ...] = ()
    output_dir: Path = Path("docs")
    data_dir: Path = Path("data")
    reh_xml_path: Path | None = None
    uam_corridor_csv_path: Path | None = None
    flight_instance_gap_seconds: float = 300.0
    flight_instance_reset_distance_m: float = 250.0
    flight_instance_jump_m: float = 5000.0
    lowc_horizontal_m: float = 500.0
    # Valores operacionais configuraveis. Os padroes correspondem a 450 ft
    # para Well Clear vertical e 100 ft para NMAC, mas ainda precisam ser
    # validados pelo responsavel operacional do projeto.
    lowc_vertical_m: float = 137.16
    nmac_horizontal_m: float = 150.0
    nmac_vertical_m: float = 30.48
    # Produto 3, Eqs. 4.2 e 4.5: beta é o fator ACAS X; a probabilidade
    # condicional provisória vem da calibração de Chen et al. (2024).
    mac_beta: float = 0.005
    mac_probability_given_nmac: float = 5.038e-3
    tls_target_per_flight_hour: float = 9.4e-6
    tls_epsilon: float = 1e-15
    conflict_sample_seconds: int = 1
    track_sample_stride: int = 20
    visualization_3d_sample_seconds: int = 5
    visualization_3d_ground_msl_ft: float = 2621.0
    trajectory_shape_points: int = 12
    trajectory_cluster_distance_m: float = 1200.0
    trajectory_endpoint_tolerance_m: float = 2500.0
    conformity_tolerance_m: float = 250.0
    capacity_window_seconds: int = 3600
    capacity_reference_percentile: float = 0.95
    crossing_capture_radius_m: float = 250.0
    heatmap_sample_stride: int = 10
