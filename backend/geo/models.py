from django.db import models

from core.geoutils import Point, point_in_geometry


class Ward(models.Model):
    """An administrative area. Boundary is stored as GeoJSON geometry.

    Under PostGIS this becomes a MultiPolygonField; the ``contains`` method is
    the only caller-visible behaviour and would delegate to ST_Contains.
    """

    name = models.CharField(max_length=120)
    code = models.CharField(max_length=32, unique=True)
    boundary = models.JSONField(
        default=dict, blank=True, help_text="GeoJSON Polygon or MultiPolygon geometry"
    )
    centroid_lat = models.FloatField(null=True, blank=True)
    centroid_lng = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.code} - {self.name}"

    def contains(self, point: Point) -> bool:
        return point_in_geometry(point, self.boundary)

    @property
    def as_feature(self) -> dict:
        return {
            "type": "Feature",
            "geometry": self.boundary or None,
            "properties": {"id": self.id, "name": self.name, "code": self.code},
        }


def ward_for_point(point: Point):
    """First ward whose boundary contains the point, else None.

    ponytail: linear scan over wards. Fine to a few hundred wards; swap for a
    PostGIS ST_Contains index if a city ever loads thousands.
    """
    for ward in Ward.objects.exclude(boundary={}):
        if ward.contains(point):
            return ward
    return None
