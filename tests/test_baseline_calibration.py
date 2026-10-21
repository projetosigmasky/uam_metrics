import copy
import csv
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import numpy as np

from generate_baseline_calibration import generate
from prepare_baseline_manifest import identity, prepare
from src.uam_dashboard.baseline_calibration import (
    BASELINES, DEFAULT_CRITERIA, analyze, estimate, full_window_counts,
    load_manifest, quantile_hist, read_replica,
)


def fixture(root, replicas=3):
    run = root / "runs/completed"
    (run / "output").mkdir(parents=True)
    (run / "summary.json").write_text(json.dumps({"scenarios": [{"status": "completed"}]}))
    entries = []
    configs = root / "source"
    for code in BASELINES:
        for n in range(1, replicas + 1):
            name = f"produto2_{code}_p100_r{n:03d}"
            source = configs / code / (name + ".json")
            source.parent.mkdir(parents=True, exist_ok=True)
            resources = {
                "R1": {"resource_id": "R1", "kind": "named_reh", "eligible": True, "network": "reh",
                       "reh_name": "CENTRO", "reh_id": "1", "lat": -23., "lon": -46., "altitude_ft": 3000},
                "R0": {"resource_id": "R0", "kind": "named_reh", "eligible": True, "network": "reh",
                       "reh_name": "SEM USO", "reh_id": "0", "lat": -24., "lon": -46., "altitude_ft": 3000},
            }
            config = {"simulation_duration_sec": 7200, "product2": {"scenario": code, "traffic_management": "none",
                      "replication": {"index": n, "seed": n, "helicopter_seed": 2*n, "evtol_seed": 2*n+1},
                      "resource_manifest": {"capacity_key": "physical_point_track", "resources": resources,
                          "flights": {"A": [{"route_index": i, "resource_id": "R1", "eligible": True} for i in range(3)]}}}}
            source.write_text(json.dumps(config), encoding="utf-8")
            event_file = run / "output" / f"WPPASS_{name}_off_headless_uuid.csv"
            event_file.write_text("time_s,flight_id,resource_id,occurrence\n0,A,R1,0\n300,A,R1,1\n3600,A,R1,2\n")
            entries.append({"scenario": code, "replication": n, "run_dir": str(run),
                            "scenario_config": str(source), "events_file": str(event_file)})
    manifest = root / "manifest.json"
    manifest.write_text(json.dumps({"expected_replicas": replicas, "replicas": entries,
                        "stability": {"minimum_replications": 2, "confirmation_window": 2, "bootstrap_samples": 100}}))
    return manifest, configs, run


class CalibrationTests(unittest.TestCase):
    def test_full_windows_are_epoch_aligned_and_half_open(self):
        counts, audit = full_window_counts([0, 299.99, 300, 899.99, 900], 0, 900, 300)
        self.assertEqual(counts, [2, 1, 1])
        self.assertEqual(audit["excluded_passages"], 1)
        counts, audit = full_window_counts([100, 299, 300, 899, 900, 999], 100, 1000, 300)
        self.assertEqual(counts, [1, 1])
        self.assertEqual(audit["first_window_start_s"], 300)
        self.assertEqual(audit["excluded_partial_seconds"], 300)
        self.assertEqual(audit["excluded_passages"], 4)

    def test_higher_quantile_matches_numpy(self):
        for values in ([0, 0, 1, 7], [1], [0]*100 + [4], [1, 2, 3]*20):
            hist = np.bincount(values)
            self.assertEqual(quantile_hist(hist)[0], np.quantile(values, .95, method="higher"))
        self.assertTrue(np.isnan(quantile_hist(np.array([0, 0]))[0]))

    def test_zero_policy_changes_reference_and_unused_is_not_capacity_zero(self):
        criteria = {**DEFAULT_CRITERIA, "minimum_replications": 2, "confirmation_window": 2, "bootstrap_samples": 100}
        weights = {n: np.ones((100, n), dtype=int) for n in range(2, 4)}
        samples = [[0]*99+[4]]*3
        all_ = estimate(samples, 300, "all", criteria, weights)
        positive = estimate(samples, 300, "positive", criteria, weights)
        self.assertEqual(all_["p95_per_hour"], 0)
        self.assertEqual(positive["p95_per_hour"], 48)
        self.assertEqual(positive["p95_operations_per_window"], 4)
        self.assertEqual(positive["confirmed_at_n"], 3)
        unused = estimate([[0, 0]]*3, 300, "all", criteria, weights)
        self.assertEqual(unused["status"], "no_observed_use")
        self.assertIsNone(unused["p95_per_hour"])
        self.assertFalse(unused["stable_at_final"])
        incomplete = estimate([[1], [], [1]], 3600, "all", criteria, weights)
        self.assertEqual(incomplete["status"], "insufficient_full_windows")
        self.assertFalse(incomplete["stable_at_final"])

    def test_native_completeness_duplicate_and_occurrence_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            path, _, _ = fixture(Path(temp))
            _, entries = load_manifest(path)
            entry = entries[0]
            replica = read_replica(entry)
            self.assertEqual(replica["events"]["R1"], [0., 300., 3600.])
            self.assertEqual(replica["passage_events"][1]["flight_id"], "A")
            self.assertEqual(replica["passage_events"][1]["occurrence"], 1)
            event_file = entry["events_file"]
            original = event_file.read_text()
            event_file.write_text(original + "0,A,R1,0\n")
            with self.assertRaisesRegex(ValueError, "Duplicate"): read_replica(entry)
            event_file.write_text(original.replace("3600,A,R1,2\n", ""))
            with self.assertRaisesRegex(ValueError, "Incomplete WPPASS"): read_replica(entry)
            event_file.write_text(original.replace("R1,2", "R0,2"))
            with self.assertRaisesRegex(ValueError, "mismatched"): read_replica(entry)

    def test_manifest_selection_failed_runs_and_no_silent_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            path, _, run = fixture(Path(temp))
            original = json.loads(path.read_text())
            invalid = copy.deepcopy(original)
            invalid["replicas"].pop()
            path.write_text(json.dumps(invalid))
            with self.assertRaisesRegex(ValueError, "exactly"): load_manifest(path)
            invalid = copy.deepcopy(original)
            invalid["replicas"][0]["passage_source"] = "geometric"
            invalid["replicas"][0]["statelog"] = invalid["replicas"][0]["events_file"]
            path.write_text(json.dumps(invalid))
            with self.assertRaisesRegex(ValueError, "allow_geometric"): load_manifest(path)
            path.write_text(json.dumps(original))
            (run / "summary.json").write_text(json.dumps({"scenarios": [{"status": "running"}]}))
            with self.assertRaisesRegex(ValueError, "incomplete or failed"): load_manifest(path)

    def test_discovery_requires_unambiguous_nominal_identity(self):
        self.assertEqual(identity("WPPASS_produto2_C1_1_p100_r002_off_uuid"), ("C1.1", 2))
        self.assertEqual(identity("produto2_C2.2_p100_r050"), ("C2.2", 50))
        self.assertIsNone(identity("produto2_C2_p100_r050"))
        with tempfile.TemporaryDirectory() as temp:
            path, configs, run = fixture(Path(temp))
            manifest = prepare(configs, [run], 3)
            self.assertEqual(len(manifest["replicas"]), 12)
            duplicate = run / "output/WPPASS_produto2_C1.1_p100_r001_other.csv"
            duplicate.write_text("")
            with self.assertRaisesRegex(ValueError, "Multiple WPPASS"): prepare(configs, [run], 3)

    def test_aggregate_bootstrap_reproducibility_and_pairing(self):
        with tempfile.TemporaryDirectory() as temp:
            path, _, _ = fixture(Path(temp))
            manifest, entries = load_manifest(path)
            replicas = [read_replica(e) for e in entries]
            first, _, _ = analyze(replicas, manifest["stability"])
            second, _, _ = analyze(replicas, manifest["stability"])
            self.assertEqual(first, second)
            resource = next(r for r in first["scenarios"]["C1.1"]["resources"] if r["waypoint_id"] == "R1")
            self.assertEqual(resource["estimates"]["300:positive"]["p95_per_hour"], 12.)
            self.assertEqual(resource["estimates"]["3600:positive"]["p95_per_hour"], 2.)
            replicas[-1]["seeds"]["seed"] = 999
            with self.assertRaisesRegex(ValueError, "not paired"): analyze(replicas, manifest["stability"])

    def test_parallel_matches_serial_including_bootstrap_and_restores_environment(self):
        with tempfile.TemporaryDirectory() as temp:
            path, _, _ = fixture(Path(temp))
            manifest, entries = load_manifest(path)
            for entry in entries:
                n = entry["replication"]
                entry["events_file"].write_text("time_s,flight_id,resource_id,occurrence\n"
                    f"{n*170},A,R1,0\n{n*400},A,R1,1\n{3600+n*100},A,R1,2\n")
            replicas = [read_replica(entry) for entry in entries]
            serial, _, _ = analyze(replicas, manifest["stability"], workers=1)
            with patch.dict(os.environ, {"OPENBLAS_NUM_THREADS": "3", "OMP_NUM_THREADS": "2"}):
                parallel, _, _ = analyze(replicas, manifest["stability"], workers=2)
                self.assertEqual(os.environ["OPENBLAS_NUM_THREADS"], "3")
                self.assertEqual(os.environ["OMP_NUM_THREADS"], "2")
            self.assertEqual(serial, parallel)

    def test_invalid_workers_fail_before_reading_or_writing(self):
        for workers in (0, -1, True, 1.5):
            with self.subTest(workers=workers):
                with self.assertRaisesRegex(ValueError, "workers must be a positive integer"):
                    analyze([], workers=workers)
                with self.assertRaisesRegex(ValueError, "workers must be a positive integer"):
                    generate(Path("missing.json"), Path("unused"), workers=workers)

    def test_publish_end_to_end_and_failure_preserves_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path, _, _ = fixture(root)
            manifest = json.loads(path.read_text())
            manifest["workers"] = 2
            path.write_text(json.dumps(manifest))
            output = root / "docs"
            with patch("generate_baseline_calibration.analyze", wraps=analyze) as analyze_call:
                generate(path, output, root / "audit")
                self.assertEqual(analyze_call.call_args.kwargs["workers"], 2)
            destination = output / "assets/data/baseline_calibration"
            self.assertEqual(len(list(destination.glob("*.png"))), 16)
            result = json.loads((destination / "calibration.json").read_text(encoding="utf-8"))
            self.assertEqual(set(result["scenarios"]), set(BASELINES))
            self.assertFalse(result["operational_capacity_proven"])
            self.assertIn("trace_columns", result)
            point = result["scenarios"]["C1.1"]["resources"][0]["estimates"]["300:positive"]["convergence"][0]
            self.assertEqual(len(point), len(result["trace_columns"]))
            self.assertFalse((output / "calibration.html").exists())
            with (destination / "comparison.csv").open() as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 4*2*3*2)
            before = (destination / "calibration.json").read_bytes()
            manifest = json.loads(path.read_text()); manifest["replicas"].pop()
            path.write_text(json.dumps(manifest))
            with self.assertRaises(ValueError): generate(path, output)
            self.assertEqual((destination / "calibration.json").read_bytes(), before)

    def test_report_command_routes_calibration_without_legacy_processing(self):
        import generate_reports
        with patch("sys.argv", ["generate_reports.py", "--baseline-manifest", "selected.json", "--workers", "25"]), \
             patch("generate_baseline_calibration.generate") as build, \
             patch("generate_reports.subprocess.run") as subprocess_run:
            generate_reports.main()
            build.assert_called_once()
            self.assertEqual(build.call_args.kwargs["workers"], 25)
            subprocess_run.assert_not_called()

    def test_report_command_rejects_mixed_selection(self):
        import generate_reports
        with patch("sys.argv", ["generate_reports.py", "--baseline-manifest", "selected.json", "--run-id", "other"]):
            with self.assertRaises(SystemExit): generate_reports.main()


if __name__ == "__main__": unittest.main()
