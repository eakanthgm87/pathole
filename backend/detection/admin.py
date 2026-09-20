from django.contrib import admin

from .models import ModelVersion


@admin.register(ModelVersion)
class ModelVersionAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "conf_threshold", "review_threshold", "imgsz", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "file_path")
