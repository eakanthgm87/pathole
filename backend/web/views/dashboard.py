"""Officer and admin dashboard views. Thin: every action calls services."""
import csv
import json

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from core.mixins import AdminRequiredMixin, OfficerRequiredMixin
from detection.models import ModelVersion
from geo.models import Ward
from reports import selectors, services
from reports.models import Report, WorkflowStatus
from web.forms import (
    AssignForm,
    BulkActionForm,
    CommentForm,
    DuplicateForm,
    FixForm,
    ModelVersionForm,
    RejectForm,
    ReportFilterForm,
    SeverityForm,
    ThresholdForm,
    WardImportForm,
)


class OverviewView(OfficerRequiredMixin, View):
    def get(self, request):
        return render(
            request,
            "dashboard/overview.html",
            {
                "kpis": selectors.kpi_summary(),
                "trend": selectors.reports_over_time(30),
                "severity_mix": selectors.severity_mix(),
                "status_mix": selectors.status_mix(),
                "top_wards": selectors.top_wards(),
                "recent": Report.objects.with_related().exclude(
                    detection_status="intact"
                )[:8],
                "review_queue": selectors.review_queue()[:5],
            },
        )


class DashboardMapView(OfficerRequiredMixin, View):
    def get(self, request):
        form = ReportFilterForm(request.GET or None)
        qs = selectors.filter_reports(
            Report.objects.exclude(detection_status="intact"),
            params=form.as_params() if form.is_bound else None,
        )
        features = [r.as_feature() for r in qs[:2000]]
        wards = [w.as_feature() for w in Ward.objects.exclude(boundary={})]
        return render(
            request,
            "dashboard/map.html",
            {
                "form": form,
                "geojson": {"type": "FeatureCollection", "features": features},
                "wards_geojson": {"type": "FeatureCollection", "features": wards},
            },
        )


class ReportsTableView(OfficerRequiredMixin, View):
    def get(self, request):
        form = ReportFilterForm(request.GET or None)
        qs = selectors.filter_reports(params=form.as_params() if form.is_bound else None)
        page = Paginator(qs, 25).get_page(request.GET.get("page"))
        querystring = request.GET.copy()
        querystring.pop("page", None)
        return render(
            request,
            "dashboard/reports.html",
            {
                "page_obj": page,
                "form": form,
                "bulk_form": BulkActionForm(),
                "querystring": querystring.urlencode(),
            },
        )


class ReportManageView(OfficerRequiredMixin, View):
    def get(self, request, pk):
        report = get_object_or_404(Report.objects.with_related(), pk=pk)
        return render(
            request,
            "dashboard/report_manage.html",
            {
                "report": report,
                "history": report.history.select_related("changed_by"),
                "comments": report.comments.select_related("author"),
                "assign_form": AssignForm(),
                "reject_form": RejectForm(),
                "severity_form": SeverityForm(initial={"severity": report.severity}),
                "duplicate_form": DuplicateForm(),
                "fix_form": FixForm(),
                "comment_form": CommentForm(),
                "detections_json": json.dumps(report.detections or []),
                "proofs": report.repair_proofs.all(),
            },
        )


class _ActionView(OfficerRequiredMixin, View):
    """Shared POST plumbing: run, flash, redirect back to the manage page."""

    def redirect_back(self, request, report):
        return redirect(request.POST.get("next") or f"/dashboard/reports/{report.id}/")

    def run(self, request, report):
        raise NotImplementedError

    def post(self, request, pk):
        report = get_object_or_404(Report, pk=pk)
        try:
            self.run(request, report)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        return self.redirect_back(request, report)


class StatusActionView(_ActionView):
    def run(self, request, report):
        to_status = request.POST.get("to_status")
        note = request.POST.get("note", "")
        if to_status == WorkflowStatus.REJECTED:
            form = RejectForm(request.POST)
            if not form.is_valid():
                raise ValidationError("A reason is required when rejecting a report.")
            services.reject(report, actor=request.user, note=form.cleaned_data["note"])
        else:
            services.change_status(report, to_status, actor=request.user, note=note)
        messages.success(request, "Status updated.")


class AssignActionView(_ActionView):
    def run(self, request, report):
        form = AssignForm(request.POST)
        if not form.is_valid():
            raise ValidationError("Choose an officer to assign.")
        services.assign(
            report,
            form.cleaned_data["officer"],
            actor=request.user,
            due_date=form.cleaned_data.get("due_date"),
        )
        messages.success(request, "Report assigned.")


class DuplicateActionView(_ActionView):
    def run(self, request, report):
        form = DuplicateForm(request.POST)
        if not form.is_valid():
            raise ValidationError("A valid parent report ID is required.")
        parent = Report.objects.filter(pk=form.cleaned_data["parent_id"]).first()
        if not parent:
            raise ValidationError("No report with that ID.")
        services.mark_duplicate(
            report, parent, actor=request.user, note=form.cleaned_data.get("note", "")
        )
        messages.success(request, "Marked as duplicate.")


class SeverityActionView(_ActionView):
    def run(self, request, report):
        form = SeverityForm(request.POST)
        if not form.is_valid():
            raise ValidationError("Unknown severity.")
        services.override_severity(report, form.cleaned_data["severity"], actor=request.user)
        messages.success(request, "Severity overridden.")


class ReanalyzeActionView(_ActionView):
    def run(self, request, report):
        services.reanalyze(report, actor=request.user)
        messages.success(request, "Re-analysed with the active model.")


class FixActionView(_ActionView):
    def run(self, request, report):
        form = FixForm(request.POST, request.FILES)
        if not form.is_valid():
            raise ValidationError(
                "; ".join(m for errs in form.errors.values() for m in errs)
            )
        services.mark_fixed(
            report,
            actor=request.user,
            after_image=form.cleaned_data["after_image"],
            note=form.cleaned_data.get("note", ""),
        )
        messages.success(request, "Marked fixed. Nice work.")


class BulkActionView(OfficerRequiredMixin, View):
    def post(self, request):
        form = BulkActionForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Select at least one report and an action.")
            return redirect("web:dashboard_reports")
        result = services.bulk_action(
            form.cleaned_data["report_ids"],
            form.cleaned_data["action"],
            actor=request.user,
            note=form.cleaned_data.get("note", ""),
        )
        messages.success(request, f"Updated {result['updated']} report(s).")
        for rid, reason in result["failed"][:5]:
            messages.warning(request, f"{rid[:8]}: {reason}")
        return redirect(f"/dashboard/reports/?{request.POST.get('querystring', '')}")


class ReviewQueueView(OfficerRequiredMixin, View):
    def get(self, request):
        queue = list(selectors.review_queue()[:50])
        return render(
            request,
            "dashboard/review.html",
            {
                "queue": queue,
                "current": queue[0] if queue else None,
                "remaining": len(queue),
            },
        )


class ReviewDecideView(OfficerRequiredMixin, View):
    def post(self, request, pk):
        report = get_object_or_404(Report, pk=pk)
        decision = request.POST.get("decision")
        try:
            if decision == "confirm":
                # An officer confirming overrides the model: it is a pothole.
                report.detection_status = "pothole_detected"
                report.save(update_fields=["detection_status"])
                services.verify(report, actor=request.user, note="Confirmed in review queue")
                messages.success(request, "Confirmed.")
            elif decision == "reject":
                services.reject(
                    report,
                    actor=request.user,
                    note=request.POST.get("note") or "Rejected in review queue",
                )
                messages.success(request, "Rejected.")
            else:
                messages.error(request, "Unknown decision.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        return redirect("web:dashboard_review")


class AnalyticsView(OfficerRequiredMixin, View):
    def get(self, request):
        days = int(request.GET.get("days") or 30)
        days = max(7, min(days, 365))
        return render(
            request,
            "dashboard/analytics.html",
            {
                "days": days,
                "trend": selectors.reports_over_time(days),
                "severity_mix": selectors.severity_mix(),
                "status_mix": selectors.status_mix(),
                "top_wards": selectors.top_wards(12),
                "ttf": selectors.time_to_fix_buckets(),
                "hotspots": selectors.hotspots(10),
                "kpis": selectors.kpi_summary(),
            },
        )


class ExportCsvView(OfficerRequiredMixin, View):
    def get(self, request):
        form = ReportFilterForm(request.GET or None)
        qs = selectors.filter_reports(params=form.as_params() if form.is_bound else None)
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="reports.csv"'
        writer = csv.writer(response)
        writer.writerow([
            "id", "created_at", "latitude", "longitude", "address", "ward",
            "detection_status", "confidence", "severity", "severity_score",
            "workflow_status", "report_count", "source", "reporter",
        ])
        for r in qs.iterator(chunk_size=500):
            writer.writerow([
                r.id, r.created_at.isoformat(), r.latitude, r.longitude, r.address,
                r.ward.name if r.ward else "", r.detection_status, round(r.confidence, 4),
                r.severity, r.severity_score, r.workflow_status, r.report_count,
                r.source, r.reporter.email if r.reporter else "",
            ])
        return response


class WardsView(OfficerRequiredMixin, View):
    def get(self, request):
        wards = Ward.objects.annotate(n=Count("reports")).order_by("-n")
        return render(
            request,
            "dashboard/wards.html",
            {
                "wards": wards,
                "import_form": WardImportForm(),
                "wards_geojson": {
                    "type": "FeatureCollection",
                    "features": [w.as_feature() for w in wards if w.boundary],
                },
            },
        )

    def post(self, request):
        if not request.user.is_admin:
            messages.error(request, "Only admins can import wards.")
            return redirect("web:dashboard_wards")
        form = WardImportForm(request.POST, request.FILES)
        if not form.is_valid():
            messages.error(request, "Upload a GeoJSON file.")
            return redirect("web:dashboard_wards")
        try:
            data = json.load(form.cleaned_data["geojson"])
            created = updated = 0
            for feature in data.get("features", []):
                props = feature.get("properties", {})
                code = str(props.get("code") or props.get("ward_no") or "").strip()
                name = str(props.get("name") or props.get("ward_name") or "").strip()
                if not code or not name:
                    continue
                _obj, was_created = Ward.objects.update_or_create(
                    code=code,
                    defaults={"name": name, "boundary": feature.get("geometry") or {}},
                )
                created += was_created
                updated += not was_created
            messages.success(request, f"Imported {created} new, updated {updated} ward(s).")
        except Exception as exc:
            messages.error(request, f"Could not parse that GeoJSON: {exc}")
        return redirect("web:dashboard_wards")


class UsersView(AdminRequiredMixin, View):
    def get(self, request):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        users = User.objects.select_related("ward").order_by("-created_at")
        return render(request, "dashboard/users.html", {"users": users, "wards": Ward.objects.all()})

    def post(self, request):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = get_object_or_404(User, pk=request.POST.get("user_id"))
        action = request.POST.get("action")
        if action == "role":
            role = request.POST.get("role")
            if role in dict(User.Role.choices):
                if user == request.user and role != "admin":
                    messages.error(request, "You cannot remove your own admin role.")
                    return redirect("web:dashboard_users")
                user.role = role
                user.save(update_fields=["role"])
                messages.success(request, f"{user.display_name} is now {role}.")
        elif action == "toggle":
            if user == request.user:
                messages.error(request, "You cannot deactivate yourself.")
                return redirect("web:dashboard_users")
            user.is_active = not user.is_active
            user.save(update_fields=["is_active"])
            messages.success(request, f"{user.display_name} {'enabled' if user.is_active else 'disabled'}.")
        elif action == "ward":
            ward_id = request.POST.get("ward") or None
            user.ward = Ward.objects.filter(pk=ward_id).first() if ward_id else None
            user.save(update_fields=["ward"])
            messages.success(request, "Ward updated.")
        return redirect("web:dashboard_users")


class SettingsView(AdminRequiredMixin, View):
    def get(self, request):
        active = ModelVersion.objects.filter(is_active=True).first()
        from django.conf import settings as dj

        return render(
            request,
            "dashboard/settings.html",
            {
                "versions": ModelVersion.objects.all(),
                "model_form": ModelVersionForm(),
                "threshold_form": ThresholdForm(
                    initial={
                        "conf_threshold": active.conf_threshold if active else dj.DETECTION["CONF_THRESHOLD"],
                        "review_threshold": active.review_threshold if active else dj.DETECTION["REVIEW_THRESHOLD"],
                        "duplicate_radius_m": dj.DUPLICATE_RADIUS_M,
                    }
                ),
                "active": active,
                "histogram": selectors.confidence_histogram(),
            },
        )

    def post(self, request):
        action = request.POST.get("action")
        if action == "activate":
            version = get_object_or_404(ModelVersion, pk=request.POST.get("version_id"))
            version.is_active = True
            version.save()
            messages.success(request, f"{version.name} is now the active model.")
        elif action == "add_model":
            form = ModelVersionForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, "Model version registered.")
            else:
                messages.error(request, "Check the model fields.")
        elif action == "thresholds":
            form = ThresholdForm(request.POST)
            active = ModelVersion.objects.filter(is_active=True).first()
            if not form.is_valid():
                messages.error(request, "; ".join(
                    m for errs in form.errors.values() for m in errs
                ))
            elif not active:
                messages.error(request, "Activate a model version before editing thresholds.")
            else:
                active.conf_threshold = form.cleaned_data["conf_threshold"]
                active.review_threshold = form.cleaned_data["review_threshold"]
                active.save()
                messages.success(request, "Thresholds saved.")
        return redirect("web:dashboard_settings")


class TasksView(OfficerRequiredMixin, View):
    def get(self, request):
        return render(
            request, "dashboard/tasks.html", {"tasks": selectors.officer_tasks(request.user)}
        )
