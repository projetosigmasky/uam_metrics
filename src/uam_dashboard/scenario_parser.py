from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import numpy as np

from .metrics import haversine_m

COMMAND_RE = re.compile(r"^\s*([\d:.]+)>\s+(.+?)\s*$")


def load_bluesky_scenario(path: str | Path) -> list[dict[str, Any]]:
    """Extract planned flight instances and waypoint coordinates from a BlueSky SCN."""

    scenario_path = Path(path)
    definitions: dict[str, list[float]] = {}
    active: dict[str, dict[str, Any]] = {}
    instance_counts: dict[str, int] = {}
    flights: list[dict[str, Any]] = []

    for raw_line in scenario_path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = COMMAND_RE.match(raw_line)
        if not match:
            continue

        timestamp, command_text = match.groups()
        parts = command_text.replace(",", " ").split()
        if not parts:
            continue

        command = parts[0].upper()
        if command == "DEFWPT" and len(parts) >= 4:
            definitions[parts[1]] = [float(parts[3]), float(parts[2])]
            continue

        if command == "CRE" and len(parts) >= 6:
            aircraft_id = parts[1]
            instance_number = instance_counts.get(aircraft_id, 0)
            instance_counts[aircraft_id] = instance_number + 1
            flight = {
                "flight_instance": f"{aircraft_id}#{instance_number}",
                "aircraft_id": aircraft_id,
                "start_time": timestamp,
                "start_simt": _timestamp_seconds(timestamp),
                "coordinates": [[float(parts[4]), float(parts[3])]],
                "scenario": scenario_path.name,
            }
            active[aircraft_id] = flight
            flights.append(flight)
            continue

        if command == "ADDWPT" and len(parts) >= 3:
            aircraft_id = parts[1]
            flight = active.get(aircraft_id)
            if flight is None:
                continue

            if len(parts) >= 4 and _is_number(parts[2]) and _is_number(parts[3]):
                coordinate = [float(parts[3]), float(parts[2])]
            else:
                coordinate = definitions.get(parts[2])
            if coordinate is not None and coordinate != flight["coordinates"][-1]:
                flight["coordinates"].append(coordinate)

    return [flight for flight in flights if len(flight["coordinates"]) >= 2]


def planned_route_distance_m(flight: dict[str, Any]) -> float:
    coordinates = np.asarray(flight["coordinates"], dtype=float)
    if len(coordinates) < 2:
        return 0.0
    return float(
        np.sum(
            haversine_m(
                coordinates[:-1, 1],
                coordinates[:-1, 0],
                coordinates[1:, 1],
                coordinates[1:, 0],
            )
        )
    )


def ground_delay_metrics(
    planned_flights: list[dict[str, Any]],
    nominal_flights: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Return Eq. 4.10 ground-delay metrics using the nominal SCN as requested schedule."""

    if not nominal_flights:
        return {"available": False}

    nominal_by_instance = {flight["flight_instance"]: flight for flight in nominal_flights}
    delays = []
    for flight in planned_flights:
        nominal = nominal_by_instance.get(flight["flight_instance"])
        if nominal is None:
            continue
        delays.append(max(0.0, float(flight["start_simt"]) - float(nominal["start_simt"])))

    if not delays:
        return {"available": False}
    return {
        "available": True,
        "matched_flights": len(delays),
        "mean_ground_delay_s": float(np.mean(delays)),
        "median_ground_delay_s": float(np.median(delays)),
        "p95_ground_delay_s": float(np.quantile(delays, 0.95)),
        "max_ground_delay_s": float(np.max(delays)),
    }


def _is_number(value: str) -> bool:
    try:
        float(value)
        return True
    except ValueError:
        return False


def _timestamp_seconds(value: str) -> float:
    hours, minutes, seconds = value.split(":")
    return float(hours) * 3600.0 + float(minutes) * 60.0 + float(seconds)
