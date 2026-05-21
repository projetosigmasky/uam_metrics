from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def _set_style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.edgecolor": "#d5dde8",
            "axes.labelcolor": "#28313f",
            "xtick.color": "#4d5a6b",
            "ytick.color": "#4d5a6b",
            "font.size": 11,
            "axes.titleweight": "bold",
            "axes.titlepad": 12,
        }
    )


def plot_active_aircraft(series: pd.DataFrame, output_path: Path) -> None:
    _set_style()
    fig, ax = plt.subplots(figsize=(10.5, 4.2))
    ax.plot(series["hour"], series["aircraft"], color="#2563eb", linewidth=1.8)
    ax.fill_between(series["hour"], series["aircraft"], color="#93c5fd", alpha=0.35)
    ax.set_title("Aeronaves simultaneas no corredor")
    ax.set_xlabel("Tempo de simulacao (h)")
    ax.set_ylabel("Aeronaves")
    ax.grid(True, linestyle="--", alpha=0.35)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_separation_histogram(
    separation_samples_m: list[float],
    threshold_m: float,
    output_path: Path,
) -> None:
    _set_style()
    fig, ax = plt.subplots(figsize=(10.5, 4.2))

    filtered = [value for value in separation_samples_m if value < 5000]
    if filtered:
        ax.hist(filtered, bins=52, color="#ef4444", alpha=0.82)
    else:
        ax.text(0.5, 0.5, "Sem amostras de separacao", ha="center", va="center", transform=ax.transAxes)

    ax.axvline(threshold_m, color="#111827", linestyle="--", linewidth=1.8, label=f"LoWC {threshold_m:.0f} m")
    ax.set_title("Distribuicao de separacao horizontal")
    ax.set_xlabel("Distancia horizontal (m)")
    ax.set_ylabel("Ocorrencias")
    ax.legend(loc="upper right")
    ax.grid(True, axis="y", linestyle="--", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_altitude_histogram(df: pd.DataFrame, threshold_m: float, output_path: Path) -> None:
    _set_style()
    fig, ax = plt.subplots(figsize=(10.5, 4.2))
    ax.hist(df["alt"], bins=48, color="#0f766e", alpha=0.82)
    ax.axvline(threshold_m, color="#b45309", linestyle="--", linewidth=1.8, label=f"{threshold_m:.0f} m")
    ax.set_title("Distribuicao de altitude")
    ax.set_xlabel("Altitude (m)")
    ax.set_ylabel("Registros")
    ax.legend(loc="upper right")
    ax.grid(True, axis="y", linestyle="--", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_route_distance_histogram(df: pd.DataFrame, output_path: Path) -> None:
    _set_style()
    distance_nm = df.groupby("id")["distflown"].max() / 1852.0

    fig, ax = plt.subplots(figsize=(10.5, 4.2))
    if len(distance_nm):
        ax.hist(distance_nm, bins=min(30, max(8, int(np.sqrt(len(distance_nm))))), color="#7c3aed", alpha=0.78)
    else:
        ax.text(0.5, 0.5, "Sem dados de distancia", ha="center", va="center", transform=ax.transAxes)

    ax.set_title("Distancia voada por aeronave")
    ax.set_xlabel("Distancia (NM)")
    ax.set_ylabel("Aeronaves")
    ax.grid(True, axis="y", linestyle="--", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)
