import logging

from .models import DeviceToken, Notification

log = logging.getLogger(__name__)


def notify(user, *, title: str, body: str = "", report=None) -> Notification:
    """Write the in-app notification, then attempt push.

    The database row is the source of truth; push is best-effort so an FCM
    outage never loses a status update.
    """
    note = Notification.objects.create(user=user, title=title, body=body, report=report)
    try:
        send_push(user, title, body, report)
    except Exception as exc:
        log.warning("push failed for user %s: %s", user.pk, exc)
    return note


def send_push(user, title: str, body: str, report=None) -> int:
    """Deliver to the user's registered devices.

    ponytail: no-op until FCM credentials are configured (Phase 5). Tokens are
    already collected so switching this on is a single function body.
    """
    tokens = list(DeviceToken.objects.filter(user=user).values_list("fcm_token", flat=True))
    if not tokens:
        return 0
    log.info("FCM not configured; would push %r to %d device(s)", title, len(tokens))
    return 0


def mark_all_read(user) -> int:
    return Notification.objects.filter(user=user, is_read=False).update(is_read=True)


def unread_count(user) -> int:
    if not user.is_authenticated:
        return 0
    return Notification.objects.filter(user=user, is_read=False).count()
