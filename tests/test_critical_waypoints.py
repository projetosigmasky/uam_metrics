from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from critical_waypoints import discover_logs, process_replica
from src.uam_dashboard.topology import network_junction_features, reh_junction_features


def feature(identifier: str, lon: float, lat: float) -> dict:
    return {
        "type": "Feature",
        "properties": {"resource_id": identifier},
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
    }


class CriticalWaypointTests(unittest.TestCase):
    def test_reh_junction_requires_three_distinct_connected_segments(self):
        def segment(identifier, start, end):
            return {
                "resource_id": identifier, "label": identifier,
                "coordinates": [start, end],
                "fix_a_name": "CENTRO" if start == [0.0, 0.0] else "Outro",
                "fix_b_name": "CENTRO" if end == [0.0, 0.0] else "Outro",
            }

        center = [0.0, 0.0]
        routes = [
            segment("REH-1", center, [1.0, 0.0]),
            segment("REH-2", center, [0.0, 1.0]),
            segment("REH-3", center, [-1.0, 0.0]),
            segment("REH-4", [1.0, 0.0], center),  # repeated physical edge
        ]
        features = reh_junction_features(routes)
        self.assertEqual(len(features), 1)
        self.assertEqual(features[0]["properties"]["network_degree"], 3)
        self.assertEqual(features[0]["properties"]["label"], "CENTRO")

    def test_only_distinct_degree_three_waypoints_enter_topology(self):
        def point(name, lat, lon, kind="Waypoint"):
            return {"name": name, "lat": lat, "lon": lon, "type": kind}

        center = point("JUNCAO", -23.0, -46.0)
        north = point("N", -22.99, -46.0)
        south = point("S", -23.01, -46.0)
        east = point("E", -23.0, -45.99)
        routes = [
            {"resource_id": "R1", "label": "R1", "points": [north, center, south]},
            {"resource_id": "R2", "label": "R2", "points": [north, center, east]},
            {"resource_id": "R3", "label": "R3", "points": [east, center, north]},
        ]
        features = network_junction_features(routes)
        self.assertEqual(len(features), 1)
        self.assertEqual(features[0]["properties"]["network_degree"], 3)
        self.assertEqual(features[0]["properties"]["node_name"], "JUNCAO")

        middle = point("SIMPLES", -23.005, -46.005)
        routes.append({"resource_id": "R_M", "label": "R_M", "points": [south, middle, east]})
        self.assertNotIn("SIMPLES", [
            item["properties"]["node_name"] for item in network_junction_features(routes)
        ])

        terminal = point("VP-001", -23.02, -46.0, "Vertiport")
        routes.extend([
            {"resource_id": "R4", "label": "R4", "points": [center, terminal]},
            {"resource_id": "R5", "label": "R5", "points": [terminal, point("A", -23.03, -46.0)]},
            {"resource_id": "R6", "label": "R6", "points": [terminal, point("B", -23.02, -46.01)]},
        ])
        self.assertNotIn("VP-001", [
            item["properties"]["node_name"] for item in network_junction_features(routes)
        ])

    def test_passage_is_counted_once_per_flight_instance(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "STATELOG_produto2_C1_seed1.log"
            log.write_text(
                "# simt,id,lat,lon,distflown,alt,cas,tas,gs\n"
                "0,A,-23.0,-46.0,1000,0,0,0,0\n"
                "10,A,-23.0,-46.0,1100,0,0,0,0\n"
                "20,A,-23.01,-46.01,1200,0,0,0,0\n"
                "30,A,-23.0,-46.0,1300,0,0,0,0\n"
                "3600,A,-23.0,-46.0,0,0,0,0,0\n",
                encoding="utf-8",
            )
            results = process_replica(
                log, [feature("X1", -46.0, -23.0), feature("X2", -47.0, -24.0)],
                250, 3600, 300, 250, 5000,
            )
            self.assertEqual(results[0]["operations"], 2)
            self.assertEqual(results[0]["window_count"], 2)
            self.assertEqual(results[0]["mean_throughput_per_hour"], 1.0)
            self.assertEqual(results[0]["peak_throughput_per_hour"], 1.0)
            self.assertEqual(results[1]["operations"], 0)

    def test_discovery_selects_only_c1_and_c2(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("STATELOG_C1_seed1.log", "STATELOG_C2_seed1.log", "STATELOG_C10_seed1.log"):
                (root / name).touch()
            self.assertEqual([scenario for scenario, _ in discover_logs(root)], ["C1", "C2"])


if __name__ == "__main__":
    unittest.main()
