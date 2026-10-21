"""Scenario identity, replica density and conservative UAM merge regressions."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import numpy as np
from shapely.geometry import shape
from shapely.ops import unary_union
from src.uam_dashboard.config import DashboardConfig, DEFAULT_REH_XML_PATH
from src.uam_dashboard.corridor_geometry import uam_geometry
from src.uam_dashboard.capacity import _buffered_route_groups, _official_uam_route_groups
from src.uam_dashboard.experiment import experiment_metadata, matching_scenario, scenario_stage
from src.uam_dashboard.exports import density_grid, merge_density_grids
from src.uam_dashboard.run_config import load_run_selection
from src.uam_dashboard.uam_corridor_parser import load_uam_corridor_network

ROOT = Path(__file__).resolve().parents[1]
CSV1 = ROOT / 'data/corridors/scenario_horizontal_3000ft_expanded_displaced.csv'
CSV2 = ROOT / 'data/corridors/new_scenario_horizontal_3000ft_displaced_validated.csv'
CODES = ('C1.1', 'C1.2', 'C2.1', 'C2.2')


def route(label, coordinates):
    points = [dict(id=i, name=f'W{i}', type='Waypoint', lon=x, lat=y,
                   altitude_m=z, height_m=20., width_m=40.) for i,(x,y,z) in enumerate(coordinates)]
    return dict(resource_id=label,label=label,route_name=label,od_pair=label,parallel_track=None,
                coordinates=[[p['lat'],p['lon']] for p in points], altitudes_m=[p['altitude_m'] for p in points],
                height_m=20.,width_m=40.,semi_width_m=20.,points=points,geometry_source='test')


class DashboardScenarioTests(unittest.TestCase):
    def test_failed_run_does_not_write_selection_or_publish(self):
        import generate_reports
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run=root/'runs/failed';run.mkdir(parents=True)
            (run/'summary.json').write_text(json.dumps({'error':'command rejected','scenarios':[{'status':'command_failed'}]}))
            config=root/'config.json';config.write_text('{}')
            with patch.object(generate_reports,'__file__',str(root/'generate_reports.py')), \
                 patch('sys.argv',['generate_reports.py','--config',str(config),'--run-id','failed','--runs-root',str(root/'runs')]), \
                 patch.object(generate_reports.subprocess,'run') as command:
                with self.assertRaisesRegex(ValueError,'incomplete or failed'):
                    generate_reports.main()
            command.assert_not_called()
            self.assertFalse((root/'run_config.local.json').exists())
            self.assertFalse((root/'docs').exists())
    def test_static_refresh_preserves_offline_calibration_and_removes_public_page(self):
        from generate_dashboard import copy_static_assets
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'docs'; assets=output/'assets';assets.mkdir(parents=True)
            (assets/'baseline_calibration_data.js').write_text('actual numerical results')
            (output/'calibration.html').write_text('retired page')
            copy_static_assets(output)
            self.assertFalse((output/'calibration.html').exists())
            self.assertEqual((assets/'baseline_calibration_data.js').read_text(),'actual numerical results')
            html=(output/'index.html').read_text(encoding='utf-8')
            for retired in ('id="layer-tracks"','id="layer-planned"','viewer3d-canvas','baseline_calibration'):
                self.assertNotIn(retired,html)

    def test_overlap_prefilter_keeps_the_intersection_vertices(self):
        from src.uam_dashboard.capacity import _polygon_overlap_points, _project_with_reference
        a={'polygons':[[[0,0],[.02,0],[.02,.02],[0,.02],[0,0]]]}
        b={'polygons':[[[.01,.01],[.03,.01],[.03,.03],[.01,.03],[.01,.01]]]}
        points=_polygon_overlap_points(a,b,0)
        # Preserve the old routine's multiplicity, including the closed-ring
        # start/end vertex. Its weighted intersection centroid must not change.
        expected=_project_with_reference(np.array([[.02,.02],[.02,.01],[.01,.02],[.01,.01],[.01,.01]]),0)
        self.assertEqual(len(points),5)
        self.assertTrue(np.allclose(sorted(map(tuple,points)),sorted(map(tuple,expected))))
        distant={'polygons':[[[1,1],[2,1],[2,2],[1,2],[1,1]]]}
        self.assertEqual(_polygon_overlap_points(a,distant,0),[])

    def test_dashboard_build_aggregates_both_replicas_and_switches_geometry(self):
        from generate_dashboard import build_dashboard
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);logs=[];scenarios=[]
            for code in CODES:
                for replica in (1,2):
                    stem=f'produto2_{code}_p100_r{replica:03d}_off'
                    log=root/code/f'STATELOG_{stem}.log'
                    log.parent.mkdir(exist_ok=True)
                    # Second replica uses a separate spatial cell, proving it
                    # contributes despite not being selected for chart rendering.
                    lat=-23.55 if replica==1 else -23.56
                    log.write_text(''.join(f'{t},EV1,{lat},{-46.63+t*.00001},{t*10},900,40,40,40\n' for t in (0,60,120)))
                    scn=root/f'{stem}.scn'
                    scn.write_text(f'00:00:00> CRE EV1 EVTOL {lat} -46.63 0 3000 40\n00:00:00> ADDWPT EV1 {lat} -46.62 3000 40\n')
                    logs.append(log);scenarios.append(scn)
            output=root/'docs'
            build_dashboard(DashboardConfig(log_paths=tuple(logs),scenario_paths=tuple(scenarios),output_dir=output,
                            workers=2,reh_xml_path=DEFAULT_REH_XML_PATH,uam_corridor_csv_path=CSV1,
                            uam_corridor_csv_by_scenario={c:CSV1 if c.endswith('.1') else CSV2 for c in CODES}))
            runs=[json.loads(p.read_text(encoding='utf-8')) for p in (output/'assets/data/runs').glob('*.json')]
            self.assertEqual({r['metadata']['scenario_key'] for r in runs},set(CODES))
            for run in runs:
                self.assertEqual(run['replica_count'],2)
                self.assertEqual(run['density']['replica_count'],2)
                self.assertEqual(run['density']['position_sample_count'],6)
                self.assertTrue(any(p[0]<-23.555 for p in run['heatmap']))
                self.assertIn('tracks',run)  # Calculation/audit feature retained.
                self.assertIn('planned_routes',run)
                if run['metadata']['scenario_key'].startswith('C1'):
                    self.assertEqual(run['uam_projection']['features'],[])
                    self.assertTrue(all(f['properties']['network']=='REH' for f in run['candidate_nodes']['features']))
                else:
                    self.assertEqual(run['uam_geometry_audit']['route_count'],72 if run['metadata']['scenario_key'].endswith('.1') else 210)
            comparison=json.loads((output/'assets/data/comparison.json').read_text(encoding='utf-8'))
            rows=comparison['days'][0]['rows']
            self.assertEqual({r['scenario_key'] for r in rows if r['is_reference']},{'C1.1','C1.2'})
            self.assertFalse((output/'calibration.html').exists())

    def test_dotted_and_underscore_codes_keep_replica_and_network(self):
        for code in (*CODES, 'C3.1.2', 'C8.2.1', 'C10.2'):
            for serialized in (code,code.replace('.','_')):
                m=experiment_metadata(f'STATELOG_orch_produto2_{serialized}_p100_r050_off.log')
                self.assertEqual((m['scenario_key'],m['replica']),(code,50))
        self.assertEqual(scenario_stage('C3.1.2'),'2')
        self.assertIsNone(scenario_stage('C5.2'))
        self.assertIsNone(scenario_stage('C10.2'))

    def test_pairing_cannot_substitute_missing_replica_or_network(self):
        paths=tuple(Path(f'scenario/produto2_{code}_p100_r001_off.scn') for code in CODES)
        self.assertEqual(matching_scenario(Path('output/C1.1/STATELOG_produto2_C1_1_p100_r001_off.log'),paths),paths[0])
        self.assertIsNone(matching_scenario(Path('output/C1.1/STATELOG_produto2_C1.1_p100_r002_off.log'),paths))
        self.assertIsNone(matching_scenario(Path('STATELOG_produto2_C1.1_p100_r001_off.log'),paths+(Path('duplicate')/paths[0].name,)))

    def test_density_includes_every_record_and_empty_cells_in_replica_mean(self):
        frame=pd.DataFrame({'lat':[-23.55,-23.55,-23.54], 'lon':[-46.63,-46.63,-46.62]})
        grid=density_grid(frame)
        self.assertEqual(sum(c[2] for c in grid),3)
        pooled=merge_density_grids([grid,[]])
        self.assertEqual(sum(c[2] for c in pooled['cells']),1.5)
        self.assertEqual(pooled['replica_count'],2)
        repeated=merge_density_grids([grid]*50)
        self.assertEqual(repeated['position_sample_count'],150)
        self.assertEqual(repeated['cells'],merge_density_grids([grid])['cells'])

    def test_partial_overlap_and_reverse_routes_become_one_network(self):
        routes=[route('A',[(0,0,900),(.02,0,900)]),
                route('reverse',[(.02,0,900),(0,0,900)]),
                route('B',[(.005,0,900),(.015,0,900)]),
                route('branch',[(.01,0,900),(.01,.01,900)])]
        before=copy.deepcopy(routes)
        result=uam_geometry(routes)
        self.assertEqual(result['audit']['duplicate_segment_occurrences'],1)
        self.assertEqual(len(result['centerlines']['features']),5)
        self.assertEqual(len(result['junctions']['features']),1)
        self.assertEqual(result['junctions']['features'][0]['properties']['network_degree'],3)
        self.assertFalse(result['junctions']['features'][0]['properties']['capacity_resource'])
        self.assertEqual(routes,before)

    def test_crossing_at_different_altitudes_and_parallel_tracks_stay_separate(self):
        routes=[route('A',[(0,0,900),(.02,0,900)]),
                route('B',[(.01,-.01,1200),(.01,.01,1200)]),
                route('parallel',[(0,.0001,900),(.02,.0001,900)])]
        result=uam_geometry(routes)
        self.assertEqual(result['junctions']['features'],[])
        self.assertEqual(len(result['centerlines']['features']),3)

    def test_same_altitude_crossing_is_noded(self):
        result=uam_geometry([route('A',[(0,0,900),(.02,0,900)]),
                             route('B',[(.01,-.01,900),(.01,.01,900)])])
        self.assertEqual(result['audit']['geometric_junctions'],1)
        self.assertEqual(result['junctions']['features'][0]['properties']['network_degree'],4)

    def test_collinear_climb_connects_only_where_altitudes_meet(self):
        result=uam_geometry([route('climb',[(0,0,900),(.02,0,1100)]),
                             route('level',[(0,0,1000),(.02,0,1000)])])
        self.assertEqual(result['audit']['geometric_junctions'],1)
        self.assertEqual(result['junctions']['features'][0]['geometry']['coordinates'],[.01,0.,1000.])

    def test_dissolve_preserves_original_covered_area(self):
        routes=load_uam_corridor_network(CSV1)['routes']
        original=unary_union([shape(c['buffer_geometry']) for c in _buffered_route_groups(_official_uam_route_groups(routes),250)])
        dissolved=unary_union([shape(f['geometry']) for f in uam_geometry(routes)['projection']['features']])
        self.assertLess(original.symmetric_difference(dissolved).area,1e-12)

    def test_four_scenario_config_selects_two_correct_networks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run=root/'runs/completed'
            for code in CODES:
                (run/'output'/code).mkdir(parents=True)
                (run/'scenario'/code).mkdir(parents=True)
                (run/'output'/code/f'STATELOG_produto2_{code}_p100_r001_off.log').touch()
                (run/'scenario'/code/f'produto2_{code}_p100_r001_off.scn').touch()
            (run/'summary.json').write_text(json.dumps({'scenarios':[{'status':'completed'}]}))
            config=root/'config.json'
            settings=dict(runs_root=str(root/'runs'),run_name='completed',scenario_codes=CODES,expected_replicas_per_scenario=1,
                          uam_corridor_csv_by_stage={'1':str(CSV1),'2':str(CSV2)})
            config.write_text(json.dumps(settings))
            with patch('src.uam_dashboard.corridor_validation.validate_c2_corridor_scenarios') as validate:
                selected=load_run_selection(config)
                self.assertEqual(validate.call_count,2)
            self.assertEqual(selected.uam_corridor_csv_by_scenario['C2.1'],CSV1)
            self.assertEqual(selected.uam_corridor_csv_by_scenario['C2.2'],CSV2)
            settings['uam_corridor_csv_by_stage']['2']=str(CSV1)
            config.write_text(json.dumps(settings))
            with self.assertRaisesRegex(ValueError,'Wrong vertiport count'):
                load_run_selection(config)
            settings['uam_corridor_csv_by_stage']['2']=str(CSV2)
            config.write_text(json.dumps(settings))
            for folder,pattern in [('output','*.log'),('scenario','*.scn')]:
                path=next((run/folder/'C1.1').glob(pattern))
                path.rename(path.with_name(path.name.replace('r001','r002')))
            with self.assertRaisesRegex(ValueError,'require exactly replicas'):
                load_run_selection(config)


if __name__=='__main__': unittest.main()
