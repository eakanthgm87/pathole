import hashlib
import io

from PIL import Image, ImageOps

THUMB_SIZE = (480, 480)


def strip_exif_and_normalise(django_file):
    """Return (clean_jpeg_bytes, thumbnail_bytes, (width, height)).

    Re-encoding through Pillow drops all EXIF, which is the privacy
    requirement, and ``exif_transpose`` first so the visual orientation
    survives the strip.
    """
    django_file.seek(0)
    img = Image.open(django_file)
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    elif img.mode == "L":
        img = img.convert("RGB")

    full = io.BytesIO()
    img.save(full, format="JPEG", quality=88, optimize=True)

    thumb = img.copy()
    thumb.thumbnail(THUMB_SIZE, Image.LANCZOS)
    tbuf = io.BytesIO()
    thumb.save(tbuf, format="JPEG", quality=80, optimize=True)

    return full.getvalue(), tbuf.getvalue(), img.size


def read_exif_gps(django_file):
    """Best-effort GPS from EXIF. Returns (lat, lng) or None."""
    try:
        django_file.seek(0)
        img = Image.open(django_file)
        exif = img.getexif()
        if not exif:
            return None
        gps = exif.get_ifd(0x8825)
        if not gps:
            return None

        def dms(vals):
            d, m, s = (float(v) for v in vals)
            return d + m / 60 + s / 3600

        lat = dms(gps[2])
        lng = dms(gps[4])
        if gps.get(1) == "S":
            lat = -lat
        if gps.get(3) == "W":
            lng = -lng
        return lat, lng
    except Exception:
        return None
    finally:
        try:
            django_file.seek(0)
        except Exception:
            pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
