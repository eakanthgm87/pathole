from django.conf import settings


def site(request):
    """Values every template needs."""
    return {
        "SITE_NAME": "PotholeWatch",
        "SITE_TAGLINE": "See it. Snap it. Fixed.",
        "DEBUG": settings.DEBUG,
    }
