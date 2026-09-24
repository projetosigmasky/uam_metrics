from __future__ import annotations

import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from src.uam_dashboard.capacity import _resource_throughput, capacity_metrics
from src.uam_dashboard.exports import conflicts_geojson, trajectory_3d_payload, tracks_geojson
from src.uam_dashboard.experiment import experiment_metadata
from src.uam_dashboard.log_parser import load_state_log
from src.uam_dashboard.metrics import (
    airborne_delay_metrics,
    detect_lowc_events,
    efficiency_metrics,
    total_delay_metrics,
    trajectory_conformity,
)
from src.uam_dashboard.scenario_parser import (
    annotate_aircraft_metadata,
    ground_delay_metrics,
    load_bluesky_scenario,
)
from src.uam_dashboard.reh_parser import load_reh_network
from src.uam_dashboard.uam_corridor_parser import load_uam_corridor_network
from generate_uam_projection import write_uam_projection_asset
from src.uam_dashboard.aggregation import average_resource_group
from src.uam_dashboard.metric_catalog import METRIC_CATALOG, SOURCE_DOCUMENT, SOURCE_VERSION


class MetricsTest(unittest.TestCase):
    def test_metric_catalog_references_final_product_three(self) -> None:
        self.assertEqual({metric["kpa"] for metric in METRIC_CATALOG}, {
            "Segurança", "Eficiência", "Capacidade", "Previsibilidade", "Equidade", "Diagnóstico complementar",
        })
        self.assertTrue(all(metric["source_document"] == SOURCE_DOCUMENT for metric in METRIC_CATALOG))
        self.assertTrue(all(SOURCE_VERSION in metric["pdf_reference"] for metric in METRIC_CATALOG))
        self.assertFalse(any("Eq. 4." in metric["pdf_reference"] for metric in METRIC_CATALOG))

    def test_product2_uam_csv_is_the_six_vertiport_network(self) -> None:
        network = load_uam_corridor_network(
            Path("data/corridors/scenario_horizontal_3000ft_expanded_displaced.csv")
        )

        self.assertEqual(network["scope"], "product2_6_vertiports")
        self.assertEqual(network["vertiports"], [f"VP-{index:03d}" for index in range(1, 7)])
        self.assertEqual(network["route_count"], 72)
        self.assertEqual(network["od_pair_count"], 36)
        self.assertEqual({route["parallel_track"] for route in network["routes"]}, {1, 2})
        self.assertEqual({route["width_m"] for route in network["routes"]}, {457.0})
        self.assertEqual({route["height_m"] for route in network["routes"]}, {305.0})
        self.assertEqual(
            {altitude for route in network["routes"] for altitude in route["altitudes_m"]},
            {760.0, 914.4, 1219.0},
        )

    def test_uam_projection_exports_buffered_route_footprints(self) -> None:
        with TemporaryDirectory() as directory:
            count = write_uam_projection_asset(
                Path("data/corridors/scenario_horizontal_3000ft_expanded_displaced.csv"), Path(directory)
            )
            script = (Path(directory) / "assets/uam_projection.js").read_text(encoding="utf-8")
            collection = json.loads(script.removeprefix("window.__UAM_CORRIDOR_PROJECTION__ = ").removesuffix(";\n"))
            self.assertEqual(count, 72)
            self.assertEqual(len(collection["features"]), 72)
            first = collection["features"][0]
            self.assertEqual(first["geometry"]["type"], "Polygon")
            self.assertEqual(first["geometry"]["coordinates"][0][0], first["geometry"]["coordinates"][0][-1])
            self.assertEqual(first["properties"]["width_m"], 457.0)

    def test_trajectory_3d_payload_uses_five_second_windows(self) -> None:
        rows = []
        for simt in range(11):
            rows.append(
                {
                    "simt": simt,
                    "id": "EV1",
                    "lat": -23.55 + simt * 0.0001,
                    "lon": -46.63,
                    "distflown": simt * 10,
                    "alt": 100 + simt,
                    "vehicle_type": "evtol",
                    "aircraft_model": "EVE",
                }
            )
        payload = trajectory_3d_payload(pd.DataFrame(rows), 5, 300, 250, 5000)

        self.assertEqual(payload["sample_seconds"], 5)
        self.assertEqual(payload["point_count"], 3)
        self.assertEqual([point[0] for point in payload["tracks"][0]["points"]], [0, 5, 10])
        self.assertEqual(payload["tracks"][0]["vehicle_type"], "evtol")
        self.assertEqual(payload["altitude_bounds_m"], [100.0, 110.0])
        self.assertEqual(payload["ground_plane_msl_ft"], 2621.0)
        self.assertAlmostEqual(payload["ground_plane_msl_m"], 798.8808)

    def test_reh_xml_parser_preserves_official_polygon_and_metadata(self) -> None:
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs" xmlns:gml="http://www.opengis.net/gml" xmlns:ICA="https://geoaisweb.decea.mil.br/geoserver/ICA">
  <gml:featureMember><ICA:CV_REH_XP_SAO_PAULO><ICA:id>208</ICA:id><ICA:geom>
    <gml:MultiPolygon><gml:polygonMember><gml:Polygon><gml:outerBoundaryIs><gml:LinearRing>
      <gml:coordinates>-46.64,-23.56 -46.62,-23.56 -46.62,-23.54 -46.64,-23.54 -46.64,-23.56</gml:coordinates>
    </gml:LinearRing></gml:outerBoundaryIs></gml:Polygon></gml:polygonMember></gml:MultiPolygon>
  </ICA:geom><ICA:tipo>Obrig</ICA:tipo><ICA:nome>TESTE</ICA:nome><ICA:trecho>1</ICA:trecho>
  <ICA:semi_largura>100.0</ICA:semi_largura><ICA:fixo_a_lat>-23.55</ICA:fixo_a_lat>
  <ICA:fixo_a_lon>-46.64</ICA:fixo_a_lon><ICA:fixo_b_lat>-23.55</ICA:fixo_b_lat>
  <ICA:fixo_b_lon>-46.62</ICA:fixo_b_lon></ICA:CV_REH_XP_SAO_PAULO></gml:featureMember>
</wfs:FeatureCollection>"""
        with TemporaryDirectory() as directory:
            path = Path(directory) / "reh.xml"
            path.write_text(xml, encoding="utf-8")
            network = load_reh_network(path)

        self.assertEqual(len(network["segments"]), 1)
        self.assertEqual(network["segments"][0]["label"], "TESTE - trecho 1")
        self.assertEqual(network["segments"][0]["semi_width_m"], 100.0)
        self.assertGreater(network["segments"][0]["area_m2"], 0.0)
        self.assertEqual(network["geojson"]["features"][0]["geometry"]["type"], "MultiPolygon")

    def test_trajectory_conformity_does_not_publish_spatial_reh_adherence(self) -> None:
        df = pd.DataFrame(
            [
                {"simt": 0, "id": "A", "lat": -23.55, "lon": -46.63, "distflown": 0, "alt": 800},
                {"simt": 60, "id": "A", "lat": -23.55, "lon": -46.62, "distflown": 1000, "alt": 800},
            ]
        )
        planned = [{
            "flight_instance": "A#0",
            "aircraft_id": "A",
            "start_time": "00:00:00.00",
            "start_simt": 0.0,
            "coordinates": [[-46.63, -23.55], [-46.62, -23.55]],
        }]
        reh_segments = [{
            "polygons": [[
                [-46.70, -23.60], [-46.69, -23.60], [-46.69, -23.59],
                [-46.70, -23.59], [-46.70, -23.60],
            ]]
        }]

        summary, _ = trajectory_conformity(df, planned, 50, 300, 250, 5000, reh_segments)

        self.assertNotIn("spatial_adherence_pct", summary)
        self.assertTrue(summary["available"])

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
            detection_horizon_seconds=60,
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
        self.assertNotIn("time_to_conflict_s", events.columns)
        self.assertNotIn("mean_time_to_conflict_s", safety)
        geojson = conflicts_geojson(events)
        self.assertEqual(geojson["features"][0]["properties"]["event_class"], "nmac")
        self.assertFalse(geojson["features"][0]["properties"]["is_mac"])
        self.assertFalse(geojson["properties"]["mac_timestamp_available"])

    def test_lowc_3d_requires_horizontal_and_vertical_penetration(self) -> None:
        rows = []
        for simt in (0, 1, 2):
            rows.extend([
                {"simt": simt, "id": "EV", "lat": -23.55, "lon": -46.63, "distflown": simt, "alt": 100, "vehicle_type": "eVTOL"},
                {"simt": simt, "id": "H1", "lat": -23.55, "lon": -46.63, "distflown": simt, "alt": 300, "vehicle_type": "helicoptero"},
                {"simt": simt, "id": "H2", "lat": -23.55, "lon": -46.63, "distflown": simt, "alt": 110, "vehicle_type": "helicoptero"},
            ])
        events, _, safety = detect_lowc_events(
            pd.DataFrame(rows), 500, 150, 1, 60, 3, 0.01, 1.0,
            5.038e-3, 0.005, 9.4e-6, 1e-15,
            lowc_vertical_threshold_m=137.16,
            nmac_vertical_threshold_m=30.48,
            operation_count=4,
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events.iloc[0]["vehicle_pair"], "eVTOL - helicoptero")
        self.assertAlmostEqual(events.iloc[0]["dist_v_m"], 10.0)
        self.assertEqual(safety["nmac_events"], 1)
        self.assertAlmostEqual(safety["lowc_per_100_operations"], 25.0)

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

        self.assertNotIn("spatial_adherence_pct", summary)
        self.assertLess(abs(summary["mean_trajectory_conformity_ratio"]), 0.03)
        self.assertAlmostEqual(by_instance["A#0"]["mean_deviation_m"], 0.0, places=4)

    def test_experiment_metadata_classifies_four_variants(self) -> None:
        metadata = experiment_metadata("bimtra_top2_2025_02_28_disturbed_seed42_mvp.log")

        self.assertEqual(metadata["day_key"], "top2_2025-02-28")
        self.assertEqual(metadata["variant_key"], "disturbed_mvp")
        self.assertTrue(metadata["disturbed"])
        self.assertTrue(metadata["mvp_enabled"])

    def test_product2_metadata_groups_c1_and_c2(self) -> None:
        c1 = experiment_metadata("STATELOG_produto2_C1_2025-11-09_off_20260818_14-48-46.log")
        c2 = experiment_metadata("produto2_C2_2025-11-09_off.scn")
        replica = experiment_metadata("STATELOG_produto2_C1_2025-11-09_off_seed42.log")
        self.assertEqual(c1["day_key"], c2["day_key"])
        self.assertEqual(c1["day_key"], replica["day_key"])
        self.assertEqual(replica["scenario_key"], "C1")
        self.assertEqual(c1["variant_key"], "c1")
        self.assertEqual(c2["variant_key"], "c2")
        self.assertEqual(c1["reference_variant_key"], "c1")

    def test_product2_p95_metadata_groups_and_orders_ten_scenarios(self) -> None:
        c2 = experiment_metadata(
            "STATELOG_produto2_C2_p95_off_headless_20260901_11-53-31.log"
        )
        c10 = experiment_metadata("produto2_C10_p95_off.scn")

        self.assertEqual(c2["day_key"], "produto2_p95")
        self.assertEqual(c10["day_key"], "produto2_p95")
        self.assertEqual(c2["scenario_key"], "C2")
        self.assertEqual(c10["scenario_key"], "C10")
        self.assertEqual(c10["rank"], 10)

    def test_extended_log_fields_and_scenario_aircraft_type_are_preserved(self) -> None:
        with TemporaryDirectory() as directory:
            directory_path = Path(directory)
            log_path = directory_path / "STATELOG_test.log"
            log_path.write_text(
                "# State log\n# simt,id,lat,lon,distflown,alt,hdg,trk,cas,tas,gs,vs\n"
                "0,EV1,-23.55,-46.63,0,900,10,11,40,41,42,2\n",
                encoding="utf-8",
            )
            scenario_path = directory_path / "produto2_C1_2025-11-09_off.scn"
            scenario_path.write_text(
                "00:00:00.00> CRE EV1 EVTOL -23.55 -46.63 0 3000 40\n"
                "00:00:00.00> ADDWPT EV1 -23.54 -46.62 3000 40\n",
                encoding="utf-8",
            )
            df = load_state_log(log_path)
            planned = load_bluesky_scenario(scenario_path)
            annotated = annotate_aircraft_metadata(df, planned)
        self.assertIn("hdg", annotated.columns)
        self.assertIn("trk", annotated.columns)
        self.assertIn("vs", annotated.columns)
        self.assertEqual(annotated.iloc[0]["vehicle_type"], "eVTOL")
        self.assertEqual(annotated.iloc[0]["aircraft_model"], "EVTOL")

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
        self.assertEqual(len(metrics["density"]["hotspots"]["features"]), 1)
        self.assertTrue(metrics["throughput"]["od_pairs"]["available"])
        self.assertIsNone(metrics["throughput"]["od_pairs"]["capacity_declared_per_hour"])
        self.assertTrue(metrics["throughput"]["od_pairs"]["utilization_available"])
        self.assertEqual(metrics["throughput"]["od_pairs"]["top_resources"][0]["capacity_reference_per_hour"], 2.0)
        self.assertEqual(metrics["throughput"]["od_pairs"]["top_resources"][0]["utilization_peak"], 1.0)
        self.assertLessEqual(len(metrics["throughput"]["od_pairs"]["top_resources"]), 5)
        self.assertTrue(metrics["throughput"]["planned_reh"]["available"])
        self.assertIn("crossings", metrics["complexity"])

    def test_capacity_rankings_are_limited_to_top_five_resources(self) -> None:
        items = [
            {"resource_id": f"R{index}", "label": f"R{index}", "time_s": index * 60}
            for index in range(8)
        ]

        metrics = _resource_throughput(items, 3600, 0.95)

        self.assertEqual(metrics["resource_count"], 8)
        self.assertEqual(len(metrics["top_resources"]), 5)

    def test_practical_capacity_uses_all_observation_windows(self) -> None:
        items = [{"resource_id": "R1", "label": "R1", "time_s": 0}]
        metrics = _resource_throughput(items, 900, 0.95, 0, 3600)
        resource = metrics["top_resources"][0]
        self.assertEqual(resource["operations"], 1)
        self.assertEqual(resource["peak_throughput_per_hour"], 4.0)
        self.assertAlmostEqual(resource["capacity_reference_per_hour"], 3.2)
        self.assertAlmostEqual(resource["utilization_peak"], 1.25)

    def test_replica_resource_average_includes_zero_for_absent_resource(self) -> None:
        first = {"resources": [{"resource_id": "R1", "label": "R1", "operations": 2,
                               "mean_throughput_per_hour": 4, "peak_throughput_per_hour": 8,
                               "capacity_reference_per_hour": 6}]}
        second = {"resources": []}
        group = average_resource_group([first, second])
        resource = group["top_resources"][0]
        self.assertEqual(group["replica_count"], 2)
        self.assertEqual(resource["operations"], 1)
        self.assertEqual(resource["mean_throughput_per_hour"], 2)
        self.assertEqual(resource["capacity_reference_per_hour"], 3)

    def test_capacity_uses_uam_reh_crossings_and_ranks_crossing_waypoints(self) -> None:
        df = pd.DataFrame([
            {"simt": 0, "id": "EV1", "lat": -23.55, "lon": -46.64, "distflown": 0, "alt": 800},
            {"simt": 60, "id": "EV1", "lat": -23.55, "lon": -46.63, "distflown": 1000, "alt": 800},
            {"simt": 120, "id": "EV1", "lat": -23.55, "lon": -46.62, "distflown": 2000, "alt": 800},
        ])
        planned = [{
            "flight_instance": "EV1#0",
            "aircraft_id": "EV1",
            "vehicle_type": "eVTOL",
            "start_time": "00:00:00.00",
            "start_simt": 0.0,
            "coordinates": [[-46.64, -23.55], [-46.62, -23.55]],
        }]
        conformity = {"EV1#0": {"planned_flight_instance": "EV1#0"}}
        tracks = tracks_geojson(df, 1, 300, 250, 5000, 8, 1200, 2500, conformity)
        reh_segments = [{
            "resource_id": "REH-1",
            "label": "REH vertical",
            "name": "REH vertical",
            "section": "1",
            "route_type": "Obrig",
            "semi_width_m": 100.0,
            "altitude_min_ft": 2500.0,
            "altitude_max_ft": 3000.0,
            "area_m2": 400000.0,
            "coordinates": [[-23.56, -46.63], [-23.54, -46.63]],
            "polygons": [[
                [-46.631, -23.56], [-46.629, -23.56], [-46.629, -23.54],
                [-46.631, -23.54], [-46.631, -23.56],
            ]],
        }]
        official_uam = [{
            "resource_id": "UAM001", "label": "UAM test", "coordinates": [[-23.55, -46.64], [-23.55, -46.62]],
            "altitudes_m": [800.0, 800.0], "height_m": 200.0, "semi_width_m": 100.0,
        }]

        metrics = capacity_metrics(
            df, planned, tracks, conformity, 0, 250, 3600, 0.95,
            300, 250, 5000, reh_segments, official_uam, crossing_capture_radius_m=300,
        )

        complexity = metrics["complexity"]
        self.assertEqual(complexity["geometry_dimension"], "3D")
        self.assertEqual(complexity["planned_route_crossings"], 1)
        crossing = complexity["crossings"]["features"][0]
        self.assertEqual(crossing["properties"]["resource_id"], "XUAMREH001")
        self.assertEqual(crossing["properties"]["operations"], 1)
        self.assertAlmostEqual(crossing["properties"]["altitude_m"], 831.0)
        self.assertIsNone(crossing["properties"]["capacity_declared_per_hour"])
        crossing_resources = metrics["throughput"]["crossing_waypoints"]
        self.assertTrue(crossing_resources["available"])
        self.assertEqual(
            crossing_resources["top_resources"][0]["map_target"]["type"],
            "crossing_waypoint",
        )

        reh_segments[0]["altitude_min_ft"] = 5000.0
        reh_segments[0]["altitude_max_ft"] = 5500.0
        separated = capacity_metrics(
            df, planned, tracks, conformity, 0, 250, 3600, 0.95,
            300, 250, 5000, reh_segments, official_uam, crossing_capture_radius_m=300,
        )
        self.assertEqual(separated["complexity"]["planned_route_crossings"], 0)


if __name__ == "__main__":
    unittest.main()
