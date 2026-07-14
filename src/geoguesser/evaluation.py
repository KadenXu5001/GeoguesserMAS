from __future__ import annotations

from collections.abc import Iterable, Mapping
from math import asin, cos, radians, sin, sqrt
from typing import Any


def country_accuracy(rows: Iterable[Mapping[str, Any]]) -> float:
    rows = list(rows)
    if not rows:
        return 0.0
    return sum(row.get("prediction") == row.get("ground_truth") for row in rows) / len(rows)


def haversine_km(latitude: float, longitude: float, other_latitude: float, other_longitude: float) -> float:
    earth_radius_km = 6371.0088
    lat1, lat2 = radians(latitude), radians(other_latitude)
    dlat = lat2 - lat1
    dlon = radians(other_longitude - longitude)
    value = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * earth_radius_km * asin(sqrt(value))


def centroid_haversine_loss(
    rows: Iterable[Mapping[str, Any]],
    centroids: Mapping[str, tuple[float, float]],
) -> float:
    distances = []
    for row in rows:
        prediction = row.get("prediction")
        ground_truth = row.get("ground_truth")
        location = row.get("location")
        if prediction not in centroids or not isinstance(location, (tuple, list)):
            continue
        distances.append(haversine_km(location[0], location[1], *centroids[prediction]))
    return sum(distances) / len(distances) if distances else 0.0


def summarize_runs(rows: Iterable[Mapping[str, Any]]) -> dict[str, float]:
    rows = list(rows)
    usage = [event for row in rows for event in row.get("usage", [])]
    costs = [float(event.get("cost_usd", 0.0)) for event in usage]
    image_tokens = [int(event.get("image_tokens", 0)) for event in usage]
    latencies = [float(event["latency_ms"]) for event in usage if event.get("latency_ms") is not None]
    return {
        "count": float(len(rows)),
        "call_count": float(len(usage)),
        "complete_cost_usd": sum(costs),
        "image_tokens": float(sum(image_tokens)),
        "mean_latency_ms": sum(latencies) / len(latencies) if latencies else 0.0,
        "specialist_rate": sum(bool(row.get("specialist_used")) for row in rows) / len(rows) if rows else 0.0,
        "reexamination_rate": sum(bool(row.get("reexamine_results")) for row in rows) / len(rows) if rows else 0.0,
    }

