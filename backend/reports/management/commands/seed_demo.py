"""Populate a demo dataset so the dashboard and map have something to show."""
import io
import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand
from django.utils import timezone
from PIL import Image, ImageDraw

from geo.models import Ward
from reports import services
from reports.models import Report, WorkflowStatus

User = get_user_model()

# A rough box over central Bengaluru.
LAT_RANGE = (12.90, 13.05)
LNG_RANGE = (77.53, 77.68)

STREETS = [
    "100 Feet Road, Indiranagar", "CMH Road, Halasuru", "Old Airport Road",
    "Bannerghatta Main Road", "Sarjapur Road", "Outer Ring Road, Marathahalli",
    "Hosur Road, Koramangala", "Bellandur Gate", "Whitefield Main Road",
    "Jayanagar 4th Block", "Malleshwaram 8th Cross", "Residency Road",
]

WARDS = [
    ("W-101", "Indiranagar"), ("W-102", "Koramangala"), ("W-103", "Whitefield"),
    ("W-104", "Jayanagar"), ("W-105", "Malleshwaram"),
]


def synthetic_road(seed: int):
    """A grey frame with a dark blob. Not a real pothole: the detector will
    usually score these 'intact', which is honest demo data rather than fake
    confidence numbers."""
    rng = random.Random(seed)
    img = Image.new("RGB", (640, 480), (96 + rng.randint(-12, 12),) * 3)
    draw = ImageDraw.Draw(img)
    for _ in range(220):
        x, y = rng.randint(0, 640), rng.randint(0, 480)
        g = rng.randint(70, 130)
        draw.ellipse([x, y, x + rng.randint(1, 4), y + rng.randint(1, 4)], fill=(g, g, g))
    cx, cy = rng.randint(180, 460), rng.randint(160, 340)
    rx, ry = rng.randint(50, 130), rng.randint(34, 90)
    draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=(38, 34, 32))
    draw.ellipse([cx - rx + 9, cy - ry + 7, cx + rx - 9, cy + ry - 7], fill=(24, 21, 20))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    buf.seek(0)
    return SimpleUploadedFile(f"seed{seed}.jpg", buf.read(), content_type="image/jpeg")


class Command(BaseCommand):
    help = "Create demo users, wards and reports."

    def add_arguments(self, parser):
        parser.add_argument("--reports", type=int, default=40)
        parser.add_argument("--reset", action="store_true", help="Delete existing reports first")

    def handle(self, *args, **options):
        if options["reset"]:
            Report.objects.all().delete()
            self.stdout.write("cleared existing reports")

        admin, created = User.objects.get_or_create(
            email="admin@pothole.dev",
            defaults={"username": "admin@pothole.dev", "name": "Admin",
                      "role": "admin", "is_staff": True, "is_superuser": True},
        )
        if created:
            admin.set_password("admin12345")
            admin.save()
            self.stdout.write(self.style.SUCCESS("admin@pothole.dev / admin12345"))

        officer, created = User.objects.get_or_create(
            email="officer@pothole.dev",
            defaults={"username": "officer@pothole.dev", "name": "Officer Rao", "role": "officer"},
        )
        if created:
            officer.set_password("officer12345")
            officer.save()
            self.stdout.write(self.style.SUCCESS("officer@pothole.dev / officer12345"))

        citizen, created = User.objects.get_or_create(
            email="citizen@pothole.dev",
            defaults={"username": "citizen@pothole.dev", "name": "Asha K", "role": "citizen"},
        )
        if created:
            citizen.set_password("citizen12345")
            citizen.save()
            self.stdout.write(self.style.SUCCESS("citizen@pothole.dev / citizen12345"))

        for code, name in WARDS:
            Ward.objects.get_or_create(code=code, defaults={"name": name})

        rng = random.Random(42)
        wards = list(Ward.objects.all())
        made = 0
        for i in range(options["reports"]):
            lat = rng.uniform(*LAT_RANGE)
            lng = rng.uniform(*LNG_RANGE)
            report = services.create_report(
                image_file=synthetic_road(i),
                latitude=lat,
                longitude=lng,
                accuracy_m=rng.uniform(4, 30),
                notes=rng.choice(["", "Near the bus stop", "Deepens after rain", "Two-wheelers swerving"]),
                reporter=rng.choice([citizen, officer, admin]),
                source=rng.choice(["web", "android", "live"]),
                resolve_address=False,
            )

            # Backdate and fill in the fields the detector cannot infer, so
            # charts and KPIs have a realistic spread.
            created_at = timezone.now() - timedelta(days=rng.randint(0, 29), hours=rng.randint(0, 23))
            severity = rng.choices(["low", "medium", "high"], weights=[5, 3, 2])[0]
            Report.objects.filter(pk=report.pk).update(
                created_at=created_at,
                address=rng.choice(STREETS) + ", Bengaluru",
                ward=rng.choice(wards) if wards else None,
                detection_status="pothole_detected",
                confidence=round(rng.uniform(0.45, 0.94), 3),
                severity=severity,
                severity_score={"low": rng.uniform(1, 4), "medium": rng.uniform(5, 15),
                                "high": rng.uniform(16, 60)}[severity],
            )
            report.refresh_from_db()

            # Walk a share of them through the workflow.
            roll = rng.random()
            try:
                if roll > 0.25:
                    services.verify(report, actor=officer, note="Verified from patrol")
                if roll > 0.55:
                    services.assign(report, officer, actor=admin)
                if roll > 0.75:
                    services.change_status(report, WorkflowStatus.IN_PROGRESS, actor=officer)
                if roll > 0.88:
                    services.mark_fixed(
                        report, actor=officer, after_image=synthetic_road(1000 + i),
                        note="Patched and compacted",
                    )
            except Exception as exc:
                self.stderr.write(f"workflow step skipped: {exc}")
            made += 1

        self.stdout.write(self.style.SUCCESS(f"seeded {made} reports"))
