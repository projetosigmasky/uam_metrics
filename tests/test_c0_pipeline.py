"""C0 must stay helicopter-only, stage-free and bound to its own replicas."""
import json
import tempfile
import unittest
from pathlib import Path

from src.uam_dashboard.run_config import load_run_selection
from tests.test_scenario_catalog import make_run

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / 'data/corridors/scenario_horizontal_3000ft_expanded_displaced.csv'


class C0PipelineTests(unittest.TestCase):
    def config(self, root, codes, name='auto'):
        path = root / 'config.json'
        path.write_text(json.dumps(dict(run_name=name, runs_root=str(root / 'runs'),
            scenario_codes=codes, expected_replicas_per_scenario=1,
            require_all_scenarios=True, uam_corridor_csv_by_stage={'1': str(CSV)})))
        return path

    def test_c0_discovery_and_fixed_run_need_no_uam_assignment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for code in ('C0', 'C1.1'):
                make_run(root / 'runs', 'new_batch', code)
            for codes in (['C0'], ['C0', 'C1.1']):
                for name in ('auto', 'new_batch'):
                    selection = load_run_selection(self.config(root, codes, name))
                    self.assertEqual(len(selection.log_paths), len(codes))
                    self.assertEqual(selection.source_runs, {code: 'new_batch' for code in codes})
                    self.assertNotIn('C0', selection.uam_corridor_csv_by_scenario)
                    self.assertEqual(selection.uam_corridor_csv_path, CSV)

    def test_c0_wrong_replica_cannot_pass_by_file_count(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_run(root / 'runs', 'new_batch', 'C0', replica=2)
            with self.assertRaisesRegex(ValueError, 'require exactly replicas'):
                load_run_selection(self.config(root, ['C0'], 'new_batch'))

    def test_c0_dashboard_and_ranking_export_only_reh_resources(self):
        import sys
        from unittest.mock import patch
        from generate_dashboard import build_dashboard
        from critical_waypoints import main as ranking_main
        from src.uam_dashboard.config import DashboardConfig, DEFAULT_REH_XML_PATH
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = make_run(root / 'runs', 'new_batch', 'C0')
            log = next((run / 'output/C0').glob('*.log'))
            scn = next((run / 'scenario/C0').glob('*.scn'))
            log.write_text(''.join(f'{t},H1,-23.55,{-46.63+t*.000001},{t*10},900,40,40,40\n'
                                   for t in (0, 60, 120)))
            scn.write_text('00:00:00> CRE H1 R22 -23.55 -46.63 0 3000 40\n'
                           '00:00:00> ADDWPT H1 -23.55 -46.62 3000 40\n')
            output = root / 'docs'
            build_dashboard(DashboardConfig(log_paths=(log,), scenario_paths=(scn,),
                output_dir=output, workers=1, reh_xml_path=DEFAULT_REH_XML_PATH,
                uam_corridor_csv_path=CSV))
            result = json.loads(next((output / 'assets/data/runs').glob('*.json')).read_text(encoding='utf-8'))
            self.assertEqual(result['metadata']['scenario_key'], 'C0')
            self.assertIsNone(result['metadata']['network_stage'])
            self.assertEqual(result['uam_projection']['features'], [])
            self.assertTrue(all(f['properties']['network'] == 'REH'
                                for f in result['candidate_nodes']['features']))
            config = self.config(root, ['C0'], 'new_batch')
            with patch.object(sys, 'argv', ['critical_waypoints.py', '--config', str(config),
                '--output-dir', str(root / 'ranking'), '--dashboard-assets', str(root / 'assets')]):
                self.assertEqual(ranking_main(), 0)
            rows = (root / 'ranking/critical_waypoints.csv').read_text(encoding='utf-8')
            self.assertIn('REH', rows)
            self.assertNotIn('UAM', rows)
