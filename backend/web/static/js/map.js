/* One reusable OpenLayers module, configured per page via data-* attributes.
 *
 * <div id="map" class="map-shell map-dark"
 *      data-map                      enable
 *      data-geojson="map-data"       json_script id holding the FeatureCollection
 *      data-wards="wards-data"       json_script id holding ward polygons
 *      data-picker="true"            click-to-place mode (writes hidden inputs)
 *      data-lat-input="#id_latitude" data-lng-input="#id_longitude"
 *      data-heatmap="true"           offer a heatmap toggle
 *      data-zoom="12" data-center="77.59,12.97">
 *
 * Requires the vendored global `ol`.
 */
import { $, jsonData, severityColor } from './core.js';

const DEFAULT_CENTER = [77.5946, 12.9716]; // Bengaluru

/* Basemap: Esri's Gray Canvas.
 *
 * Not tile.openstreetmap.org — their usage policy forbids application use of
 * the volunteer servers and they serve a 403 "Access blocked" tile instead.
 * Not Carto either: their keyless tier now stamps "API KEY REQUIRED" across
 * every tile. Esri's Canvas basemaps need no key and are genuinely dark, so
 * the map matches the black canvas natively rather than being CSS-inverted
 * (inverting raster tiles wrecked the label colours).
 *
 * Esri tiles are addressed {z}/{row}/{col}, i.e. y before x — not the usual
 * XYZ order. Getting this backwards yields a plausible-looking map of the
 * wrong place, so it is spelled out in the template below.
 */
const ESRI = 'https://services.arcgisonline.com/ArcGIS/rest/services/Canvas';
const ESRI_ATTRIB =
  'Tiles &copy; <a href="https://www.esri.com/">Esri</a> &mdash; ' +
  'Sources: Esri, HERE, Garmin, &copy; OpenStreetMap contributors';

const BASEMAPS = {
  dark: { base: `${ESRI}/World_Dark_Gray_Base`, labels: `${ESRI}/World_Dark_Gray_Reference` },
  light: { base: `${ESRI}/World_Light_Gray_Base`, labels: `${ESRI}/World_Light_Gray_Reference` },
};

function esriSource(service, attribute) {
  return new ol.source.XYZ({
    url: `${service}/MapServer/tile/{z}/{y}/{x}`,
    attributions: attribute ? ESRI_ATTRIB : undefined,
    maxZoom: 16,
    crossOrigin: 'anonymous',
    transition: 300,
  });
}

/** [base, labels] — labels ride above the data so place names stay readable. */
function basemapLayers() {
  const spec =
    document.documentElement.dataset.theme === 'light' ? BASEMAPS.light : BASEMAPS.dark;
  return [
    new ol.layer.Tile({ source: esriSource(spec.base, true), zIndex: 0 }),
    new ol.layer.Tile({ source: esriSource(spec.labels, false), zIndex: 8, opacity: 0.85 }),
  ];
}

function iconFor(severity, status, count) {
  const color = severityColor(severity);
  const faded = status === 'fixed';
  const radius = count > 1 ? 9 : 7;
  return new ol.style.Style({
    image: new ol.style.Circle({
      radius,
      fill: new ol.style.Fill({ color: faded ? 'rgba(120,130,140,.55)' : color }),
      stroke: new ol.style.Stroke({
        color: faded ? 'rgba(255,255,255,.35)' : 'rgba(255,255,255,.85)',
        width: 1.6,
      }),
    }),
    text:
      count > 1
        ? new ol.style.Text({
            text: String(count),
            font: '600 10px Inter, sans-serif',
            fill: new ol.style.Fill({ color: '#04050a' }),
          })
        : undefined,
  });
}

// ol needs rgba(); convert #rrggbb rather than string-patching the hex.
function hexToRgba(hex, alpha) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

function styleCluster(feature) {
  const features = feature.get('features') || [];
  if (features.length === 1) {
    const f = features[0];
    return iconFor(f.get('severity'), f.get('status'), f.get('count') || 1);
  }
  const worst = features.some((f) => f.get('severity') === 'high')
    ? 'high'
    : features.some((f) => f.get('severity') === 'medium')
    ? 'medium'
    : 'low';
  const color = severityColor(worst);
  const size = features.length;
  const r = Math.min(26, 13 + Math.log2(size + 1) * 3.4);
  return new ol.style.Style({
    image: new ol.style.Circle({
      radius: r,
      fill: new ol.style.Fill({ color: hexToRgba(color, 0.25) }),
      stroke: new ol.style.Stroke({ color, width: 2 }),
    }),
    text: new ol.style.Text({
      text: String(size),
      font: '650 12px Inter, sans-serif',
      fill: new ol.style.Fill({ color: '#fff' }),
    }),
  });
}

export function initMap(el) {
  const fmt = new ol.format.GeoJSON({ featureProjection: 'EPSG:3857' });
  const collection = jsonData(el.dataset.geojson || '') || {
    type: 'FeatureCollection',
    features: [],
  };

  const source = new ol.source.Vector({
    features: collection.features?.length ? fmt.readFeatures(collection) : [],
  });

  const cluster = new ol.source.Cluster({ distance: 40, source });
  const pointLayer = new ol.layer.Vector({ source: cluster, style: styleCluster, zIndex: 5 });

  const heatLayer = new ol.layer.Heatmap({
    source,
    blur: 22,
    radius: 14,
    zIndex: 4,
    visible: false,
    weight: (f) => Math.min(1, (f.get('severity_score') || 1) / 30),
  });

  const layers = [...basemapLayers(), heatLayer, pointLayer];

  // Ward polygons, if the page supplied them.
  const wardData = jsonData(el.dataset.wards || '');
  let wardLayer = null;
  if (wardData && wardData.features?.length) {
    wardLayer = new ol.layer.Vector({
      source: new ol.source.Vector({ features: fmt.readFeatures(wardData) }),
      style: new ol.style.Style({
        stroke: new ol.style.Stroke({ color: 'rgba(157,107,255,.55)', width: 1.2 }),
        fill: new ol.style.Fill({ color: 'rgba(157,107,255,.05)' }),
      }),
      zIndex: 2,
    });
    // zIndex decides draw order, so position in this array does not matter.
    layers.push(wardLayer);
  }

  const centerAttr = (el.dataset.center || '').split(',').map(Number);
  const center = centerAttr.length === 2 && !centerAttr.some(isNaN) ? centerAttr : DEFAULT_CENTER;

  const map = new ol.Map({
    target: el,
    layers,
    view: new ol.View({
      center: ol.proj.fromLonLat(center),
      zoom: Number(el.dataset.zoom) || 12,
      maxZoom: 19,
    }),
    controls: ol.control.defaults.defaults({ attributionOptions: { collapsible: true } }),
  });

  // Fit to the data when there is any.
  if (source.getFeatures().length > 1) {
    map.getView().fit(source.getExtent(), { padding: [60, 60, 60, 60], maxZoom: 16, duration: 400 });
  }

  setupPopup(map, el);
  setupPicker(map, el);
  setupLayerToggles(el, { heatLayer, pointLayer, wardLayer });
  setupLocate(map, el);
  setupSearch(map, el);

  el._olMap = map;
  return map;
}

function setupPopup(map, el) {
  const container = document.createElement('div');
  container.className = 'ol-popup';
  container.style.display = 'none';
  container.innerHTML =
    '<button class="ol-popup-close" aria-label="Close">&times;</button>' +
    '<div class="ol-popup-content"></div>';
  el.appendChild(container);

  const overlay = new ol.Overlay({
    element: container,
    positioning: 'bottom-center',
    stopEvent: true,
    offset: [0, -12],
  });
  map.addOverlay(overlay);

  container.querySelector('.ol-popup-close').addEventListener('click', () => {
    container.style.display = 'none';
  });

  map.on('click', (evt) => {
    if (el.dataset.picker === 'true') return; // picker owns clicks
    const hit = map.forEachFeatureAtPixel(evt.pixel, (f) => f);
    if (!hit) {
      container.style.display = 'none';
      return;
    }
    const members = hit.get('features');
    if (members && members.length > 1) {
      // Zoom into a cluster rather than trying to show many popups.
      const extent = ol.extent.createEmpty();
      members.forEach((m) => ol.extent.extend(extent, m.getGeometry().getExtent()));
      map.getView().fit(extent, { padding: [70, 70, 70, 70], duration: 350, maxZoom: 18 });
      return;
    }
    const f = members ? members[0] : hit;
    const p = f.getProperties();
    if (!p.id) return;

    container.querySelector('.ol-popup-content').innerHTML = `
      ${p.thumb ? `<img src="${p.thumb}" alt="">` : ''}
      <div class="ol-popup-body">
        <div class="row" style="gap:6px;margin-bottom:6px">
          <span class="chip chip-${p.severity}">${p.severity}</span>
          <span class="chip chip-${p.status} chip-plain">${p.status_label || p.status}</span>
        </div>
        <div class="tiny faint">Confidence ${(p.confidence * 100).toFixed(0)}%${
      p.count > 1 ? ` &middot; ${p.count} reports` : ''
    }</div>
        <a class="btn btn-sm btn-primary" style="margin-top:9px;width:100%" href="${p.url}">View details</a>
      </div>`;
    overlay.setPosition(f.getGeometry().getCoordinates());
    container.style.display = '';
  });

  map.on('pointermove', (evt) => {
    if (el.dataset.picker === 'true') return;
    const hit = map.hasFeatureAtPixel(evt.pixel);
    map.getTargetElement().style.cursor = hit ? 'pointer' : '';
  });
}

/** Click-to-place mode for the report form and manual reports. */
function setupPicker(map, el) {
  if (el.dataset.picker !== 'true') return;

  const latInput = document.querySelector(el.dataset.latInput || '#id_latitude');
  const lngInput = document.querySelector(el.dataset.lngInput || '#id_longitude');

  const markerSource = new ol.source.Vector();
  map.addLayer(
    new ol.layer.Vector({
      source: markerSource,
      zIndex: 20,
      style: new ol.style.Style({
        image: new ol.style.Circle({
          radius: 9,
          fill: new ol.style.Fill({ color: 'rgba(91,140,255,.9)' }),
          stroke: new ol.style.Stroke({ color: '#fff', width: 2.5 }),
        }),
      }),
    })
  );

  const place = (lonLat) => {
    markerSource.clear();
    markerSource.addFeature(
      new ol.Feature({ geometry: new ol.geom.Point(ol.proj.fromLonLat(lonLat)) })
    );
    if (latInput) latInput.value = lonLat[1].toFixed(6);
    if (lngInput) lngInput.value = lonLat[0].toFixed(6);
    el.dispatchEvent(new CustomEvent('location:set', { detail: { lat: lonLat[1], lng: lonLat[0] }, bubbles: true }));
  };

  map.on('click', (evt) => place(ol.proj.toLonLat(evt.coordinate)));

  // Let other modules (geolocation, EXIF) drive the marker.
  el.addEventListener('location:request', (e) => {
    const { lat, lng, zoom } = e.detail || {};
    if (typeof lat !== 'number' || typeof lng !== 'number') return;
    place([lng, lat]);
    map.getView().animate({ center: ol.proj.fromLonLat([lng, lat]), zoom: zoom || 17, duration: 400 });
  });

  if (latInput?.value && lngInput?.value) {
    place([parseFloat(lngInput.value), parseFloat(latInput.value)]);
  }
}

function setupLayerToggles(el, { heatLayer, pointLayer, wardLayer }) {
  const root = el.parentElement || document;
  const bind = (sel, fn) => {
    const box = root.querySelector(sel);
    if (box) box.addEventListener('change', () => fn(box.checked));
  };
  bind('[data-toggle-heat]', (on) => {
    heatLayer.setVisible(on);
    pointLayer.setVisible(!on);
  });
  bind('[data-toggle-wards]', (on) => wardLayer && wardLayer.setVisible(on));
  bind('[data-toggle-points]', (on) => pointLayer.setVisible(on));
}

function setupLocate(map, el) {
  const root = el.parentElement || document;
  const btn = root.querySelector('[data-locate]');
  if (!btn || !navigator.geolocation) return;

  const meSource = new ol.source.Vector();
  map.addLayer(
    new ol.layer.Vector({
      source: meSource,
      zIndex: 25,
      style: (f) =>
        f.get('kind') === 'accuracy'
          ? new ol.style.Style({
              fill: new ol.style.Fill({ color: 'rgba(91,140,255,.12)' }),
              stroke: new ol.style.Stroke({ color: 'rgba(91,140,255,.5)', width: 1 }),
            })
          : new ol.style.Style({
              image: new ol.style.Circle({
                radius: 6,
                fill: new ol.style.Fill({ color: '#5b8cff' }),
                stroke: new ol.style.Stroke({ color: '#fff', width: 2 }),
              }),
            }),
    })
  );

  btn.addEventListener('click', () => {
    btn.disabled = true;
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        btn.disabled = false;
        const { latitude, longitude, accuracy } = pos.coords;
        const coord = ol.proj.fromLonLat([longitude, latitude]);
        meSource.clear();
        meSource.addFeature(new ol.Feature({ geometry: new ol.geom.Point(coord) }));
        if (accuracy) {
          const circle = new ol.Feature({
            geometry: new ol.geom.Circle(coord, accuracy),
          });
          circle.set('kind', 'accuracy');
          meSource.addFeature(circle);
        }
        map.getView().animate({ center: coord, zoom: 16, duration: 450 });
        el.dispatchEvent(
          new CustomEvent('location:request', {
            detail: { lat: latitude, lng: longitude },
            bubbles: false,
          })
        );
      },
      () => {
        btn.disabled = false;
        alert('Could not get your location. Check browser permissions.');
      },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  });
}

function setupSearch(map, el) {
  const root = el.parentElement || document;
  const input = root.querySelector('[data-geosearch]');
  const list = root.querySelector('[data-georesults]');
  if (!input || !list) return;

  let timer = null;
  input.addEventListener('input', () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 3) {
      list.innerHTML = '';
      return;
    }
    // Debounced: Nominatim's policy is one request per second.
    timer = setTimeout(async () => {
      try {
        const res = await fetch(`/geocode/?q=${encodeURIComponent(q)}`, {
          credentials: 'same-origin',
        });
        const data = await res.json();
        list.innerHTML = (data.results || [])
          .map((r) => `<li data-lat="${r.lat}" data-lng="${r.lng}">${r.label}</li>`)
          .join('');
      } catch {
        list.innerHTML = '';
      }
    }, 550);
  });

  list.addEventListener('click', (e) => {
    const li = e.target.closest('li');
    if (!li) return;
    const lat = parseFloat(li.dataset.lat);
    const lng = parseFloat(li.dataset.lng);
    map.getView().animate({ center: ol.proj.fromLonLat([lng, lat]), zoom: 17, duration: 450 });
    el.dispatchEvent(new CustomEvent('location:request', { detail: { lat, lng }, bubbles: false }));
    list.innerHTML = '';
    input.value = li.textContent;
  });
}

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-map]').forEach(initMap);
});
