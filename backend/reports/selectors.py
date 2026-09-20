"""All querying and filtering. Views call these; they never build querysets."""
from __future__ import annotations

from datetime import datetime, timedelta

from django.db.models import Avg, Count, F, Q
from django.utils import timezone

from core.geoutils import Point, in_bbox, within_radius

from .models import DetectionStatus, Report, Severity, WorkflowStatus


def _parse_date(value: str | None):
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return timezone.make_aware(datetime.strptime(value, fmt))
        except (ValueError, TypeError):
            continue
    return None


def filter_reports(queryset=None, *, params=None, user=None):
    """Apply the dashboard/list filter form to a queryset.

    Accepts a plain dict or a QueryDict, so both the web GET form and the DRF
    query params go through one implementation.
    """
    qs = Report.objects.all() if queryset is None else queryset
    params = params or {}

    status = params.get("status")
    if status:
        qs = qs.filter(workflow_status=status)

    detection = params.get("detection")
    if detection:
        qs = qs.filter(detection_status=detection)

    severity = params.get("severity")
    if severity:
        qs = qs.filter(severity=severity)

    ward = params.get("ward")
    if ward:
        qs = qs.filter(ward_id=ward)

    source = params.get("source")
    if source:
        qs = qs.filter(source=source)

    start = _parse_date(params.get("from"))
    if start:
        qs = qs.filter(created_at__gte=start)

    end = _parse_date(params.get("to"))
    if end:
        qs = qs.filter(created_at__lt=end + timedelta(days=1))

    search = (params.get("q") or "").strip()
    if search:
        qs = qs.filter(
            Q(address__icontains=search)
            | Q(notes__icontains=search)
            | Q(reporter__email__icontains=search)
            | Q(reporter__name__icontains=search)
        )

    if params.get("open") == "1":
        qs = qs.open()
    if params.get("hide_duplicates") == "1":
        qs = qs.filter(duplicate_of__isnull=True)

    if params.get("mine") == "1" and user is not None:
        qs = qs.filter(assignments__officer=user, assignments__is_active=True)

    ordering = params.get("sort") or "-created_at"
    allowed = {
        "-created_at", "created_at", "-severity_score", "severity_score",
        "-confidence", "confidence", "-report_count",
    }
    if ordering in allowed:
        qs = qs.order_by(ordering)

    return qs.with_related()


def public_map_features(params=None, cap: int | None = None):
    """GeoJSON FeatureCollection of publicly visible reports."""
    from django.conf import settings

    cap = cap or settings.MAP_POINT_CAP
    qs = filter_reports(Report.objects.public(), params=params)
    bbox = (params or {}).get("bbox")
    if bbox:
        try:
            w, s, e, n = (float(v) for v in bbox.split(","))
            qs = in_bbox(qs, w, s, e, n)
        except (ValueError, TypeError):
            pass
    # as_feature() touches no related rows, so drop the select_related that
    # filter_reports adds; .only() and select_related on the same field is a
    # FieldError.
    rows = list(qs.select_related(None).only(
        "id", "latitude", "longitude", "severity", "severity_score",
        "workflow_status", "confidence", "thumbnail", "created_at", "report_count",
    )[:cap])
    return {
        "type": "FeatureCollection",
        "features": [r.as_feature() for r in rows],
        "truncated": len(rows) >= cap,
    }


def nearby(lat: float, lng: float, radius_m: float = 500, limit: int = 50):
    return within_radius(Report.objects.public().with_related(), Point(lat, lng), radius_m)[:limit]


def for_user(user):
    """Reports a user may list. Citizens see only their own."""
    if user.is_officer:
        return Report.objects.all().with_related()
    return Report.objects.filter(reporter=user).with_related()


def review_queue():
    return Report.objects.needs_review().with_related().order_by("-confidence", "-created_at")


def officer_tasks(user):
    return (
        Report.objects.filter(assignments__officer=user, assignments__is_active=True)
        .exclude(workflow_status__in=[WorkflowStatus.FIXED, WorkflowStatus.REJECTED])
        .with_related()
        .distinct()
    )


# --- dashboard aggregates -------------------------------------------------


def kpi_summary() -> dict:
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    real = Report.objects.exclude(detection_status=DetectionStatus.INTACT).filter(
        duplicate_of__isnull=True
    )

    fixed_this_month = real.filter(
        workflow_status=WorkflowStatus.FIXED, updated_at__gte=month_start
    )
    avg_fix = fixed_this_month.aggregate(
        avg=Avg(F("updated_at") - F("created_at"))
    )["avg"]

    return {
        "total": real.count(),
        "open": real.open().count(),
        "high_open": real.open().filter(severity=Severity.HIGH).count(),
        "fixed_month": fixed_this_month.count(),
        "avg_fix_days": round(avg_fix.total_seconds() / 86400, 1) if avg_fix else None,
        "today": real.filter(created_at__gte=today_start).count(),
        "review": Report.objects.needs_review().count(),
    }


def reports_over_time(days: int = 30) -> dict:
    """Daily counts for the trend line, zero-filled so the chart has no gaps."""
    since = timezone.now() - timedelta(days=days - 1)
    rows = (
        Report.objects.filter(created_at__gte=since)
        .exclude(detection_status=DetectionStatus.INTACT)
        .values_list("created_at", flat=True)
    )
    buckets: dict[str, int] = {}
    for i in range(days):
        day = (since + timedelta(days=i)).date().isoformat()
        buckets[day] = 0
    for created in rows:
        key = timezone.localtime(created).date().isoformat()
        if key in buckets:
            buckets[key] += 1
    return {"labels": list(buckets.keys()), "values": list(buckets.values())}


def severity_mix() -> dict:
    rows = (
        Report.objects.exclude(detection_status=DetectionStatus.INTACT)
        .filter(duplicate_of__isnull=True)
        .values("severity")
        .annotate(n=Count("id"))
    )
    order = [Severity.LOW, Severity.MEDIUM, Severity.HIGH]
    counts = {r["severity"]: r["n"] for r in rows}
    return {
        "labels": [s.label for s in order],
        "values": [counts.get(s.value, 0) for s in order],
    }


def status_mix() -> dict:
    rows = (
        Report.objects.filter(duplicate_of__isnull=True)
        .exclude(detection_status=DetectionStatus.INTACT)
        .values("workflow_status")
        .annotate(n=Count("id"))
    )
    counts = {r["workflow_status"]: r["n"] for r in rows}
    choices = [c for c in WorkflowStatus if c != WorkflowStatus.DUPLICATE]
    return {
        "labels": [c.label for c in choices],
        "values": [counts.get(c.value, 0) for c in choices],
    }


def top_wards(limit: int = 8) -> dict:
    rows = (
        Report.objects.exclude(detection_status=DetectionStatus.INTACT)
        .filter(ward__isnull=False, duplicate_of__isnull=True)
        .values("ward__name")
        .annotate(n=Count("id"))
        .order_by("-n")[:limit]
    )
    return {
        "labels": [r["ward__name"] for r in rows],
        "values": [r["n"] for r in rows],
    }


def hotspots(limit: int = 10):
    """Most-confirmed locations: report_count is incremented by dedupe."""
    return (
        Report.objects.public()
        .filter(report_count__gt=1)
        .order_by("-report_count", "-severity_score")
        .with_related()[:limit]
    )


def time_to_fix_buckets() -> dict:
    """Distribution of repair turnaround, in day bands."""
    fixed = Report.objects.filter(workflow_status=WorkflowStatus.FIXED)
    bands = [("< 1 day", 0, 1), ("1-3 days", 1, 3), ("3-7 days", 3, 7),
             ("1-2 weeks", 7, 14), ("2+ weeks", 14, 10**6)]
    values = [0] * len(bands)
    for created, updated in fixed.values_list("created_at", "updated_at"):
        days = (updated - created).total_seconds() / 86400
        for i, (_label, lo, hi) in enumerate(bands):
            if lo <= days < hi:
                values[i] += 1
                break
    return {"labels": [b[0] for b in bands], "values": values}


def confidence_histogram(bins: int = 10) -> dict:
    """Confidence distribution, for tuning the thresholds on the settings page."""
    values = [0] * bins
    for conf in Report.objects.exclude(confidence=0).values_list("confidence", flat=True):
        idx = min(int(conf * bins), bins - 1)
        values[idx] += 1
    labels = [f"{i / bins:.1f}-{(i + 1) / bins:.1f}" for i in range(bins)]
    return {"labels": labels, "values": values}
