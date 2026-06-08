from __future__ import annotations

import unittest

import pandas as pd

from src.uam_dashboard.metrics import detect_lowc_events, efficiency_metrics, environment_metrics


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

    def test_low_altitude_uses_origin_agl_proxy(self) -> None:
        df = pd.DataFrame(
            [
                {"simt": 0, "id": "A", "lat": -23.55, "lon": -46.63, "distflown": 0, "alt": 750},
                {"simt": 1, "id": "A", "lat": -23.55, "lon": -46.62, "distflown": 50, "alt": 780},
                {"simt": 2, "id": "A", "lat": -23.55, "lon": -46.61, "distflown": 100, "alt": 1300},
            ]
        )

        metrics = environment_metrics(df, low_altitude_ft=1500, reference_samples=1)

        self.assertEqual(metrics["low_altitude_reference_mode"], "origin_agl_proxy")
        self.assertAlmostEqual(metrics["median_origin_altitude_m"], 750)
        self.assertAlmostEqual(metrics["low_altitude_threshold_m"], 457.2)
        self.assertAlmostEqual(metrics["low_altitude_share_pct"], (2 / 3) * 100)


if __name__ == "__main__":
    unittest.main()
