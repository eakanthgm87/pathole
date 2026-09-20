# PotholeWatch

Pothole detection and repair tracking. A server-rendered Django site for citizens
and officers, a REST API for the Android app, and YOLO detection on every photo —
including a live video mode that runs the model on a camera feed in real time.

```
pothole-system/
├── weights/              # the YOLO models (best.pt, last.pt, potholenet_yolo11m.pt)
├── backend/              # Django 5: site, dashboard, API, detection
├── android/              # Kotlin + Jetpack Compose client
├── deploy/               # nginx config
├── docs/                 # model evaluation notes
└── docker-compose.yml    # postgres, redis, gunicorn, worker, nginx
```

## Run it locally

```bash
cd backend
python -m venv ../.venv && ../.venv/Scripts/activate      # Windows
# python3 -m venv ../.venv && source ../.venv/bin/activate # macOS/Linux

pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision
pip install -r requirements/base.txt

cp .env.example .env
python manage.py migrate
python manage.py register_models     # registers weights/*.pt as ModelVersion rows
python manage.py seed_demo           # optional: 40 demo reports + logins
python manage.py runserver
```

Open http://127.0.0.1:8000.

Demo logins created by `seed_demo`:

| Role | Email | Password |
|---|---|---|
| Admin | admin@pothole.dev | admin12345 |
| Officer | officer@pothole.dev | officer12345 |
| Citizen | citizen@pothole.dev | citizen12345 |

## What is where

| Path | Purpose |
|---|---|
| `reports/services.py` | **All** business logic: create, dedupe, status changes, repair proof |
| `reports/selectors.py` | **All** queries, filters and dashboard aggregates |
| `detection/engine.py` | Model loading (once per worker) and inference |
| `detection/scoring.py` | Detection status rules and the severity formula |
| `core/geoutils.py` | Distance, bounding box, point-in-polygon |
| `web/` | Template views, forms, templates, CSS/JS |
| `api/` | DRF serializers and viewsets — Android only |

The rule the codebase enforces: **views are thin**. A template view and an API
endpoint that do the same thing call the same `services.py` function, so a rule
like "rejecting needs a reason" is written once.

## Live video

`/report/live/` streams frames from the camera (or a video file you load) to
`POST /live/frame/`, draws the returned boxes on an overlay canvas, and lets you
promote any frame into a real report with `POST /live/capture/`.

Frames are paced by the client: one request in flight at a time, the next frame
grabbed only when the previous result lands, so the stream self-throttles to
whatever the server sustains. The server additionally caps each user at 8 fps.
Measured here: **~50–70 ms per frame on CPU** after warm-up (the first frame
takes ~6 s while the weights load — run `manage.py warmup_model` to pay that
cost at boot instead).

A plain POST rather than a WebSocket keeps session auth, CSRF and rate limiting
working exactly as everywhere else and needs no ASGI server. Moving to Channels
later changes only the transport, not `services.analyse_live_frame`.

## Geo: no PostGIS

The spec asked for PostGIS. This build uses the fallback the spec itself allows:
lat/lng floats, a composite index, a bounding-box prefilter and an exact
haversine pass. Reason: GeoDjango needs GDAL binaries that are painful to
install on Windows, which would leave the project unable to run at all.

Every caller goes through `Report.location` (a `Point`) and the helpers in
`core/geoutils.py` — never raw columns — so switching to PostGIS means changing
that one module and the model field, not the application.

`within_radius()` is the `ST_DWithin` stand-in and `in_bbox()` the viewport
query. Both are indexed on `(latitude, longitude)`.

## Detection: the ensemble

A single pass of `best.pt` at 640 is not good enough. Measured on 41 unseen
photos (33 containing a pothole), it found **57.6% at conf 0.25**. The two
shipped models miss *different* images, so uploads run both and merge the
boxes with NMS.

| strategy | recall @0.25 | false pos | ms/img |
|---|---|---|---|
| `best.pt` @640 (was the default) | 57.6% | 3/8 | 260 |
| `best.pt` @960 | 60.6% | 1/8 | 270 |
| both models merged | 75.8% | 3/8 | 1096 |
| **accurate profile (shipped)** | **93.9%** | 4/8 | ~2000 |

End to end through `services.create_report`, the accurate profile now detects
**31/33 = 93.9%** of real potholes, up from roughly 70%.

Two things make the extra recall safe rather than noisy:

**Consensus decides what is public.** Each merged box records how many passes
agreed on it. A box goes on the public map only when two passes agree at the
confirm threshold, or when one pass is very sure (`STRONG_CONF`). Everything
else lands in the officer review queue instead of being discarded. Result:
23 of 33 straight to public, 8 queued, and only 2 of the 8 pothole-free
images reach the public map — the other 3 sit in the queue where they belong.
(Requiring agreement as a hard *filter* was tried and rejected: it cuts
recall to 51%.)

**Severity uses union area.** Summing box areas double-counted every overlap,
and after an ensemble merge that pushed 30 of 36 reports to "high". It now
rasterises the union of the boxes. Bands are 20 / 50, calibrated to the real
distribution (median 34), not the 5 / 15 a sum-of-areas score implied.

Caveat worth knowing: frame coverage conflates pothole size with camera
distance. A small hole photographed closely scores like a large one. It ranks
reports usefully but is not an absolute measure, which is why officers can
override the band.

Profiles live in `settings.DETECTION["PROFILES"]`: `accurate` (uploads),
`balanced`, and `fast` (live video, one pass, ~110 ms). Switch with
`UPLOAD_PROFILE` / `LIVE_PROFILE`.

## Docker

```bash
cp backend/.env.example backend/.env    # set SECRET_KEY and ALLOWED_HOSTS
docker compose up --build
```

Brings up Postgres, Redis, gunicorn, a Celery worker and nginx on port 80.
`WEIGHTS_DIR=/app/weights` is set for the containers because the image has no
repo root.

## Maps

Both the website and the app use **OpenLayers** against **Esri's Gray Canvas**
basemap. Two providers were tried and rejected first, so do not switch back:

| Provider | Why not |
|---|---|
| `tile.openstreetmap.org` | Their usage policy forbids application use of the volunteer servers. They serve a 403 "Access blocked" tile, which is what produced the wall of error tiles. |
| Carto `basemaps.cartocdn.com` | The keyless tier is gone: every tile is now stamped "API KEY REQUIRED". |
| **Esri Canvas** (in use) | No key, genuinely dark, attribution only. |

Esri addresses tiles `{z}/{row}/{col}` - **y before x**, not the usual XYZ
order. Getting it backwards renders a plausible map of the wrong place.

A dark basemap means no CSS inversion: inverting raster tiles wrecked the
label colours. A `brightness(0.52) contrast(1.15)` filter seats the tiles
behind the markers, and the app uses the same value so the two match.

## Android

```bash
cd android
./gradlew assembleDebug        # -> app/build/outputs/apk/debug/app-debug.apk
```

Needs JDK 17 and the Android SDK (platform 35, build-tools 35). On this
machine they live in `AndroidTools/{jdk,sdk,gradle}` under your home
directory, and `local.properties` points `sdk.dir` at the SDK.

The map is **OpenLayers in a WebView**, not a native map SDK: the same
library, basemap and cluster styling as the website, loaded from
`assets/map/`. Kotlin drives it through `OpenLayersController`
(`setReports`, `setCenter`, `setMe`, `setPickMode`) and the page calls back
over a `@JavascriptInterface` bridge. One map implementation, so a change to
the marker language happens once instead of twice.

The debug build points at `http://10.0.2.2:8000/api/v1/` — the host machine as
seen from the emulator. Change `API_BASE` in `app/build.gradle.kts` for a
device on your LAN.

Offline capture is the part worth knowing about: a capture is written to a Room
queue **before** the upload is attempted, with a `client_uuid` that is resent on
every retry. The server keys on it, so a flaky network produces retries, never
duplicate reports. WorkManager drains the queue with exponential backoff and
drops rows the server permanently rejects.

**Push is not wired up.** The FCM dependency and `DeviceToken` registration are
present, but there is no `google-services.json` and
`notifications/services.py:send_push` logs instead of sending. In-app
notifications work fully; add Firebase credentials to switch push on.

## Motion

Animation is a layer, not a rewrite: every effect is opt-in per element and
the whole lot is disabled under `prefers-reduced-motion`.

- Scroll reveal via `IntersectionObserver`, applied by JS, so content is fully
  visible if the script never runs and nothing hides behind a failed animation
- KPI numbers count up from the server-rendered value (the DOM stays the source of truth)
- Staggered dashboard tile entrance, drawer transitions, sheen on primary buttons
- Ambient bloom drifts and follows the pointer, skipped on coarse-pointer devices
- In the app: `RevealIn` fade-and-rise on panel changes, a breathing shutter
  button, animated map camera moves

## Tests

```bash
cd backend && python manage.py test reports
```

41 tests covering the geo maths, the severity formula, report creation,
idempotency, every workflow transition rule, role permissions, the live video
endpoints and the API error shape.

## Security

- CSRF on every POST; session cookies HttpOnly and Secure in production
- JWT for the API only, with rotation and blacklisting; Android stores tokens in `EncryptedSharedPreferences`
- Uploads are size-checked, decoded to prove they are images, and re-encoded through Pillow, which strips EXIF
- Upload throttled to 20/hour per user; login rate-limited by django-axes in production
- Reporter identity never appears on public pages or in the public API
- Nominatim is proxied server-side with caching and a 1 req/s limit, per its usage policy
