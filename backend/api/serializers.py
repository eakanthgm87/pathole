from django.contrib.auth import get_user_model
from rest_framework import serializers

from geo.models import Ward
from notifications.models import DeviceToken, Notification
from reports.models import Comment, Report, StatusHistory

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8, style={"input_type": "password"})

    class Meta:
        model = User
        fields = ("email", "name", "phone", "password")

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def create(self, validated_data):
        return User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            name=validated_data.get("name", ""),
            phone=validated_data.get("phone", ""),
        )


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "name", "phone", "role", "ward")
        read_only_fields = ("id", "email", "role", "ward")


class LocationField(serializers.Serializer):
    lat = serializers.FloatField()
    lng = serializers.FloatField()


class StatusHistorySerializer(serializers.ModelSerializer):
    changed_by = serializers.CharField(source="changed_by.display_name", default="", read_only=True)

    class Meta:
        model = StatusHistory
        fields = ("from_status", "to_status", "changed_by", "note", "created_at")


class CommentSerializer(serializers.ModelSerializer):
    author = serializers.CharField(source="author.display_name", default="", read_only=True)

    class Meta:
        model = Comment
        fields = ("id", "author", "body", "is_internal", "created_at")
        read_only_fields = ("id", "author", "created_at")


class ReportSerializer(serializers.ModelSerializer):
    location = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    thumbnail = serializers.SerializerMethodField()
    distance_m = serializers.SerializerMethodField()

    class Meta:
        model = Report
        fields = (
            "id", "client_uuid", "location", "accuracy_m", "address", "image", "thumbnail",
            "detection_status", "confidence", "severity", "severity_score", "detections",
            "workflow_status", "duplicate_of", "report_count", "source", "notes",
            "captured_at", "created_at", "updated_at", "distance_m",
        )
        read_only_fields = fields

    def get_location(self, obj):
        return {"lat": obj.latitude, "lng": obj.longitude}

    def _abs(self, field):
        if not field:
            return ""
        request = self.context.get("request")
        return request.build_absolute_uri(field.url) if request else field.url

    def get_image(self, obj):
        return self._abs(obj.image)

    def get_thumbnail(self, obj):
        return self._abs(obj.thumbnail)

    def get_distance_m(self, obj):
        return getattr(obj, "distance_m", None)


class ReportDetailSerializer(ReportSerializer):
    history = StatusHistorySerializer(many=True, read_only=True)
    comments = serializers.SerializerMethodField()

    class Meta(ReportSerializer.Meta):
        fields = ReportSerializer.Meta.fields + ("history", "comments")

    def get_comments(self, obj):
        qs = obj.comments.select_related("author")
        user = self.context["request"].user
        if not user.is_officer:
            qs = qs.filter(is_internal=False)
        return CommentSerializer(qs, many=True).data


class ReportCreateSerializer(serializers.Serializer):
    """Multipart upload from the Android client."""

    image = serializers.ImageField()
    latitude = serializers.FloatField(min_value=-90, max_value=90)
    longitude = serializers.FloatField(min_value=-180, max_value=180)
    accuracy_m = serializers.FloatField(required=False, allow_null=True)
    captured_at = serializers.DateTimeField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    client_uuid = serializers.UUIDField(required=False, allow_null=True)
    source = serializers.ChoiceField(
        choices=["android", "web", "live"], required=False, default="android"
    )

    def validate_image(self, image):
        from django.conf import settings

        if image.size > settings.MAX_UPLOAD_BYTES:
            raise serializers.ValidationError("Image exceeds the size limit.")
        return image


class WardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ward
        fields = ("id", "name", "code", "boundary")


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ("id", "title", "body", "report", "is_read", "created_at")
        read_only_fields = ("id", "title", "body", "report", "created_at")


class DeviceTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceToken
        fields = ("fcm_token", "platform")


class StatusUpdateSerializer(serializers.Serializer):
    to_status = serializers.CharField()
    note = serializers.CharField(required=False, allow_blank=True, default="")


class RepairProofSerializer(serializers.Serializer):
    after_image = serializers.ImageField()
    note = serializers.CharField(required=False, allow_blank=True, default="")
