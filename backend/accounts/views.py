from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.contrib.auth.views import LogoutView as DjangoLogoutView
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView

from .forms import LoginForm, ProfileForm, RegisterForm


class LoginView(DjangoLoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def get_success_url(self):
        user = self.request.user
        if user.is_officer:
            return reverse_lazy("web:dashboard_overview")
        return reverse_lazy("web:my_reports")

    def form_valid(self, form):
        messages.success(self.request, "Signed in.")
        return super().form_valid(form)


class LogoutView(DjangoLogoutView):
    next_page = reverse_lazy("web:landing")


class RegisterView(CreateView):
    template_name = "accounts/register.html"
    form_class = RegisterForm
    success_url = reverse_lazy("web:report_new")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("web:landing")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object, backend="accounts.backends.EmailBackend")
        messages.success(self.request, "Welcome aboard. Report your first pothole.")
        return response


class ProfileView(LoginRequiredMixin, View):
    template_name = "accounts/profile.html"

    def get(self, request):
        return render(
            request,
            self.template_name,
            {"form": ProfileForm(instance=request.user),
             "password_form": PasswordChangeForm(request.user)},
        )

    def post(self, request):
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect("accounts:profile")
        return render(
            request,
            self.template_name,
            {"form": form, "password_form": PasswordChangeForm(request.user)},
        )


class PasswordChangeView(LoginRequiredMixin, View):
    def post(self, request):
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Password changed.")
        else:
            for error in form.errors.values():
                messages.error(request, error.as_text())
        return redirect("accounts:profile")
