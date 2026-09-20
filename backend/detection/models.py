from django.core.exceptions import ValidationError
from django.db import models


class ModelVersion(models.Model):
    """A YOLO weights file plus the thresholds it should run with.

    Thresholds live per-version because a new model rarely shares the previous
    one's operating point. Exactly one row is active at a time.
    """

    name = models.CharField(max_length=120, unique=True)
    file_path = models.CharField(
        max_length=500,
        help_text="Path to .pt weights, absolute or relative to the weights/ directory",
    )
    notes = models.TextField(blank=True)
    conf_threshold = models.FloatField(default=0.60)
    review_threshold = models.FloatField(default=0.30)
    imgsz = models.PositiveIntegerField(default=640)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_active", "-created_at"]

    def __str__(self):
        return f"{self.name}{' (active)' if self.is_active else ''}"

    def clean(self):
        if self.review_threshold > self.conf_threshold:
            raise ValidationError(
                {"review_threshold": "Review threshold must not exceed the confidence threshold."}
            )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_active:
            # Enforce a single active version without a partial-unique index,
            # which SQLite and Postgres spell differently.
            ModelVersion.objects.exclude(pk=self.pk).filter(is_active=True).update(
                is_active=False
            )

    @property
    def resolved_path(self):
        from pathlib import Path

        from django.conf import settings

        p = Path(self.file_path)
        return p if p.is_absolute() else settings.DETECTION["WEIGHTS_DIR"] / self.file_path
