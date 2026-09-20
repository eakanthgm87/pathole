/* Shared helpers. Loaded on every page, deliberately tiny. */

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

/** Read a json_script block by id. Returns null when absent. */
export function jsonData(id) {
  const el = document.getElementById(id);
  if (!el) return null;
  try {
    return JSON.parse(el.textContent);
  } catch (err) {
    console.warn('bad json_script payload', id, err);
    return null;
  }
}

/** Django's CSRF cookie, for fetch POSTs. */
export function csrfToken() {
  const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  if (m) return decodeURIComponent(m[1]);
  const input = document.querySelector('input[name=csrfmiddlewaretoken]');
  return input ? input.value : '';
}

export async function postForm(url, formData) {
  const res = await fetch(url, {
    method: 'POST',
    body: formData,
    headers: { 'X-CSRFToken': csrfToken(), 'X-Requested-With': 'XMLHttpRequest' },
    credentials: 'same-origin',
  });
  const text = await res.text();
  let body;
  try {
    body = JSON.parse(text);
  } catch {
    body = { ok: false, error: `Server returned ${res.status}` };
  }
  return { ok: res.ok, status: res.status, body };
}

export const SEVERITY_COLORS = {
  low: '#35d0a5',
  medium: '#f5b83d',
  high: '#ff5a6e',
};

export function severityColor(sev) {
  return SEVERITY_COLORS[sev] || '#5b8cff';
}

/** Dismissible toasts, auto-hiding after a readable delay. */
export function initToasts() {
  $$('.toast').forEach((toast) => {
    const close = () => {
      toast.style.transition = 'opacity .3s, transform .3s';
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(24px)';
      setTimeout(() => toast.remove(), 300);
    };
    const btn = toast.querySelector('button');
    if (btn) btn.addEventListener('click', close);
    setTimeout(close, 6000);
  });
}

export function initNav() {
  const toggle = $('.nav-toggle');
  const nav = $('.nav');
  if (toggle && nav) {
    toggle.addEventListener('click', () => {
      const open = nav.classList.toggle('open');
      toggle.setAttribute('aria-expanded', String(open));
    });
  }
  const sideToggle = $('[data-side-toggle]');
  const side = $('.dash-side');
  if (sideToggle && side) {
    sideToggle.addEventListener('click', () => side.classList.toggle('open'));
  }
}

/** Theme switch. Defaults to the pure-black dark theme. */
export function initTheme() {
  const KEY = 'pw-theme';
  let stored = null;
  try {
    stored = localStorage.getItem(KEY);
  } catch { /* private mode: fall through to the default */ }
  if (stored === 'light') document.documentElement.dataset.theme = 'light';

  const apply = (next) => {
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem(KEY, next);
    } catch { /* not fatal */ }
    // Keep every toggle on the page in sync: checked means dark.
    $$('input[data-theme-toggle]').forEach((box) => {
      box.checked = next === 'dark';
    });
  };

  $$('[data-theme-toggle]').forEach((el) => {
    if (el.tagName === 'INPUT') {
      el.checked = document.documentElement.dataset.theme !== 'light';
      el.addEventListener('change', () => apply(el.checked ? 'dark' : 'light'));
    } else {
      el.addEventListener('click', () =>
        apply(document.documentElement.dataset.theme === 'light' ? 'dark' : 'light')
      );
    }
  });
}

/** Draw detection boxes over an image on a canvas, scaling to the render size. */
export function drawDetections(canvas, img, detections, opts = {}) {
  if (!canvas || !img) return;
  const ctx = canvas.getContext('2d');
  const w = img.naturalWidth || img.videoWidth || img.width;
  const h = img.naturalHeight || img.videoHeight || img.height;
  if (!w || !h) return;

  canvas.width = w;
  canvas.height = h;
  ctx.clearRect(0, 0, w, h);
  if (opts.drawImage !== false) ctx.drawImage(img, 0, 0, w, h);

  const scale = Math.max(w, h) / 900;
  ctx.lineWidth = Math.max(2, 3 * scale);
  ctx.font = `${Math.max(13, 15 * scale)}px Inter, system-ui, sans-serif`;
  ctx.textBaseline = 'top';

  (detections || []).forEach((det) => {
    const [x1, y1, x2, y2] = det.bbox;
    const conf = det.conf ?? 0;
    const isPothole = det.class === 'pothole';
    const color = isPothole
      ? conf >= 0.6 ? '#ff5a6e' : conf >= 0.35 ? '#f5b83d' : '#5b8cff'
      : '#9d6bff';

    ctx.strokeStyle = color;
    ctx.shadowColor = color;
    ctx.shadowBlur = 14 * scale;
    ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
    ctx.shadowBlur = 0;

    const label = `${det.class} ${(conf * 100).toFixed(0)}%`;
    const pad = 6 * scale;
    const tw = ctx.measureText(label).width;
    const th = Math.max(19, 21 * scale);
    const ly = Math.max(0, y1 - th);
    ctx.fillStyle = color;
    ctx.fillRect(x1, ly, tw + pad * 2, th);
    ctx.fillStyle = '#08080c';
    ctx.fillText(label, x1 + pad, ly + pad * 0.5);
  });
}

document.addEventListener('DOMContentLoaded', () => {
  initToasts();
  initNav();
  initTheme();
});

/* --- motion ------------------------------------------------------------- */

/** Reveal-on-scroll. Elements are visible by default in CSS terms only once
 *  .reveal is applied by this function, so a JS failure leaves content shown. */
export function initReveal() {
  // .kpi is excluded on purpose: it has its own staggered entrance in
  // dashboard.css, and running both produces a double fade.
  const targets = $$('[data-reveal], .card-hover, .chart-card, [data-reveal-group] > *');
  if (!targets.length) return;

  if (!('IntersectionObserver' in window)) {
    targets.forEach((el) => el.classList.add('is-in'));
    return;
  }

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('is-in');
        observer.unobserve(entry.target); // reveal once, never re-hide
      });
    },
    { rootMargin: '0px 0px -8% 0px', threshold: 0.08 }
  );

  targets.forEach((el, i) => {
    el.classList.add('reveal');
    // Stagger within a row, but cap it so long lists do not crawl in.
    el.style.setProperty('--i', String(i % 6));
    observer.observe(el);
  });
}

/** Count numbers up on first view. Reads the final value from the DOM so the
 *  server stays the source of truth and the page degrades to plain text. */
export function initCounters() {
  const nodes = $$('.kpi-value, [data-count]');
  if (!nodes.length || !('IntersectionObserver' in window)) return;
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  const animate = (el) => {
    const text = el.textContent.trim();
    // Split the leading number from any trailing unit ("17.3 d", "42").
    const match = text.match(/^([\d.,]+)(.*)$/);
    if (!match) return;
    const numeric = match[1].replace(/,/g, '');
    const suffix = match[2];
    const target = parseFloat(numeric);
    if (!isFinite(target) || target === 0) return;
    // Decimals come from the number only; reading them off the whole string
    // turned "17.3 d" into "17.300 d".
    const decimals = (numeric.split('.')[1] || '').length;
    const duration = 900;
    const start = performance.now();

    const step = (now) => {
      const t = Math.min(1, (now - start) / duration);
      // easeOutCubic: fast then settling, which reads as "counting up".
      const eased = 1 - Math.pow(1 - t, 3);
      const value = target * eased;
      el.textContent =
        (decimals ? value.toFixed(decimals) : Math.round(value).toLocaleString()) + suffix;
      if (t < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  };

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        animate(entry.target);
        observer.unobserve(entry.target);
      });
    },
    { threshold: 0.5 }
  );
  nodes.forEach((el) => observer.observe(el));
}

/** Subtle parallax on the ambient bloom, tied to pointer position. */
export function initAmbient() {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  if (window.matchMedia('(pointer: coarse)').matches) return;
  let raf = null;
  window.addEventListener('pointermove', (e) => {
    if (raf) return;
    raf = requestAnimationFrame(() => {
      raf = null;
      const x = (e.clientX / window.innerWidth - 0.5) * 14;
      const y = (e.clientY / window.innerHeight - 0.5) * 14;
      document.body.style.setProperty('--bloom-x', `${x}px`);
      document.body.style.setProperty('--bloom-y', `${y}px`);
    });
  }, { passive: true });
}

document.addEventListener('DOMContentLoaded', () => {
  initReveal();
  initCounters();
  initAmbient();
});

/* --- components --------------------------------------------------------- */

/** Dismiss the loading screen once the page is interactive. */
export function initLoader() {
  const screen = $('.loader-screen');
  if (!screen) return;
  const hide = () => {
    screen.classList.add('is-done');
    // Remove it so it can never swallow a click after fading out.
    setTimeout(() => screen.remove(), 700);
  };
  // Keep it up long enough to read, but never hold the page hostage.
  const shown = Number(screen.dataset.minMs || 450);
  const start = Number(screen.dataset.start || Date.now());
  const wait = Math.max(0, shown - (Date.now() - start));
  if (document.readyState === 'complete') setTimeout(hide, wait);
  else window.addEventListener('load', () => setTimeout(hide, wait), { once: true });
  // Safety net: a stalled image must not leave a black screen forever.
  setTimeout(hide, 4000);
}

/** Sliding pill behind the nav. Pure decoration over real links. */
export function initNavPill() {
  const nav = $('.nav');
  if (!nav || window.matchMedia('(max-width: 860px)').matches) return;

  const pill = document.createElement('span');
  pill.className = 'nav-pill';
  nav.prepend(pill);

  const links = $$('a', nav).filter((a) => !a.classList.contains('btn'));
  const active = links.find((a) => a.classList.contains('active'));

  const moveTo = (el) => {
    if (!el) {
      pill.classList.remove('is-on');
      return;
    }
    pill.style.width = `${el.offsetWidth}px`;
    pill.style.transform = `translateX(${el.offsetLeft}px)`;
    pill.classList.add('is-on');
  };

  links.forEach((a) => {
    a.addEventListener('mouseenter', () => moveTo(a));
    a.addEventListener('focus', () => moveTo(a));
  });
  nav.addEventListener('mouseleave', () => moveTo(active));
  requestAnimationFrame(() => moveTo(active));
  window.addEventListener('resize', () => moveTo(active), { passive: true });
}

/** Randomise the sparkle particles so no two buttons pulse identically. */
export function initSparkles() {
  $$('.particle-pen').forEach((pen) => {
    $$('.particle', pen).forEach((particle) => {
      const rand = (min, max) => min + Math.random() * (max - min);
      particle.style.setProperty('--x', rand(10, 90).toFixed(1));
      particle.style.setProperty('--y', rand(10, 90).toFixed(1));
      particle.style.setProperty('--duration', rand(6, 20).toFixed(1));
      particle.style.setProperty('--delay', rand(0, 20).toFixed(1));
      particle.style.setProperty('--alpha', rand(0.3, 0.9).toFixed(2));
      particle.style.setProperty('--origin-x', `${rand(-200, 500).toFixed(0)}%`);
      particle.style.setProperty('--origin-y', `${rand(-200, 500).toFixed(0)}%`);
      particle.style.setProperty('--size', rand(0.15, 0.6).toFixed(2));
    });
  });
}

document.addEventListener('DOMContentLoaded', () => {
  initLoader();
  initNavPill();
  initSparkles();
});
