"""Create the first admin account on a fresh deploy.

A one-click deploy that lands on a login screen with no account is not a
deploy, it is a puzzle. This runs on every build and is idempotent: it only
ever creates the account once, and never rewrites an existing password.
"""
import os
import secrets

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create the initial admin user from environment variables, once."

    def handle(self, *args, **options):
        User = get_user_model()
        email = (os.getenv("ADMIN_EMAIL") or "").strip().lower()
        if not email:
            self.stdout.write("ADMIN_EMAIL not set; skipping admin bootstrap.")
            return

        if User.objects.filter(email__iexact=email).exists():
            self.stdout.write(f"admin {email} already exists; leaving it alone.")
            return

        password = os.getenv("ADMIN_PASSWORD")
        generated = False
        if not password:
            # Better a random password printed once in the build log than a
            # predictable default sitting on the public internet.
            password = secrets.token_urlsafe(14)
            generated = True

        User.objects.create_superuser(
            email=email,
            password=password,
            name=os.getenv("ADMIN_NAME", "Administrator"),
        )
        self.stdout.write(self.style.SUCCESS(f"created admin {email}"))
        if generated:
            self.stdout.write(
                self.style.WARNING(
                    f"generated password: {password}\n"
                    "Copy it now: it is not stored anywhere and will not be shown again."
                )
            )
