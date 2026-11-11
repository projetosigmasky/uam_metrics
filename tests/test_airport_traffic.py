import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from src.uam_dashboard.airport_traffic import average_evtol_airport, evtol_airport_safety, load_airport_traffic
from src.uam_dashboard.log_cleaning import trim_terminal_hover

COMMON = dict(lowc_horizontal_m=500.0, lowc_vertical_m=137.16, nmac_horizontal_m=152.0, nmac_vertical_m=30.0,
              sample_seconds=1, gap_seconds=300.0, reset_distance_m=250.0, jump_m=5000.0, mac_beta=0.005,
              mac_probability_given_nmac=5.038e-3, tls_target_per_flight_hour=8.9e-6, tls_epsilon=1e-15)
DEG_PER_M = 1 / 111_195.0


def write_traffic(rows):
    directory = tempfile.mkdtemp()
    path = Path(directory) / "traffic.csv"
    pd.DataFrame(rows, columns=["fr24_id", "callsign", "equip", "airport", "movement", "plan_dep", "real_arr",
                                "sim_time_s", "lat", "lon", "alt_ft", "gs_kt"]).to_csv(path, index=False)
    load_airport_traffic.cache_clear()
    return str(path)


def track(aircraft_id, vehicle_type, times, lat, lon=-46.6, alt=1000.0, gs=30.0):
    times = np.asarray(times, dtype=float)
    return pd.DataFrame({"simt": times, "id": aircraft_id, "lat": lat if np.ndim(lat) else np.full(len(times), lat),
                         "lon": lon, "alt": alt, "distflown": (times - times[0]) * gs, "gs": gs,
                         "vehicle_type": vehicle_type})


class AirportTrafficTests(unittest.TestCase):
    def test_interpolates_to_whole_seconds_and_keeps_long_gaps_empty(self):
        path = write_traffic([
            ["1", "AAA1", "B738", "SBSP", "arr", "SBRJ", "SBSP", 100, -23.60, -46.60, 3000, 140],
            ["1", "AAA1", "B738", "SBSP", "arr", "SBRJ", "SBSP", 100, -23.60, -46.60, 3000, 140],
            ["1", "AAA1", "B738", "SBSP", "arr", "SBRJ", "SBSP", 110, -23.61, -46.60, 2900, 140],
            ["1", "AAA1", "B738", "SBSP", "arr", "SBRJ", "SBSP", 300, -23.70, -46.60, 2700, 140],
        ])
        traffic = load_airport_traffic(path, 60.0)
        self.assertEqual(traffic["simt"].tolist(), list(range(100, 111)) + [300])
        middle = traffic[traffic["simt"] == 105].iloc[0]
        self.assertAlmostEqual(middle["lat"], -23.605)
        self.assertAlmostEqual(middle["alt"], 2950 * 0.3048)
        self.assertEqual(middle["airport"], "SBSP")

    def test_only_evtols_are_paired_with_airport_traffic(self):
        alt_ft = 1000.0 / 0.3048
        path = write_traffic([
            ["7", "GLO1", "B738", "SBSP", "arr", "SBRJ", "SBSP", 0, -23.60, -46.60, alt_ft, 140],
            ["7", "GLO1", "B738", "SBSP", "arr", "SBRJ", "SBSP", 60, -23.60, -46.60, alt_ft, 140],
        ])
        traffic = load_airport_traffic(path, 60.0)
        times = np.arange(0, 61)
        df = pd.concat([
            # eVTOL 100 m away for 11 s (LoWC + NMAC by 10 m vertical), otherwise 2 km away.
            track("EC1", "eVTOL", times, np.where((times >= 20) & (times <= 30), -23.60 + 100 * DEG_PER_M,
                                                  -23.60 + 2000 * DEG_PER_M), alt=1010.0),
            # Helicopter on top of the airliner: ignored by this analysis.
            track("HP1", "helicoptero", times, -23.60, alt=1000.0),
        ], ignore_index=True)
        events, payload = evtol_airport_safety(df, traffic, **COMMON)
        self.assertTrue(payload["available"])
        self.assertEqual(len(events), 1)
        self.assertEqual(payload["lowc_events"], 1)
        self.assertEqual(payload["nmac_events"], 1)
        self.assertEqual(events[0]["id_a"], "EC1")
        self.assertEqual(events[0]["airport"], "SBSP")
        self.assertEqual(events[0]["duration_s"], 11.0)
        self.assertEqual(payload["events_by_airport"], {"SBSP": {"lowc_events": 1, "nmac_events": 1}})
        self.assertEqual(payload["evtol_operations"], 1)
        self.assertAlmostEqual(payload["evtol_flight_hours"], 60 / 3600)
        self.assertAlmostEqual(payload["lowc_per_100_operations"], 100.0)
        self.assertAlmostEqual(payload["min_horizontal_m_co_altitude"], 100.0, delta=1.0)

    def test_scenario_without_evtol_is_not_applicable(self):
        path = write_traffic([["7", "GLO1", "B738", "SBSP", "arr", "SBRJ", "SBSP", 0, -23.6, -46.6, 3000, 140]])
        df = track("HP1", "helicoptero", np.arange(0, 10), -23.60)
        events, payload = evtol_airport_safety(df, load_airport_traffic(path, 60.0), **COMMON)
        self.assertEqual(events, [])
        self.assertFalse(payload["available"])
        self.assertEqual(average_evtol_airport([payload, payload])["available"], False)

    def test_replica_mean_counts_absent_airports_as_zero(self):
        base = {"available": True, "source": {}, "definition": "", "thresholds": {}, "lowc_events": 2,
                "nmac_events": 0, "expected_mac_rate_per_flight_hour": 2e-6, "tls_target_per_flight_hour": 8.9e-6,
                "tls_epsilon": 1e-15, "min_severity_ratio": 0.4, "events_by_vehicle_pair": {},
                "events_by_airport_movement": {}}
        first = base | {"events_by_airport": {"SBSP": {"lowc_events": 2, "nmac_events": 0}}}
        second = base | {"lowc_events": 0, "min_severity_ratio": None, "expected_mac_rate_per_flight_hour": 0.0,
                         "events_by_airport": {}}
        mean = average_evtol_airport([first, second])
        self.assertEqual(mean["lowc_events"], 1.0)
        self.assertEqual(mean["events_by_airport"], {"SBSP": {"lowc_events": 1.0, "nmac_events": 0.0}})
        self.assertEqual(mean["min_severity_ratio"], 0.4)
        self.assertAlmostEqual(mean["tls_margin"], 8.9e-6 / 1e-6)
        self.assertEqual(mean["replica_count"], 2)


class TerminalHoverTests(unittest.TestCase):
    def test_cuts_long_terminal_hover_after_arrival(self):
        times = np.arange(0, 400)
        gs = np.where(times < 100, 30.0, 0.2)
        df = track("HP1", "helicoptero", times, -23.6)
        df["gs"] = gs
        trimmed, report = trim_terminal_hover(df, 60.0, 1.0)
        self.assertEqual(trimmed["simt"].max(), 100.0)
        self.assertEqual(report["trimmed_flights"], 1)
        self.assertEqual(report["trimmed_records"], 299)

    def test_keeps_normal_arrival_and_mid_flight_slow_phase(self):
        times = np.arange(0, 400)
        df = track("EC1", "eVTOL", times, -23.6)
        df.loc[(df["simt"] >= 100) & (df["simt"] < 250), "gs"] = 0.1   # slow, then flies on
        df.loc[df["simt"] >= 390, "gs"] = 0.5                          # 10 s stop before deletion
        trimmed, report = trim_terminal_hover(df, 60.0, 1.0)
        self.assertEqual(len(trimmed), len(df))
        self.assertEqual(report["trimmed_flights"], 0)
        _, disabled = trim_terminal_hover(df, 0.0, 1.0)
        self.assertFalse(disabled["applied"])


if __name__ == "__main__":
    unittest.main()
