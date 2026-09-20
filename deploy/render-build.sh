#!/usr/bin/env bash
# Render build step. Runs from the repo root.
set -o errexit

# CPU-only torch: the default wheel drags in ~3 GB of CUDA that a Render web
# service can never use.
pip install --upgrade pip
pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch torchvision
pip install --no-cache-dir -r backend/requirements/base.txt

cd backend
python manage.py collectstatic --no-input
python manage.py migrate --no-input
# Register weights/*.pt as ModelVersion rows and activate the fast model.
python manage.py register_models || true
