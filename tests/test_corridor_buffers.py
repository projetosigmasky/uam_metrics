"""Regression coverage for crossed and pinched UAM corridor footprints."""
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from shapely.geometry import LineString, Point, shape
from src.uam_dashboard.capacity import _corridor_buffer_geometry, _project_with_reference, _route_inside_mask
from src.uam_dashboard.uam_corridor_parser import load_uam_corridor_network
from generate_uam_projection import write_uam_projection_asset

ROOT=Path(__file__).resolve().parents[1]

class CorridorBufferTests(unittest.TestCase):
    def test_hairpin_duplicate_vertices_and_reversal_are_valid(self):
        line=np.array([[0.,0.],[0.,.01],[0.,.01],[.0001,.001],[0.,.005],[0.,0.]])
        geometry,area=_corridor_buffer_geometry(line,250.)
        polygon=shape(geometry)
        self.assertTrue(polygon.is_valid)
        self.assertGreater(area,0)
        self.assertTrue(all(polygon.covers(Point(lon,lat)) for lat,lon in line))

    def test_width_at_bend_matches_geometric_buffer_and_preserves_holes(self):
        line=np.array([[0.,0.],[0.,.02],[.02,.02],[.02,0.],[0.,0.]])
        geometry,area=_corridor_buffer_geometry(line,100.)
        self.assertTrue(shape(geometry).is_valid)
        self.assertEqual(len(geometry['coordinates']),2)
        expected=LineString(_project_with_reference(line,float(line[:,0].mean()))).buffer(100,quad_segs=16,cap_style='round',join_style='round')
        self.assertAlmostEqual(area,expected.area)
        self.assertTrue(shape(geometry).covers(Point(.0005,.0005)))
        self.assertFalse(shape(geometry).covers(Point(.01,.01)))
        mask=_route_inside_mask(np.array([[.01,.01],[0.,.01]]),{'buffer_geometry':geometry},100.)
        self.assertEqual(mask.tolist(),[False,True])

    def test_every_exported_route_has_valid_buffer_and_keeps_centerline(self):
        for filename,count in [('scenario_horizontal_3000ft_expanded_displaced.csv',72),('new_scenario_horizontal_3000ft_displaced.csv',210)]:
            network=load_uam_corridor_network(ROOT/'data/corridors'/filename)
            self.assertEqual(len(network['routes']),count)
            for route in network['routes']:
                geometry,_=_corridor_buffer_geometry(np.asarray(route['coordinates']),route['semi_width_m'])
                polygon=shape(geometry)
                self.assertTrue(polygon.is_valid,route['label'])
                self.assertTrue(all(polygon.covers(Point(lon,lat)) for lat,lon in route['coordinates']),route['label'])

    def test_export_preserves_complete_valid_geometry_and_width(self):
        with tempfile.TemporaryDirectory() as directory:
            write_uam_projection_asset(ROOT/'data/corridors/scenario_horizontal_3000ft_expanded_displaced.csv',Path(directory))
            text=(Path(directory)/'assets/uam_projection.js').read_text(encoding='utf-8')
            collection=json.loads(text.split('=',1)[1].strip().rstrip(';'))
            self.assertEqual(len(collection['features']),72)
            self.assertTrue(all(shape(f['geometry']).is_valid and f['properties']['buffer_method']=='metric_linestring_buffer_round_joins_caps' and f['properties']['width_m']>0 for f in collection['features']))

if __name__=='__main__':unittest.main()
