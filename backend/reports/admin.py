from django.contrib import admin
from django.utils.html import format_html

from .models import Assignment, Comment, RepairProof, Report, StatusHistory


class StatusHistoryInline(admin.TabularInline):
    model = StatusHistory
    extra = 0
    readonly_fields = ("from_status", "to_status", "changed_by", "note", "created_at")


class CommentInline(admin.TabularInline):
    model = Comment
    extra = 0


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("short_id", "thumb", "detection_status", "confidence", "severity",
                    "workflow_status", "ward", "report_count", "created_at")
    list_filter = ("detection_status", "workflow_status", "severity", "source", "ward")
    search_fields = ("id", "address", "notes", "reporter__email")
    readonly_fields = ("id", "client_uuid", "created_at", "updated_at", "preview")
    inlines = [StatusHistoryInline, CommentInline]
    date_hierarchy = "created_at"

    @admin.display(description="ID")
    def short_id(self, obj):
        return str(obj.id)[:8]

    @admin.display(description="Image")
    def thumb(self, obj):
        if obj.thumbnail:
            return format_html('<img src="{}" style="height:44px;border-radius:6px">', obj.thumbnail.url)
        return "-"

    @admin.display(description="Preview")
    def preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-width:520px">', obj.image.url)
        return "-"


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("report", "officer", "assigned_by", "due_date", "is_active", "created_at")
    list_filter = ("is_active",)


@admin.register(RepairProof)
class RepairProofAdmin(admin.ModelAdmin):
    list_display = ("report", "created_by", "created_at")


@admin.register(StatusHistory)
class StatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("report", "from_status", "to_status", "changed_by", "created_at")
    list_filter = ("to_status",)
