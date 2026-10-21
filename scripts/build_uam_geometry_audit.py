"""Reproduce the VP-005–VP-006 corridor merge audit without simulation logs."""
from pathlib import Path
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import PathPatch
from matplotlib.path import Path as PlotPath
from src.uam_dashboard.capacity import _buffered_route_groups, _official_uam_route_groups
from src.uam_dashboard.corridor_geometry import uam_geometry
from src.uam_dashboard.named_waypoints import source_record
from src.uam_dashboard.uam_corridor_parser import load_uam_corridor_network


def main():
    destination=ROOT/'reports/uam_geometry_2026-10-21'
    destination.mkdir(parents=True,exist_ok=True)
    summaries={}
    for stage,filename in [('1','scenario_horizontal_3000ft_expanded_displaced.csv'),
                           ('2','new_scenario_horizontal_3000ft_displaced_validated.csv')]:
        csv=ROOT/'data/corridors'/filename
        routes=load_uam_corridor_network(csv)['routes']
        geometry=uam_geometry(routes)
        geometry['audit']['source']=source_record(csv)
        summaries[stage]=geometry['audit']
        (destination/f'network_stage_{stage}.json').write_text(json.dumps(geometry,ensure_ascii=False,indent=2),encoding='utf-8')
        fig,axes=plt.subplots(1,2,figsize=(12,6),sharex=True,sharey=True,layout='constrained')
        original=_buffered_route_groups(_official_uam_route_groups(routes),250)
        def polygon_patch(geometry, **style):
            # Compound paths preserve holes, just as GeoJSON/Leaflet do.
            return PathPatch(PlotPath.make_compound_path(*[PlotPath(ring,closed=True) for ring in geometry['coordinates']]),**style)
        for corridor in original:
            axes[0].add_patch(polygon_patch(corridor['buffer_geometry'],facecolor='#f472b6',edgecolor='#be185d',alpha=.15,linewidth=.7))
        for feature in geometry['projection']['features']:
            axes[1].add_patch(polygon_patch(feature['geometry'],facecolor='#f472b6',edgecolor='#be185d',alpha=.25,linewidth=1))
        for feature in geometry['centerlines']['features']:
            c=feature['geometry']['coordinates']
            axes[1].plot([p[0] for p in c],[p[1] for p in c],color='#64748b',alpha=.55,linewidth=.6)
        local=[]
        for feature in geometry['junctions']['features']:
            lon,lat,alt=feature['geometry']['coordinates']
            if -46.846<=lon<=-46.775 and -23.568<=lat<=-23.510:
                local.append(feature)
                axes[1].scatter(lon,lat,s=22,facecolor='#22d3ee',edgecolor='#075985',linewidth=.7,zorder=4)
        for ax in axes:
            ax.set(xlim=(-46.846,-46.775),ylim=(-23.568,-23.510),xlabel='Longitude (graus)')
            ax.set_aspect(1/.916)
            ax.grid(alpha=.16)
        axes[0].set_ylabel('Latitude (graus)')
        axes[0].set_title('Antes: uma área por rota OD')
        axes[1].set_title('Depois: área unificada e junções dos eixos 3D')
        fig.suptitle(f'Rede de {6 if stage=="1" else 12} vertiportos · entorno VP-005 / Rodoanel Castelo\nRecorte do trajeto VP-005–VP-006; sem ajuste de proximidade ou alteração das rotas',fontsize=12)
        fig.savefig(destination/f'vp005_vp006_stage_{stage}.png',dpi=200)
        plt.close(fig)
        (destination/f'local_junctions_stage_{stage}.geojson').write_text(json.dumps({'type':'FeatureCollection','features':local},ensure_ascii=False,indent=2),encoding='utf-8')
    (destination/'summary.json').write_text(json.dumps(summaries,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summaries,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
