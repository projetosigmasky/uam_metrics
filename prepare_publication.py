"""Repackage completed dashboard results without reading STATELOGs again."""
from __future__ import annotations

import argparse
import hashlib
import re
import json
import shutil
from pathlib import Path

from src.uam_dashboard.publication import check_publication, repack_publication
from src.uam_dashboard.scenario_catalog import CATALOG
from src.uam_dashboard.metric_catalog import write_metric_catalog_asset, write_metric_matrix


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("docs"))
    args = parser.parse_args()
    manifest = repack_publication(args.output)
    source = Path(__file__).resolve().parent / "web"
    # Refresh only the loader/UI, preserving generated rankings and geometry.
    for relative in ("index.html", "assets/dashboard.js", "assets/dashboard.css"):
        shutil.copy2(source / relative, args.output / relative)
    write_metric_catalog_asset(args.output)
    write_metric_matrix(args.output / "MATRIZ_KPIS_PRODUTO_3.md")
    (args.output / "assets/scenario_catalog.js").write_text(
        "window.__UAM_SCENARIO_CATALOG__ = " + json.dumps(CATALOG, ensure_ascii=False) + ";\n", encoding="utf-8")
    index = args.output / "index.html"
    text = index.read_text(encoding="utf-8")
    for asset in (args.output / "assets").iterdir():
        if asset.is_file() and asset.suffix in {".js", ".css"}:
            digest = hashlib.sha256(asset.read_bytes()).hexdigest()[:12]
            text = re.sub(r"(assets/" + re.escape(asset.name) + r"\?v=)[^\"]+", lambda match: match[1] + digest, text)
    index.write_text(text, encoding="utf-8")
    check_publication(args.output)
    print(f"Publication ready: {len(manifest['runs'])} scenarios; no metrics recomputed.")
    print("passage_events.jsonl remains on disk as a local audit; do not add it to Git.")


if __name__ == "__main__":
    main()
