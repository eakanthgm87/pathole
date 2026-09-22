#!/usr/bin/env bash
# Render build step. Runs from the repo root with the service's env vars set.
set -o errexit

# CPU-only torch. The default wheel pulls ~3 GB of CUDA that a Render web
# service can never use, and will blow the build cache limit.
pip install --upgrade pip
pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch torchvision
pip install --no-cache-dir -r backend/requirements/base.txt

cd backend
python manage.py collectstatic --no-input
python manage.py migrate --no-input

# Register weights/*.pt as ModelVersion rows and activate the fast model.
# Non-fatal: a missing weights file should not block the whole deploy.
python manage.py register_models || true

# Create the first admin so the site is usable the moment it boots.
python manage.py ensure_admin || true
