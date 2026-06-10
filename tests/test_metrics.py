from __future__ import annotations

import unittest

import pandas as pd

from src.uam_dashboard.exports import tracks_geojson
from src.uam_dashboard.metrics import detect_lowc_events, efficiency_metrics


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
            vertical_threshold_m=30,
            nmac_horizontal_threshold_m=150,
            nmac_vertical_threshold_m=30,
            sample_seconds=10,
            same_altitude_band_m=150,
            aircraft_count=2,
            total_flight_hours=40 / 3600,
            total_distance_km=0.4,
            mac_probability_bands=(0.001, 0.01, 0.05),
        )

        self.assertEqual(len(separation_samples), 3)
        self.assertEqual(len(events), 1)
        self.assertEqual(safety["lowc_events"], 1)
        self.assertEqual(safety["nmac_events"], 1)
        self.assertAlmostEqual(safety["lowc_per_100_operations"], 50.0)
        self.assertAlmostEqual(safety["total_time_below_threshold_s"], 30.0)
        self.assertAlmostEqual(safety["expected_mac_nominal"], 0.01)

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


if __name__ == "__main__":
    unittest.main()
