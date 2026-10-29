import json
from pathlib import Path
from unittest.mock import patch

import unittest
import tempfile
import warnings

from src.uam_dashboard.experiment import experiment_metadata, scenario_stage
from src.uam_dashboard.scenario_catalog import NOMINAL_CODES, SCENARIOS
from src.uam_dashboard.run_config import load_run_selection

ROOT = Path(__file__).resolve().parents[1]


def make_run(root, name, code, replica=1, status='completed'):
    run = root / name
    (run / 'output' / code).mkdir(parents=True, exist_ok=True)
    (run / 'scenario' / code).mkdir(parents=True, exist_ok=True)
    (run / 'summary.json').write_text(json.dumps({'scenarios': [{'status': status}]}))
    stem = f'produto2_{code}_p100_r{replica:03d}_off'
    (run / 'output' / code / f'STATELOG_{stem}.log').touch()
    (run / 'scenario' / code / f'{stem}.scn').touch()
    return run


class ScenarioCatalogTests(unittest.TestCase):
    def test_report_commands_share_a_fixed_discovery(self):
        import generate_reports
        import sys
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runs = root / 'runs'
            make_run(runs, '20261027_batch', 'C1.1')
            config = root / 'config.json'
            config.write_text(json.dumps(dict(run_name='auto', runs_root=str(runs),
                scenario_codes=['C1.1'], expected_replicas_per_scenario=1,
                uam_corridor_csv_by_stage={'1': str(ROOT / 'data/corridors/scenario_horizontal_3000ft_expanded_displaced.csv')})))
            assets = root / 'docs/assets'
            assets.mkdir(parents=True)
            (root / 'docs/index.html').write_text((ROOT / 'web/index.html').read_text(encoding='utf-8'), encoding='utf-8')
            for name in ('data_bundle.js', 'waypoint_rankings.js', 'candidate_nodes.js', 'dashboard.js', 'dashboard.css', 'uam_projection.js', 'crossing_waypoints_3d.js', 'scenario_catalog.js'):
                (assets / name).write_text('fixture')
            called = []
            def command(argv, **kwargs):
                pinned = Path(argv[argv.index('--config') + 1])
                make_run(runs, '20261030_newer', 'C1.1')
                called.append(load_run_selection(pinned).source_runs)
            with patch.object(generate_reports, '__file__', str(root / 'generate_reports.py')), \
                 patch.object(sys, 'argv', ['generate_reports.py', '--config', str(config)]), \
                 patch.object(generate_reports.subprocess, 'run', side_effect=command):
                generate_reports.main()
            self.assertEqual(called, [{'C1.1': '20261027_batch'}] * 2)

    def test_micro_lowc_threshold_changes_measured_events(self):
        from generate_dashboard import analyze_log
        from src.uam_dashboard.config import DashboardConfig
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            counts = []
            for profile, threshold in ((1, 555.6), (2, 1111.2), (3, 1852.0)):
                log = root / f'STATELOG_produto2_C8.1.1.{profile}_p100_r001_off.log'
                # Two aircraft ~780 m apart: outside profile 1, inside 2 and 3.
                log.write_text(''.join(
                    f'{t},{aircraft},{lat},-46.63,{t*40},900,40,40,40\n'
                    for t in (0, 60, 120) for aircraft, lat in (('EV1', -23.55), ('EV2', -23.543))))
                result = analyze_log(log, DashboardConfig(log_paths=(log,)), root, 0, False)
                safety = result['dashboard']['safety']
                self.assertAlmostEqual(safety['lowc_horizontal_m'], threshold)
                counts.append(safety['lowc_events'])
            self.assertEqual(counts[0], 0)
            self.assertGreater(counts[1], 0)
            self.assertEqual(counts[1], counts[2])

    def test_canonical_catalog_profiles_and_references(self):
        assert len(NOMINAL_CODES) == 36
        for code in NOMINAL_CODES:
            row = SCENARIOS[code]
            metadata = experiment_metadata(f'STATELOG_produto2_{code.replace(".", "_")}_p100_r050_off.log')
            assert metadata['scenario_dimensions'] == row
            assert metadata['replica'] == 50
            assert scenario_stage(code) == ('1' if row['vertiports'] == 6 else '2')
            expected = 'c2' if code.startswith(('C3.', 'C4.')) else 'c1'
            assert metadata['reference_variant_key'] == f'{expected}.{scenario_stage(code)}'
        assert scenario_stage('C4.1.2.1') == '2'
        assert scenario_stage('C8.2.1.3') == '1'
        assert experiment_metadata('produto2_C5.1_p100_r001_off.scn')['disturbed']
        assert scenario_stage('C5.1') is None
        assert [SCENARIOS[f'C4.1.1.{p}']['lowc_distance_nm'] * 1852 for p in (1, 2, 3)] == [555.6, 1111.2, 1852.0]


    def test_discovery_selects_latest_complete_per_scenario_without_ambiguous_scns(self):
        with tempfile.TemporaryDirectory() as directory:
            self.check_discovery(Path(directory))

    def check_discovery(self, tmp_path):
        runs = tmp_path / 'runs'
        make_run(runs, '20261015_old', 'C1.1')
        make_run(runs, '20261027_new', 'C1.1')
        # A newer pilot has the wrong replica; it cannot displace a complete batch.
        make_run(runs, '20261028_pilot', 'C1.1', replica=2)
        make_run(runs, '20261029_failed', 'C1.1', status='failed')
        make_run(runs, '20261027_micro', 'C4.1.2.3')
        config = tmp_path / 'config.json'
        config.write_text(json.dumps(dict(run_name='auto', runs_root=str(runs),
            scenario_codes=['C1.1', 'C4.1.2.3', 'C8.1.1.1'], expected_replicas_per_scenario=1,
            uam_corridor_csv_by_stage={
                '1': str(ROOT / 'data/corridors/scenario_horizontal_3000ft_expanded_displaced.csv'),
                '2': str(ROOT / 'data/corridors/new_scenario_horizontal_3000ft_displaced_validated.csv')})))
        with patch('src.uam_dashboard.corridor_validation.validate_c2_corridor_scenarios'), warnings.catch_warnings(record=True):
            selection = load_run_selection(config)
        assert selection.source_runs == {'C1.1': '20261027_new', 'C4.1.2.3': '20261027_micro'}
        assert selection.unavailable_scenarios == ('C8.1.1.1',)
        assert len(selection.log_paths) == len(selection.scenario_paths) == 2
        assert all('old' not in str(p) for p in selection.scenario_paths)
        settings = json.loads(config.read_text())
        pinned = dict(settings, scenario_codes=list(selection.source_runs), scenario_runs=selection.source_runs)
        make_run(runs, '20261030_newer', 'C1.1')
        config.write_text(json.dumps(pinned))
        with patch('src.uam_dashboard.corridor_validation.validate_c2_corridor_scenarios'):
            self.assertEqual(load_run_selection(config).source_runs, selection.source_runs)
        # A fixed selection cannot silently fall back when its source disappears.
        pinned['scenario_runs']['C1.1'] = 'missing'
        config.write_text(json.dumps(pinned))
        with self.assertRaisesRegex(ValueError, 'C1.1'):
            load_run_selection(config)
        settings['require_all_scenarios'] = True
        config.write_text(json.dumps(settings))
        with patch('src.uam_dashboard.corridor_validation.validate_c2_corridor_scenarios'), self.assertRaisesRegex(ValueError, 'C8.1.1.1'):
            load_run_selection(config)
