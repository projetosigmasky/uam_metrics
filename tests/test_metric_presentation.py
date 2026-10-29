"""Publication hierarchy and traceability links must remain auditable."""
import ast
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
    def test_optional_content_is_closed_and_primary_capacity_is_visible(self):
        dom = Structure((ROOT / 'web/index.html').read_text(encoding='utf-8'))
        for panel in ('overview', 'safety', 'efficiency', 'capacity'):
            node, _ = dom.nodes[f'auxiliary-{panel}']
            self.assertEqual(node['tag'], 'details')
            self.assertNotIn('open', node)
        for name in ('metric-records', 'metric-aircraft', 'metric-peak', 'kpa-safety-sample',
                     'kpa-spatial-adherence', 'capacity-area', 'capacity-crossings',
                     'chart-active', 'chart-altitude', 'chart-separation'):
            _, parents = dom.nodes[name]
            self.assertTrue(any('auxiliary-metrics' in p.get('class', '') for p in parents), name)
        for name in ('metric-lowc', 'metric-nmac', 'metric-flight-time', 'metric-distance',
                     'chart-severity', 'capacity-table-body', 'capacity-atd', 'waypoint-ranking-table-body'):
            _, parents = dom.nodes[name]
            self.assertFalse(any('auxiliary-metrics' in p.get('class', '') for p in parents), name)
        _, parents = dom.nodes['capacity-table-body']
        self.assertFalse(any(p['tag'] == 'details' for p in parents))

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
