import json
import tempfile
import unittest
from pathlib import Path
from critical_waypoints import process_replica
from src.uam_dashboard.config import DEFAULT_REH_XML_PATH
from src.uam_dashboard.named_waypoints import named_waypoint_features, named_waypoint_inventory, uam_selection_inventory, normalize_name
from src.uam_dashboard.reh_parser import load_reh_network
from src.uam_dashboard.uam_corridor_parser import load_uam_corridor_network
from src.uam_dashboard.waypoint_passages import percentile95

ROOT = Path(__file__).resolve().parents[1]

class NamedWaypointTests(unittest.TestCase):
    def test_selection_both_exports_and_stable_identity(self):
        reh = load_reh_network(DEFAULT_REH_XML_PATH)['segments']
        for filename, n_routes, n_resources, n_names in [
            ('scenario_horizontal_3000ft_expanded_displaced.csv',72,96,26),
            ('new_scenario_horizontal_3000ft_displaced.csv',210,177,35)]:
            network=load_uam_corridor_network(ROOT/'data/corridors'/filename)
            features=named_waypoint_inventory(network['routes'],reh)
            uam=[f for f in features if f['properties']['network']=='UAM']
            self.assertEqual(len(network['routes']),n_routes)
            self.assertEqual(len(uam),n_resources)
            self.assertEqual(len({f['properties']['normalized_name'] for f in uam}),n_names)
            self.assertEqual(sum(f['properties']['network']=='REH' for f in features),91)
            self.assertEqual({f['properties']['resource_id'] for f in features}, {f['properties']['resource_id'] for f in named_waypoint_inventory(list(reversed(network['routes'])),list(reversed(reh)))})
            self.assertTrue(all(f['properties']['original_names'] for f in features))
        for name,count in [('CEBOLAO',16),('PONTE_ESTAIADA',20)]:
            positions=[f for f in uam if f['properties']['normalized_name']==name]
            self.assertEqual(len(positions),count)
            self.assertEqual(len({tuple(f['geometry']['coordinates']) for f in positions}),count)
            self.assertTrue(all(f['properties']['name_position_count']==count for f in positions))
        self.assertEqual(normalize_name('Cebolão'),normalize_name('CEBOLAO'))

    def test_inventory_waypoint_only_and_no_proximity_merge(self):
        def point(name, kind, lon, alt=900):
            return dict(name=name,type=kind,lat=-23.,lon=lon,altitude_m=alt,height_m=20,width_m=40)
        route=dict(resource_id='R',label='R',points=[point('A','Waypoint',-46.),point('GEOM','Geometric Node',-46.01),point('','Waypoint',-46.02),point('A','Waypoint',-46.000001),point('A','Waypoint',-46.,910)])
        features=named_waypoint_inventory([route,route],[])
        self.assertEqual(len(features),3)
        self.assertEqual(len({f['properties']['resource_id'] for f in features}),3)

    def test_reh_no_polygon_fallback_no_arbitrary_altitude(self):
        segment={'resource_id':'S','label':'route','coordinates':[[0,0],[1,1]],'fix_a_name':'Fake'}
        self.assertEqual(named_waypoint_features([], [segment]),[])
        segment['explicit_fixes']=[dict(name='Named',lat=0.,lon=0.)]
        feature=named_waypoint_inventory([], [segment])[0]
        self.assertIsNone(feature['properties']['altitude_m'])
        self.assertEqual(feature['properties']['vertical_intervals_m'],[])

    def run_log(self, lines, features, radius=80):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'STATELOG_C1.log'; path.write_text(lines)
            return process_replica(path,features,radius,10,300,250,5000)

    def feature(self, identifier, lon, low=990, high=1010):
        return {'properties':{'resource_id':identifier,'network':'UAM','vertical_intervals_m':[[low,high]],'altitude_m':(low+high)/2},'geometry':{'coordinates':[lon,0.]}}

    def test_interpolation_duplicates_zero_windows_partial_and_event_direction(self):
        lines='0,A,0,-0.002,0,1000,0,0,0\n10,A,0,0.002,450,1000,0,0,0\n10,A,0,0.002,450,1000,0,0,0\n35,B,1,1,0,1000,0,0,0\n'
        row=self.run_log(lines,[self.feature('x',0.)])[0]
        self.assertEqual(row['operations'],1)
        self.assertEqual(row['window_rates_per_hour'],[360.,0.,0.])
        self.assertEqual(row['excluded_partial_seconds'],5)
        self.assertAlmostEqual(row['p95_throughput_per_hour'],324.)
        self.assertAlmostEqual(row['passage_events'][0]['time_s'],5.)
        self.assertAlmostEqual(row['passage_events'][0]['direction_deg'],90.)

    def test_overlap_competes_and_altitude_bands_remain_distinct(self):
        lines='0,A,0,-0.002,0,1000,0,0,0\n10,A,0,0.002,450,1000,0,0,0\n'
        # Both centers lie on path: closest distance ties cannot resolve route.
        rows=self.run_log(lines,[self.feature('a',0.),self.feature('b',0.0001)])
        self.assertEqual([r['operations'] for r in rows],[0,0])
        self.assertEqual([r['ambiguous_encounters'] for r in rows],[1,1])
        rows=self.run_log(lines,[self.feature('a',0.),self.feature('b',0.,1090,1110)])
        self.assertEqual([r['operations'] for r in rows],[1,0])

    def test_disjoint_contacts_one_sparse_segment_are_two_passages(self):
        rows=self.run_log('0,A,0,-0.005,0,1000,0,0,0\n10,A,0,0.005,1200,1000,0,0,0\n',[self.feature('a',-.003),self.feature('b',.003)])
        self.assertEqual([r['operations'] for r in rows],[1,1])

    def test_conflicting_duplicates_raise(self):
        with self.assertRaisesRegex(ValueError,'Conflicting duplicate'):
            self.run_log('0,A,0,0,0,1000,0,0,0\n0,A,0,0.001,0,1000,0,0,0\n',[self.feature('a',0.)])

    def test_pooled_percentile_not_sum_or_average_individual_percentiles(self):
        self.assertAlmostEqual(percentile95([0,0,0,100]),85)
        self.assertEqual(percentile95([0]*20+[100]),0)
        self.assertIsNone(percentile95([]))

    def test_scn_validation_rejects_wrong_corridor(self):
        from src.uam_dashboard.corridor_validation import validate_c2_corridor_scenarios
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'C2.scn'
            path.write_text('00:00:00> CRE A EVTOL 0 0 0 3000 100\n00:00:00> ADDWPT A 0 0.01 3000 100\n00:00:00> ADDWPT A 0 0.02 3000 100\n')
            routes=[{'coordinates':[[0,0],[0,.02]]}]
            audit=validate_c2_corridor_scenarios([path],routes)
            self.assertEqual(audit[0]['checked_interior_positions'],1)
            with self.assertRaisesRegex(ValueError,'Corridor/SCN mismatch'):
                validate_c2_corridor_scenarios([path],[{'coordinates':[[1,0],[1,.02]]}])

    def test_unknown_reh_altitude_never_becomes_zero_capacity(self):
        row=self.run_log('0,A,0,0,0,1000,0,0,0\n20,A,0,0,50,1000,0,0,0\n',[{'properties':{'resource_id':'REH','network':'REH','altitude_m':None,'vertical_intervals_m':[]},'geometry':{'coordinates':[0.,0.]}}])[0]
        self.assertIsNone(row['operations'])
        self.assertIsNone(row['p95_throughput_per_hour'])
        self.assertEqual(row['window_rates_per_hour'],[])

    def test_vertiport_configuration_and_invalid_coordinates(self):
        path=ROOT/'data/corridors/new_scenario_horizontal_3000ft_displaced.csv'
        with self.assertRaisesRegex(ValueError,'Expected vertiports'):
            load_uam_corridor_network(path,{f'VP-{i:03d}' for i in range(1,7)})
        self.assertEqual(len(load_uam_corridor_network(path,{f'VP-{i:03d}' for i in range(1,13)})['vertiports']),12)
        with tempfile.TemporaryDirectory() as directory:
            bad=Path(directory)/'bad.csv'
            bad.write_text('route,id,name,lat,lon,type,altitude,height,width\nR,1,VP-001,nan,0,Vertiport,900,20,40\nR,2,VP-002,0,0,Vertiport,900,20,40\n')
            with self.assertRaisesRegex(ValueError,'Invalid corridor'):
                load_uam_corridor_network(bad)

    def test_cli_publishes_fresh_nulls_then_recomputes_and_audits_events(self):
        import subprocess, sys
        network=load_uam_corridor_network(ROOT/'data/corridors/scenario_horizontal_3000ft_expanded_displaced.csv')
        selected=next(f for f in named_waypoint_features(network['routes'],load_reh_network(DEFAULT_REH_XML_PATH)['segments']) if f['properties']['network']=='UAM')
        lon,lat=selected['geometry']['coordinates'];p={'lat':lat,'lon':lon,'altitude_m':selected['properties']['altitude_m']}
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory); assets=out/'assets'; results=assets/'data/critical_waypoints'
            args=[sys.executable,str(ROOT/'critical_waypoints.py'),'--uam-csv',network['source'],'--output-dir',str(results),'--dashboard-assets',str(assets)]
            subprocess.run(args+['--geometry-only'],check=True,capture_output=True)
            rows=list(__import__('csv').DictReader((results/'critical_waypoints.csv').read_text(encoding='utf-8').splitlines()))
            self.assertTrue(all(row['status']=='unavailable_raw_logs' and row['p95_throughput_per_hour']=='' for row in rows))
            log=out/'STATELOG_C1.log'; log.write_text(''.join(f"{t},A,{p['lat']},{p['lon']},{t},{p['altitude_m']},0,0,0\n" for t in (0,900,1800)))
            (out/'STATELOG_C2.log').write_text(log.read_text())
            manifest=out/'manifest.csv';manifest.write_text('scenario,path\nC1,STATELOG_C1.log\nC2,STATELOG_C2.log\n')
            subprocess.run(args+['--manifest',str(manifest)],check=True,capture_output=True)
            rows=list(__import__('csv').DictReader((results/'critical_waypoints.csv').read_text(encoding='utf-8').splitlines()))
            self.assertTrue(any(float(row['p95_throughput_per_hour'] or 0)>0 for row in rows))
            events=[json.loads(line) for line in (results/'passage_events.jsonl').read_text().splitlines()]
            self.assertEqual(len(events),6)
            self.assertEqual({e['flight_instance'] for e in events},{0,1,2})
            self.assertEqual(json.loads((results/'run_metadata.json').read_text())['status'],'recomputed')
            before=(results/'critical_waypoints.csv').read_bytes()
            manifest.write_text('scenario,path\nC1,STATELOG_C1.log\nC2,STATELOG_C1.log\n')
            failed=subprocess.run(args+['--manifest',str(manifest)],capture_output=True)
            self.assertNotEqual(failed.returncode,0)
            self.assertIn(b'cannot be reused',failed.stderr)
            self.assertEqual((results/'critical_waypoints.csv').read_bytes(),before)

    def test_reh_selection_matches_original_junctions(self):
        from src.uam_dashboard.topology import reh_junction_features
        segments=load_reh_network(DEFAULT_REH_XML_PATH)['segments']
        original=reh_junction_features(segments)
        selected=named_waypoint_features([],segments)
        def topology_key(f):
            return tuple(round(v,6) for v in f['geometry']['coordinates'])
        self.assertEqual(len(selected),31)
        self.assertEqual({topology_key(f):f['properties']['network_degree'] for f in selected},
                         {topology_key(f):f['properties']['network_degree'] for f in original})
        self.assertEqual({f['properties']['label'] for f in selected},
                         {f['properties']['label'] for f in original})

    def test_uam_selection_requires_reh_junction_and_nonterminal_use(self):
        reh=load_reh_network(DEFAULT_REH_XML_PATH)['segments']
        for filename,expected in [('scenario_horizontal_3000ft_expanded_displaced.csv',16),('new_scenario_horizontal_3000ft_displaced.csv',28)]:
            routes=load_uam_corridor_network(ROOT/'data/corridors'/filename)['routes']
            features=named_waypoint_features(routes,reh)
            uam=[f for f in features if f['properties']['network']=='UAM']
            self.assertEqual(len(uam),expected)
            self.assertEqual(sum(f['properties']['network']=='REH' for f in features),31)
            self.assertTrue(all(f['properties']['network_degree']>=3 and not f['properties']['terminal_only'] and f['properties']['reh_reference']['horizontal_distance_m']<=500 for f in uam))
            self.assertNotIn('CLUBE_SIRIO',[f['properties']['normalized_name'] for f in uam])
            self.assertTrue(any(f['properties']['normalized_name']=='AVENIDA_MORUMBI' for f in uam))
            self.assertEqual({f['properties']['resource_id'] for f in features},{f['properties']['resource_id'] for f in named_waypoint_features(list(reversed(routes)),list(reversed(reh)))})

    def test_alias_spatial_guard_and_terminal_branch_cannot_inherit_reh_degree(self):
        def point(name,lat,lon,kind='Waypoint'):
            return dict(name=name,type=kind,lat=lat,lon=lon,altitude_m=900,height_m=20,width_m=40)
        center=point('AVENIDA_MORUMBI',0.,0.)
        tips=[point('A',-.01,0.),point('B',.01,0.),point('C',0.,.01)]
        routes=[dict(resource_id=str(i),label=str(i),points=[center,tip]) for i,tip in enumerate(tips)]
        reh=[dict(resource_id='REH1',label='REH1',explicit_fixes=[dict(name='Morumbi',lat=0.,lon=0.)])]
        selected=named_waypoint_features(routes,reh)
        match=next(f['properties'] for f in selected if f['properties']['network']=='UAM')
        self.assertEqual(match['reh_reference']['match_method'],'documented_alias')
        self.assertEqual(match['network_degree'],3)
        reh[0]['explicit_fixes'][0]['lon']=1.
        self.assertFalse(any(f['properties']['network']=='UAM' for f in named_waypoint_features(routes,reh)))
        # Even a branched gateway is excluded when every occurrence accesses a terminal.
        reh[0]['explicit_fixes'][0]['lon']=0.
        for r in routes:r['points'].insert(0,point('VP-001',-.02,0.,'Vertiport'))
        audit=uam_selection_inventory(routes,reh)
        center_props=next(f['properties'] for f in audit if f['properties']['normalized_name']=='AVENIDA_MORUMBI')
        self.assertIn('terminal_gateway_only',center_props['selection_reasons'])
        self.assertFalse(center_props['capacity_eligible'])

if __name__=='__main__': unittest.main()
