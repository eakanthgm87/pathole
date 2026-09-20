from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

User = get_user_model()


class StyledMixin:
    """Attach the site's input class to every widget, so templates stay clean."""

    default_class = "field-input"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, (forms.CheckboxInput, forms.RadioSelect)):
                continue
            existing = widget.attrs.get("class", "")
            widget.attrs["class"] = f"{existing} {self.default_class}".strip()
            if not widget.attrs.get("placeholder") and field.label:
                widget.attrs["placeholder"] = str(field.label)


class RegisterForm(StyledMixin, UserCreationForm):
    name = forms.CharField(max_length=120, required=True, label="Full name")
    email = forms.EmailField(required=True)
    phone = forms.CharField(max_length=20, required=False)

    class Meta:
        model = User
        fields = ("name", "email", "phone")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.username = user.email
        user.role = User.Role.CITIZEN
        if commit:
            user.save()
        return user


class LoginForm(StyledMixin, AuthenticationForm):
    username = forms.EmailField(label="Email")


class ProfileForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ("name", "phone")
