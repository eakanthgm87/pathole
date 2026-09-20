from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from detection.models import ModelVersion

# Thresholds come from the real evaluation in docs/model-evaluation.md:
# best.pt's usable operating point is well below the 0.25 default.
KNOWN = {
    "best.pt": dict(conf_threshold=0.35, review_threshold=0.15, imgsz=960,
                    notes="YOLO11n. Runs in the ensemble at 640+TTA and 960."),
    "last.pt": dict(conf_threshold=0.35, review_threshold=0.15, imgsz=640,
                    notes="Final epoch of the same run as best.pt. Not in the ensemble."),
    "potholenet_yolo11m.pt": dict(conf_threshold=0.35, review_threshold=0.15, imgsz=768,
                                  notes="HF Vansh180/PotholeNet-V1. Only its pothole class is used; garbage is unreliable."),
    "pothole_v8m.pt": dict(conf_threshold=0.35, review_threshold=0.15, imgsz=640,
                           notes="YOLOv8m from the earlier project. Best single-pass model: 90.9% recall at 365 ms. Class is named 'Potholes'."),
}


class Command(BaseCommand):
    help = "Register the .pt files in weights/ as ModelVersion rows."

    def add_arguments(self, parser):
        parser.add_argument("--activate", default="pothole_v8m.pt")

    def handle(self, *args, **options):
        weights_dir = Path(settings.DETECTION["WEIGHTS_DIR"])
        if not weights_dir.exists():
            self.stderr.write(f"no weights directory at {weights_dir}")
            return
        for path in sorted(weights_dir.glob("*.pt")):
            defaults = dict(file_path=path.name, **KNOWN.get(path.name, {}))
            obj, created = ModelVersion.objects.get_or_create(
                name=path.stem, defaults=defaults
            )
            self.stdout.write(f"{'created' if created else 'exists '} {obj.name}")
        target = ModelVersion.objects.filter(file_path=options["activate"]).first()
        if target:
            target.is_active = True
            target.save()
            self.stdout.write(self.style.SUCCESS(f"activated {target.name}"))
