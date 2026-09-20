"""All business logic. Template views and DRF views both call in here.

Nothing in this module may import from `web` or `api`.
"""
from __future__ import annotations

import logging
import uuid

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from core.geoutils import Point, within_radius
from core.utils import strip_exif_and_normalise
from detection import engine, scoring
from geo.models import ward_for_point

from .models import (
    ALLOWED_TRANSITIONS,
    Assignment,
    Comment,
    DetectionStatus,
    RepairProof,
    Report,
    Severity,
    StatusHistory,
    WorkflowStatus,
)

log = logging.getLogger(__name__)


class ServiceError(ValidationError):
    """Raised for rule violations the caller should surface to the user."""


# --- creation -------------------------------------------------------------


def find_duplicate(point: Point, radius_m: float | None = None):
    """An existing open report within the merge radius, or None."""
    from django.conf import settings

    radius = settings.DUPLICATE_RADIUS_M if radius_m is None else radius_m
    candidates = Report.objects.open().filter(duplicate_of__isnull=True).exclude(
        detection_status=DetectionStatus.INTACT
    )
    hits = within_radius(candidates, point, radius)
    return hits[0] if hits else None


@transaction.atomic
def create_report(
    *,
    image_file,
    latitude: float,
    longitude: float,
    reporter=None,
    accuracy_m: float | None = None,
    notes: str = "",
    source: str = "web",
    captured_at=None,
    client_uuid: str | None = None,
    resolve_address: bool = True,
) -> Report:
    """Create a report: clean the image, run detection, score, dedupe, save.

    Idempotent on ``client_uuid`` so the Android offline queue can retry
    without creating duplicates.
    """
    if client_uuid:
        existing = Report.objects.filter(client_uuid=client_uuid).first()
        if existing:
            return existing

    if latitude is None or longitude is None:
        raise ServiceError("A location is required.")
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ServiceError("Location is outside valid coordinate range.")

    clean_bytes, thumb_bytes, _size = strip_exif_and_normalise(image_file)

    result = engine.detect_image(clean_bytes)
    scored = scoring.score_all(result)
    if not result.ok:
        log.warning("detection failed for new report: %s", result.error)

    point = Point(latitude, longitude)
    report = Report(
        client_uuid=client_uuid or uuid.uuid4(),
        reporter=reporter,
        latitude=latitude,
        longitude=longitude,
        accuracy_m=accuracy_m,
        notes=notes or "",
        source=source,
        captured_at=captured_at,
        model_version=engine.active_version(),
        **scored,
    )
    report.ward = ward_for_point(point)

    name = f"{report.id}.jpg"
    report.image.save(name, ContentFile(clean_bytes), save=False)
    report.thumbnail.save(f"t_{name}", ContentFile(thumb_bytes), save=False)

    # Only real detections take part in deduplication; an "intact" photo is
    # not a pothole and must never merge into one.
    if report.detection_status in (
        DetectionStatus.POTHOLE_DETECTED,
        DetectionStatus.NEEDS_REVIEW,
    ):
        dup = find_duplicate(point)
        if dup:
            report.duplicate_of = dup
            report.workflow_status = WorkflowStatus.DUPLICATE
            Report.objects.filter(pk=dup.pk).update(report_count=dup.report_count + 1)
            # Keep the parent's severity honest: a hole reported repeatedly is
            # worse than the first photo suggested.
            if report.severity_score > dup.severity_score and not dup.severity_overridden:
                Report.objects.filter(pk=dup.pk).update(
                    severity_score=report.severity_score, severity=report.severity
                )

    report.save()

    StatusHistory.objects.create(
        report=report,
        from_status="",
        to_status=report.workflow_status,
        changed_by=reporter,
        note="Report created",
    )

    if resolve_address:
        _attach_address(report)

    if report.duplicate_of_id:
        _notify(
            report.duplicate_of.reporter,
            "Another citizen reported this pothole",
            "Your report now has additional confirmations.",
            report.duplicate_of,
        )

    return report


def _attach_address(report: Report) -> None:
    """Reverse geocode without ever failing the submission."""
    try:
        from geo.services import reverse_geocode

        address = reverse_geocode(report.latitude, report.longitude)
        if address:
            Report.objects.filter(pk=report.pk).update(address=address)
            report.address = address
    except Exception as exc:
        log.warning("reverse geocode skipped: %s", exc)


# --- workflow -------------------------------------------------------------


@transaction.atomic
def change_status(report: Report, to_status: str, *, actor=None, note: str = "") -> Report:
    """Move a report through the workflow, recording history and notifying."""
    current = report.workflow_status
    if to_status == current:
        return report
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if to_status not in allowed:
        raise ServiceError(
            f"Cannot move a {report.get_workflow_status_display().lower()} report to "
            f"{to_status.replace('_', ' ')}."
        )

    report.workflow_status = to_status
    report.save(update_fields=["workflow_status", "updated_at"])

    StatusHistory.objects.create(
        report=report,
        from_status=current,
        to_status=to_status,
        changed_by=actor,
        note=note,
    )

    labels = dict(WorkflowStatus.choices)
    _notify(
        report.reporter,
        f"Your report is now {labels.get(to_status, to_status)}",
        note or f"Status changed from {labels.get(current, current)}.",
        report,
    )
    return report


@transaction.atomic
def verify(report, *, actor, note=""):
    return change_status(report, WorkflowStatus.VERIFIED, actor=actor, note=note)


@transaction.atomic
def reject(report, *, actor, note=""):
    if not note:
        raise ServiceError("A reason is required when rejecting a report.")
    return change_status(report, WorkflowStatus.REJECTED, actor=actor, note=note)


@transaction.atomic
def mark_duplicate(report: Report, parent: Report, *, actor, note: str = "") -> Report:
    if parent.pk == report.pk:
        raise ServiceError("A report cannot duplicate itself.")
    if parent.duplicate_of_id:
        raise ServiceError("That parent is itself marked as a duplicate.")
    report.duplicate_of = parent
    report.save(update_fields=["duplicate_of", "updated_at"])
    Report.objects.filter(pk=parent.pk).update(report_count=parent.report_count + 1)
    return change_status(
        report, WorkflowStatus.DUPLICATE, actor=actor, note=note or f"Duplicate of {parent.id}"
    )


@transaction.atomic
def assign(report: Report, officer, *, actor, due_date=None) -> Report:
    if not officer.is_officer:
        raise ServiceError("Reports can only be assigned to officers.")
    Assignment.objects.filter(report=report, is_active=True).update(is_active=False)
    Assignment.objects.create(
        report=report, officer=officer, assigned_by=actor, due_date=due_date
    )
    if report.workflow_status in (WorkflowStatus.SUBMITTED,):
        change_status(report, WorkflowStatus.VERIFIED, actor=actor, note="Auto-verified on assignment")
    report.refresh_from_db()
    if report.workflow_status != WorkflowStatus.ASSIGNED:
        change_status(
            report,
            WorkflowStatus.ASSIGNED,
            actor=actor,
            note=f"Assigned to {officer.display_name}",
        )
    _notify(
        officer,
        "New report assigned to you",
        f"A {report.severity} severity pothole needs your attention.",
        report,
    )
    return report


@transaction.atomic
def override_severity(report: Report, severity: str, *, actor) -> Report:
    if severity not in dict(Severity.choices):
        raise ServiceError("Unknown severity value.")
    report.severity = severity
    report.severity_overridden = True
    report.save(update_fields=["severity", "severity_overridden", "updated_at"])
    StatusHistory.objects.create(
        report=report,
        from_status=report.workflow_status,
        to_status=report.workflow_status,
        changed_by=actor,
        note=f"Severity overridden to {severity}",
    )
    return report


@transaction.atomic
def mark_fixed(report: Report, *, actor, after_image=None, note: str = "") -> Report:
    """Close a report. An after-photo is required as proof of repair."""
    if after_image is None:
        raise ServiceError("An after-photo is required to mark a report fixed.")
    clean_bytes, _thumb, _size = strip_exif_and_normalise(after_image)
    proof = RepairProof(report=report, note=note, created_by=actor)
    proof.after_image.save(f"{report.id}_after.jpg", ContentFile(clean_bytes), save=False)
    proof.save()
    return change_status(
        report, WorkflowStatus.FIXED, actor=actor, note=note or "Repair completed"
    )


@transaction.atomic
def reanalyze(report: Report, *, actor=None) -> Report:
    """Re-run detection against the currently active model."""
    report.image.open("rb")
    try:
        data = report.image.read()
    finally:
        report.image.close()

    result = engine.detect_image(data)
    scored = scoring.score_all(result)
    if not result.ok:
        raise ServiceError(f"Detection failed: {result.error}")

    for key, value in scored.items():
        if key == "severity" and report.severity_overridden:
            continue
        setattr(report, key, value)
    report.model_version = engine.active_version()
    report.save()

    StatusHistory.objects.create(
        report=report,
        from_status=report.workflow_status,
        to_status=report.workflow_status,
        changed_by=actor,
        note=f"Re-analysed with {report.model_version.name if report.model_version else 'default model'}",
    )
    return report


def add_comment(report: Report, *, author, body: str, is_internal: bool = False) -> Comment:
    body = (body or "").strip()
    if not body:
        raise ServiceError("Comment cannot be empty.")
    if is_internal and not author.is_officer:
        raise ServiceError("Only officers can leave internal notes.")
    comment = Comment.objects.create(
        report=report, author=author, body=body, is_internal=is_internal
    )
    if not is_internal and report.reporter_id and report.reporter_id != author.id:
        _notify(report.reporter, "New comment on your report", body[:140], report)
    return comment


def bulk_action(report_ids, action: str, *, actor, note: str = "") -> dict:
    """Apply one workflow action to many reports. Never aborts the batch."""
    done, failed = 0, []
    for report in Report.objects.filter(id__in=report_ids):
        try:
            if action == "verify":
                verify(report, actor=actor, note=note)
            elif action == "reject":
                reject(report, actor=actor, note=note or "Bulk rejection")
            elif action == "in_progress":
                change_status(report, WorkflowStatus.IN_PROGRESS, actor=actor, note=note)
            else:
                raise ServiceError(f"Unknown bulk action '{action}'.")
            done += 1
        except ValidationError as exc:
            failed.append((str(report.id), "; ".join(exc.messages)))
    return {"updated": done, "failed": failed}


def _notify(user, title: str, body: str, report=None) -> None:
    if not user:
        return
    try:
        from notifications.services import notify

        notify(user, title=title, body=body, report=report)
    except Exception as exc:
        log.warning("notification skipped: %s", exc)


# --- live video -----------------------------------------------------------


def analyse_live_frame(frame_bytes: bytes) -> dict:
    """Run one webcam/dashcam frame. Nothing is persisted.

    Returns boxes in source-pixel coordinates plus a running severity score so
    the client can show a live band without a second round trip.
    """
    result = engine.detect_frame(frame_bytes)
    if not result.ok:
        return {"ok": False, "error": result.error, "detections": []}
    score = scoring.severity_score(result)
    return {
        "ok": True,
        "detections": result.as_list(),
        "width": result.width,
        "height": result.height,
        "count": len(result.potholes),
        "best_conf": round(result.best_confidence, 3),
        "severity_score": score,
        "severity": scoring.severity_band(score),
        "ts": timezone.now().isoformat(),
    }
