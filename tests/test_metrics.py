from __future__ import annotations

import unittest

import pandas as pd

from src.uam_dashboard.capacity import capacity_metrics
from src.uam_dashboard.exports import tracks_geojson
from src.uam_dashboard.experiment import experiment_metadata
from src.uam_dashboard.metrics import (
    airborne_delay_metrics,
    detect_lowc_events,
    efficiency_metrics,
    total_delay_metrics,
    trajectory_conformity,
)
from src.uam_dashboard.scenario_parser import ground_delay_metrics


class MetricsTest(unittest.TestCase):
    def test_efficiency_exposure_metrics(self) -> None:
        df = pd.DataFrame(
            [
                {"simt": 0, "id": "A", "lat": -23.55, "lon": -46.63, "distflown": 0, "alt": 100},
                {"simt": 60, "id": "A", "lat": -23.55, "lon": -46.62, "distflown": 2000, "alt": 100},
                {"simt": 0, "id": "B", "lat": -23.56, "lon": -46.63, "distflown": 0, "alt": 120},
                {"simt": 120, "id": "B", "lat": -23.56, "lon": -46.61, "distflown": 4000, "alt": 120},
            ]
        )

        metrics = efficiency_metrics(df)

        self.assertAlmostEqual(metrics["total_flight_hours"], 0.05)
        self.assertAlmostEqual(metrics["total_distance_km"], 6.0)
        self.assertAlmostEqual(metrics["mean_flight_time_min"], 1.5)
        self.assertGreater(metrics["p95_distance_nm"], metrics["median_distance_nm"])

    def test_lowc_samples_are_collapsed_into_events_and_rates(self) -> None:
        rows = []
        for simt in (0, 10, 20):
            rows.extend(
                [
                    {"simt": simt, "id": "A", "lat": -23.55, "lon": -46.63, "distflown": simt * 10, "alt": 100},
                    {"simt": simt, "id": "B", "lat": -23.55, "lon": -46.63, "distflown": simt * 10, "alt": 100},
                ]
            )
        df = pd.DataFrame(rows)

        events, separation_samples, safety = detect_lowc_events(
            df,
            horizontal_threshold_m=500,
            nmac_horizontal_threshold_m=150,
            sample_seconds=10,
            aircraft_count=2,
            total_flight_hours=40 / 3600,
            total_distance_km=0.4,
            mac_beta=5.038e-3,
            mac_probability_given_nmac=0.005,
            tls_target_per_flight_hour=9.4e-6,
            tls_epsilon=1e-15,
        )

        self.assertEqual(len(separation_samples), 3)
        self.assertEqual(len(events), 1)
        self.assertEqual(safety["lowc_events"], 1)
        self.assertEqual(safety["nmac_events"], 1)
        self.assertAlmostEqual(safety["lowc_per_100_operations"], 50.0)
        self.assertAlmostEqual(safety["total_time_below_threshold_s"], 30.0)
        self.assertAlmostEqual(safety["expected_mac"], 5.038e-3 * 0.005)
        self.assertAlmostEqual(
            safety["expected_mac_per_100k_flight_hours"],
            (5.038e-3 * 0.005) / (40 / 3600) * 100000,
        )
        expected_rate = (5.038e-3 * 0.005) / (40 / 3600)
        self.assertAlmostEqual(safety["tls_margin"], 9.4e-6 / (expected_rate + 1e-15))
        self.assertFalse(safety["tls_compliant"])
        self.assertAlmostEqual(events.iloc[0]["severity_ratio"], 0.0)

    def test_similar_trajectories_share_frequency_group(self) -> None:
        rows = []
        for aircraft_id, lat_offset, lon_offset in (("A", 0.0, 0.0), ("B", 0.001, 0.001), ("C", 0.08, 0.08)):
            for simt, step in enumerate(range(4)):
                rows.append(
                    {
                        "simt": simt,
                        "id": aircraft_id,
                        "lat": -23.55 + lat_offset,
                        "lon": -46.63 + lon_offset + step * 0.01,
                        "distflown": step * 1000,
                        "alt": 800,
                    }
                )
        df = pd.DataFrame(rows)

        geojson = tracks_geojson(
            df,
            sample_stride=1,
            instance_gap_seconds=300,
            instance_reset_distance_m=250,
            instance_jump_m=5000,
            shape_points=8,
            cluster_distance_m=1200,
            endpoint_tolerance_m=2500,
        )

        frequencies = sorted(feature["properties"]["frequency"] for feature in geojson["features"])
        self.assertEqual(frequencies, [1, 2, 2])
        self.assertEqual(geojson["properties"]["trajectory_group_count"], 2)

    def test_trajectory_conformity_uses_distance_to_planned_polyline(self) -> None:
        df = pd.DataFrame(
            [
                {"simt": 0, "id": "A", "lat": -23.55, "lon": -46.63, "distflown": 0, "alt": 800},
                {"simt": 1, "id": "A", "lat": -23.55, "lon": -46.62, "distflown": 1000, "alt": 800},
                {"simt": 2, "id": "A", "lat": -23.55, "lon": -46.61, "distflown": 2000, "alt": 800},
            ]
        )
        planned = [
            {
                "flight_instance": "A#0",
                "aircraft_id": "A",
                "start_time": "00:00:00.00",
                "start_simt": 0.0,
                "coordinates": [[-46.63, -23.55], [-46.61, -23.55]],
            }
        ]

        summary, by_instance = trajectory_conformity(df, planned, 50, 300, 250, 5000)

        self.assertAlmostEqual(summary["spatial_adherence_pct"], 100.0)
        self.assertLess(abs(summary["mean_trajectory_conformity_ratio"]), 0.03)
        self.assertAlmostEqual(by_instance["A#0"]["mean_deviation_m"], 0.0, places=4)

    def test_experiment_metadata_classifies_four_variants(self) -> None:
        metadata = experiment_metadata("bimtra_top2_2025_02_28_disturbed_seed42_mvp.log")

        self.assertEqual(metadata["day_key"], "top2_2025-02-28")
        self.assertEqual(metadata["variant_key"], "disturbed_mvp")
        self.assertTrue(metadata["disturbed"])
        self.assertTrue(metadata["mvp_enabled"])

    def test_ground_delay_uses_nominal_scenario_as_requested_schedule(self) -> None:
        nominal = [
            {"flight_instance": "A#0", "start_simt": 100.0},
            {"flight_instance": "B#0", "start_simt": 200.0},
        ]
        disturbed = [
            {"flight_instance": "A#0", "start_simt": 130.0},
            {"flight_instance": "B#0", "start_simt": 290.0},
        ]

        metrics = ground_delay_metrics(disturbed, nominal)

        self.assertAlmostEqual(metrics["mean_ground_delay_s"], 60.0)
        self.assertAlmostEqual(metrics["max_ground_delay_s"], 90.0)

    def test_airborne_and_total_delay_use_off_reference_duration(self) -> None:
        evaluated = pd.DataFrame(
            [
                {"simt": 0, "id": "A", "lat": -23.55, "lon": -46.63, "distflown": 0, "alt": 800},
                {"simt": 130, "id": "A", "lat": -23.55, "lon": -46.62, "distflown": 1000, "alt": 800},
                {"simt": 0, "id": "B", "lat": -23.56, "lon": -46.63, "distflown": 0, "alt": 800},
                {"simt": 80, "id": "B", "lat": -23.56, "lon": -46.62, "distflown": 1000, "alt": 800},
            ]
        )
        reference = pd.DataFrame(
            [
                {"simt": 0, "id": "A", "lat": -23.55, "lon": -46.63, "distflown": 0, "alt": 800},
                {"simt": 100, "id": "A", "lat": -23.55, "lon": -46.62, "distflown": 1000, "alt": 800},
                {"simt": 0, "id": "B", "lat": -23.56, "lon": -46.63, "distflown": 0, "alt": 800},
                {"simt": 100, "id": "B", "lat": -23.56, "lon": -46.62, "distflown": 1000, "alt": 800},
            ]
        )

        airborne = airborne_delay_metrics(evaluated, reference, 300, 250, 5000)
        total = total_delay_metrics({"available": True, "mean_ground_delay_s": 20.0}, airborne)

        self.assertAlmostEqual(airborne["mean_airborne_delay_s"], 15.0)
        self.assertAlmostEqual(airborne["max_airborne_delay_s"], 30.0)
        self.assertAlmostEqual(total["mean_total_delay_s"], 35.0)

    def test_capacity_metrics_use_reh_corridors_and_p95_utilization(self) -> None:
        df = pd.DataFrame(
            [
                {"simt": 0, "id": "A", "lat": -23.55, "lon": -46.63, "distflown": 0, "alt": 800},
                {"simt": 60, "id": "A", "lat": -23.55, "lon": -46.62, "distflown": 1000, "alt": 800},
                {"simt": 120, "id": "B", "lat": -23.55, "lon": -46.63, "distflown": 0, "alt": 800},
                {"simt": 180, "id": "B", "lat": -23.55, "lon": -46.62, "distflown": 1000, "alt": 800},
            ]
        )
        planned = [
            {
                "flight_instance": "A#0",
                "aircraft_id": "A",
                "start_time": "00:00:00.00",
                "start_simt": 0.0,
                "coordinates": [[-46.63, -23.55], [-46.62, -23.55]],
            },
            {
                "flight_instance": "B#0",
                "aircraft_id": "B",
                "start_time": "00:02:00.00",
                "start_simt": 120.0,
                "coordinates": [[-46.63, -23.55], [-46.62, -23.55]],
            },
        ]
        conformity = {
            "A#0": {"planned_flight_instance": "A#0"},
            "B#0": {"planned_flight_instance": "B#0"},
        }
        tracks = tracks_geojson(df, 1, 300, 250, 5000, 8, 1200, 2500, conformity)

        metrics = capacity_metrics(df, planned, tracks, conformity, 0, 250, 3600, 0.95, 300, 250, 5000)

        self.assertTrue(metrics["density"]["available"])
        self.assertGreater(metrics["density"]["air_traffic_density_per_km2"], 0)
        self.assertTrue(metrics["throughput"]["od_pairs"]["available"])
        self.assertGreater(metrics["throughput"]["od_pairs"]["capacity_reference_per_hour"], 0)
        self.assertTrue(metrics["throughput"]["planned_reh"]["available"])


if __name__ == "__main__":
    unittest.main()
