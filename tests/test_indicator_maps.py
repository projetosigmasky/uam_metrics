import unittest

import pandas as pd

from src.uam_dashboard.indicator_maps import IndicatorMaps, summarize_indicator_maps


class IndicatorMapTests(unittest.TestCase):
    def test_aggregation_excludes_truncated_tracks_and_counts_distinct_flights_per_window(self):
        plans = [{"flight_instance": "plan", "coordinates": [[-46.635, -23.555], [-46.625, -23.555]]}]
        match = {"planned_flight_instance": "plan", "executed_horizontal_inefficiency_ratio": .2,
                 "trajectory_conformity_ratio": -.03}
        layers = IndicatorMaps()
        for duration, extra in ((100, True), (200, False)):
            rows = [
                ("a", 0, -23.555, -46.635),
                ("a", 30, -23.555, -46.634),
                ("a", duration, -23.555, -46.625),
                ("truncated", 80, -23.555, -46.63),
                ("clock", 600, -23.6, -46.6),
            ]
            if extra:
                rows += [("b", 20, -23.555, -46.635), ("b", 60, -23.555, -46.634)]
            frame = pd.DataFrame(rows, columns=["flight_instance", "simt", "lat", "lon"])
            layers.add(summarize_indicator_maps(frame, plans, {"a": match, "truncated": match}, 12))
        payload = layers.payload()
        [track] = payload["mean_tracks"]["features"]
        self.assertEqual(track["properties"]["flights"], 2)
        self.assertEqual(track["properties"]["horizontal_excess_pct"], 20)
        self.assertEqual(track["properties"]["conformity_excess_pct"], 0)
        self.assertEqual(len(track["geometry"]["coordinates"]), 12)
        [od] = payload["od_pairs"]["features"]
        self.assertEqual(od["properties"]["iqr_s"], 50)
        self.assertAlmostEqual(od["properties"]["std_s"], 70.71, places=2)
        grid = payload["capacity_grid"]
        self.assertEqual(grid["replicas"], 2)
        self.assertEqual({(lat, lon): peak for lat, lon, peak in grid["cells"]},
                         {(-2356, -4664): 1.5, (-2356, -4663): 2.0})
