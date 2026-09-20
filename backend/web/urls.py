from django.urls import path

from .views import dashboard as dash
from .views import live, public

app_name = "web"

urlpatterns = [
    # Public
    path("", public.landing, name="landing"),
    path("map/", public.public_map, name="map"),
    path("map/data/", public.map_data, name="map_data"),
    path("geocode/", public.geocode_search, name="geocode"),
    # Citizen
    path("report/new/", public.ReportCreateView.as_view(), name="report_new"),
    path("report/live/", public.LiveDetectView.as_view(), name="live"),
    path("live/frame/", live.analyse_frame, name="live_frame"),
    path("live/capture/", live.capture_from_live, name="live_capture"),
    path("my-reports/", public.MyReportsView.as_view(), name="my_reports"),
    path("notifications/", public.NotificationsView.as_view(), name="notifications"),
    path("reports/<uuid:pk>/", public.ReportDetailView.as_view(), name="report_detail"),
    path("reports/<uuid:pk>/result/", public.ReportResultView.as_view(), name="report_result"),
    path("reports/<uuid:pk>/comments/", public.add_comment, name="report_comment"),
    # Dashboard
    path("dashboard/", dash.OverviewView.as_view(), name="dashboard_overview"),
    path("dashboard/map/", dash.DashboardMapView.as_view(), name="dashboard_map"),
    path("dashboard/reports/", dash.ReportsTableView.as_view(), name="dashboard_reports"),
    path("dashboard/reports/export/", dash.ExportCsvView.as_view(), name="dashboard_export"),
    path("dashboard/reports/bulk/", dash.BulkActionView.as_view(), name="dashboard_bulk"),
    path("dashboard/reports/<uuid:pk>/", dash.ReportManageView.as_view(), name="dashboard_report"),
    path("dashboard/reports/<uuid:pk>/status/", dash.StatusActionView.as_view(), name="dashboard_status"),
    path("dashboard/reports/<uuid:pk>/assign/", dash.AssignActionView.as_view(), name="dashboard_assign"),
    path("dashboard/reports/<uuid:pk>/duplicate/", dash.DuplicateActionView.as_view(), name="dashboard_duplicate"),
    path("dashboard/reports/<uuid:pk>/severity/", dash.SeverityActionView.as_view(), name="dashboard_severity"),
    path("dashboard/reports/<uuid:pk>/reanalyze/", dash.ReanalyzeActionView.as_view(), name="dashboard_reanalyze"),
    path("dashboard/reports/<uuid:pk>/fix/", dash.FixActionView.as_view(), name="dashboard_fix"),
    path("dashboard/review/", dash.ReviewQueueView.as_view(), name="dashboard_review"),
    path("dashboard/review/<uuid:pk>/decide/", dash.ReviewDecideView.as_view(), name="dashboard_review_decide"),
    path("dashboard/analytics/", dash.AnalyticsView.as_view(), name="dashboard_analytics"),
    path("dashboard/tasks/", dash.TasksView.as_view(), name="dashboard_tasks"),
    path("dashboard/wards/", dash.WardsView.as_view(), name="dashboard_wards"),
    path("dashboard/users/", dash.UsersView.as_view(), name="dashboard_users"),
    path("dashboard/settings/", dash.SettingsView.as_view(), name="dashboard_settings"),
]
