"""Lossless, demand-loaded static assets with bounded individual file sizes."""
from __future__ import annotations

import hashlib
import json
import re
import os
import tempfile
from pathlib import Path

PREFIX = "window.__UAM_DASHBOARD_DATA__ = "
PART_CHARACTERS = 2 * 1024 * 1024
MAX_ASSET_BYTES = 50 * 1024 * 1024
LOCAL_AUDIT = Path("assets/data/critical_waypoints/passage_events.jsonl")
LOCAL_RUNS = Path("assets/data/runs")


def serialized(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def write_asset(path: Path, content: str) -> None:
    data = content.encode("utf-8")
    if path.is_file() and path.read_bytes() == data:
        return
    # Never leave the previous publication index truncated after a failed write.
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix="." + path.name, suffix=".tmp", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(data)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_bundle(path: Path) -> dict:
    text = path.read_text(encoding="utf-8").strip()
    if not text.startswith(PREFIX) or not text.endswith(";"):
        raise ValueError(f"Unsupported dashboard bundle: {path}")
    return json.loads(text[len(PREFIX):-1])


def write_publication(output_dir: Path, model: dict, part_characters: int = PART_CHARACTERS) -> dict:
    if not isinstance(part_characters, int) or not 1 <= part_characters <= PART_CHARACTERS:
        raise ValueError("Invalid publication part size")
    assets = output_dir / "assets"
    parts_dir = assets / "run_data"
    parts_dir.mkdir(parents=True, exist_ok=True)
    summaries = []
    for run in model["runs"]:
        run_id = run["id"]
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", run_id):
            raise ValueError(f"Invalid run asset identifier: {run_id}")
        text = serialized(run)
        token = hashlib.sha256(text.encode("utf-8")).hexdigest()
        count = (len(text) + part_characters - 1) // part_characters
        paths = []
        for index in range(count):
            # Fragments are string literals, never executable data. ASCII
            # escaping also preserves Unicode and script delimiters losslessly.
            fragment = json.dumps(text[index * part_characters:(index + 1) * part_characters], ensure_ascii=True)
            content = f'window.__UAM_RUN_PART__({json.dumps(token)},{index},{count},{fragment});\n'
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            path = parts_dir / f"{digest}-{index:04d}.js"
            write_asset(path, content)
            paths.append(f"assets/run_data/{path.name}")
        json_path = assets / "data/runs" / f"{run_id}.json"
        json_path.parent.mkdir(parents=True, exist_ok=True)
        write_asset(json_path, text)
        summary = {key: run[key] for key in (
            "id", "name", "metadata", "replica_count", "representative_log", "analysis_schema_version", "density", "stability"
        ) if key in run}
        # Keep cross-scenario stability panels without loading trajectories.
        summary["aggregate_analysis"] = {key: run.get("aggregate_analysis", {})[key]
            for key in ("schema_version", "coverage") if key in run.get("aggregate_analysis", {})}
        summary.update(data_token=token, data_parts=paths, data_json=f"assets/data/runs/{run_id}.json")
        summaries.append(summary)
    manifest = {key: value for key, value in model.items() if key not in {
        "runs", "tracks", "planned_routes", "official_reh", "conflicts", "heatmap", "trajectory_3d"
    }}
    manifest.update(bundle_format_version=2, runs=summaries)
    content = PREFIX + serialized(manifest) + ";\n"
    if len(content.encode("utf-8")) >= MAX_ASSET_BYTES:
        raise ValueError("Dashboard index exceeds the 50 MiB publication budget")
    write_asset(assets / "data_bundle.js", content)
    active = {Path(path).name for summary in summaries for path in summary["data_parts"]}
    for path in parts_dir.iterdir():
        if re.fullmatch(r"[0-9a-f]{64}-\d{4,}\.js", path.name) and path.name not in active:
            path.unlink()
    return manifest


def repack_publication(output_dir: Path) -> dict:
    model = read_bundle(output_dir / "assets/data_bundle.js")
    if model.get("bundle_format_version") == 2:
        runs = []
        for summary in model["runs"]:
            fragments = []
            for index, relative in enumerate(summary["data_parts"]):
                path = (output_dir / relative).resolve()
                if not path.is_relative_to((output_dir / "assets/run_data").resolve()):
                    raise ValueError("Run fragments must be inside assets/run_data")
                content = path.read_text(encoding="utf-8").strip()
                prefix = "window.__UAM_RUN_PART__("
                if not content.startswith(prefix) or not content.endswith(");"):
                    raise ValueError(f"Invalid run fragment: {path}")
                token, part_index, count, fragment = json.loads("[" + content[len(prefix):-2] + "]")
                if (token, part_index, count) != (summary["data_token"], index, len(summary["data_parts"])):
                    raise ValueError(f"Run fragment identity mismatch: {path}")
                fragments.append(fragment)
            text = "".join(fragments)
            if hashlib.sha256(text.encode("utf-8")).hexdigest() != summary["data_token"]:
                raise ValueError("Run fragment checksum mismatch")
            run = json.loads(text)
            if run["id"] != summary["id"]:
                raise ValueError(f"Run JSON identity mismatch: {path}")
            runs.append(run)
        model["runs"] = runs
    return write_publication(output_dir, model)


def check_publication(output_dir: Path) -> None:
    oversized = [str(path.relative_to(output_dir)) for path in output_dir.rglob("*")
        if path.is_file() and path.relative_to(output_dir) != LOCAL_AUDIT
        and not path.relative_to(output_dir).is_relative_to(LOCAL_RUNS) and path.stat().st_size >= MAX_ASSET_BYTES]
    if oversized:
        raise ValueError("Public assets exceed the 50 MiB budget: " + ", ".join(oversized))
