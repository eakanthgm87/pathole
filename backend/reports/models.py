import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse

from core.geoutils import Point


class DetectionStatus(models.TextChoices):
    INTACT = "intact", "No pothole found"
    POTHOLE_DETECTED = "pothole_detected", "Pothole detected"
    NEEDS_REVIEW = "needs_review", "Needs review"
    UNKNOWN = "unknown", "Analysis failed"


class WorkflowStatus(models.TextChoices):
    SUBMITTED = "submitted", "Submitted"
    VERIFIED = "verified", "Verified"
    ASSIGNED = "assigned", "Assigned"
    IN_PROGRESS = "in_progress", "In progress"
    FIXED = "fixed", "Fixed"
    REJECTED = "rejected", "Rejected"
    DUPLICATE = "duplicate", "Duplicate"


class Severity(models.TextChoices):
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"


# Which transitions the workflow permits. Enforced in services.change_status.
ALLOWED_TRANSITIONS = {
    WorkflowStatus.SUBMITTED: {
        WorkflowStatus.VERIFIED,
        WorkflowStatus.REJECTED,
        WorkflowStatus.DUPLICATE,
    },
    WorkflowStatus.VERIFIED: {
        WorkflowStatus.ASSIGNED,
        WorkflowStatus.IN_PROGRESS,
        WorkflowStatus.REJECTED,
        WorkflowStatus.DUPLICATE,
    },
    WorkflowStatus.ASSIGNED: {
        WorkflowStatus.IN_PROGRESS,
        WorkflowStatus.FIXED,
        WorkflowStatus.VERIFIED,
        WorkflowStatus.REJECTED,
    },
    WorkflowStatus.IN_PROGRESS: {WorkflowStatus.FIXED, WorkflowStatus.ASSIGNED},
    WorkflowStatus.FIXED: {WorkflowStatus.IN_PROGRESS},
    WorkflowStatus.REJECTED: {WorkflowStatus.SUBMITTED},
    WorkflowStatus.DUPLICATE: {WorkflowStatus.SUBMITTED},
}

PUBLIC_WORKFLOW_STATUSES = [
    WorkflowStatus.VERIFIED,
    WorkflowStatus.ASSIGNED,
    WorkflowStatus.IN_PROGRESS,
    WorkflowStatus.FIXED,
]


def report_image_path(instance, filename):
    return f"reports/{instance.created_at:%Y/%m}/{instance.id}.jpg" if instance.created_at \
        else f"reports/incoming/{instance.id}.jpg"


class ReportQuerySet(models.QuerySet):
    def public(self):
        """Confirmed, non-duplicate reports safe to show on the public map."""
        return self.filter(
            detection_status=DetectionStatus.POTHOLE_DETECTED,
            workflow_status__in=PUBLIC_WORKFLOW_STATUSES,
            duplicate_of__isnull=True,
        )

    def open(self):
        return self.exclude(
            workflow_status__in=[
                WorkflowStatus.FIXED,
                WorkflowStatus.REJECTED,
                WorkflowStatus.DUPLICATE,
            ]
        )

    def needs_review(self):
        return self.filter(
            detection_status=DetectionStatus.NEEDS_REVIEW,
            workflow_status=WorkflowStatus.SUBMITTED,
            duplicate_of__isnull=True,
        )

    def with_related(self):
        return self.select_related("reporter", "ward", "model_version", "duplicate_of")


class Report(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client_uuid = models.UUIDField(
        unique=True,
        default=uuid.uuid4,
        help_text="Supplied by the mobile client so offline retries stay idempotent",
    )
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="reports"
    )
    image = models.ImageField(upload_to="reports/%Y/%m/")
    thumbnail = models.ImageField(upload_to="thumbs/%Y/%m/", blank=True)

    # Stored as plain floats; always read through the `location` property so a
    # future PostGIS migration touches only core.geoutils.
    latitude = models.FloatField()
    longitude = models.FloatField()
    accuracy_m = models.FloatField(null=True, blank=True)
    address = models.TextField(blank=True)
    ward = models.ForeignKey(
        "geo.Ward", null=True, blank=True, on_delete=models.SET_NULL, related_name="reports"
    )

    detection_status = models.CharField(
        max_length=20, choices=DetectionStatus.choices, default=DetectionStatus.UNKNOWN
    )
    confidence = models.FloatField(default=0.0)
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.LOW)
    severity_score = models.FloatField(default=0.0)
    severity_overridden = models.BooleanField(default=False)
    detections = models.JSONField(default=list, blank=True)
    model_version = models.ForeignKey(
        "detection.ModelVersion", null=True, blank=True, on_delete=models.SET_NULL
    )

    workflow_status = models.CharField(
        max_length=20, choices=WorkflowStatus.choices, default=WorkflowStatus.SUBMITTED
    )
    duplicate_of = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="duplicates"
    )
    report_count = models.PositiveIntegerField(default=1)

    source = models.CharField(
        max_length=10,
        choices=[("web", "Web"), ("android", "Android"), ("live", "Live video")],
        default="web",
    )
    notes = models.TextField(blank=True)
    captured_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ReportQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            # Stands in for the GiST index: the bbox prefilter hits this.
            models.Index(fields=["latitude", "longitude"], name="report_latlng_idx"),
            models.Index(fields=["workflow_status", "detection_status"]),
            models.Index(fields=["-created_at"]),
            models.Index(fields=["severity"]),
            models.Index(fields=["ward"]),
        ]

    def __str__(self):
        return f"{self.get_severity_display()} pothole @ {self.latitude:.5f},{self.longitude:.5f}"

    def get_absolute_url(self):
        return reverse("web:report_detail", args=[self.id])

    # --- location abstraction ---------------------------------------------
    @property
    def location(self) -> Point:
        return Point(self.latitude, self.longitude)

    @location.setter
    def location(self, point: Point):
        self.latitude, self.longitude = point.lat, point.lng

    @property
    def is_public(self) -> bool:
        return (
            self.detection_status == DetectionStatus.POTHOLE_DETECTED
            and self.workflow_status in PUBLIC_WORKFLOW_STATUSES
            and self.duplicate_of_id is None
        )

    @property
    def is_open(self) -> bool:
        return self.workflow_status not in (
            WorkflowStatus.FIXED,
            WorkflowStatus.REJECTED,
            WorkflowStatus.DUPLICATE,
        )

    @property
    def pothole_boxes(self) -> list:
        return [d for d in (self.detections or []) if d.get("class") == "pothole"]

    def as_feature(self) -> dict:
        """GeoJSON feature for the map layers. No reporter identity: this is
        embedded in public pages."""
        return {
            "type": "Feature",
            "geometry": self.location.geojson,
            "properties": {
                "id": str(self.id),
                "severity": self.severity,
                "severity_score": self.severity_score,
                "status": self.workflow_status,
                "status_label": self.get_workflow_status_display(),
                "confidence": round(self.confidence, 2),
                "thumb": self.thumbnail.url if self.thumbnail else "",
                "url": self.get_absolute_url(),
                "created": self.created_at.isoformat() if self.created_at else "",
                "count": self.report_count,
            },
        }


class StatusHistory(models.Model):
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="history")
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name_plural = "status history"

    def __str__(self):
        return f"{self.report_id}: {self.from_status} -> {self.to_status}"


class Assignment(models.Model):
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="assignments")
    officer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="assigned_reports"
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    due_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Comment(models.Model):
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    body = models.TextField()
    is_internal = models.BooleanField(
        default=False, help_text="Internal notes are hidden from the reporter"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class RepairProof(models.Model):
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="repair_proofs")
    after_image = models.ImageField(upload_to="repairs/%Y/%m/")
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
