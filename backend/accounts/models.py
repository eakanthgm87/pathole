from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create(self, email, password, **extra):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, username=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("role", User.Role.CITIZEN)
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("role", User.Role.ADMIN)
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        return self._create(email, password, **extra)


class User(AbstractUser):
    class Role(models.TextChoices):
        CITIZEN = "citizen", "Citizen"
        OFFICER = "officer", "Officer"
        ADMIN = "admin", "Admin"

    email = models.EmailField(unique=True)
    name = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.CITIZEN)
    ward = models.ForeignKey(
        "geo.Ward", null=True, blank=True, on_delete=models.SET_NULL, related_name="officers"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        indexes = [models.Index(fields=["role"])]

    def __str__(self):
        return self.email

    @property
    def display_name(self) -> str:
        return self.name or self.email.split("@")[0]

    @property
    def is_officer(self) -> bool:
        return self.role in ("officer", "admin") or self.is_superuser

    @property
    def is_admin(self) -> bool:
        return self.role == "admin" or self.is_superuser

    @property
    def initials(self) -> str:
        parts = (self.name or self.email).replace(".", " ").split()
        return "".join(p[0] for p in parts[:2]).upper() or "U"
