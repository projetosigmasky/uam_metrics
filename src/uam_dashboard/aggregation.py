"""Replica-level resource aggregation shared by dashboard generation and tests."""

from __future__ import annotations

from typing import Any


def average_resource_group(groups: list[dict[str, Any]]) -> dict[str, Any]:
    indexed = [
        {item["resource_id"]: item for item in group.get("resources", group.get("top_resources", []))}
        for group in groups
    ]
    identifiers = sorted({identifier for group in indexed for identifier in group})
    resources = []
    for identifier in identifiers:
        representative = next(group[identifier] for group in indexed if identifier in group)
        resource = {"resource_id": identifier, "label": representative["label"], "map_target": representative.get("map_target")}
        for field in ("operations", "mean_throughput_per_hour", "peak_throughput_per_hour", "capacity_reference_per_hour"):
            resource[field] = sum((group.get(identifier, {}).get(field, 0) or 0) for group in indexed) / len(indexed)
        capacity = resource["capacity_reference_per_hour"]
        resource["utilization_peak"] = resource["peak_throughput_per_hour"] / capacity if capacity > 0 else None
        resource["utilization_mean"] = resource["mean_throughput_per_hour"] / capacity if capacity > 0 else None
        resources.append(resource)
    resources.sort(key=lambda item: (item["mean_throughput_per_hour"], item["peak_throughput_per_hour"]), reverse=True)
    return {
        "available": bool(resources), "resource_count": len(resources), "replica_count": len(groups),
        "capacity_method": "mean_replica_P95_observed_throughput", "capacity_declared_per_hour": None,
        "utilization_available": any(item["capacity_reference_per_hour"] > 0 for item in resources),
        "violation_available": False, "resources": resources, "top_resources": resources[:5],
    }
