"""YOLO inference.

Models are loaded once per worker process and cached. Loading costs seconds
and a few hundred MB, so doing it per request would be the worst thing we
could do to throughput.

Accuracy strategy
-----------------
A single pass of `best.pt` at 640 finds only about 58% of real potholes at a
0.25 threshold (measured on 41 unseen photos; see docs/model-evaluation.md).
The two shipped models fail on *different* images, so uploads run an
**ensemble**: every model in the accurate profile runs, and the boxes are
merged with NMS. Measured on the same set, that lifts recall to ~94%.

Live video keeps a single fast pass, because it has a frame budget.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from django.conf import settings

log = logging.getLogger(__name__)

_MODELS: dict[str, object] = {}
_LOCK = threading.Lock()
# ponytail: one global load lock. Contention only happens on the first request
# after boot; make it per-path if multi-model serving ever gets hot.


@dataclass
class Detection:
    label: str
    conf: float
    bbox: list[int]  # [x1, y1, x2, y2] in pixels
    # How many independent passes found this box. Two models agreeing is a
    # far stronger signal than one model being confident, so this drives the
    # public/review split rather than confidence alone.
    votes: int = 1

    def as_dict(self) -> dict:
        return {
            "class": self.label,
            "conf": round(self.conf, 4),
            "bbox": self.bbox,
            "votes": self.votes,
        }


@dataclass
class InferenceResult:
    detections: list[Detection] = field(default_factory=list)
    width: int = 0
    height: int = 0
    error: str = ""
    model_name: str = ""

    @property
    def ok(self) -> bool:
        return not self.error

    @property
    def best_confidence(self) -> float:
        return max((d.conf for d in self.detections), default=0.0)

    @property
    def potholes(self) -> list[Detection]:
        return [d for d in self.detections if d.label == "pothole"]

    def as_list(self) -> list[dict]:
        return [d.as_dict() for d in self.detections]


# --- geometry -------------------------------------------------------------


def _iou(a: list[int], b: list[int]) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter == 0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def merge_detections(dets: list[Detection], iou_threshold: float = 0.55) -> list[Detection]:
    """Greedy NMS across passes, counting agreement.

    Two models finding the same hole must not become two reports. The
    surviving box keeps the highest confidence and records how many passes
    agreed with it, which `scoring` uses to decide public vs review.
    """
    kept: list[Detection] = []
    for det in sorted(dets, key=lambda d: d.conf, reverse=True):
        for other in kept:
            if other.label == det.label and _iou(det.bbox, other.bbox) >= iou_threshold:
                other.votes += 1
                break
        else:
            kept.append(
                Detection(label=det.label, conf=det.conf, bbox=list(det.bbox), votes=1)
            )
    return kept


def union_area(boxes: list[list[int]], width: int, height: int) -> float:
    """Fraction of the image covered by the union of `boxes`.

    Summing box areas double-counts every overlap, which after an ensemble
    merge inflated nearly every report to "high". Rasterising to a coarse
    grid is exact enough for a severity band and costs nothing.
    """
    if not boxes or width <= 0 or height <= 0:
        return 0.0
    grid = 128
    mask = np.zeros((grid, grid), dtype=bool)
    for x1, y1, x2, y2 in boxes:
        gx1 = max(0, min(grid - 1, int(x1 / width * grid)))
        gx2 = max(0, min(grid, int(round(x2 / width * grid))))
        gy1 = max(0, min(grid - 1, int(y1 / height * grid)))
        gy2 = max(0, min(grid, int(round(y2 / height * grid))))
        if gx2 > gx1 and gy2 > gy1:
            mask[gy1:gy2, gx1:gx2] = True
    return float(mask.sum()) / (grid * grid)


# --- model handling -------------------------------------------------------


def active_version():
    """The active ModelVersion row, or None to fall back to settings."""
    from detection.models import ModelVersion

    return ModelVersion.objects.filter(is_active=True).first()


def resolve_weights() -> Path:
    version = active_version()
    if version and version.resolved_path.exists():
        return version.resolved_path
    return settings.DETECTION["WEIGHTS_DIR"] / settings.DETECTION["DEFAULT_WEIGHTS"]


def thresholds() -> tuple[float, float, int]:
    """(confirm, review, imgsz) from the active version, else settings."""
    version = active_version()
    if version:
        return version.conf_threshold, version.review_threshold, version.imgsz
    d = settings.DETECTION
    return d["CONF_THRESHOLD"], d["REVIEW_THRESHOLD"], d["IMGSZ"]


def get_model(path: Path | None = None):
    """Load and memoise a YOLO model keyed by weights path."""
    path = Path(path or resolve_weights())
    key = str(path)
    model = _MODELS.get(key)
    if model is not None:
        return model
    with _LOCK:
        model = _MODELS.get(key)
        if model is None:
            if not path.exists():
                raise FileNotFoundError(f"Weights not found: {path}")
            from ultralytics import YOLO

            log.info("loading YOLO weights %s", path)
            model = YOLO(str(path))
            _MODELS[key] = model
    return model


def is_pothole_class(name: str) -> bool:
    """Do the model's own words for this class mean "pothole"?

    The three shipped models disagree: `best.pt` says "pothole",
    `pothole_v8m.pt` says "Potholes", `potholenet_yolo11m.pt` says "pothole"
    plus "road_damage" and "garbage". An exact `== "pothole"` test silently
    discarded every detection from the v8m model, which looked like the
    model simply not working.
    """
    return "pothole" in name.strip().lower()


def _pass(frame, weights: Path, imgsz: int, conf: float, augment: bool) -> list[Detection]:
    """One model over one frame. Returns pothole detections only."""
    model = get_model(weights)
    result = model.predict(frame, imgsz=imgsz, conf=conf, augment=augment, verbose=False)[0]
    names = result.names
    out = []
    for box in result.boxes:
        raw = str(names[int(box.cls)])
        # potholenet also emits road_damage and garbage. Its garbage class
        # labels people and animals as rubbish (measured), so it is dropped.
        if not is_pothole_class(raw):
            continue
        x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
        # Normalise the label so downstream code and the UI see one word
        # regardless of which model found it.
        out.append(Detection(label="pothole", conf=float(box.conf), bbox=[x1, y1, x2, y2]))
    return out


def _decode(image_bytes: bytes):
    import cv2

    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def _profile(name: str) -> list[dict]:
    """Resolve a named profile from settings into runnable pass specs."""
    weights_dir = Path(settings.DETECTION["WEIGHTS_DIR"])
    specs = []
    for spec in settings.DETECTION["PROFILES"].get(name, []):
        path = weights_dir / spec["weights"]
        if not path.exists():
            log.warning("profile %s: missing weights %s, skipping", name, path)
            continue
        specs.append({**spec, "path": path})
    if not specs:
        # Never leave the caller with nothing to run.
        specs = [{"path": resolve_weights(), "imgsz": 640, "augment": False}]
    return specs


def detect_image(image_bytes: bytes, profile: str | None = None) -> InferenceResult:
    """Run the accurate profile over an uploaded photo.

    Every pass runs at a low floor so borderline boxes survive into the
    officer review queue; the scoring rules decide what counts as confirmed.
    """
    frame = _decode(image_bytes)
    if frame is None:
        return InferenceResult(error="Image could not be decoded")

    profile = profile or settings.DETECTION["UPLOAD_PROFILE"]
    specs = _profile(profile)
    floor = settings.DETECTION["PASS_FLOOR"]

    found: list[Detection] = []
    used: list[str] = []
    errors: list[str] = []
    for spec in specs:
        try:
            found += _pass(frame, spec["path"], spec["imgsz"], floor, spec.get("augment", False))
            used.append(f"{spec['path'].stem}@{spec['imgsz']}{'+tta' if spec.get('augment') else ''}")
        except Exception as exc:
            # One model failing must not lose the other's detections.
            log.exception("inference pass failed for %s", spec["path"])
            errors.append(str(exc))

    if not used:
        return InferenceResult(error="; ".join(errors) or "All inference passes failed")

    h, w = frame.shape[:2]
    merged = merge_detections(found, settings.DETECTION["MERGE_IOU"])
    merged.sort(key=lambda d: d.conf, reverse=True)
    return InferenceResult(
        detections=merged, width=w, height=h, model_name=" + ".join(used)
    )


def detect_frame(frame_bytes: bytes) -> InferenceResult:
    """Single fast pass for the live video stream."""
    frame = _decode(frame_bytes)
    if frame is None:
        return InferenceResult(error="Frame could not be decoded")

    d = settings.DETECTION
    specs = _profile(d["LIVE_PROFILE"])[:1]  # live gets exactly one pass
    spec = specs[0]
    try:
        dets = _pass(frame, spec["path"], d["LIVE_IMGSZ"], d["LIVE_CONF"], False)
    except Exception as exc:
        log.exception("live inference failed")
        return InferenceResult(error=str(exc))

    h, w = frame.shape[:2]
    dets.sort(key=lambda x: x.conf, reverse=True)
    return InferenceResult(detections=dets, width=w, height=h, model_name=spec["path"].stem)


def warmup() -> bool:
    """Load every model the profiles reference and run one tiny inference, so
    the first real request is not paying for several cold loads."""
    blank = np.zeros((64, 64, 3), dtype=np.uint8)
    ok = True
    seen = set()
    for name in set(settings.DETECTION["PROFILES"]):
        for spec in _profile(name):
            if spec["path"] in seen:
                continue
            seen.add(spec["path"])
            try:
                get_model(spec["path"]).predict(blank, imgsz=64, verbose=False)
                log.info("warmed %s", spec["path"].name)
            except Exception as exc:
                log.warning("warmup failed for %s: %s", spec["path"], exc)
                ok = False
    return ok
