from __future__ import annotations

from pathlib import Path
from io import StringIO

import pandas as pd

from .config import EXTENDED_LOG_COLUMNS, LOG_COLUMNS


def load_state_log(path: str | Path) -> pd.DataFrame:
    """Load a BlueSky STATELOG-style CSV file into a clean DataFrame."""

    log_path = Path(path)
    if not log_path.exists():
        raise FileNotFoundError(f"Log file not found: {log_path}")

    text = _decode_log(log_path)
    lines = _state_log_lines(text)
    if not lines:
        raise ValueError(f"No STATELOG rows found in: {log_path}")

    first_data = next(line for line in lines if not line.lstrip().startswith("#"))
    column_count = len(first_data.split(","))
    names = EXTENDED_LOG_COLUMNS if column_count >= len(EXTENDED_LOG_COLUMNS) else LOG_COLUMNS
    df = pd.read_csv(StringIO("\n".join(lines)), comment="#", names=names, skipinitialspace=True)
    df = df[[column for column in LOG_COLUMNS if column in df.columns]]
    df = df.dropna(subset=["simt", "id", "lat", "lon"])

    numeric_columns = [column for column in LOG_COLUMNS if column != "id"]
    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df = df.dropna(subset=numeric_columns)
    df["id"] = df["id"].astype(str).str.strip()
    df = df.sort_values(["simt", "id"]).reset_index(drop=True)
    return df


def _decode_log(log_path: Path) -> str:
    data = log_path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def _state_log_lines(text: str) -> list[str]:
    lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            lines.append(line)
            continue
        first = line.split(",", 1)[0]
        try:
            float(first)
        except ValueError:
            continue
        if line.count(",") >= len(LOG_COLUMNS) - 1:
            lines.append(line)
    return lines
