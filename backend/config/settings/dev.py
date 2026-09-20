import os

from .base import *  # noqa: F401,F403
from .base import BASE_DIR

DEBUG = True
ALLOWED_HOSTS = ["*"]

# Defaults to SQLite so the project runs with no external services.
# Set DB_ENGINE=postgres (after `docker compose up db`) for prod parity.
if os.getenv("DB_ENGINE", "sqlite") == "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME", "pothole"),
            "USER": os.getenv("DB_USER", "pothole"),
            "PASSWORD": os.getenv("DB_PASSWORD", "pothole"),
            "HOST": os.getenv("DB_HOST", "localhost"),
            "PORT": os.getenv("DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AXES_ENABLED = os.getenv("AXES_ENABLED", "0") == "1"
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
