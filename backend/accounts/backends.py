from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailBackend(ModelBackend):
    """Authenticate by email, case-insensitively.

    Django's default backend matches USERNAME_FIELD exactly; users type mixed
    case, so normalise here rather than at every call site.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        email = (username or kwargs.get("email") or "").strip().lower()
        if not email or password is None:
            return None
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            # Equalise timing against the user-exists path.
            User().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
