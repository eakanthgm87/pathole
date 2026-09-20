/* Report upload page: geolocation, EXIF fallback, webcam capture, preview. */
import { $, jsonData, drawDetections } from './core.js';

function setLocation(lat, lng, accuracy, source) {
  const latIn = $('#id_latitude');
  const lngIn = $('#id_longitude');
  const accIn = $('#id_accuracy_m');
  if (latIn) latIn.value = lat.toFixed(6);
  if (lngIn) lngIn.value = lng.toFixed(6);
  if (accIn && accuracy) accIn.value = Math.round(accuracy);

  const status = $('[data-loc-status]');
  if (status) {
    status.textContent =
      `${lat.toFixed(5)}, ${lng.toFixed(5)}` +
      (accuracy ? ` (±${Math.round(accuracy)}m)` : '') +
      ` · ${source}`;
    status.classList.remove('faint');
  }
  const map = $('[data-map]');
  if (map) {
    map.dispatchEvent(new CustomEvent('location:request', { detail: { lat, lng } }));
  }
  const submit = $('[data-submit]');
  if (submit) submit.disabled = false;
}

function autoLocate() {
  const status = $('[data-loc-status]');
  if (!navigator.geolocation) {
    if (status) status.textContent = 'Geolocation unavailable. Tap the map to place a pin.';
    return;
  }
  if (status) status.textContent = 'Finding your location…';
  navigator.geolocation.getCurrentPosition(
    (pos) => setLocation(pos.coords.latitude, pos.coords.longitude, pos.coords.accuracy, 'GPS'),
    () => {
      if (status) {
        status.textContent =
          'Location blocked. Tap the map to place a pin, or upload a photo that has GPS data.';
      }
    },
    { enableHighAccuracy: true, timeout: 12000 }
  );
}

/* Minimal EXIF GPS reader. Walks only the GPS IFD, which is all we need and
   avoids pulling in a library for one tag group. */
function exifGps(arrayBuffer) {
  const view = new DataView(arrayBuffer);
  if (view.byteLength < 4 || view.getUint16(0) !== 0xffd8) return null;

  let offset = 2;
  while (offset < view.byteLength - 3) {
    if (view.getUint8(offset) !== 0xff) break;
    const marker = view.getUint8(offset + 1);
    const size = view.getUint16(offset + 2);
    if (marker === 0xe1) {
      const start = offset + 4;
      if (view.getUint32(start) !== 0x45786966) return null;
      const tiff = start + 6;
      const little = view.getUint16(tiff) === 0x4949;
      const get16 = (o) => view.getUint16(o, little);
      const get32 = (o) => view.getUint32(o, little);

      const ifd0 = tiff + get32(tiff + 4);
      const entries = get16(ifd0);
      let gpsOffset = 0;
      for (let i = 0; i < entries; i += 1) {
        const e = ifd0 + 2 + i * 12;
        if (get16(e) === 0x8825) gpsOffset = tiff + get32(e + 8);
      }
      if (!gpsOffset) return null;

      const gpsEntries = get16(gpsOffset);
      const tags = {};
      for (let i = 0; i < gpsEntries; i += 1) {
        const e = gpsOffset + 2 + i * 12;
        const tag = get16(e);
        const type = get16(e + 2);
        const count = get32(e + 4);
        let valueOffset = e + 8;
        const byteLen = (type === 5 ? 8 : type === 2 ? 1 : 4) * count;
        if (byteLen > 4) valueOffset = tiff + get32(e + 8);

        if (type === 2) {
          tags[tag] = String.fromCharCode(view.getUint8(valueOffset));
        } else if (type === 5) {
          const parts = [];
          for (let j = 0; j < count; j += 1) {
            const num = get32(valueOffset + j * 8);
            const den = get32(valueOffset + j * 8 + 4);
            parts.push(den ? num / den : 0);
          }
          tags[tag] = parts;
        }
      }
      if (!tags[2] || !tags[4]) return null;
      const dms = (p) => p[0] + p[1] / 60 + p[2] / 3600;
      let lat = dms(tags[2]);
      let lng = dms(tags[4]);
      if (tags[1] === 'S') lat = -lat;
      if (tags[3] === 'W') lng = -lng;
      return { lat, lng };
    }
    offset += 2 + size;
  }
  return null;
}

function handleFile(file) {
  const preview = $('[data-preview]');
  if (preview) {
    preview.src = URL.createObjectURL(file);
    preview.hidden = false;
    const ph = $('[data-preview-placeholder]');
    if (ph) ph.hidden = true;
  }

  const latIn = $('#id_latitude');
  if (latIn && latIn.value) return; // already located; do not override

  file.arrayBuffer().then((buf) => {
    try {
      const gps = exifGps(buf);
      if (gps) setLocation(gps.lat, gps.lng, null, 'photo EXIF');
    } catch {
      /* EXIF is a bonus, never a requirement */
    }
  });
}

function initWebcam() {
  const btn = $('[data-webcam-start]');
  const shot = $('[data-webcam-shoot]');
  const video = $('[data-webcam-video]');
  const wrap = $('[data-webcam-wrap]');
  const fileInput = $('#id_image');
  if (!btn || !video) return;

  let stream = null;

  btn.addEventListener('click', async () => {
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' },
        audio: false,
      });
    } catch {
      alert('Could not open the camera.');
      return;
    }
    video.srcObject = stream;
    await video.play();
    if (wrap) wrap.hidden = false;
    btn.hidden = true;
    if (shot) shot.hidden = false;
  });

  if (!shot) return;
  shot.addEventListener('click', () => {
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);
    canvas.toBlob(
      (blob) => {
        // Write the capture into the real file input, so the plain Django
        // form submits it with no special server-side handling.
        const dt = new DataTransfer();
        dt.items.add(new File([blob], 'capture.jpg', { type: 'image/jpeg' }));
        if (fileInput) {
          fileInput.files = dt.files;
          handleFile(dt.files[0]);
        }
        if (stream) stream.getTracks().forEach((t) => t.stop());
        if (wrap) wrap.hidden = true;
        shot.hidden = true;
        btn.hidden = false;
      },
      'image/jpeg',
      0.92
    );
  });
}

document.addEventListener('DOMContentLoaded', () => {
  const fileInput = $('#id_image');
  if (fileInput) {
    fileInput.addEventListener('change', (e) => {
      const f = e.target.files && e.target.files[0];
      if (f) handleFile(f);
    });
  }

  const locBtn = $('[data-locate-me]');
  if (locBtn) locBtn.addEventListener('click', autoLocate);

  const map = $('[data-map]');
  if (map) {
    map.addEventListener('location:set', (e) => {
      setLocation(e.detail.lat, e.detail.lng, null, 'map pin');
    });
  }

  if ($('#id_latitude')) autoLocate();
  initWebcam();

  // Result page: paint detection boxes over the stored image.
  const resultCanvas = $('[data-result-canvas]');
  const resultImg = $('[data-result-image]');
  if (resultCanvas && resultImg) {
    const dets = jsonData('detections-data') || [];
    const paint = () => drawDetections(resultCanvas, resultImg, dets);
    if (resultImg.complete) paint();
    else resultImg.addEventListener('load', paint);
  }
});
