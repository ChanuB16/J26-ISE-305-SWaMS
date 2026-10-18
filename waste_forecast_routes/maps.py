"""
Interactive maps (HTML files you open in a web browser). You do not need to edit this file.
The background map (CARTO / OpenStreetMap tiles) needs internet; the bins and routes are inside the file.
"""
import html
import json

COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]

TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  html, body { margin: 0; height: 100%; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; background: #fcfcfb; }
  #top { padding: 10px 16px; border-bottom: 1px solid #e1e0d9; }
  #top h1 { margin: 0; font-size: 17px; color: #0b0b0b; }
  #top p { margin: 4px 0 0; font-size: 13px; color: #52514e; }
  #map { position: absolute; top: 64px; bottom: 0; left: 0; right: 0; }
  .legend { background: #fff; padding: 8px 10px; border-radius: 6px; font-size: 12px; line-height: 18px;
            box-shadow: 0 1px 4px rgba(0,0,0,.2); }
  .legend i { display: inline-block; width: 14px; height: 4px; margin-right: 6px; vertical-align: middle; }
</style></head>
<body>
<div id="top"><h1>__TITLE__</h1><p>__SUBTITLE__</p></div>
<div id="map"></div>
<script>
const DATA = __DATA__;
const map = L.map("map").setView(DATA.center, 13);
// background map: OpenStreetMap tiles (free, no API key)
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",
  {maxZoom: 19, attribution: "&copy; OpenStreetMap contributors"}).addTo(map);  // free, no API key
const all = [];
DATA.routes.forEach(r => {
  const line = L.polyline(r.coords, {color: r.color, weight: 5, opacity: 0.85}).addTo(map);
  line.bindPopup(r.popup);
  r.coords.forEach(c => all.push(c));
});
DATA.incidents.forEach(z => {
  L.circle([z.lat, z.lng], {radius: z.radius, color: "#d03b3b", fillOpacity: 0.15}).addTo(map).bindPopup(z.popup);
});
DATA.bins.forEach(b => {
  L.circleMarker([b.lat, b.lng], {radius: 7, color: "#0b0b0b", weight: 1.5, fillColor: b.fill_color,
                   fillOpacity: 1}).addTo(map).bindPopup(b.popup);
  all.push([b.lat, b.lng]);
});
L.marker(DATA.depot.coords, {title: DATA.depot.name}).addTo(map).bindPopup(DATA.depot.name);
all.push(DATA.depot.coords);
if (all.length > 1) map.fitBounds(all, {padding: [30, 30]});
const legend = L.control({position: "bottomright"});
legend.onAdd = function () {
  const div = L.DomUtil.create("div", "legend");
  div.innerHTML = DATA.legend.map(x => `<div><i style="background:${x.color}"></i>${x.label}</div>`).join("");
  return div;
};
if (DATA.legend.length) legend.addTo(map);
</script></body></html>
"""


def fill_color(fill):
    """Bin colour by fill level: green below 50%, yellow below 80%, red from 80%."""
    if fill is None:
        return "#898781"
    if fill >= 80:
        return "#d03b3b"
    if fill >= 50:
        return "#fab219"
    return "#0ca30c"


def write_map(path, title, subtitle, depot, depot_name, bins, routes=(), incidents=(), legend=()):
    """bins: dicts (lat, lng, label, fill or None, extra). routes: dicts (name, coords [(lat, lng)], popup).
    incidents: dicts (lat, lng, radius, popup)."""
    data = {
        "center": [depot[0], depot[1]],
        "depot": {"coords": [depot[0], depot[1]], "name": html.escape(depot_name)},
        "bins": [{"lat": b["lat"], "lng": b["lng"], "fill_color": fill_color(b.get("fill")),
                  "popup": f"<b>{html.escape(str(b['label']))}</b><br>{html.escape(str(b.get('extra', '')))}"}
                 for b in bins],
        "routes": [{"coords": r["coords"], "color": COLORS[i % len(COLORS)],
                    "popup": html.escape(r.get("popup", r["name"]))} for i, r in enumerate(routes)],
        "incidents": [{"lat": z["lat"], "lng": z["lng"], "radius": z.get("radius", 400),
                       "popup": html.escape(z.get("popup", "Road closed"))} for z in incidents],
        "legend": [{"color": COLORS[i % len(COLORS)], "label": html.escape(r["name"])} for i, r in enumerate(routes)]
        + [dict(x) for x in legend],
    }
    page = (TEMPLATE.replace("__TITLE__", html.escape(title)).replace("__SUBTITLE__", html.escape(subtitle))
            .replace("__DATA__", json.dumps(data)))
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)
