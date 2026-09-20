"""Detection status rules and the severity formula.

Kept separate from the inference engine so the policy can be tuned (and
unit-tested) without touching model plumbing.
"""
from __future__ import annotations

from django.conf import settings

from .engine import InferenceResult, thresholds, union_area

# Status values live here rather than on the Report model so that scoring can
# be unit-tested without the ORM.
INTACT = "intact"
POTHOLE_DETECTED = "pothole_detected"
NEEDS_REVIEW = "needs_review"
UNKNOWN = "unknown"

LOW, MEDIUM, HIGH = "low", "medium", "high"


def _settings():
    d = settings.DETECTION
    return (
        d.get("STRONG_CONF", 0.55),
        d.get("CONSENSUS_VOTES", 2),
    )


def classify(result: InferenceResult) -> tuple[str, float]:
    """Map an inference result onto (detection_status, confidence).

    The ensemble finds ~94% of real potholes but also fires on some bare
    tarmac, so confidence alone is not enough to publish. A box goes public
    only when independent passes agree, or when one pass is very sure:

        votes >= 2 and conf >= confirm   -> pothole_detected (public)
        conf >= strong                   -> pothole_detected (public)
        conf >= review                   -> needs_review     (officer queue)
        otherwise                        -> intact
        inference error                  -> unknown

    Everything uncertain lands in the review queue rather than being thrown
    away, so recall is preserved without polluting the public map.
    """
    if not result.ok:
        return UNKNOWN, 0.0

    confirm, review, _ = thresholds()
    strong, min_votes = _settings()

    potholes = result.potholes
    if not potholes:
        return INTACT, 0.0

    best = max(d.conf for d in potholes)
    publishable = [
        d for d in potholes
        if (d.conf >= confirm and d.votes >= min_votes) or d.conf >= strong
    ]
    if publishable:
        return POTHOLE_DETECTED, max(d.conf for d in publishable)
    if best >= review:
        return NEEDS_REVIEW, best
    return INTACT, best


def severity_score(result: InferenceResult) -> float:
    """How much of the frame the potholes actually cover, 0..100.

    Uses the *union* of the boxes: the ensemble produces overlapping
    detections of the same hole, and summing their areas pushed almost
    every report into "high".

    Only boxes at or above the review threshold count, so a weak box that is
    merely queued for review does not drive the severity band.
    """
    if not result.width or not result.height:
        return 0.0

    _confirm, review, _ = thresholds()
    boxes = [d.bbox for d in result.potholes if d.conf >= review]
    if not boxes:
        return 0.0

    coverage = union_area(boxes, result.width, result.height)
    # A road with several distinct holes is worse than one hole of the same
    # total area, but the bump is small: the ensemble inflates box counts.
    score = coverage * 100 + 1.5 * max(0, len(boxes) - 1)
    return round(max(0.0, min(100.0, score)), 2)


def severity_band(score: float) -> str:
    """Band the coverage score: low < 20 <= medium <= 50 < high.

    Calibrated against the real distribution over the evaluation set
    (median 34, p25 18, p75 52), which splits it roughly into thirds. The
    spec's 5/15 cutoffs were written for a sum-of-areas score and put 30 of
    36 detected reports into "high", which told an officer nothing.

    Caveat worth knowing: frame coverage conflates pothole size with camera
    distance. A small hole photographed closely scores like a large one. It
    ranks reports usefully, but it is not an absolute measure, which is why
    officers can override the band.
    """
    if score > settings.DETECTION.get("SEVERITY_HIGH", 50):
        return HIGH
    if score >= settings.DETECTION.get("SEVERITY_MEDIUM", 20):
        return MEDIUM
    return LOW


def score_all(result: InferenceResult) -> dict:
    """Everything the report needs from one inference pass."""
    status, confidence = classify(result)
    score = severity_score(result)
    return {
        "detection_status": status,
        "confidence": round(confidence, 4),
        "severity_score": score,
        "severity": severity_band(score),
        "detections": result.as_list(),
    }
