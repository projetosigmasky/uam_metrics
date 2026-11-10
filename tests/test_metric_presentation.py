"""Publication hierarchy and traceability links must remain auditable."""
import ast
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path
import tempfile
import unittest

from src.uam_dashboard.metric_catalog import METRIC_CATALOG, write_metric_matrix

ROOT = Path(__file__).resolve().parents[1]


class Structure(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.stack = []
        self.nodes = {}
        self.feed(text)
        assert not self.stack, self.stack

    def handle_starttag(self, tag, attrs):
        node = dict(attrs)
        node['tag'] = tag
        if 'id' in node:
            assert node['id'] not in self.nodes, node['id']
            self.nodes[node['id']] = (node, list(self.stack))
        if tag not in {'meta', 'link', 'input', 'img', 'br', 'hr'}:
            self.stack.append(node)

    def handle_endtag(self, tag):
        assert self.stack and self.stack[-1]['tag'] == tag, (tag, self.stack[-1:])
        self.stack.pop()

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if self.stack and self.stack[-1]['tag'] == tag:
            self.handle_endtag(tag)


class MetricPresentationTests(unittest.TestCase):
    def test_only_five_formal_kpa_panels_are_published(self):
        html = (ROOT / 'web/index.html').read_text(encoding='utf-8')
        dom = Structure(html)
        for panel in ('safety', 'efficiency', 'capacity', 'predictability', 'equity'):
            self.assertEqual(dom.nodes[f'panel-{panel}'][0]['role'], 'tabpanel')
            self.assertIn(f'kpis-{panel}', dom.nodes)
            self.assertIn(f'charts-{panel}', dom.nodes)
            self.assertNotIn(f'stability-{panel}', dom.nodes)
        for removed in ('auxiliary-', 'chart-severity', 'capacity-atd', 'traceability-table', 'data-kpa-tab="overview"'):
            self.assertNotIn(removed, html)
        self.assertEqual({m['kpa'] for m in METRIC_CATALOG},
                         {'Segurança', 'Eficiência', 'Capacidade', 'Previsibilidade', 'Equidade'})
        self.assertEqual(len(METRIC_CATALOG), 22)
        self.assertTrue(all(m['presentation_group'] == 'kpi' for m in METRIC_CATALOG))

    def test_overview_and_each_kpa_have_separate_maps(self):
        html = (ROOT / 'web/index.html').read_text(encoding='utf-8')
        dom = Structure(html)
        self.assertLess(html.index('data-kpa-tab="maps"'), html.index('data-kpa-tab="safety"'))
        self.assertEqual(dom.nodes['tab-maps'][0]['aria-selected'], 'true')
        for panel in ('maps', 'safety', 'efficiency', 'capacity', 'predictability', 'equity'):
            self.assertTrue(any(p.get('id') == f'panel-{panel}' for p in dom.nodes[f'indicator-map-{panel}'][1]))
        self.assertTrue(any(p.get('id') == 'panel-safety' for p in dom.nodes['viewer3d-canvas'][1]))
        self.assertTrue(any(p.get('id') == 'panel-resources' for p in dom.nodes['map'][1]))
        self.assertNotIn('conflict-timeline-body', dom.nodes)

    @unittest.skipUnless(shutil.which('node'), 'Node.js required for JavaScript presentation checks')
    def test_public_series_exclude_internal_diagnostics(self):
        subprocess.run(['node', 'tests/test_kpi_visibility.cjs'], cwd=ROOT, check=True, capture_output=True, text=True)

    def test_traceability_points_to_existing_functions(self):
        ids = [m['id'] for m in METRIC_CATALOG]
        self.assertEqual(len(ids), len(set(ids)))
        for metric in METRIC_CATALOG:
            for reference in metric['code_reference'].split('; '):
                if reference == '-':
                    continue
                filename, function = reference.split('::')
                source = ROOT / filename if (ROOT / filename).is_file() else ROOT / 'src/uam_dashboard' / filename
                functions = {node.name for node in ast.parse(source.read_text(encoding='utf-8')).body
                             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
                self.assertIn(function, functions, metric['id'])

    def test_markdown_matches_the_live_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'matrix.md'
            write_metric_matrix(target)
            self.assertEqual(target.read_text(encoding='utf-8'),
                             (ROOT / 'docs/MATRIZ_KPIS_PRODUTO_3.md').read_text(encoding='utf-8'))
