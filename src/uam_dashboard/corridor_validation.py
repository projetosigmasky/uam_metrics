"""Check a dedicated C2 SCN against the selected corridor centerlines."""
from pathlib import Path
import numpy as np
from .scenario_parser import load_bluesky_scenario
from .metrics import _point_to_polyline_distances_m
from .named_waypoints import source_record


def validate_c2_corridor_scenarios(paths, routes, tolerance_m=2.0):
    """Numeric exported SCN positions may be rounded (2 m tolerance).

    Origins and final arrival fixes are excluded as terminal procedures. Every
    remaining planned eVTOL position must lie on the chosen corridor centerlines.
    C1 shared-REH paths are not used to select a dedicated UAM CSV.
    """
    audits=[]
    for path in sorted(set(map(Path, paths))):
        flights=[f for f in load_bluesky_scenario(path) if f['vehicle_type']=='eVTOL']
        points=np.asarray([[c[1],c[0]] for f in flights for c in f['coordinates'][1:-1]],dtype=float)
        if len(points)==0:
            raise ValueError(f"Cannot validate dedicated C2 corridor: no interior eVTOL coordinates in {path}")
        distances=np.full(len(points),np.inf)
        for route in routes:
            distances=np.minimum(distances,_point_to_polyline_distances_m(points,np.asarray(route['coordinates'],dtype=float)))
        bad=int(np.sum(distances>tolerance_m))
        if bad:
            raise ValueError(f"Corridor/SCN mismatch in {path.name}: {bad}/{len(points)} interior eVTOL positions exceed {tolerance_m} m; max {float(distances.max()):.1f} m. Select the export belonging to this run; do not substitute a newer scenario.")
        audits.append({**source_record(path),'checked_interior_positions':len(points),'max_horizontal_deviation_m':float(distances.max()),'tolerance_m':tolerance_m,'vertical_validation':'not available in scenario_parser; exported corridor envelope used'})
    return audits
