from __future__ import annotations

import re
from pathlib import Path
from typing import Any


EXPERIMENT_RE = re.compile(
    r"^(?:STATELOG_)?bimtra_top(?P<rank>\d+)_(?P<date>\d{4}_\d{2}_\d{2})"
    r"(?P<disturbed>_disturbed_seed(?P<seed>\d+))?_(?P<mode>mvp|off)$",
    re.IGNORECASE,
)

HEADLESS_SUFFIX_RE = re.compile(r"_headless(?:_\d{8}_\d{2}-\d{2}-\d{2})?$", re.IGNORECASE)
PRODUCT2_RE = re.compile(
    r"^(?:STATELOG_)?produto2_(?P<scenario>C[12])_(?P<date>\d{4}[-_]\d{2}[-_]\d{2})"
    r"_(?P<mode>mvp|off)(?:_.+)?$",
    re.IGNORECASE,
)
PRODUCT2_P95_RE = re.compile(
    r"^(?:STATELOG_)?produto2_(?P<scenario>C\d+)_p95_(?P<mode>mvp|off)(?:_.+)?$",
    re.IGNORECASE,
)


def experiment_metadata(path: str | Path) -> dict[str, Any]:
    stem = HEADLESS_SUFFIX_RE.sub("", Path(path).stem)
    product2_p95_match = PRODUCT2_P95_RE.match(stem)
    if product2_p95_match:
        values = product2_p95_match.groupdict()
        scenario = values["scenario"].upper()
        rank = int(scenario[1:])
        return {
            "experiment_family": "produto2",
            "day_key": "produto2_p95",
            "day_label": "Produto 2 - demanda P95",
            "variant_key": scenario.lower(),
            "variant_label": f"{scenario} - cenário P95",
            "scenario_key": scenario,
            "reference_variant_key": "c1",
            "mvp_enabled": values["mode"].lower() == "mvp",
            "disturbed": False,
            "rank": rank,
            "date": None,
            "seed": None,
        }
    product2_match = PRODUCT2_RE.match(stem)
    if product2_match:
        values = product2_match.groupdict()
        scenario = values["scenario"].upper()
        date = values["date"].replace("_", "-")
        labels = {
            "C1": "C1 - REH compartilhada",
            "C2": "C2 - corredor UAM dedicado",
        }
        return {
            "experiment_family": "produto2",
            "day_key": f"produto2_{date}",
            "day_label": f"Produto 2 - {date}",
            "variant_key": scenario.lower(),
            "variant_label": labels[scenario],
            "scenario_key": scenario,
            "reference_variant_key": "c1",
            "mvp_enabled": values["mode"].lower() == "mvp",
            "disturbed": False,
            "rank": int(scenario[-1]),
            "date": date,
            "seed": None,
        }
    match = EXPERIMENT_RE.match(stem)
    if not match:
        return {
            "experiment_family": "desconhecida",
            "day_key": stem,
            "day_label": stem,
            "variant_key": stem,
            "variant_label": stem,
            "mvp_enabled": None,
            "disturbed": None,
            "rank": None,
            "date": None,
            "seed": None,
        }

    values = match.groupdict()
    rank = int(values["rank"])
    date = values["date"].replace("_", "-")
    disturbed = bool(values["disturbed"])
    mvp_enabled = values["mode"].lower() == "mvp"
    variant_key = f"{'disturbed' if disturbed else 'nominal'}_{'mvp' if mvp_enabled else 'off'}"
    return {
        "experiment_family": "bimtra",
        "day_key": f"top{rank}_{date}",
        "day_label": f"Dia {rank} - {date}",
        "variant_key": variant_key,
        "variant_label": (
            f"{'MVP ligado' if mvp_enabled else 'MVP desligado'}"
            f" / {'com disturbios' if disturbed else 'sem disturbios'}"
        ),
        "mvp_enabled": mvp_enabled,
        "disturbed": disturbed,
        "rank": rank,
        "date": date,
        "seed": int(values["seed"]) if values["seed"] else None,
    }


def experiment_sort_key(path: str | Path) -> tuple[int, int, int]:
    metadata = experiment_metadata(path)
    rank = metadata["rank"] if metadata["rank"] is not None else 999
    variant_order = {
        "c1": 0,
        "c2": 1,
        "disturbed_mvp": 0,
        "disturbed_off": 1,
        "nominal_mvp": 2,
        "nominal_off": 3,
    }
    return rank, variant_order.get(metadata["variant_key"], 99), 0
