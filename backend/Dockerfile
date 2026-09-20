FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

# opencv and Pillow need these at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 libgl1 libjpeg62-turbo zlib1g curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements/ /app/requirements/
# CPU torch from the dedicated index keeps the image ~3 GB instead of ~8 GB.
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch torchvision \
 && pip install --no-cache-dir -r requirements/base.txt

COPY backend/ /app/
COPY weights/ /app/weights/

WORKDIR /app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
  CMD curl -fsS http://localhost:8000/api/v1/health/ || exit 1

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120"]
