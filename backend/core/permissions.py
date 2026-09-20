from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsOfficer(BasePermission):
    """Officer or admin. Mirrors core.mixins.OfficerRequiredMixin."""

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (user.role in ("officer", "admin") or user.is_superuser)
        )


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user and user.is_authenticated and (user.role == "admin" or user.is_superuser)
        )


class IsOwnerOrOfficer(BasePermission):
    """Citizens reach only their own objects; officers reach everything."""

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.role in ("officer", "admin") or user.is_superuser:
            return True
        owner = getattr(obj, "reporter_id", None) or getattr(obj, "user_id", None)
        if owner == user.id:
            return True
        return request.method in SAFE_METHODS and getattr(obj, "is_public", False)
