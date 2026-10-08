"""Rank explicitly named UAM/REH waypoint positions from C1/C2 replicas.

Run this script on the machine holding the raw logs. Only CSV/JSON summaries
need to be copied back; STATELOG files are read one at a time in a stream.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from src.uam_dashboard.config import DEFAULT_REH_XML_PATH, EXTENDED_LOG_COLUMNS, LOG_COLUMNS
from src.uam_dashboard.run_config import load_run_selection
from src.uam_dashboard.reh_parser import load_reh_network
from src.uam_dashboard.uam_corridor_parser import load_uam_corridor_network


SCENARIO_RE = re.compile(r"(?:^|[_-])(C[12])(?:[_-]|$)", re.IGNORECASE)
EARTH_RADIUS_M = 6371000.0


def discover_logs(root: Path) -> list[tuple[str, Path]]:
    found = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".log", ".csv"} and "STATELOG" in path.name.upper():
            match = SCENARIO_RE.search(path.stem)
            if match:
                found.append((match.group(1).upper(), path))
    return found


def manifest_logs(path: Path) -> list[tuple[str, Path]]:
    found = []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            scenario = row["scenario"].strip().upper()
            if scenario not in {"C1", "C2"}:
                raise ValueError(f"Invalid scenario {scenario!r}; expected C1 or C2")
            log = Path(row["path"].strip())
            if not log.is_absolute():
                log = path.parent / log
            found.append((scenario, log))
    return found


def state_rows(path: Path):
    """Yield time, id, 3D position and flown distance from STATELOGs."""
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
        for line_number, line in enumerate(stream, 1):
            parts = [part.strip() for part in line.split(",")]
            if len(parts) < len(LOG_COLUMNS):
                continue
            try:
                simt = float(parts[0])
            except ValueError:
                continue
            names = EXTENDED_LOG_COLUMNS if len(parts) >= len(EXTENDED_LOG_COLUMNS) else LOG_COLUMNS
            try:
                fields = dict(zip(names, parts))
                row = (simt, fields["id"], float(fields["lat"]), float(fields["lon"]), float(fields["alt"]), float(fields["distflown"]))
            except ValueError as exc:
                raise ValueError(f"Invalid STATELOG row in {path}:{line_number}") from exc
            if not all(math.isfinite(value) for value in (row[0], row[2], row[3], row[4], row[5])):
                raise ValueError(f"Non-finite STATELOG value in {path}:{line_number}")
            yield row


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    a = math.sin(math.radians(lat2 - lat1) / 2) ** 2
    a += math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def crossing_index(features: list[dict], radius_m: float):
    # Approximate 250 m cells; exact capture is checked by haversine below.
    cell_deg = radius_m / 111000.0
    grid = defaultdict(list)
    for index, feature in enumerate(features):
        if feature["properties"].get("altitude_m") is None and not feature["properties"].get("vertical_intervals_m"):
            continue
        lon, lat = feature["geometry"]["coordinates"]
        lat_cell = math.floor(lat / cell_deg)
        lon_span = radius_m / (111000.0 * max(0.1, math.cos(math.radians(lat))))
        lo = math.floor((lon - lon_span) / cell_deg)
        hi = math.floor((lon + lon_span) / cell_deg)
        for y in range(lat_cell - 1, lat_cell + 2):
            for x in range(lo, hi + 1):
                grid[y, x].append(index)
    return grid, cell_deg


def process_replica(path: Path, features: list[dict], radius_m: float, window_s: int,
                    gap_s: float, reset_m: float, jump_m: float) -> list[dict]:
    """One passage per connected capture encounter/network, assigned to closest position.

    Overlapping cylinders compete, rather than crediting a flight to every nearby
    parallel. Ties are ambiguous and excluded. Linear interpolation never creates
    capacity resources. Reentry after exit is another passage, including reversal.
    """
    from src.uam_dashboard.waypoint_passages import contact, percentile95
    if min(radius_m, window_s, gap_s, jump_m) <= 0 or reset_m < 0:
        raise ValueError("Invalid capture/window/flight-instance settings")
    grid, cell_deg = crossing_index(features, radius_m)
    states = {}; encounters = {}; events = defaultdict(list); ambiguous = defaultdict(int)
    start = end = None; samples = 0
    def finish(key):
        encounter = encounters.pop(key, None)
        if encounter is None: return
        best = sorted(encounter["candidates"].items(), key=lambda item: (item[1][0], item[0]))
        index, (distance, timestamp, direction) = best[0]
        if len(best) > 1 and abs(best[1][1][0] - distance) < 0.001:
            for candidate, _ in best: ambiguous[candidate] += 1
            return
        events[index].append({"time_s": timestamp, "aircraft": key[0], "flight_instance": key[1],
                              "direction_deg": direction, "competing_positions": len(best)})
    for current in state_rows(path):
        simt, aircraft, lat, lon, altitude, distance = current
        if end is not None and simt < end: raise ValueError(f"STATELOG must be ordered by simt: {path}")
        start = simt if start is None else start; end = simt; samples += 1
        previous_state = states.get(aircraft)
        instance = previous_state[1] if previous_state else 0
        previous = previous_state[0] if previous_state else current
        reset = previous_state is not None and (simt-previous[0] > gap_s or distance+reset_m < previous[5]
                or haversine(previous[2],previous[3],lat,lon) > jump_m)
        if reset:
            for key in list(encounters):
                if key[:2] == (aircraft, instance): finish(key)
            instance += 1; previous = current
        if previous_state and simt == previous[0] and not reset:
            if current != previous: raise ValueError(f"Conflicting duplicate aircraft/time in {path}: {aircraft}/{simt}")
            continue
        states[aircraft] = current, instance
        contacts = defaultdict(list)
        # Bounding-box pruning avoids evaluating every cylinder for long STATELOGs.
        candidate_indices = set()
        for y in range(math.floor(min(previous[2],lat)/cell_deg), math.floor(max(previous[2],lat)/cell_deg)+1):
            for x in range(math.floor(min(previous[3],lon)/cell_deg), math.floor(max(previous[3],lon)/cell_deg)+1):
                candidate_indices.update(grid.get((y,x),()))
        for index in candidate_indices:
            feature = features[index]
            plon, plat = feature["geometry"]["coordinates"]
            if plat < min(previous[2],lat)-radius_m/110000 or plat > max(previous[2],lat)+radius_m/110000: continue
            lon_pad = radius_m/(110000*max(.1, math.cos(math.radians(plat))))
            if plon < min(previous[3],lon)-lon_pad or plon > max(previous[3],lon)+lon_pad: continue
            network = feature["properties"].get("network", "UAM")
            for lo,hi,u,d in contact(previous,current,feature,radius_m):
                contacts[network].append((lo,hi,index,u,d))
        networks = set(contacts) | {key[2] for key in encounters if key[:2] == (aircraft,instance)}
        dt=simt-previous[0]
        direction = math.degrees(math.atan2((lon-previous[3])*math.cos(math.radians(lat)),lat-previous[2])) % 360 if dt and (lat,lon)!=(previous[2],previous[3]) else None
        for network in networks:
            key=aircraft,instance,network
            for lo,hi,index,u,d in sorted(contacts[network]):
                encounter=encounters.get(key)
                if encounter is not None and lo > encounter["end_fraction"] + 1e-9: finish(key); encounter=None
                if encounter is None:
                    encounter={"end_fraction":hi,"candidates":{}}; encounters[key]=encounter
                encounter["end_fraction"]=max(encounter["end_fraction"],hi)
                candidate=(d,previous[0]+u*dt,direction)
                if index not in encounter["candidates"] or d < encounter["candidates"][index][0]: encounter["candidates"][index]=candidate
            encounter=encounters.get(key)
            if encounter:
                if encounter["end_fraction"] < 1-1e-9: finish(key)
                else: encounter["end_fraction"]=0.0
    for key in list(encounters): finish(key)
    if not samples: raise ValueError(f"No valid STATELOG samples in {path}")
    windows=int((end-start)//window_s)
    rows=[]
    for index,feature in enumerate(features):
        p=feature["properties"]; available=bool(p.get("vertical_intervals_m")) or p.get("altitude_m") is not None
        bins=[0]*windows
        for event in events[index]:
            bucket=int((event["time_s"]-start)//window_s)
            if 0 <= bucket < windows: bins[bucket]+=1
        rates=[n*3600/window_s for n in bins]
        rows.append({"waypoint_id":p["resource_id"],"criterion":p.get("criterion"),"network_degree":p.get("network_degree"),
                     "altitude_m":p.get("altitude_m"),"operations":len(events[index]) if available else None,
                     "full_window_operations":sum(bins) if available else None,
                     "mean_throughput_per_hour":sum(rates)/windows if available and windows else None,
                     "peak_throughput_per_hour":max(rates) if available and windows else None,
                     "p95_throughput_per_hour":percentile95(rates) if available else None,
                     "window_count":windows,"excluded_partial_seconds":end-start-windows*window_s,
                     "window_rates_per_hour":rates if available else [],"ambiguous_encounters":ambiguous[index],
                     "sample_count":samples,"passage_events":events[index] if available else []})
    return rows


def write_csv(path: Path, rows: list[dict]):
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    from src.uam_dashboard.named_waypoints import named_waypoint_features, source_record
    from src.uam_dashboard.waypoint_passages import percentile95
    from src.uam_dashboard.topology import write_candidate_node_assets
    parser = argparse.ArgumentParser(description="Named waypoint empirical demand P95; no demonstrated operational limit")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--logs-root", type=Path)
    source.add_argument("--manifest", type=Path)
    source.add_argument("--config", type=Path)
    source.add_argument("--geometry-only", action="store_true")
    parser.add_argument("--reh-xml", type=Path, default=DEFAULT_REH_XML_PATH)
    parser.add_argument("--uam-csv", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("docs/assets/data/critical_waypoints"))
    parser.add_argument("--dashboard-assets", type=Path, default=Path("docs/assets"))
    parser.add_argument("--capture-radius-m", type=float, default=250)
    parser.add_argument("--window-seconds", type=int, default=900)
    parser.add_argument("--gap-seconds", type=float, default=300)
    parser.add_argument("--reset-distance-m", type=float, default=250)
    parser.add_argument("--jump-m", type=float, default=5000)
    parser.add_argument("--workers", type=int, default=1)
    args=parser.parse_args()
    if min(args.capture_radius_m,args.window_seconds,args.gap_seconds,args.jump_m,args.workers)<=0 or args.reset_distance_m<0:
        parser.error("Invalid positive settings")
    prior_metadata_path = args.output_dir / "run_metadata.json"
    prior_metadata = json.loads(prior_metadata_path.read_text(encoding="utf-8")) if prior_metadata_path.exists() else {}
    retired_run = prior_metadata.get("retired_legacy_run") or (prior_metadata.get("source_run") if prior_metadata.get("method_version") not in {"named-waypoints-v1", "reh-anchored-uam-junctions-v2", "reh-uam-junctions-v3"} else None)
    selection=None; logs=[]
    if args.config:
        selection=load_run_selection(args.config)
        logs=[(path.parent.name,path) for path in selection.log_paths]
        if selection.uam_corridor_csv_path is None:
            parser.error("Set uam_corridor_csv in the run config; its C2 SCN association must be validated")
        if args.uam_csv is not None and args.uam_csv.resolve() != selection.uam_corridor_csv_path.resolve():
            parser.error("--uam-csv differs from the validated run configuration; update the run config explicitly")
        args.uam_csv=selection.uam_corridor_csv_path
    if args.uam_csv is None:
        parser.error("Select --uam-csv or config uam_corridor_csv explicitly; topology must correspond to the log scenario")
    if not args.geometry_only and not args.config:
        logs=manifest_logs(args.manifest) if args.manifest else discover_logs(args.logs_root)
    if not args.geometry_only and (not logs or {scenario for scenario,_ in logs}!={"C1","C2"}):
        parser.error("At least one C1 and C2 log required")
    resolved_logs = [path.resolve() for _, path in logs]
    if len(set(resolved_logs)) != len(resolved_logs):
        parser.error("A STATELOG cannot be reused as multiple replicas or scenarios")
    for scenario, path in logs:
        if not path.is_file(): parser.error(f"Missing log: {path}")
        marker = SCENARIO_RE.search(path.stem)
        if marker and marker.group(1).upper() != scenario:
            parser.error(f"Manifest scenario {scenario} conflicts with log name: {path.name}")
    uam=load_uam_corridor_network(args.uam_csv)
    features=named_waypoint_features(uam['routes'],load_reh_network(args.reh_xml)['segments'])
    sources={'uam':source_record(args.uam_csv),'reh':source_record(args.reh_xml)}
    for feature in features: feature['properties']['source']=sources[feature['properties']['network'].lower()]
    replica_rows=[]
    if logs:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures=[pool.submit(process_replica,path,features,args.capture_radius_m,args.window_seconds,args.gap_seconds,args.reset_distance_m,args.jump_m) for _,path in logs]
            for (scenario,path),future in zip(logs,futures):
                replica_rows.extend({'scenario':scenario,'replica':str(path),**row} for row in future.result())
                print(f"Completed {path.name}",file=sys.stderr,flush=True)
    grouped=defaultdict(list)
    for row in replica_rows: grouped[row['scenario'],row['waypoint_id']].append(row)
    summary=[]
    for scenario in ('C1','C2'):
        for feature in features:
            p=feature['properties']; rows=grouped[scenario,p['resource_id']]
            rates=[rate for row in rows for rate in row['window_rates_per_hour']]
            p95=percentile95(rates)
            lon,lat=feature['geometry']['coordinates']
            summary.append({'scenario':scenario,'waypoint_id':p['resource_id'],'label':p['label'],'criterion':p['criterion'],
                'latitude':lat,'longitude':lon,'altitude_m':p['altitude_m'],'replica_count':len(rows),'window_count':len(rates),'window_seconds':args.window_seconds,
                'mean_operations_per_replica':sum(r['operations'] for r in rows)/len(rows) if rows and all(r['operations'] is not None for r in rows) else None,
                'mean_throughput_per_hour':sum(rates)/len(rates) if rates else None,
                'p95_throughput_per_hour':p95,'capacity_reference_per_hour':p95,'capacity_declared_per_hour':None,
                'mean_peak_throughput_per_hour':sum(r['peak_throughput_per_hour'] for r in rows)/len(rows) if rows and all(r['peak_throughput_per_hour'] is not None for r in rows) else None,
                'source_sha256':sources[p['network'].lower()]['sha256'],'analysis_method_version':p['analysis_method_version'],
                'status':'recomputed' if rates else 'unavailable_no_full_windows_or_altitude' if rows else 'unavailable_raw_logs',
                'uam_route_ids':';'.join(p['uam_route_ids']),'reh_resource_ids':';'.join(p['reh_resource_ids'])})
    summary.sort(key=lambda row:(row['scenario'], -(row['p95_throughput_per_hour'] if row['p95_throughput_per_hour'] is not None else -1),row['waypoint_id']))
    ranks=defaultdict(int)
    for row in summary:
        if row['p95_throughput_per_hour'] is not None: ranks[row['scenario']]+=1; row['rank']=ranks[row['scenario']]
        else: row['rank']=None
    args.output_dir.mkdir(parents=True,exist_ok=True); args.dashboard_assets.mkdir(parents=True,exist_ok=True)
    write_csv(args.output_dir/'critical_waypoints.csv',summary)
    # Replace stale replica results even when raw logs are unavailable.
    (args.output_dir/'waypoints_by_replica.csv').write_text('',encoding='utf-8')
    if replica_rows:
        write_csv(args.output_dir/'waypoints_by_replica.csv',[{k:json.dumps(v) if isinstance(v,list) else v for k,v in row.items() if k!='passage_events'} for row in replica_rows])
    with (args.output_dir/'passage_events.jsonl').open('w',encoding='utf-8') as stream:
        for row in replica_rows:
            for event in row['passage_events']:
                stream.write(json.dumps({'scenario':row['scenario'],'replica':row['replica'],'waypoint_id':row['waypoint_id'],**event})+'\n')
    (args.dashboard_assets/'waypoint_rankings.js').write_text('window.__UAM_WAYPOINT_RANKINGS__ = '+json.dumps(summary,ensure_ascii=False)+';\n',encoding='utf-8')
    (args.output_dir/'critical_waypoints.geojson').write_text(json.dumps({'type':'FeatureCollection','features':features},ensure_ascii=False),encoding='utf-8')
    # This file was formerly included as capacity resources. Geometric crossings are diagnostics elsewhere.
    (args.output_dir/'crossing_waypoints.geojson').write_text(json.dumps({'type':'FeatureCollection','features':[]}),encoding='utf-8')
    write_candidate_node_assets(args.dashboard_assets.parent,args.uam_csv,args.reh_xml)
    metadata={'method_version':'reh-uam-junctions-v3','status':'recomputed' if logs else 'geometry_only_raw_logs_unavailable',
        'sources':sources,'topology_selection':'C2 SCN interior positions validated within 2m of selected corridor centerlines' if selection else 'explicit caller selection; SCN association unverified',
        'source_run':selection.run_dir.name if selection else None,'retired_legacy_run':retired_run,'vertiports':uam['vertiports'],'route_count':uam['route_count'],
        'resource_count':len(features),'reh_selection_rule':'original degree >=3 distinct undirected neighbors; endpoint topology rounded to 6 decimals','uam_selection_rule':'named Waypoint; >=3 exact distinct physical edges; nonterminal use; exact/explicit alias REH name within 500m','named_position_counts':{net:sum(f['properties']['network']==net for f in features) for net in ('UAM','REH')},
        'capture_radius_m':args.capture_radius_m,'window_seconds':args.window_seconds,
        'vertical_rule':'UAM exported altitude +/- height/2; REH union of complete valid incident envelopes; any unknown disables counting',
        'passage_rule':'connected trajectory/cylinder encounter per aircraft/flight/network; closest horizontal position wins; ties <1mm excluded; reentry counts again',
        'windows':'[first log time,last log time); aligned to first log time; full windows only, including zeros; trailing partial excluded; all encounter operations retained separately',
        'percentile':'linear interpolation at .95*(n-1) of pooled full-window hourly rates across replicas; equal weight per full window; never sum individual P95',
        'capacity_interpretation':'empirical demand sizing reference, no demonstrated safe operational limit',
        'grouping':'network + normalized name indexes positions only; no analytical consolidation by name',
        'limitations':['linear trajectory assumption between samples; no interpolation across gap/reset/jump', 'unknown flight reuse without observable reset cannot be inferred','connected overlapping captures represent one encounter; dense waypoint chains can reduce distinct passage counts','first/last inside capture encounters are censored but counted as observed contacts; complete transits not guaranteed'],
        'scenario_sources':[source_record(path) for path in selection.scenario_paths] if selection else [],
        'logs':[{'scenario':scenario,**source_record(path)} for scenario,path in logs]}
    (args.output_dir/'run_metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
