"""Reverse geocoding via Nominatim, behind a cache and a rate limit.

Nominatim's usage policy caps anonymous use at 1 req/s and requires an
identifying User-Agent. We cache aggressively and fail soft: an address is a
nicety, never a reason to reject a report.
"""
import json
import logging
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.cache import cache

log = logging.getLogger(__name__)

NOMINATIM_REVERSE = "https://nominatim.openstreetmap.org/reverse"
NOMINATIM_SEARCH = "https://nominatim.openstreetmap.org/search"
_RATE_KEY = "nominatim:last-call"


def _throttled_get(url: str, params: dict, timeout: int = 6):
    if cache.get(_RATE_KEY):
        return None
    cache.set(_RATE_KEY, 1, timeout=1)
    req = urllib.request.Request(
        f"{url}?{urllib.parse.urlencode(params)}",
        headers={"User-Agent": settings.NOMINATIM_USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        log.warning("nominatim request failed: %s", exc)
        return None


def reverse_geocode(lat: float, lng: float) -> str:
    """Human-readable address, or empty string. Cached for a week."""
    key = f"revgeo:{lat:.5f},{lng:.5f}"
    hit = cache.get(key)
    if hit is not None:
        return hit
    data = _throttled_get(
        NOMINATIM_REVERSE,
        {"lat": lat, "lon": lng, "format": "jsonv2", "zoom": 18},
    )
    address = (data or {}).get("display_name", "") if data else ""
    if address:
        cache.set(key, address, 60 * 60 * 24 * 7)
    return address


def forward_geocode(query: str, limit: int = 5) -> list:
    """Place search for the map search box. Cached for a day."""
    query = (query or "").strip()
    if len(query) < 3:
        return []
    key = f"fwdgeo:{query.lower()[:80]}"
    hit = cache.get(key)
    if hit is not None:
        return hit
    data = _throttled_get(
        NOMINATIM_SEARCH, {"q": query, "format": "jsonv2", "limit": limit}
    )
    results = [
        {
            "label": row.get("display_name", ""),
            "lat": float(row["lat"]),
            "lng": float(row["lon"]),
        }
        for row in (data or [])
        if row.get("lat") and row.get("lon")
    ]
    if results:
        cache.set(key, results, 60 * 60 * 24)
    return results
