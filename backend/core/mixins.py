from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin


class RoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Gate a template view on the user's role.

    Set ``roles`` to a tuple of role strings. Admins always pass, so views
    never need to spell out ``("officer", "admin")`` unless they want to.
    """

    roles: tuple[str, ...] = ()

    def test_func(self) -> bool:
        user = self.request.user
        if not user.is_authenticated:
            return False
        if user.role == "admin" or user.is_superuser:
            return True
        return user.role in self.roles


class OfficerRequiredMixin(RoleRequiredMixin):
    roles = ("officer", "admin")


class AdminRequiredMixin(RoleRequiredMixin):
    roles = ("admin",)
