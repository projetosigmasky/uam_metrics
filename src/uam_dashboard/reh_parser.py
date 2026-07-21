from __future__ import annotations

from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import numpy as np


GML_NS = "http://www.opengis.net/gml"
ICA_NS = "https://geoaisweb.decea.mil.br/geoserver/ICA"
NS = {"gml": GML_NS, "ICA": ICA_NS}


def load_reh_network(path: str | Path) -> dict[str, Any]:
    """Load the official Sao Paulo REH WFS/GML export."""

    xml_path = Path(path)
    root = ET.parse(xml_path).getroot()
    segments: list[dict[str, Any]] = []
    features: list[dict[str, Any]] = []

    for element in root.findall(".//ICA:CV_REH_XP_SAO_PAULO", NS):
        properties = _properties(element)
        polygons = _polygons(element)
        if not polygons:
            continue

        resource_id = f"REH-{properties.get('id') or len(segments) + 1}"
        name = properties.get("nome") or resource_id
        section = properties.get("trecho") or ""
        label = f"{name} - trecho {section}" if section else name
        centerline = _centerline(properties, polygons)
        area_m2 = float(sum(polygon_area_m2(ring) for ring in polygons))
        segment = {
            "resource_id": resource_id,
            "label": label,
            "name": name,
            "section": section,
            "route_type": properties.get("tipo") or "",
            "airspace_class": properties.get("classe") or "",
            "semi_width_m": _float_or_none(properties.get("semi_largura")),
            "altitude_min_ft": _float_or_none(properties.get("altmin")),
            "altitude_max_ft": _float_or_none(properties.get("altmax")),
            "altitude_compulsory_ft": _float_or_none(properties.get("altcomp")),
            "fix_a_name": properties.get("fixo_a_nome") or "",
            "fix_b_name": properties.get("fixo_b_nome") or "",
            "ats": properties.get("ats") or properties.get("fca") or "",
            "effective_date": properties.get("efetivacao") or "",
            "source_identifier": properties.get("identificador") or "",
            "axis_key": properties.get("eixokey") or "",
            "polygons": polygons,
            "coordinates": centerline,
            "waypoint_count": len(centerline),
            "area_m2": area_m2,
        }
        segments.append(segment)
        features.append(
            {
                "type": "Feature",
                "properties": {key: value for key, value in segment.items() if key not in {"polygons", "coordinates"}},
                "geometry": {
                    "type": "MultiPolygon",
                    "coordinates": [[ring] for ring in polygons],
                },
            }
        )

    return {
        "source_path": str(xml_path),
        "segments": segments,
        "geojson": {
            "type": "FeatureCollection",
            "properties": {
                "source": xml_path.name,
                "geometry_reference": "official_wfs_gml_polygons",
                "segment_count": len(features),
            },
            "features": features,
        },
    }


def points_in_polygons(points: np.ndarray, polygons: list[list[list[float]]]) -> np.ndarray:
    """Return a mask for points [lat, lon] inside any GeoJSON exterior ring."""

    inside = np.zeros(len(points), dtype=bool)
    if len(points) == 0:
        return inside
    for ring in polygons:
        inside |= _points_in_ring(points, ring)
    return inside


def points_in_reh_network(points: np.ndarray, segments: list[dict[str, Any]]) -> np.ndarray:
    inside = np.zeros(len(points), dtype=bool)
    for segment in segments:
        inside |= points_in_polygons(points, segment.get("polygons", []))
    return inside


def polygon_area_m2(ring: list[list[float]]) -> float:
    """Approximate a GeoJSON ring area in a local equirectangular projection."""

    if len(ring) < 3:
        return 0.0
    coordinates = np.asarray(ring, dtype=float)
    reference_lat = float(np.mean(coordinates[:, 1]))
    x = coordinates[:, 0] * 111_320.0 * np.cos(np.radians(reference_lat))
    y = coordinates[:, 1] * 111_320.0
    return float(abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1))) / 2.0)


def _properties(element: ET.Element) -> dict[str, str]:
    values: dict[str, str] = {}
    for child in element:
        local_name = child.tag.rsplit("}", 1)[-1]
        if local_name in {"boundedBy", "geom"}:
            continue
        values[local_name] = (child.text or "").strip()
    return values


def _polygons(element: ET.Element) -> list[list[list[float]]]:
    polygons = []
    for coordinate_element in element.findall(".//gml:outerBoundaryIs//gml:coordinates", NS):
        ring = []
        for pair in (coordinate_element.text or "").split():
            values = pair.split(",")
            if len(values) >= 2:
                ring.append([float(values[0]), float(values[1])])
        if len(ring) >= 3:
            if ring[0] != ring[-1]:
                ring.append(ring[0])
            polygons.append(ring)
    return polygons


def _centerline(properties: dict[str, str], polygons: list[list[list[float]]]) -> list[list[float]]:
    coordinates = []
    for suffix in ("a", "b"):
        lat = _float_or_none(properties.get(f"fixo_{suffix}_lat"))
        lon = _float_or_none(properties.get(f"fixo_{suffix}_lon"))
        if lat is not None and lon is not None:
            coordinates.append([lat, lon])
    if len(coordinates) == 2:
        return coordinates

    ring = polygons[0]
    return [[ring[0][1], ring[0][0]], [ring[len(ring) // 2][1], ring[len(ring) // 2][0]]]


def _points_in_ring(points: np.ndarray, ring: list[list[float]]) -> np.ndarray:
    coordinates = np.asarray(ring, dtype=float)
    if len(coordinates) < 3:
        return np.zeros(len(points), dtype=bool)

    point_y = points[:, 0]
    point_x = points[:, 1]
    min_x, max_x = float(np.min(coordinates[:, 0])), float(np.max(coordinates[:, 0]))
    min_y, max_y = float(np.min(coordinates[:, 1])), float(np.max(coordinates[:, 1]))
    candidates = (point_x >= min_x) & (point_x <= max_x) & (point_y >= min_y) & (point_y <= max_y)
    result = np.zeros(len(points), dtype=bool)
    if not np.any(candidates):
        return result

    x = point_x[candidates]
    y = point_y[candidates]
    inside = np.zeros(len(x), dtype=bool)
    previous = coordinates[-1]
    for current in coordinates:
        x1, y1 = previous
        x2, y2 = current
        intersects = ((y1 > y) != (y2 > y)) & (
            x < (x2 - x1) * (y - y1) / (y2 - y1 + np.finfo(float).eps) + x1
        )
        inside ^= intersects
        previous = current
    result[np.flatnonzero(candidates)] = inside
    return result


def _float_or_none(value: str | None) -> float | None:
    try:
        return float(value) if value not in {None, ""} else None
    except ValueError:
        return None
