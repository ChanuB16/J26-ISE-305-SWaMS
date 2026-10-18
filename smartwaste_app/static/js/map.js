// Maps. Uses Leaflet + OpenStreetMap/CARTO tiles when there is internet.
// Without internet it draws a simple map (points and lines only, no streets) so the page still works.
import { esc, showTip, hideTip } from "./ui.js";

let leafletPromise = null;
function loadLeaflet() {
  if (window.L) return Promise.resolve(window.L);
  if (leafletPromise) return leafletPromise;
  leafletPromise = new Promise((resolve) => {
    const css = document.createElement("link");
    css.rel = "stylesheet";
    css.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
    css.integrity = "sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=";
    css.crossOrigin = "";
    document.head.appendChild(css);
    const s = document.createElement("script");
    s.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
    s.integrity = "sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=";
    s.crossOrigin = "";
    const done = (ok) => { clearTimeout(t); resolve(ok && window.L ? window.L : null); };
    const t = setTimeout(() => done(false), 7000);
    s.onload = () => done(true);
    s.onerror = () => done(false);
    document.head.appendChild(s);
  });
  return leafletPromise;
}

function markerHTML(it) {
  if (it.kind === "num") return `<div class="mk mk-num" style="background:${it.color}">${esc(it.n)}</div>`;
  if (it.kind === "truck") return `<div class="mk mk-truck" style="background:${it.color}">🚚 ${esc(it.text)}</div>`;
  if (it.kind === "depot") return `<div class="mk-depot">${esc(it.text || "Depot")}</div>`;
  if (it.kind === "me") return `<div class="mk" style="background:#2a78d6;width:16px;height:16px"></div>`;
  const s = it.size || 20;
  return `<div class="mk" style="background:${it.color};width:${s}px;height:${s}px;color:${it.ink || "#fff"};font-size:${Math.round(s * 0.5)}px;${it.highlight ? "outline:3px solid #17231b;outline-offset:1px;" : ""}">${esc(it.sym || "")}</div>`;
}
const ICON_SIZE = { num: [24, 24], me: [16, 16], truck: [70, 20], depot: [50, 20] };

const okNum = (v) => v != null && v !== "" && isFinite(Number(v));
// drops markers without a position and line points without a position (bad data must not break the map)
function usable(items) {
  return (items || []).map((it) => (it.kind === "line" ? { ...it, points: (it.points || []).filter((p) => p && okNum(p[0]) && okNum(p[1])) } : it))
    .filter((it) => (it.kind === "line" ? it.points.length > 1 : okNum(it.lat) && okNum(it.lng)));
}

export async function createMap(container, opts = {}) {
  const L = opts.forceSimple ? null : await loadLeaflet();
  return L ? leafletMap(L, container, opts) : simpleMap(container, opts);
}

// ---------------------------------------------------------------------------
function leafletMap(L, container, opts) {
  container.innerHTML = "";
  const map = L.map(container, { zoomControl: true, attributionControl: true }).setView(opts.center || [6.92, 79.96], opts.zoom || 13);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    { maxZoom: 19, attribution: "&copy; OpenStreetMap contributors" }).addTo(map);  // free, no API key
  const groups = {};
  let fitted = false;
  if (opts.onClick) map.on("click", (e) => opts.onClick(e.latlng.lat, e.latlng.lng));
  const api = {
    leaflet: true,
    set(name, items) {
      items = usable(items);
      if (!groups[name]) groups[name] = L.layerGroup().addTo(map);
      const g = groups[name];
      g.clearLayers();
      for (const it of items || []) {
        let layer;
        if (it.kind === "line") {
          if (!it.points || it.points.length < 2) continue;
          layer = L.polyline(it.points, { color: it.color, weight: it.width || 5, opacity: it.opacity ?? 0.85, dashArray: it.dash ? "8 8" : null });
        } else if (it.kind === "zone") {
          layer = L.circle([it.lat, it.lng], { radius: it.radius || 300, color: it.color || "#d03b3b", weight: 2, fillOpacity: it.fillOpacity ?? 0.18 });
        } else {
          const sz = ICON_SIZE[it.kind] || [it.size || 20, it.size || 20];
          layer = L.marker([it.lat, it.lng], { icon: L.divIcon({ className: "", html: markerHTML(it), iconSize: sz }), zIndexOffset: it.z || 0, keyboard: false });
        }
        if (it.popup) layer.bindPopup(it.popup);
        if (it.hover) layer.bindTooltip(it.hover, { direction: "top", offset: [0, -8] });
        if (it.onClick) layer.on("click", (e) => { L.DomEvent.stopPropagation(e); it.onClick(); });
        layer.addTo(g);
      }
    },
    fit(points, force = false) {
      const pts = (points || []).filter((p) => p && p[0] != null && p[1] != null);
      if (!pts.length || (fitted && !force)) return;
      if (pts.length === 1) map.setView(pts[0], 15);
      else map.fitBounds(pts, { padding: [30, 30], maxZoom: 16 });
      fitted = true;
    },
    view(center, zoom) { map.setView(center, zoom || map.getZoom()); },
    resize() { map.invalidateSize(); },
  };
  setTimeout(() => map.invalidateSize(), 50);
  return api;
}

// ---------------------------------------------------------------------------
// Simple map without internet: plain SVG with the same functions.
// ---------------------------------------------------------------------------
function simpleMap(container, opts) {
  container.innerHTML = "";
  const layers = {};
  let bounds = null;
  const pop = document.createElement("div");
  pop.className = "card";
  pop.style.cssText = "position:absolute;z-index:600;display:none;max-width:260px;padding:10px 12px;font-size:13px";
  const note = document.createElement("div");
  note.className = "note-offline";
  note.textContent = "Simple map (no internet for street tiles)";
  const svgNS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgNS, "svg");
  svg.setAttribute("class", "svgmap");
  container.append(svg, pop, note);

  function allPoints() {
    const pts = [];
    for (const items of Object.values(layers)) for (const it of items) {
      if (it.kind === "line") pts.push(...(it.points || []));
      else if (it.lat != null) pts.push([it.lat, it.lng]);
    }
    return pts;
  }
  function project() {
    const W = container.clientWidth || 600, H = container.clientHeight || 400;
    let b = bounds;
    if (!b) {
      const pts = allPoints();
      if (!pts.length) {
        const c = opts.center || [6.92, 79.96];
        b = [[c[0] - 0.03, c[1] - 0.04], [c[0] + 0.03, c[1] + 0.04]];
      } else {
        b = [[Math.min(...pts.map((p) => p[0])), Math.min(...pts.map((p) => p[1]))], [Math.max(...pts.map((p) => p[0])), Math.max(...pts.map((p) => p[1]))]];
      }
    }
    let [[la0, ln0], [la1, ln1]] = b;
    const padLa = Math.max(0.004, (la1 - la0) * 0.12), padLn = Math.max(0.004, (ln1 - ln0) * 0.12);
    la0 -= padLa; la1 += padLa; ln0 -= padLn; ln1 += padLn;
    // keep the shape right: 1 degree of longitude is cos(lat) x shorter
    const k = Math.cos(((la0 + la1) / 2) * Math.PI / 180);
    const sx = W / ((ln1 - ln0) * k), sy = H / (la1 - la0), s = Math.min(sx, sy);
    const cx = (ln0 + ln1) / 2, cy = (la0 + la1) / 2;
    return {
      W, H,
      x: (ln) => W / 2 + (ln - cx) * k * s,
      y: (la) => H / 2 - (la - cy) * s,
      lat: (py) => cy - (py - H / 2) / s,
      lng: (px) => cx + (px - W / 2) / (k * s),
      mPerPx: 111320 / s,
    };
  }
  function draw() {
    const P = project();
    svg.setAttribute("viewBox", `0 0 ${P.W} ${P.H}`);
    let h = `<rect width="${P.W}" height="${P.H}" fill="#eef1ea"/>`;
    for (let i = 1; i < 8; i++) h += `<line x1="${(P.W * i) / 8}" x2="${(P.W * i) / 8}" y1="0" y2="${P.H}" stroke="#e1e5dc"/><line y1="${(P.H * i) / 8}" y2="${(P.H * i) / 8}" x1="0" x2="${P.W}" stroke="#e1e5dc"/>`;
    const order = (it) => (it.kind === "zone" ? 0 : it.kind === "line" ? 1 : 2);
    const items = Object.values(layers).flat().map((it, i) => ({ it, i })).sort((a, b) => order(a.it) - order(b.it));
    items.forEach(({ it }, idx) => {
      const id = `data-k="${idx}"`;
      if (it.kind === "line") {
        if (!it.points || it.points.length < 2) return;
        h += `<polyline ${id} points="${it.points.map((p) => P.x(p[1]).toFixed(1) + "," + P.y(p[0]).toFixed(1)).join(" ")}" fill="none" stroke="${it.color}" stroke-width="${it.width || 4}" stroke-opacity="${it.opacity ?? 0.85}" ${it.dash ? 'stroke-dasharray="8 8"' : ""} stroke-linejoin="round"/>`;
      } else if (it.kind === "zone") {
        h += `<circle ${id} cx="${P.x(it.lng)}" cy="${P.y(it.lat)}" r="${Math.max(6, (it.radius || 300) / P.mPerPx)}" fill="${it.color || "#d03b3b"}" fill-opacity="${it.fillOpacity ?? 0.18}" stroke="${it.color || "#d03b3b"}" stroke-width="2"/>`;
      } else {
        const x = P.x(it.lng), y = P.y(it.lat);
        if (it.kind === "num") h += `<g ${id} style="cursor:pointer"><circle cx="${x}" cy="${y}" r="11" fill="${it.color}" stroke="#fff" stroke-width="2"/><text x="${x}" y="${y + 3.5}" font-size="10" font-weight="700" fill="#fff" text-anchor="middle">${esc(it.n)}</text></g>`;
        else if (it.kind === "truck" || it.kind === "depot") {
          const t = it.kind === "depot" ? it.text || "Depot" : "🚚 " + it.text, w = t.length * 6.5 + 12;
          h += `<g ${id} style="cursor:pointer"><rect x="${x - w / 2}" y="${y - 10}" width="${w}" height="20" rx="6" fill="${it.kind === "depot" ? "#0b0b0b" : it.color}" stroke="#fff" stroke-width="2"/><text x="${x}" y="${y + 4}" font-size="11" font-weight="700" fill="#fff" text-anchor="middle">${esc(t)}</text></g>`;
        } else if (it.kind === "me") h += `<circle ${id} cx="${x}" cy="${y}" r="8" fill="#2a78d6" stroke="#fff" stroke-width="3"/>`;
        else {
          const r = (it.size || 20) / 2;
          h += `<g ${id} style="cursor:pointer">${it.highlight ? `<circle cx="${x}" cy="${y}" r="${r + 4}" fill="none" stroke="#17231b" stroke-width="2.5"/>` : ""}<circle cx="${x}" cy="${y}" r="${r}" fill="${it.color}" stroke="#fff" stroke-width="2"/><text x="${x}" y="${y + r * 0.36}" font-size="${r}" fill="${it.ink || "#fff"}" text-anchor="middle">${esc(it.sym || "")}</text></g>`;
        }
      }
    });
    svg.innerHTML = h;
    svg._items = items.map((x) => x.it);
    svg._P = P;
  }
  svg.addEventListener("mousemove", (e) => {
    const g = e.target.closest("[data-k]");
    const it = g && svg._items[Number(g.dataset.k)];
    if (it && (it.hover || it.popup)) showTip(e, it.hover || it.popup);
    else hideTip();
  });
  svg.addEventListener("mouseleave", hideTip);
  svg.addEventListener("click", (e) => {
    const g = e.target.closest("[data-k]");
    const it = g && svg._items[Number(g.dataset.k)];
    pop.style.display = "none";
    if (it && it.kind !== "zone" && it.kind !== "line") {
      if (it.onClick) it.onClick();
      if (it.popup) {
        const r = container.getBoundingClientRect();
        pop.innerHTML = it.popup;
        pop.style.display = "block";
        pop.style.left = Math.min(e.clientX - r.left + 10, r.width - 270) + "px";
        pop.style.top = Math.max(4, e.clientY - r.top - 10) + "px";
      }
      return;
    }
    if (opts.onClick) {
      const r = svg.getBoundingClientRect(), P = svg._P;
      const px = ((e.clientX - r.left) / r.width) * P.W, py = ((e.clientY - r.top) / r.height) * P.H;
      opts.onClick(P.lat(py), P.lng(px));
    }
  });
  new ResizeObserver(() => draw()).observe(container);
  return {
    leaflet: false,
    set(name, items) { layers[name] = usable(items); draw(); },
    fit(points, force = false) {
      const pts = (points || []).filter((p) => p && p[0] != null);
      if (!pts.length || (bounds && !force)) return;
      bounds = [[Math.min(...pts.map((p) => p[0])), Math.min(...pts.map((p) => p[1]))], [Math.max(...pts.map((p) => p[0])), Math.max(...pts.map((p) => p[1]))]];
      draw();
    },
    view() {},
    resize() { draw(); },
  };
}

// Marker for a bin, coloured by fill level (with a symbol, so it is not colour only).
export function binMarker(b, level, extra = {}) {
  return {
    kind: "bin", lat: b.lat, lng: b.lng, color: level.color, sym: level.sym, ink: level.key === "filling" ? "#3d2a00" : "#fff",
    hover: `<b>${esc(b.id)}</b> ${esc(b.name || "")}<br>${level.label}${b.fill != null ? " · " + Math.round(b.fill) + "% full" : ""}`,
    ...extra,
  };
}
