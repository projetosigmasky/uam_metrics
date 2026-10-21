import copy
import unittest
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from src.uam_dashboard.config import DashboardConfig
from src.uam_dashboard.metrics import active_aircraft_series, trajectory_conformity
from src.uam_dashboard.replica_analysis import (
    BINS, histogram, aggregate_summaries, summarize_replica, cumulative_mean,
)


def row(active, values):
    return {"active": active, "coverage": {}, "histograms": {
        k: histogram(values.get(k, []), width) for k, (width, _, _) in BINS.items()}}


class ReplicaAnalysisTests(unittest.TestCase):
    def test_simulation_time_alignment_does_not_fill_missing_coverage(self):
        data = aggregate_summaries([row([[0, 2], [1, 4]], {}), row([[1, 8], [2, 10]], {})])
        series = data["charts"]["active_aircraft"]
        self.assertEqual(series["mean"], [2, 6, 10])
        self.assertEqual(series["valid_replicas"], [1, 2, 1])
        self.assertEqual(series["lower"], [2, 4, 10])
        self.assertEqual(series["upper"], [2, 8, 10])

    def test_percentages_equal_replica_weight_not_pooled_flights(self):
        data = aggregate_summaries([row([], {"distance_histogram": [1]}),
                                    row([], {"distance_histogram": [3] * 9})])
        chart = data["charts"]["distance_histogram"]
        self.assertEqual(chart["x"], [1, 3])
        self.assertEqual(chart["mean"], [50, 50])
        self.assertEqual(chart["counts_per_replica"], [1, 9])

    def test_event_zero_is_observed_but_no_separations_is_missing(self):
        data = aggregate_summaries([row([], {"severity_histogram": [.2, .2]}), row([], {})])
        self.assertEqual(data["charts"]["severity_histogram"]["mean"], [1])
        self.assertEqual(data["charts"]["severity_histogram"]["valid_replicas"], 2)
        self.assertEqual(data["charts"]["separation_histogram"]["valid_replicas"], 0)
        self.assertEqual(data["charts"]["trajectory_conformity"]["mean"], [])

    def test_fixed_bins_and_raw_altitude_record_units(self):
        data = aggregate_summaries([row([], {"altitude_histogram": [900] * 3}),
                                    row([], {"altitude_histogram": [924, 925]})])
        self.assertEqual(data["charts"]["altitude_histogram"]["mean"], [2, .5])
        self.assertEqual(data["charts"]["altitude_histogram"]["bin_width"], 25)
        self.assertEqual(histogram([-5, 0, 5], 5)["counts"], {"-1": 1, "0": 1, "1": 1})

    def test_distance_uses_flight_instances_and_delta_not_aircraft_id_max(self):
        df = pd.DataFrame({"id": ["A"]*4, "simt": [0, 1, 1000, 1001],
                           "lat": [0]*4, "lon": [0]*4, "alt": [900]*4,
                           "distflown": [100, 1952, 300, 4004]})
        summary = summarize_replica(df, active_aircraft_series(df), [], pd.DataFrame(), {}, DashboardConfig(log_paths=()))
        self.assertEqual(summary["coverage"]["flight_instances"], 2)
        self.assertEqual(summary["histograms"]["distance_histogram"]["valid_count"], 2)
        self.assertEqual(summary["coverage"]["matched_flights"], 0)

    def test_zero_length_planned_route_is_not_zero_deviation(self):
        df = pd.DataFrame({"id": ["A", "A"], "simt": [0, 1], "lat": [0, 0], "lon": [0, .001],
                           "alt": [900, 900], "distflown": [0, 100]})
        plan = [{"aircraft_id": "A", "start_simt": 0, "coordinates": [[0, 0], [0, 0]]}]
        summary, matches = trajectory_conformity(df, plan, 250, 300, 250, 5000)
        self.assertFalse(summary["available"])
        self.assertEqual(matches, {})

    def test_actual_confirmation_requires_15_prefixes_after_30(self):
        values = [100 + (n % 2)*.1 for n in range(50)]
        result = cumulative_mean(values)
        self.assertEqual(result["status"], "confirmed")
        self.assertEqual(result["stable_from_n"], 30)
        self.assertEqual(result["confirmed_at_n"], 44)
        self.assertEqual(result["trace"][-1]["mean"], np.mean(values))
        self.assertEqual(cumulative_mean(values[:43])["status"], "not_confirmed")

    def test_constant_zero_missing_and_near_zero_do_not_fake_convergence(self):
        self.assertEqual(cumulative_mean([0]*50)["status"], "constant_observed_no_inference")
        self.assertEqual(cumulative_mean([None]*50)["status"], "unavailable")
        self.assertEqual(cumulative_mean([1, -1]*25)["status"], "not_confirmed")
        data = cumulative_mean([100, 100.1]*24 + [None, None])
        self.assertEqual(data["status"], "not_confirmed")
        self.assertEqual(data["valid_count"], 48)
        self.assertIsNotNone(data["first_confirmed_at_n"])

    def test_bootstrap_is_deterministic_in_worker_and_parent(self):
        values = [10, 11, 12, None]*12
        expected = cumulative_mean(values)
        with ProcessPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(cumulative_mean, [values, copy.copy(values)]))
        self.assertEqual(results, [expected, expected])

    def test_transformed_estimator_matches_ratio_of_means_not_mean_of_ratios(self):
        result = cumulative_mean([1, 3], transform=lambda value: 2/value)
        self.assertEqual(result["trace"][-1]["mean"], 1)
        self.assertLessEqual(result["trace"][-1]["ci95"][0], 1)
        self.assertGreaterEqual(result["trace"][-1]["ci95"][1], 1)

    def test_ratio_bootstrap_keeps_replica_numerator_and_denominator_paired(self):
        result = cumulative_mean([10, 30], denominators=[2, 3])
        self.assertEqual(result["trace"][-1]["mean"], 8)
        self.assertGreaterEqual(result["trace"][-1]["ci95"][0], 5)
        self.assertLessEqual(result["trace"][-1]["ci95"][1], 10)
        self.assertEqual(cumulative_mean([0, 0], denominators=[0, 0])["status"], "unavailable")

    def test_empty_sample_and_missing_ratio_components_are_unavailable(self):
        self.assertEqual(cumulative_mean([])["status"], "unavailable")
        result = cumulative_mean([10, 30], denominators=[2, None])
        self.assertEqual(result["valid_count"], 1)
        self.assertFalse(result["trace"][-1]["criterion_met"])


if __name__ == "__main__":
    unittest.main()
