import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.uam_dashboard.publication import read_bundle, write_publication, repack_publication, check_publication


class PublicationTests(unittest.TestCase):
    def test_lossless_parts_and_repack_without_local_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runs = [dict(id=f'r{i}', name=f'C{i}', metadata={'scenario_key': f'C{i}'},
                         dashboard={'summary': {'records': 42}}, tracks={'text': 'ação 😀 </script> "\\\n' * 20}) for i in range(2)]
            model = dict(runs=runs, dashboard={'metric_catalog_version': 'test'}, comparison={'days': []}, tracks=runs[0]['tracks'])
            manifest = write_publication(root, model, part_characters=40)
            self.assertNotIn('tracks', manifest)
            self.assertTrue(all('tracks' not in run for run in manifest['runs']))
            for run in runs:
                self.assertEqual(json.loads((root / f'assets/data/runs/{run["id"]}.json').read_text(encoding='utf-8')), run)
                (root / f'assets/data/runs/{run["id"]}.json').unlink()
            repack_publication(root)
            self.assertEqual(read_bundle(root / 'assets/data_bundle.js')['bundle_format_version'], 2)
            for run in runs:
                self.assertEqual(json.loads((root / f'assets/data/runs/{run["id"]}.json').read_text(encoding='utf-8')), run)
            # Obsolete generated chunks disappear, unrelated files remain.
            keep = root / 'assets/run_data/keep.txt'; keep.write_text('keep')
            write_publication(root, dict(model, runs=runs[:1]))
            self.assertTrue(keep.exists())
            self.assertEqual(len(list(keep.parent.glob('*.js'))), 1)

    def test_repack_rejects_a_corrupt_fragment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = write_publication(root, {'runs': [{'id': 'r1', 'metadata': {}, 'value': 42}]})
            path = root / manifest['runs'][0]['data_parts'][0]
            path.write_text(path.read_text().replace('42', '43'))
            with self.assertRaisesRegex(ValueError, 'mismatch'):
                repack_publication(root)

    def test_publication_budget_excludes_only_local_audits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audit = root / 'assets/data/critical_waypoints/passage_events.jsonl'
            audit.parent.mkdir(parents=True); audit.write_text('x' * 100)
            local_run = root / 'assets/data/runs/r1.json'
            local_run.parent.mkdir(parents=True); local_run.write_text('x' * 100)
            with patch('src.uam_dashboard.publication.MAX_ASSET_BYTES', 50):
                check_publication(root)
                (root / 'assets/data_bundle.js').write_text('x' * 100)
                with self.assertRaisesRegex(ValueError, 'data_bundle.js'):
                    check_publication(root)

    def test_recovery_preserves_generated_rankings(self):
        import prepare_publication
        import sys
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_publication(root, {'runs': [{'id': 'r1', 'metadata': {}, 'value': 42}]})
            path = root / 'assets/waypoint_rankings.js'
            path.write_text('actual numerical results')
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            with patch.object(sys, 'argv', ['prepare_publication.py', '--output', str(root)]):
                prepare_publication.main()
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
