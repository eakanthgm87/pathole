"""Public and citizen-facing template views."""
import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.decorators.http import require_POST

from geo.models import Ward
from reports import selectors, services
from reports.models import DetectionStatus, Report
from web.forms import CommentForm, ReportFilterForm, ReportUploadForm


def landing(request):
    kpis = selectors.kpi_summary()
    recent = Report.objects.public()[:6]
    return render(request, "public/landing.html", {"kpis": kpis, "recent": recent})


def public_map(request):
    form = ReportFilterForm(request.GET or None)
    features = selectors.public_map_features(form.as_params() if form.is_bound else None)
    wards = [w.as_feature() for w in Ward.objects.exclude(boundary={})]
    return render(
        request,
        "public/map.html",
        {
            "form": form,
            "geojson": features,
            "wards_geojson": {"type": "FeatureCollection", "features": wards},
            "point_cap": settings.MAP_POINT_CAP,
        },
    )


def map_data(request):
    """Same-origin JSON for viewport loading when the embedded cap is hit.

    Session-authenticated, not part of the Android API.
    """
    params = request.GET.dict()
    return JsonResponse(selectors.public_map_features(params))


def geocode_search(request):
    """Proxy Nominatim so the browser never calls it directly (usage policy)."""
    from geo.services import forward_geocode

    return JsonResponse({"results": forward_geocode(request.GET.get("q", ""))})


class ReportCreateView(LoginRequiredMixin, View):
    template_name = "citizen/report_new.html"

    def get(self, request):
        return render(request, self.template_name, {"form": ReportUploadForm()})

    def post(self, request):
        form = ReportUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            messages.error(request, "Please fix the errors below.")
            return render(request, self.template_name, {"form": form}, status=400)

        data = form.cleaned_data
        try:
            report = services.create_report(
                image_file=data["image"],
                latitude=data["latitude"],
                longitude=data["longitude"],
                accuracy_m=data.get("accuracy_m"),
                notes=data.get("notes", ""),
                reporter=request.user,
                source="web",
            )
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return render(request, self.template_name, {"form": form}, status=400)

        if report.detection_status == DetectionStatus.POTHOLE_DETECTED:
            messages.success(request, "Pothole confirmed and added to the map.")
        elif report.detection_status == DetectionStatus.NEEDS_REVIEW:
            messages.info(request, "Submitted. An officer will review this one.")
        elif report.detection_status == DetectionStatus.INTACT:
            messages.warning(request, "No pothole found in that photo, but we saved it.")
        else:
            messages.warning(request, "Saved, but analysis failed. An officer will look.")
        return redirect("web:report_result", pk=report.id)


class ReportResultView(LoginRequiredMixin, View):
    def get(self, request, pk):
        report = get_object_or_404(Report.objects.with_related(), pk=pk)
        if report.reporter_id != request.user.id and not request.user.is_officer:
            raise Http404
        return render(
            request,
            "citizen/report_result.html",
            {"report": report, "detections_json": json.dumps(report.detections or [])},
        )


class MyReportsView(LoginRequiredMixin, View):
    def get(self, request):
        form = ReportFilterForm(request.GET or None)
        qs = selectors.filter_reports(
            Report.objects.filter(reporter=request.user),
            params=form.as_params() if form.is_bound else None,
        )
        page = Paginator(qs, 12).get_page(request.GET.get("page"))
        return render(request, "citizen/my_reports.html", {"page_obj": page, "form": form})


class ReportDetailView(LoginRequiredMixin, View):
    def get(self, request, pk):
        report = get_object_or_404(Report.objects.with_related(), pk=pk)
        is_owner = report.reporter_id == request.user.id
        if not is_owner and not request.user.is_officer and not report.is_public:
            raise Http404
        comments = report.comments.select_related("author")
        if not request.user.is_officer:
            comments = comments.filter(is_internal=False)
        return render(
            request,
            "citizen/report_detail.html",
            {
                "report": report,
                "comments": comments,
                "history": report.history.select_related("changed_by"),
                "comment_form": CommentForm(),
                "detections_json": json.dumps(report.detections or []),
                "is_owner": is_owner,
            },
        )


@login_required
@require_POST
def add_comment(request, pk):
    report = get_object_or_404(Report, pk=pk)
    form = CommentForm(request.POST)
    if form.is_valid():
        try:
            services.add_comment(
                report,
                author=request.user,
                body=form.cleaned_data["body"],
                is_internal=form.cleaned_data.get("is_internal", False),
            )
            messages.success(request, "Comment added.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
    else:
        messages.error(request, "Comment cannot be empty.")
    return redirect(request.POST.get("next") or report.get_absolute_url())


class NotificationsView(LoginRequiredMixin, View):
    def get(self, request):
        notes = request.user.notifications.select_related("report")[:100]
        return render(request, "citizen/notifications.html", {"notifications": notes})

    def post(self, request):
        from notifications.services import mark_all_read

        mark_all_read(request.user)
        messages.success(request, "All caught up.")
        return redirect("web:notifications")


class LiveDetectView(LoginRequiredMixin, View):
    """The live video page. Frames are analysed by web.views.live.analyse_frame."""

    def get(self, request):
        return render(request, "citizen/live.html", {})
