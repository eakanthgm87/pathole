"""Shared settings. Environment-specific modules import * from here."""
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = BASE_DIR.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("SECRET_KEY", "dev-insecure-change-me")
DEBUG = os.getenv("DEBUG", "1") == "1"
ALLOWED_HOSTS = [h for h in os.getenv("ALLOWED_HOSTS", "*").split(",") if h]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "axes",
    "core",
    "accounts",
    "geo",
    "detection",
    "reports",
    "notifications",
    "analytics",
    "web",
    "api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "web" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.site",
                "notifications.context_processors.unread_notifications",
            ],
        },
    },
]

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "accounts.backends.EmailBackend",
    "django.contrib.auth.backends.ModelBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("TIME_ZONE", "Asia/Kolkata")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "web" / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "web:landing"
LOGOUT_REDIRECT_URL = "web:landing"

FILE_UPLOAD_MAX_MEMORY_SIZE = 8 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024

# --- Domain configuration -------------------------------------------------
# Thresholds are overridable per ModelVersion row; these are the fallbacks
# used when no active ModelVersion exists.
DETECTION = {
    # Confirm/review thresholds. These are low on purpose: measured recall of
    # the shipped models is poor at the 0.6/0.3 a spec would suggest.
    "CONF_THRESHOLD": float(os.getenv("CONF_THRESHOLD", "0.35")),
    "REVIEW_THRESHOLD": float(os.getenv("REVIEW_THRESHOLD", "0.15")),
    "IMGSZ": int(os.getenv("DETECTION_IMGSZ", "640")),
    # Defaults to <repo>/weights for a local checkout; containers set
    # WEIGHTS_DIR explicitly because the image has no repo root.
    "WEIGHTS_DIR": Path(os.getenv("WEIGHTS_DIR", REPO_ROOT / "weights")),
    "DEFAULT_WEIGHTS": os.getenv("DEFAULT_WEIGHTS", "best.pt"),

    # Inference profiles. Each entry is one pass; results are NMS-merged.
    #
    # Benchmarked on 41 unseen photos (33 with a pothole), recall @0.25:
    #   best.pt @640 ....................... 57.6%   (260 ms)
    #   best.pt @960 ....................... 60.6%   (319 ms)
    #   potholenet @768 .................... 45.5%   (549 ms)
    #   pothole_v8m @640 ................... 90.9%   (365 ms)   <- default
    #   pothole_v8m @640 + best @960 ....... 93.9%   (995 ms)
    #   3-model + TTA ensemble ............. 93.9%  (1961 ms)
    #
    # pothole_v8m (YOLOv8m, from the earlier project) beats a three-model TTA
    # ensemble on its own, at a fifth of the latency, so the default is a
    # single pass. The heavy ensemble is kept as an opt-in for batch work.
    "PROFILES": {
        "fast": [
            {"weights": "pothole_v8m.pt", "imgsz": 640, "augment": False},
        ],
        "balanced": [
            {"weights": "pothole_v8m.pt", "imgsz": 640, "augment": False},
            {"weights": "best.pt", "imgsz": 960, "augment": False},
        ],
        "accurate": [
            {"weights": "pothole_v8m.pt", "imgsz": 640, "augment": False},
            {"weights": "pothole_v8m.pt", "imgsz": 960, "augment": False},
            {"weights": "best.pt", "imgsz": 960, "augment": False},
        ],
        # Nano model only: 55 ms, ~18 fps. Big models cannot hold a stream.
        "live": [
            {"weights": "best.pt", "imgsz": 480, "augment": False},
        ],
    },
    "UPLOAD_PROFILE": os.getenv("UPLOAD_PROFILE", "fast"),
    "LIVE_PROFILE": os.getenv("LIVE_PROFILE", "live"),
    # Every pass runs at this floor so weak boxes survive into the review
    # queue; CONF/REVIEW_THRESHOLD then decide what is public.
    "PASS_FLOOR": float(os.getenv("PASS_FLOOR", "0.10")),
    "MERGE_IOU": float(os.getenv("MERGE_IOU", "0.55")),
    # A box goes public when this many passes agree at CONF_THRESHOLD, or
    # when a single pass reaches STRONG_CONF on its own.
    "CONSENSUS_VOTES": int(os.getenv("CONSENSUS_VOTES", "2")),
    "STRONG_CONF": float(os.getenv("STRONG_CONF", "0.55")),
    # Severity bands over frame-coverage percent, calibrated to the measured
    # distribution (median 34). See detection/scoring.severity_band.
    "SEVERITY_MEDIUM": float(os.getenv("SEVERITY_MEDIUM", "20")),
    "SEVERITY_HIGH": float(os.getenv("SEVERITY_HIGH", "50")),
    # Live video runs smaller and looser for responsiveness.
    "LIVE_IMGSZ": int(os.getenv("LIVE_IMGSZ", "640")),
    "LIVE_CONF": float(os.getenv("LIVE_CONF", "0.25")),
}
DUPLICATE_RADIUS_M = float(os.getenv("DUPLICATE_RADIUS_M", "15"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(8 * 1024 * 1024)))
MAP_POINT_CAP = int(os.getenv("MAP_POINT_CAP", "5000"))
NOMINATIM_USER_AGENT = os.getenv("NOMINATIM_USER_AGENT", "pothole-system/2.0")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": ("rest_framework.throttling.ScopedRateThrottle",),
    "DEFAULT_THROTTLE_RATES": {"upload": "20/hour", "auth": "30/hour"},
    "EXCEPTION_HANDLER": "api.exceptions.standard_exception_handler",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Pothole Detection and Reporting API",
    "DESCRIPTION": "Mobile API for the Android client. The website is server-rendered and does not use this API.",
    "VERSION": "2.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

AXES_FAILURE_LIMIT = 8
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_LOCKOUT_PARAMETERS = ["ip_address"]
AXES_RESET_ON_SUCCESS = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "std": {"format": "{levelname} {asctime} {name} {message}", "style": "{"}
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "std"}},
    "root": {"handlers": ["console"], "level": os.getenv("LOG_LEVEL", "INFO")},
}

CELERY_BROKER_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_TASK_ALWAYS_EAGER = os.getenv("CELERY_EAGER", "1") == "1"
