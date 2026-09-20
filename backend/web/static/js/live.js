/* Live video detection.
 *
 * Pulls frames from a camera (or a chosen video file), encodes each to JPEG,
 * POSTs it to /live/frame/, and paints the returned boxes on an overlay canvas.
 *
 * Pacing: one request in flight at a time, and the next frame is only grabbed
 * after the previous response lands. That self-throttles to whatever the
 * server can actually sustain instead of queueing work it will never finish.
 */
import { $, postForm, drawDetections } from './core.js';

const FRAME_QUALITY = 0.65;
const MAX_EDGE = 640; // downscale before upload; the model runs at 480 anyway

export class LiveDetector {
  constructor(root) {
    this.root = root;
    this.video = $('[data-live-video]', root);
    this.overlay = $('[data-live-overlay]', root);
    this.placeholder = $('[data-live-placeholder]', root);

    this.hud = {
      fps: $('[data-hud-fps]', root),
      count: $('[data-hud-count]', root),
      severity: $('[data-hud-severity]', root),
      latency: $('[data-hud-latency]', root),
      state: $('[data-hud-state]', root),
    };

    this.stream = null;
    this.running = false;
    this.busy = false;
    this.lastDetections = [];
    this.frameTimes = [];
    this.location = null;
    this.scratch = document.createElement('canvas');

    this.bind();
    this.watchLocation();
  }

  bind() {
    const on = (sel, ev, fn) => {
      const el = $(sel, this.root);
      if (el) el.addEventListener(ev, fn);
    };
    on('[data-live-start]', 'click', () => this.start());
    on('[data-live-stop]', 'click', () => this.stop());
    on('[data-live-capture]', 'click', () => this.capture());
    on('[data-live-switch]', 'click', () => this.switchCamera());

    const fileInput = $('[data-live-file]', this.root);
    if (fileInput) {
      fileInput.addEventListener('change', (e) => {
        const file = e.target.files?.[0];
        if (file) this.playFile(file);
      });
    }

    this.facing = 'environment';
    window.addEventListener('beforeunload', () => this.stop());
  }

  /** Keep a current fix so a capture can be saved without a second prompt. */
  watchLocation() {
    if (!navigator.geolocation) return;
    this.watchId = navigator.geolocation.watchPosition(
      (pos) => {
        this.location = {
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
        };
        const el = $('[data-live-gps]', this.root);
        if (el) {
          el.textContent = `GPS ±${Math.round(pos.coords.accuracy)}m`;
          el.hidden = false;
        }
      },
      () => {},
      { enableHighAccuracy: true, maximumAge: 10000, timeout: 15000 }
    );
  }

  async start() {
    if (this.running) return;
    this.setState('starting');
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: this.facing, width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
    } catch (err) {
      this.setState('error');
      this.showPlaceholder(
        err.name === 'NotAllowedError'
          ? 'Camera permission denied. Allow access and try again.'
          : 'No camera available on this device.'
      );
      return;
    }
    this.video.srcObject = this.stream;
    this.video.muted = true;
    await this.video.play();
    this.hidePlaceholder();
    this.running = true;
    this.setState('live');
    this.toggleButtons(true);
    this.loop();
  }

  async playFile(file) {
    this.stop();
    this.video.srcObject = null;
    this.video.src = URL.createObjectURL(file);
    this.video.loop = true;
    this.video.muted = true;
    await this.video.play();
    this.hidePlaceholder();
    this.running = true;
    this.setState('file');
    this.toggleButtons(true);
    this.loop();
  }

  async switchCamera() {
    this.facing = this.facing === 'environment' ? 'user' : 'environment';
    if (this.running) {
      this.stop();
      await this.start();
    }
  }

  stop() {
    this.running = false;
    if (this.stream) {
      this.stream.getTracks().forEach((t) => t.stop());
      this.stream = null;
    }
    if (this.video) {
      this.video.pause();
      this.video.srcObject = null;
    }
    this.clearOverlay();
    this.setState('stopped');
    this.toggleButtons(false);
  }

  toggleButtons(live) {
    const set = (sel, hidden) => {
      const el = $(sel, this.root);
      if (el) el.hidden = hidden;
    };
    set('[data-live-start]', live);
    set('[data-live-stop]', !live);
    set('[data-live-capture]', !live);
  }

  setState(state) {
    if (this.hud.state) {
      this.hud.state.textContent =
        { starting: 'Starting…', live: 'LIVE', file: 'PLAYING', stopped: 'Stopped', error: 'Error' }[
          state
        ] || state;
    }
  }

  showPlaceholder(msg) {
    if (!this.placeholder) return;
    this.placeholder.hidden = false;
    const p = this.placeholder.querySelector('[data-live-message]');
    if (p) p.textContent = msg;
  }

  hidePlaceholder() {
    if (this.placeholder) this.placeholder.hidden = true;
  }

  clearOverlay() {
    if (!this.overlay) return;
    const ctx = this.overlay.getContext('2d');
    ctx.clearRect(0, 0, this.overlay.width, this.overlay.height);
  }

  /** Encode the current video frame to a JPEG blob, downscaled. */
  grabFrame() {
    const vw = this.video.videoWidth;
    const vh = this.video.videoHeight;
    if (!vw || !vh) return null;

    const scale = Math.min(1, MAX_EDGE / Math.max(vw, vh));
    const w = Math.round(vw * scale);
    const h = Math.round(vh * scale);
    this.scratch.width = w;
    this.scratch.height = h;
    this.scratch.getContext('2d').drawImage(this.video, 0, 0, w, h);
    return { canvas: this.scratch, scale, vw, vh };
  }

  async loop() {
    while (this.running) {
      const t0 = performance.now();
      const frame = this.grabFrame();
      if (!frame) {
        await new Promise((r) => setTimeout(r, 120));
        continue;
      }

      const blob = await new Promise((resolve) =>
        frame.canvas.toBlob(resolve, 'image/jpeg', FRAME_QUALITY)
      );
      if (!blob || !this.running) break;

      const fd = new FormData();
      fd.append('frame', blob, 'frame.jpg');

      let result;
      try {
        result = await postForm('/live/frame/', fd);
      } catch {
        await new Promise((r) => setTimeout(r, 500));
        continue;
      }
      if (!this.running) break;

      const body = result.body || {};
      if (body.ok && !body.skipped) {
        // Boxes come back in the downscaled frame's pixel space; rescale to
        // the source video so the overlay lines up at any display size.
        const inv = 1 / frame.scale;
        this.lastDetections = (body.detections || []).map((d) => ({
          ...d,
          bbox: d.bbox.map((v) => Math.round(v * inv)),
        }));
        this.render(frame.vw, frame.vh);
        this.updateHud(body, performance.now() - t0);
      } else if (!body.ok && body.error) {
        this.setState('error');
      }
    }
  }

  render(vw, vh) {
    if (!this.overlay) return;
    this.overlay.width = vw;
    this.overlay.height = vh;
    drawDetections(this.overlay, { naturalWidth: vw, naturalHeight: vh }, this.lastDetections, {
      drawImage: false,
    });
  }

  updateHud(body, elapsed) {
    this.frameTimes.push(elapsed);
    if (this.frameTimes.length > 12) this.frameTimes.shift();
    const avg = this.frameTimes.reduce((a, b) => a + b, 0) / this.frameTimes.length;

    if (this.hud.fps) this.hud.fps.textContent = `${(1000 / avg).toFixed(1)} fps`;
    if (this.hud.latency) this.hud.latency.textContent = `${body.ms ?? Math.round(avg)} ms`;
    if (this.hud.count) this.hud.count.textContent = `${body.count ?? 0} detected`;
    if (this.hud.severity) {
      const sev = body.severity || 'low';
      this.hud.severity.textContent = sev;
      this.hud.severity.className = `hud-pill chip-${sev}`;
    }
  }

  /** Promote the current frame into a persisted report. */
  async capture() {
    if (!this.running) return;
    if (!this.location) {
      alert('Waiting for a GPS fix. Allow location access, then try again.');
      return;
    }
    const frame = this.grabFrame();
    if (!frame) return;

    // Save at full resolution, not the downscaled inference frame.
    const full = document.createElement('canvas');
    full.width = this.video.videoWidth;
    full.height = this.video.videoHeight;
    full.getContext('2d').drawImage(this.video, 0, 0);
    const blob = await new Promise((r) => full.toBlob(r, 'image/jpeg', 0.9));

    const fd = new FormData();
    fd.append('frame', blob, 'capture.jpg');
    fd.append('latitude', this.location.lat);
    fd.append('longitude', this.location.lng);
    fd.append('accuracy_m', this.location.accuracy || '');

    const btn = $('[data-live-capture]', this.root);
    if (btn) btn.disabled = true;
    const { body } = await postForm('/live/capture/', fd);
    if (btn) btn.disabled = false;

    const banner = $('[data-live-saved]', this.root);
    if (body.ok && banner) {
      banner.hidden = false;
      banner.innerHTML = `Saved as <strong>${body.severity}</strong> severity. <a href="${body.url}">Open report</a>`;
    } else if (!body.ok) {
      alert(body.error || 'Could not save that capture.');
    }
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const root = document.querySelector('[data-live-root]');
  if (root) new LiveDetector(root);
});
