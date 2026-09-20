from django.core.management.base import BaseCommand

from detection.engine import resolve_weights, warmup


class Command(BaseCommand):
    help = "Load the active YOLO weights and run one inference to warm the cache."

    def handle(self, *args, **options):
        path = resolve_weights()
        self.stdout.write(f"weights: {path}")
        if warmup():
            self.stdout.write(self.style.SUCCESS("model warm"))
        else:
            self.stderr.write("warmup failed - see log")
