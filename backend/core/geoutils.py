"""Geo helpers.

This is the single module that would change if the project moves to PostGIS.
Everything else talks to ``Report.location`` (a ``Point`` namedtuple) and the
queryset helpers below, never to raw ``latitude`` / ``longitude`` columns.
"""
from __future__ import annotations

import math
from typing import NamedTuple

EARTH_RADIUS_M = 6_371_008.8


class Point(NamedTuple):
    """A WGS84 coordinate. Mirrors the shape of a GEOS Point we would use
    under PostGIS, so call sites do not care which backend is active."""

    lat: float
    lng: float

    @property
    def geojson(self) -> dict:
        return {"type": "Point", "coordinates": [self.lng, self.lat]}


def haversine_m(a: Point, b: Point) -> float:
    """Great-circle distance in metres."""
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dphi = p2 - p1
    dlam = math.radians(b.lng - a.lng)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def bbox_around(point: Point, radius_m: float) -> tuple[float, float, float, float]:
    """Return (min_lat, min_lng, max_lat, max_lng) enclosing the radius.

    Used as a cheap index-friendly prefilter before the exact haversine pass,
    which is the documented stand-in for ``ST_DWithin``.
    """
    dlat = math.degrees(radius_m / EARTH_RADIUS_M)
    # Guard the pole singularity: cos(lat) -> 0 makes dlng explode.
    coslat = math.cos(math.radians(point.lat))
    if abs(coslat) < 1e-9:
        dlng = 180.0
    else:
        dlng = math.degrees(radius_m / (EARTH_RADIUS_M * coslat))
        dlng = min(dlng, 180.0)
    return (point.lat - dlat, point.lng - dlng, point.lat + dlat, point.lng + dlng)


def within_radius(queryset, point: Point, radius_m: float):
    """Filter a Report queryset to rows within ``radius_m`` of ``point``.

    Two-stage: an indexed bounding-box filter in SQL, then exact haversine in
    Python. Returns a list ordered by distance, with ``.distance_m`` attached.
    """
    min_lat, min_lng, max_lat, max_lng = bbox_around(point, radius_m)
    candidates = queryset.filter(
        latitude__gte=min_lat,
        latitude__lte=max_lat,
        longitude__gte=min_lng,
        longitude__lte=max_lng,
    )
    hits = []
    for obj in candidates:
        d = haversine_m(point, Point(obj.latitude, obj.longitude))
        if d <= radius_m:
            obj.distance_m = round(d, 1)
            hits.append(obj)
    hits.sort(key=lambda o: o.distance_m)
    return hits


def in_bbox(queryset, west: float, south: float, east: float, north: float):
    """Filter to a viewport. Accepts the OpenLayers/Leaflet w,s,e,n order."""
    return queryset.filter(
        longitude__gte=west,
        longitude__lte=east,
        latitude__gte=south,
        latitude__lte=north,
    )


def point_in_ring(point: Point, ring: list) -> bool:
    """Ray-casting point-in-polygon for a single GeoJSON linear ring."""
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        if (y1 > point.lat) != (y2 > point.lat):
            xin = (x2 - x1) * (point.lat - y1) / (y2 - y1) + x1
            if point.lng < xin:
                inside = not inside
    return inside


def point_in_geometry(point: Point, geometry: dict) -> bool:
    """Point-in-polygon against a GeoJSON Polygon or MultiPolygon, honouring holes."""
    if not geometry:
        return False
    gtype = geometry.get("type")
    coords = geometry.get("coordinates") or []
    polygons = coords if gtype == "MultiPolygon" else [coords] if gtype == "Polygon" else []
    for poly in polygons:
        if not poly:
            continue
        if point_in_ring(point, poly[0]) and not any(
            point_in_ring(point, hole) for hole in poly[1:]
        ):
            return True
    return False
