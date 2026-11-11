"""Build data/airport_traffic/fr24_sbsp_peak_<date>.csv.gz from FR24 daily .Rda files.

Input: the folder of daily FR24 files (``12/2022-12-DD.Rda``, one data frame
``df`` each). Needs ``pyreadr`` in addition to requirements.txt (only for this
rebuild; the dashboard reads the CSV).

1. Movements: arrival = first GND_ARR point of a flight with real_arr == airport,
   departure = first DEP_40 point of a flight with plan_dep == airport (both 1 NM
   from the airport); de-duplicated by FR24 flight id across files.
2. Peak day: local date (UTC-3, no DST in 2022) with most SBSP movements.
3. Tracks: airborne points (alt > 0 ft) below 10,000 ft in lat -24.2..-23.0,
   lon -47.3..-46.0, from the peak-day file and the next one, kept to
   0..28 h after 00:00 UTC of the peak day. The BlueSky scenarios count time in
   seconds from 00:00 UTC (BIMTRA hours, blockage windows), so sim_time_s is
   seconds since that instant.

Usage: build_fr24_peak_day.py FR24_DIR [--airport SBSP] [--output data/airport_traffic]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from multiprocessing import Pool
from pathlib import Path

import pandas as pd

AIRPORTS = ("SBSP", "SBGR", "SBKP")
BOX = {"lat": (-24.2, -23.0), "lon": (-47.3, -46.0)}
MAX_ALT_FT = 10000
WINDOW_S = 28 * 3600
COLUMNS = ["fr24_id", "callsign", "equip", "airport", "movement", "plan_dep", "real_arr",
           "sim_time_s", "lat", "lon", "alt_ft", "gs_kt"]


def read_day(path: Path) -> pd.DataFrame:
    import pyreadr
    return pyreadr.read_r(str(path))["df"]


def movements(path: Path) -> pd.DataFrame:
    df = read_day(path)
    parts = []
    for airport in AIRPORTS:
        for kind, rows in (("arr", df[(df.real_arr == airport) & (df.phase == "GND_ARR")]),
                           ("dep", df[(df.plan_dep == airport) & (df.phase == "DEP_40")])):
            first = rows.sort_values("time").groupby("indicat", as_index=False).first()
            parts.append(first.assign(airport=airport, movement=kind)[["indicat", "airport", "movement", "time"]])
    return pd.concat(parts)


def tracks(path: Path) -> pd.DataFrame:
    df = read_day(path)
    return df[df.lat.between(*BOX["lat"]) & df.lon.between(*BOX["lon"]) & (df.alt > 0) & (df.alt <= MAX_ALT_FT)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("fr24_dir", type=Path)
    parser.add_argument("--airport", default="SBSP")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "airport_traffic")
    parser.add_argument("--processes", type=int, default=6)
    args = parser.parse_args()
    files = sorted(args.fr24_dir.glob("*.Rda"))
    with Pool(args.processes) as pool:
        moves = pd.concat(pool.map(movements, files))
    moves = moves.sort_values("time").drop_duplicates(["indicat", "airport", "movement"])
    moves["local_date"] = (moves.time - pd.Timedelta(hours=3)).dt.date.astype(str)
    month = sorted(moves.local_date.unique())
    month = [d for d in month if any(f.stem == d for f in files)]
    daily = moves[moves.local_date.isin(month)].groupby(["local_date", "airport"]).size().unstack(fill_value=0)
    peak = str(daily[args.airport].idxmax())
    origin = pd.Timestamp(peak)
    names = {f.stem: f for f in files}
    next_day = str((origin + pd.Timedelta(days=1)).date())
    df = pd.concat(tracks(names[d]) for d in (peak, next_day) if d in names)
    df = df.drop_duplicates(["indicat", "time", "lat", "lon", "alt"])
    df["sim_time_s"] = ((df.time - origin).dt.total_seconds()).round().astype(int)
    df = df[(df.sim_time_s >= 0) & (df.sim_time_s <= WINDOW_S)]
    df["airport"] = df.plan_dep.where(df.plan_dep.isin(AIRPORTS), df.real_arr.where(df.real_arr.isin(AIRPORTS), "none"))
    df["movement"] = "overflight"
    df.loc[df.plan_dep.isin(AIRPORTS), "movement"] = "dep"
    df.loc[df.real_arr.isin(AIRPORTS), "movement"] = "arr"
    df["callsign"] = df.id_icao.where(df.id_icao != "", df.reg)
    out = df.rename(columns={"indicat": "fr24_id", "alt": "alt_ft", "speed": "gs_kt"})[COLUMNS]
    out = out.sort_values(["fr24_id", "sim_time_s"])
    stem = f"fr24_{args.airport.lower()}_peak_{peak.replace('-', '')}"
    args.output.mkdir(parents=True, exist_ok=True)
    csv_path = args.output / f"{stem}.csv.gz"
    out.to_csv(csv_path, index=False, compression={"method": "gzip", "mtime": 0}, float_format="%.6f")
    metadata = {
        "source": "Flightradar24 daily .Rda files, December 2022 (12.zip shared by the project, 2026-11-11)",
        "source_files": [names[d].name for d in (peak, next_day) if d in names],
        "content": "commercial flights only (FR24 types ALL_BR/ARR_BR/DEP_BR/ALL_EXT); no helicopters, no general aviation, no SBMT",
        "peak_rule": f"local date (UTC-3) with most {args.airport} arrivals + departures in the month",
        "peak_day_local": peak,
        "daily_movements": {d: {a: int(v) for a, v in row.items()} for d, row in daily.iterrows()},
        "sim_time_origin_utc": f"{peak}T00:00:00Z",
        "sim_time_window_s": [0, WINDOW_S],
        "filters": {"box_lat": list(BOX["lat"]), "box_lon": list(BOX["lon"]), "airborne": "alt_ft > 0",
                    "max_alt_ft": MAX_ALT_FT},
        "altitude": "FR24 altitude in ft as delivered (ADS-B barometric); ground points (0 ft) removed",
        "airports": list(AIRPORTS),
        "rows": int(len(out)), "flights": int(out.fr24_id.nunique()),
        "csv": csv_path.name, "csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
    }
    (args.output / f"{stem}.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in metadata.items() if k != "daily_movements"}, indent=2))


if __name__ == "__main__":
    main()
