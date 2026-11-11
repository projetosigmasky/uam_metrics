"""Remove terminal hovers that BlueSky never ends.

In the 06/11/2026 wind run, helicopters reach their last waypoint against the
wind, slow to ~0.2 m/s about 1 m short of it and are never deleted (``DEL`` fires
only when the waypoint is passed). They then hover until the end of the scenario,
or for minutes before creeping past it. These samples are not flight: they
inflate flight time, distance, simultaneity and pair exposure.

Rule: for each aircraft id, the trailing samples after its last sample with
ground speed >= ``speed_mps`` are a terminal stop. When the stop lasts at least
``min_seconds``, it is cut after its first sample (the arrival). Slow phases
followed by motion are never touched, and normal arrivals (deleted within a few
seconds of slowing down) stay unchanged.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def trim_terminal_hover(df: pd.DataFrame, min_seconds: float = 60.0, speed_mps: float = 1.0) -> tuple[pd.DataFrame, dict[str, Any]]:
    report: dict[str, Any] = {"rule": "trailing gs < speed_mps lasting >= min_seconds, cut after arrival",
                              "min_seconds": float(min_seconds), "speed_mps": float(speed_mps),
                              "trimmed_flights": 0, "trimmed_records": 0, "trimmed_seconds": 0.0, "trimmed_ids": []}
    if min_seconds <= 0 or df.empty or "gs" not in df.columns:
        report["applied"] = False
        return df, report
    ordered = df.sort_values(["id", "simt"], kind="stable")
    fast = ordered["gs"].to_numpy(float) >= speed_mps
    ids = ordered["id"].to_numpy()
    simt = ordered["simt"].to_numpy(float)
    # Position (within ordered) of the last fast sample per id; -1 if never fast.
    position = np.arange(len(ordered))
    last_fast = pd.Series(np.where(fast, position, -1)).groupby(ids).transform("max").to_numpy()
    first_row = pd.Series(position).groupby(ids).transform("min").to_numpy()
    stop_start = np.maximum(last_fast + 1, first_row)          # first sample of the trailing stop
    in_tail = position >= stop_start
    tail_start_time = simt[np.clip(stop_start, 0, len(simt) - 1)]
    last_time = pd.Series(simt).groupby(ids).transform("max").to_numpy()
    long_stop = in_tail & (last_time - tail_start_time >= min_seconds)
    drop = long_stop & (position > stop_start)                 # keep the arrival sample
    if drop.any():
        dropped = ordered[drop]
        durations = dropped.groupby("id")["simt"].agg(["min", "max"])
        report.update(trimmed_flights=int(len(durations)), trimmed_records=int(drop.sum()),
                      trimmed_seconds=float((durations["max"] - durations["min"] + 1).sum()),
                      trimmed_ids=sorted(map(str, durations.index))[:50])
    report["applied"] = True
    kept = ordered[~drop]
    return kept.sort_values(["simt", "id"]).reset_index(drop=True), report
