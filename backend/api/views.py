"""DRF endpoints for the Android client.

These are thin wrappers over reports.services, the same layer the website
uses. No business rule may live in this module.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsOfficer
from geo.models import Ward
from notifications.models import DeviceToken, Notification
from reports import selectors, services
from reports.models import Report

from .serializers import (
    CommentSerializer,
    DeviceTokenSerializer,
    NotificationSerializer,
    RegisterSerializer,
    RepairProofSerializer,
    ReportCreateSerializer,
    ReportDetailSerializer,
    ReportSerializer,
    StatusUpdateSerializer,
    UserSerializer,
    WardSerializer,
)


class RegisterView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    @extend_schema(request=RegisterSerializer, responses={201: UserSerializer})
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class MeView(RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class ReportViewSet(viewsets.ReadOnlyModelViewSet):
    """List and retrieve. Creation goes through the multipart action below."""

    serializer_class = ReportSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        return selectors.filter_reports(
            selectors.for_user(self.request.user),
            params=self.request.query_params,
            user=self.request.user,
        )

    def get_serializer_class(self):
        return ReportDetailSerializer if self.action == "retrieve" else ReportSerializer

    @extend_schema(request=ReportCreateSerializer, responses={201: ReportSerializer})
    def create(self, request):
        serializer = ReportCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            report = services.create_report(
                image_file=data["image"],
                latitude=data["latitude"],
                longitude=data["longitude"],
                accuracy_m=data.get("accuracy_m"),
                captured_at=data.get("captured_at"),
                notes=data.get("notes", ""),
                client_uuid=str(data["client_uuid"]) if data.get("client_uuid") else None,
                source=data.get("source", "android"),
                reporter=request.user,
            )
        except DjangoValidationError as exc:
            return Response(
                {"error": {"code": "validation_error", "message": "; ".join(exc.messages)}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        body = ReportSerializer(report, context={"request": request}).data
        return Response({"report": body}, status=status.HTTP_201_CREATED)

    def get_throttles(self):
        if self.action == "create":
            self.throttle_scope = "upload"
        return super().get_throttles()

    @action(detail=True, methods=["post"], url_path="comments")
    def comments(self, request, pk=None):
        report = self.get_object()
        try:
            comment = services.add_comment(
                report,
                author=request.user,
                body=request.data.get("body", ""),
                is_internal=bool(request.data.get("is_internal")) and request.user.is_officer,
            )
        except DjangoValidationError as exc:
            return Response(
                {"error": {"code": "validation_error", "message": "; ".join(exc.messages)}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(CommentSerializer(comment).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch"], url_path="status", permission_classes=[IsOfficer])
    def set_status(self, request, pk=None):
        report = self.get_object()
        serializer = StatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            services.change_status(
                report,
                serializer.validated_data["to_status"],
                actor=request.user,
                note=serializer.validated_data.get("note", ""),
            )
        except DjangoValidationError as exc:
            return Response(
                {"error": {"code": "invalid_transition", "message": "; ".join(exc.messages)}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        report.refresh_from_db()
        return Response(ReportSerializer(report, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="repair-proof", permission_classes=[IsOfficer])
    def repair_proof(self, request, pk=None):
        report = self.get_object()
        serializer = RepairProofSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            services.mark_fixed(
                report,
                actor=request.user,
                after_image=serializer.validated_data["after_image"],
                note=serializer.validated_data.get("note", ""),
            )
        except DjangoValidationError as exc:
            return Response(
                {"error": {"code": "validation_error", "message": "; ".join(exc.messages)}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        report.refresh_from_db()
        return Response(ReportSerializer(report, context={"request": request}).data)


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([AllowAny])
def reports_geojson(request):
    return Response(selectors.public_map_features(request.query_params))


@api_view(["GET"])
@permission_classes([AllowAny])
def reports_nearby(request):
    try:
        lat = float(request.query_params["lat"])
        lng = float(request.query_params["lng"])
    except (KeyError, TypeError, ValueError):
        return Response(
            {"error": {"code": "bad_request", "message": "lat and lng are required."}},
            status=status.HTTP_400_BAD_REQUEST,
        )
    radius = float(request.query_params.get("radius") or 1000)
    radius = max(10.0, min(radius, 20000.0))
    rows = selectors.nearby(lat, lng, radius)
    return Response(ReportSerializer(rows, many=True, context={"request": request}).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def wards(request):
    return Response(WardSerializer(Ward.objects.all(), many=True).data)


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)

    @action(detail=True, methods=["patch"], url_path="read")
    def mark_read(self, request, pk=None):
        note = self.get_object()
        note.is_read = True
        note.save(update_fields=["is_read"])
        return Response(NotificationSerializer(note).data)

    @action(detail=False, methods=["patch"], url_path="read-all")
    def mark_all(self, request):
        from notifications.services import mark_all_read

        return Response({"updated": mark_all_read(request.user)})


class DeviceView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = DeviceTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        DeviceToken.objects.update_or_create(
            fcm_token=serializer.validated_data["fcm_token"],
            defaults={
                "user": request.user,
                "platform": serializer.validated_data.get("platform", "android"),
            },
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    def delete(self, request):
        token = request.data.get("fcm_token")
        DeviceToken.objects.filter(fcm_token=token, user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@permission_classes([IsOfficer])
def officer_tasks(request):
    rows = selectors.officer_tasks(request.user)
    return Response(ReportSerializer(rows, many=True, context={"request": request}).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    """Liveness probe. Reports whether weights are reachable."""
    from detection.engine import resolve_weights

    path = resolve_weights()
    return Response({"status": "ok", "weights": path.name, "weights_present": path.exists()})
