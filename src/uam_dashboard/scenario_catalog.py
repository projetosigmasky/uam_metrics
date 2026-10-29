"""Scenario dimensions from the simulation project's canonical workbook.

The JSON snapshot also drives the browser controls, so code and UI share IDs.
"""
from __future__ import annotations

import json
from pathlib import Path

CATALOG = json.loads((Path(__file__).resolve().parents[2] / "data/scenario_catalog.json").read_text(encoding="utf-8"))
SCENARIOS = {row["scenario"]: row for row in CATALOG["scenarios"]}
NOMINAL_CODES = tuple(code for code, row in SCENARIOS.items() if row["condition"] == "nominal")


def scenario_dimensions(code: str) -> dict:
    code = code.upper().replace("_", ".")
    if code in SCENARIOS:
        return dict(SCENARIOS[code])
    # Historical micro codes had no profile component; never infer a time/LOWC.
    parts = code.split(".")
    if len(parts) == 3 and parts[0] in {"C4", "C8"} and parts[1] in {"1", "2"} and parts[2] in {"1", "2"}:
        row = dict(SCENARIOS[code + ".1"])
        row.update(scenario=code, separation_seconds=None, lowc_distance_nm=None)
        return row
    return {}
