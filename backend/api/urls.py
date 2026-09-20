from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from . import views

app_name = "api"

router = DefaultRouter()
router.register("reports", views.ReportViewSet, basename="report")
router.register("notifications", views.NotificationViewSet, basename="notification")

urlpatterns = [
    path("auth/register/", views.RegisterView.as_view(), name="register"),
    path("auth/login/", TokenObtainPairView.as_view(), name="login"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="refresh"),
    path("auth/me/", views.MeView.as_view(), name="me"),
    path("reports/geojson/", views.reports_geojson, name="reports-geojson"),
    path("reports/nearby/", views.reports_nearby, name="reports-nearby"),
    path("wards/", views.wards, name="wards"),
    path("devices/", views.DeviceView.as_view(), name="devices"),
    path("tasks/", views.officer_tasks, name="tasks"),
    path("health/", views.health, name="health"),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="api:schema"), name="docs"),
    path("", include(router.urls)),
]
