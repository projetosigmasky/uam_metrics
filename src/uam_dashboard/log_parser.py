from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import LOG_COLUMNS


def load_state_log(path: str | Path) -> pd.DataFrame:
    """Load a BlueSky STATELOG-style CSV file into a clean DataFrame."""

    log_path = Path(path)
    if not log_path.exists():
        raise FileNotFoundError(f"Log file not found: {log_path}")

    df = pd.read_csv(log_path, comment="#", names=LOG_COLUMNS, skipinitialspace=True)
    df = df.dropna(subset=["simt", "id", "lat", "lon"])

    numeric_columns = [column for column in LOG_COLUMNS if column != "id"]
    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df = df.dropna(subset=numeric_columns)
    df["id"] = df["id"].astype(str).str.strip()
    df = df.sort_values(["simt", "id"]).reset_index(drop=True)
    return df
