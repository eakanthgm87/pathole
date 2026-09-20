from django.contrib import admin

from .models import Ward


@admin.register(Ward)
class WardAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "centroid_lat", "centroid_lng")
    search_fields = ("code", "name")
