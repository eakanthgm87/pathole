"""Live video detection.

Transport choice: the browser grabs frames from a <video> element, encodes
each to JPEG on a canvas, and POSTs it here. The server answers with boxes in
source-pixel coordinates and the client paints them on an overlay canvas.

Why not WebSockets: a plain POST keeps session auth, CSRF and rate limiting
working exactly as they do everywhere else, needs no ASGI server or Channels,
and at the 3-6 fps a CPU model sustains the per-request overhead is noise.
Swapping to Channels later only changes the transport, not `analyse_live_frame`.
"""
from __future__ import annotations

import time

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from reports import services

# Per-user frame budget. A browser that ignores its own throttle must not be
# able to saturate the worker pool.
MAX_FPS = 8
MAX_FRAME_BYTES = 2 * 1024 * 1024


@login_required
@require_POST
def analyse_frame(request):
    """Analyse one frame. Stateless: nothing is written to the database."""
    frame = request.FILES.get("frame")
    if frame is None:
        return JsonResponse(
            {"ok": False, "error": "No frame supplied", "detections": []}, status=400
        )
    if frame.size > MAX_FRAME_BYTES:
        return JsonResponse(
            {"ok": False, "error": "Frame too large", "detections": []}, status=413
        )

    key = f"live:rate:{request.user.pk}"
    last = cache.get(key)
    now = time.monotonic()
    if last and (now - last) < (1.0 / MAX_FPS):
        # Not an error: tell the client to back off and drop the frame.
        return JsonResponse({"ok": True, "skipped": True, "detections": []}, status=200)
    cache.set(key, now, timeout=5)

    started = time.perf_counter()
    payload = services.analyse_live_frame(frame.read())
    payload["ms"] = round((time.perf_counter() - started) * 1000)
    return JsonResponse(payload)


@login_required
@require_POST
def capture_from_live(request):
    """Promote the current live frame into a real, persisted report.

    Lets someone driving with the live view open keep a detection they care
    about without breaking out of the stream.
    """
    frame = request.FILES.get("frame")
    if frame is None:
        return JsonResponse({"ok": False, "error": "No frame supplied"}, status=400)

    try:
        lat = float(request.POST["latitude"])
        lng = float(request.POST["longitude"])
    except (KeyError, TypeError, ValueError):
        return JsonResponse(
            {"ok": False, "error": "A location is required to save a capture."}, status=400
        )

    accuracy = request.POST.get("accuracy_m")
    try:
        report = services.create_report(
            image_file=frame,
            latitude=lat,
            longitude=lng,
            accuracy_m=float(accuracy) if accuracy else None,
            notes=request.POST.get("notes", "Captured from live video"),
            reporter=request.user,
            source="live",
        )
    except Exception as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    return JsonResponse(
        {
            "ok": True,
            "id": str(report.id),
            "url": report.get_absolute_url(),
            "detection_status": report.detection_status,
            "severity": report.severity,
            "confidence": round(report.confidence, 3),
        }
    )
