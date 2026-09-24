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
PRODUCT2_PERCENTILE_RE = re.compile(
    r"(?:^|_)produto2_(?P<scenario>C\d+)_p(?P<percentile>\d+)"
    r"(?:_r(?P<replica>\d+))?_(?P<mode>mvp|off)(?:_|$)",
    re.IGNORECASE,
)


def experiment_metadata(path: str | Path) -> dict[str, Any]:
    stem = HEADLESS_SUFFIX_RE.sub("", Path(path).stem)
    product2_percentile_match = PRODUCT2_PERCENTILE_RE.search(stem)
    if product2_percentile_match:
        values = product2_percentile_match.groupdict()
        scenario = values["scenario"].upper()
        rank = int(scenario[1:])
        percentile = int(values["percentile"])
        return {
            "experiment_family": "produto2",
            "day_key": f"produto2_p{percentile}",
            "day_label": f"Produto 2 - demanda P{percentile}",
            "variant_key": scenario.lower(),
            "variant_label": f"{scenario} - cenário P{percentile}",
            "scenario_key": scenario,
            "replica": int(values["replica"]) if values["replica"] else None,
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


def matching_scenario(path: str | Path, scenario_paths: tuple[Path, ...]) -> Path | None:
    log_path = Path(path)
    stem = log_path.stem.lower()
    metadata = experiment_metadata(log_path)
    candidates = list(scenario_paths)
    if metadata["experiment_family"] == "produto2":
        candidates = [
            scenario for scenario in candidates
            if (scenario_metadata := experiment_metadata(scenario)).get("scenario_key") == metadata.get("scenario_key")
            and scenario_metadata["day_key"] == metadata["day_key"]
            and scenario_metadata["mvp_enabled"] == metadata["mvp_enabled"]
        ]
        replica = metadata.get("replica")
        if replica is not None:
            replica_matches = [
                scenario for scenario in candidates
                if experiment_metadata(scenario).get("replica") == replica
            ]
            if replica_matches:
                candidates = replica_matches
    named_matches = [scenario for scenario in candidates if scenario.stem.lower() in stem]
    if named_matches:
        return max(named_matches, key=lambda scenario: len(scenario.stem))

    # Orchestrator replicas may use an opaque filename but live in output/C1
    # or output/C2. Only infer the scenario when exactly one SCN matches that
    # folder; choosing between multiple versions would silently corrupt KPIs.
    scenario_key = log_path.parent.name.upper()
    if not re.fullmatch(r"C\d+", scenario_key):
        return None
    folder_matches = [
        scenario for scenario in candidates
        if experiment_metadata(scenario).get("scenario_key") == scenario_key
    ]
    return folder_matches[0] if len(folder_matches) == 1 else None


def log_experiment_metadata(path: str | Path, scenario_paths: tuple[Path, ...]) -> dict[str, Any]:
    metadata = experiment_metadata(path)
    if metadata["experiment_family"] != "desconhecida":
        return metadata
    scenario = matching_scenario(path, scenario_paths)
    return experiment_metadata(scenario) if scenario is not None else metadata


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
