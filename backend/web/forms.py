from django import forms
from django.conf import settings
from PIL import Image

from accounts.forms import StyledMixin
from geo.models import Ward
from reports.models import Report, Severity, WorkflowStatus


class ImageFieldMixin:
    """Validate an uploaded image at the trust boundary.

    Checks size, then that Pillow can actually decode it. A file that merely
    ends in .jpg is not an image.
    """

    max_bytes = settings.MAX_UPLOAD_BYTES

    def _validate_image(self, image, field_name="image"):
        if image is None:
            return image
        if image.size > self.max_bytes:
            mb = self.max_bytes / (1024 * 1024)
            raise forms.ValidationError(f"Image must be under {mb:.0f} MB.")
        try:
            image.seek(0)
            Image.open(image).verify()
        except Exception:
            raise forms.ValidationError("That file is not a readable image.")
        finally:
            image.seek(0)
        return image


class ReportUploadForm(ImageFieldMixin, StyledMixin, forms.Form):
    image = forms.ImageField(
        label="Photo of the pothole",
        widget=forms.ClearableFileInput(
            attrs={"accept": "image/*", "capture": "environment", "id": "id_image"}
        ),
    )
    latitude = forms.FloatField(widget=forms.HiddenInput())
    longitude = forms.FloatField(widget=forms.HiddenInput())
    accuracy_m = forms.FloatField(required=False, widget=forms.HiddenInput())
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Landmark, lane, anything useful"}),
    )

    def clean_image(self):
        return self._validate_image(self.cleaned_data.get("image"))

    def clean_latitude(self):
        lat = self.cleaned_data["latitude"]
        if not -90 <= lat <= 90:
            raise forms.ValidationError("Invalid latitude.")
        return lat

    def clean_longitude(self):
        lng = self.cleaned_data["longitude"]
        if not -180 <= lng <= 180:
            raise forms.ValidationError("Invalid longitude.")
        return lng


class ReportFilterForm(StyledMixin, forms.Form):
    """GET filter form. Every field optional; blank means no constraint."""

    q = forms.CharField(required=False, label="Search")
    status = forms.ChoiceField(required=False, choices=[("", "Any status")] + WorkflowStatus.choices)
    severity = forms.ChoiceField(required=False, choices=[("", "Any severity")] + Severity.choices)
    ward = forms.ModelChoiceField(required=False, queryset=Ward.objects.all(), empty_label="Any ward")
    source = forms.ChoiceField(
        required=False,
        choices=[("", "Any source"), ("web", "Web"), ("android", "Android"), ("live", "Live video")],
    )
    date_from = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"}), label="From"
    )
    date_to = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"}), label="To"
    )

    def as_params(self) -> dict:
        """Normalise to the keys selectors.filter_reports expects."""
        if not self.is_valid():
            return {}
        c = self.cleaned_data
        return {
            "q": c.get("q") or "",
            "status": c.get("status") or "",
            "severity": c.get("severity") or "",
            "ward": c["ward"].id if c.get("ward") else "",
            "source": c.get("source") or "",
            "from": c["date_from"].isoformat() if c.get("date_from") else "",
            "to": c["date_to"].isoformat() if c.get("date_to") else "",
        }


class StatusActionForm(forms.Form):
    to_status = forms.ChoiceField(choices=WorkflowStatus.choices)
    note = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))


class RejectForm(forms.Form):
    note = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Why is this being rejected?"}),
        label="Reason",
    )


class AssignForm(forms.Form):
    officer = forms.ModelChoiceField(queryset=None, label="Assign to")
    due_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.fields["officer"].queryset = User.objects.filter(
            role__in=["officer", "admin"], is_active=True
        ).order_by("name", "email")
        self.fields["officer"].widget.attrs["class"] = "field-input"
        self.fields["due_date"].widget.attrs["class"] = "field-input"


class SeverityForm(forms.Form):
    severity = forms.ChoiceField(choices=Severity.choices)


class DuplicateForm(forms.Form):
    parent_id = forms.UUIDField(label="Parent report ID")
    note = forms.CharField(required=False)


class FixForm(ImageFieldMixin, forms.Form):
    after_image = forms.ImageField(
        label="After photo",
        widget=forms.ClearableFileInput(attrs={"accept": "image/*", "capture": "environment"}),
    )
    note = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def clean_after_image(self):
        return self._validate_image(self.cleaned_data.get("after_image"), "after_image")


class CommentForm(StyledMixin, forms.Form):
    body = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Add a comment"}), label=""
    )
    is_internal = forms.BooleanField(required=False, label="Internal note (officers only)")


class BulkActionForm(forms.Form):
    action = forms.ChoiceField(
        choices=[("verify", "Verify"), ("reject", "Reject"), ("in_progress", "Mark in progress")]
    )
    report_ids = forms.CharField(widget=forms.HiddenInput())
    note = forms.CharField(required=False)

    def clean_report_ids(self):
        raw = self.cleaned_data["report_ids"]
        ids = [i for i in raw.split(",") if i.strip()]
        if not ids:
            raise forms.ValidationError("Select at least one report.")
        return ids


class WardImportForm(forms.Form):
    geojson = forms.FileField(
        label="Ward boundaries (GeoJSON FeatureCollection)",
        help_text="Each feature needs 'name' and 'code' properties.",
    )


class ModelVersionForm(StyledMixin, forms.ModelForm):
    class Meta:
        from detection.models import ModelVersion

        model = ModelVersion
        fields = ("name", "file_path", "conf_threshold", "review_threshold", "imgsz", "notes", "is_active")


class ThresholdForm(forms.Form):
    conf_threshold = forms.FloatField(min_value=0.01, max_value=0.99)
    review_threshold = forms.FloatField(min_value=0.01, max_value=0.99)
    duplicate_radius_m = forms.FloatField(min_value=1, max_value=500)

    def clean(self):
        cleaned = super().clean()
        conf, review = cleaned.get("conf_threshold"), cleaned.get("review_threshold")
        if conf and review and review > conf:
            raise forms.ValidationError("Review threshold must not exceed the confidence threshold.")
        return cleaned
