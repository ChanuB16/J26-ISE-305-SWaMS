"""
Road network code shared by r1, r2 and r3. You do not need to edit this file.

  - download_osm_roads(): the real roads of the area from OpenStreetMap (Overpass API, free)
  - make_demo_roads():    a made-up road grid, ONLY for testing without internet
  - RoadNetwork:          travel times with rush hours, road closures and traffic jams,
                          fastest paths between bins (Dijkstra, scipy)
"""
import json
import math
import os
import time

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components, dijkstra
from scipy.spatial import cKDTree

import settings as S
from wastelib import DATA_DIR

DRIVABLE = {"motorway": "trunk", "motorway_link": "trunk", "trunk": "trunk", "trunk_link": "trunk",
            "primary": "primary", "primary_link": "primary", "secondary": "secondary", "secondary_link": "secondary",
            "tertiary": "tertiary", "tertiary_link": "tertiary", "unclassified": "unclassified",
            "residential": "residential", "living_street": "living_street", "service": "service", "road": "other"}
MAIN_ROADS = {"trunk", "primary", "secondary"}  # these get slower at rush hour
OVERPASS_URLS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
                 "https://maps.mail.ru/osm/tools/overpass/api/interpreter"]
NODES_CSV = os.path.join(DATA_DIR, "roads_nodes.csv")
EDGES_CSV = os.path.join(DATA_DIR, "roads_edges.csv")
INFO_JSON = os.path.join(DATA_DIR, "roads_info.json")


def to_xy(lat, lng, lat0):
    """Degrees -> metres on a flat map (good enough for a 20 km area)."""
    return (np.asarray(lng) * 111320.0 * math.cos(math.radians(lat0)), np.asarray(lat) * 110540.0)


def haversine_m(lat1, lng1, lat2, lng2):
    lat1, lng1, lat2, lng2 = map(np.radians, (lat1, lng1, lat2, lng2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lng2 - lng1) / 2) ** 2
    return 2 * 6371000.0 * np.arcsin(np.sqrt(a))


def area_bbox(points, margin_km=2.5):
    lats = [p[0] for p in points]
    lngs = [p[1] for p in points]
    dlat = margin_km / 110.54
    dlng = margin_km / (111.32 * math.cos(math.radians(np.mean(lats))))
    return (min(lats) - dlat, min(lngs) - dlng, max(lats) + dlat, max(lngs) + dlng)  # south, west, north, east


# ---------------------------------------------------------------------------
# Getting the roads
# ---------------------------------------------------------------------------
def download_osm_roads(bbox, log=print):
    """Real roads from OpenStreetMap (Overpass API). bbox = (south, west, north, east)."""
    import requests
    s, w, n, e = bbox
    query = f"""
    [out:json][timeout:180];
    way["highway"~"^({'|'.join(DRIVABLE)})$"]["access"!~"^(private|no)$"]["service"!~"^(parking_aisle|driveway)$"]
       ({s:.5f},{w:.5f},{n:.5f},{e:.5f});
    (._;>;);
    out body;
    """
    last = None
    for url in OVERPASS_URLS:
        try:
            log(f"  asking {url} ... (this can take 1-3 minutes)")
            r = requests.post(url, data={"data": query}, timeout=240)
            r.raise_for_status()
            return parse_overpass(r.json())
        except Exception as ex:  # try the next server
            last = ex
            log(f"  that server did not answer ({type(ex).__name__}), trying the next one")
    raise RuntimeError(f"Could not download the roads: {last}")


def parse_overpass(data):
    """Overpass JSON -> (nodes DataFrame [id, lat, lng], edges DataFrame [u, v, length_m, road_type, name])."""
    coords = {}
    ways = []
    for el in data.get("elements", []):
        if el.get("type") == "node":
            coords[el["id"]] = (el["lat"], el["lon"])
        elif el.get("type") == "way":
            ways.append(el)
    rows = []
    for w in ways:
        tags = w.get("tags", {})
        kind = DRIVABLE.get(tags.get("highway"))
        if kind is None:
            continue
        ow = str(tags.get("oneway", "no")).lower()
        forward_only = ow in ("yes", "true", "1") or tags.get("junction") in ("roundabout", "circular")
        backward_only = ow == "-1"
        name = tags.get("name", tags.get("ref", ""))
        nds = [n for n in w.get("nodes", []) if n in coords]
        for a, b in zip(nds[:-1], nds[1:]):
            if a == b:
                continue
            if not backward_only:
                rows.append((a, b, kind, name))
            if not forward_only:
                rows.append((b, a, kind, name))
    used = sorted({r[0] for r in rows} | {r[1] for r in rows})
    nodes = pd.DataFrame({"id": used, "lat": [coords[i][0] for i in used], "lng": [coords[i][1] for i in used]})
    edges = pd.DataFrame(rows, columns=["u", "v", "road_type", "name"])
    pos = nodes.set_index("id")
    edges["length_m"] = haversine_m(pos.loc[edges.u, "lat"].to_numpy(), pos.loc[edges.u, "lng"].to_numpy(),
                                    pos.loc[edges.v, "lat"].to_numpy(), pos.loc[edges.v, "lng"].to_numpy()).round(1)
    return nodes, edges[["u", "v", "length_m", "road_type", "name"]]


def make_demo_roads(bbox, seed=42):
    """A MADE-UP road grid (250 m blocks + a few main roads between the town centres).
    Only for testing without internet - distances are NOT the real Kaduwela roads."""
    rng = np.random.default_rng(seed)
    s, w, n, e = bbox
    step = 0.0024  # about 250 m
    lats = np.arange(s, n + step / 2, step)
    lngs = np.arange(w, e + step / 2, step)
    ids, lat_l, lng_l = [], [], []
    grid = {}
    k = 1
    for i, la in enumerate(lats):
        for j, lo in enumerate(lngs):
            grid[(i, j)] = k
            ids.append(k)
            lat_l.append(la + rng.normal(0, step * 0.12))
            lng_l.append(lo + rng.normal(0, step * 0.12))
            k += 1
    rows = []
    for (i, j), u in grid.items():
        for di, dj in ((1, 0), (0, 1)):
            v = grid.get((i + di, j + dj))
            if v is None or rng.random() < 0.12:  # some blocks have no road (paddy fields, canals)
                continue
            kind = "secondary" if (i % 8 == 0 and dj) or (j % 8 == 0 and di) else "residential"
            rows += [(u, v, kind, ""), (v, u, kind, "")]
    nodes = pd.DataFrame({"id": ids, "lat": lat_l, "lng": lng_l})
    # main roads: straight lines between the town centres, joined to the grid
    centres = {z: (v[0], v[1]) for z, v in S.ZONES.items()}
    links = [("Battaramulla", "Thalangama"), ("Thalangama", "Malabe"), ("Malabe", "Kaduwela"),
             ("Malabe", "Athurugiriya"), ("Malabe", "Hokandara"), ("Hokandara", "Athurugiriya")]
    tree = cKDTree(np.column_stack(to_xy(nodes.lat, nodes.lng, np.mean(lats))))
    for a, b in links:
        if a not in centres or b not in centres:
            continue
        (la1, lo1), (la2, lo2) = centres[a], centres[b]
        steps = max(2, int(haversine_m(la1, lo1, la2, lo2) / 300))
        prev = None
        for t in np.linspace(0, 1, steps + 1):
            la, lo = la1 + (la2 - la1) * t, lo1 + (lo2 - lo1) * t
            nid = k
            k += 1
            nodes.loc[len(nodes)] = [nid, la, lo]
            _, near = tree.query(np.column_stack(to_xy([la], [lo], np.mean(lats))))
            g = int(nodes.iloc[int(near[0])]["id"])
            rows += [(nid, g, "residential", ""), (g, nid, "residential", "")]
            if prev is not None:
                rows += [(prev, nid, "primary", f"{a} - {b} road"), (nid, prev, "primary", f"{a} - {b} road")]
            prev = nid
    edges = pd.DataFrame(rows, columns=["u", "v", "road_type", "name"])
    pos = nodes.set_index("id")
    edges["length_m"] = haversine_m(pos.loc[edges.u, "lat"].to_numpy(), pos.loc[edges.u, "lng"].to_numpy(),
                                    pos.loc[edges.v, "lat"].to_numpy(), pos.loc[edges.v, "lng"].to_numpy()).round(1)
    nodes["id"] = nodes["id"].astype(int)
    return nodes, edges[["u", "v", "length_m", "road_type", "name"]]


def save_roads(nodes, edges, info):
    nodes.to_csv(NODES_CSV, index=False)
    edges.to_csv(EDGES_CSV, index=False)
    with open(INFO_JSON, "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2)


# ---------------------------------------------------------------------------
# Travel times
# ---------------------------------------------------------------------------
def is_rush(hour):
    return any(a <= hour % 24 < b for a, b in S.RUSH_HOURS)


class RoadNetwork:
    def __init__(self, nodes=None, edges=None):
        if nodes is None:
            if not os.path.exists(NODES_CSV):
                raise SystemExit(f"Missing file: {NODES_CSV}\nRun first:  python r1_road_map.py")
            nodes = pd.read_csv(NODES_CSV)
            edges = pd.read_csv(EDGES_CSV, keep_default_na=False)
            with open(INFO_JSON, encoding="utf-8") as f:
                self.info = json.load(f)
        else:
            self.info = {}
        edges = edges[edges.u.isin(nodes.id) & edges.v.isin(nodes.id) & (edges.u != edges.v)]
        # two roads between the same two points: keep the shorter one
        edges = edges.sort_values("length_m").drop_duplicates(["u", "v"], keep="first")
        idx = pd.Series(np.arange(len(nodes)), index=nodes["id"].to_numpy())
        u = idx.loc[edges.u].to_numpy()
        v = idx.loc[edges.v].to_numpy()
        n = len(nodes)
        # keep only the biggest part of the network where every road can reach every other road
        g = csr_matrix((np.ones(len(u)), (u, v)), shape=(n, n))
        _, labels = connected_components(g, directed=True, connection="strong")
        main = np.bincount(labels).argmax()
        keep_nodes = labels == main
        keep = keep_nodes[u] & keep_nodes[v]
        new_index = -np.ones(n, dtype=int)
        new_index[keep_nodes] = np.arange(keep_nodes.sum())
        self.lat = nodes["lat"].to_numpy()[keep_nodes]
        self.lng = nodes["lng"].to_numpy()[keep_nodes]
        self.osm_id = nodes["id"].to_numpy()[keep_nodes]
        self.u = new_index[u[keep]]
        self.v = new_index[v[keep]]
        self.length = edges["length_m"].to_numpy(dtype=float)[keep]
        self.kind = edges["road_type"].to_numpy()[keep]
        self.name = edges["name"].astype(str).to_numpy()[keep]
        self.n = int(keep_nodes.sum())
        self.lat0 = float(np.mean(self.lat))
        self.tree = cKDTree(np.column_stack(to_xy(self.lat, self.lng, self.lat0)))
        base = np.array([S.ROAD_SPEED_KMH.get(k, S.ROAD_SPEED_KMH["other"]) for k in self.kind], dtype=float)
        self.speed_normal = base
        self.speed_rush = np.where(np.isin(self.kind, list(MAIN_ROADS)), base * S.RUSH_SLOWDOWN, base)
        self.blocked = np.zeros(len(self.u), dtype=bool)   # road closures
        self.jam = np.ones(len(self.u))                    # traffic jams: speed x factor

    # -- incidents --------------------------------------------------------------
    def edges_near(self, lat, lng, radius_m):
        mid_lat = (self.lat[self.u] + self.lat[self.v]) / 2
        mid_lng = (self.lng[self.u] + self.lng[self.v]) / 2
        return haversine_m(mid_lat, mid_lng, lat, lng) <= radius_m

    def clear_incidents(self):
        self.blocked[:] = False
        self.jam[:] = 1.0

    def add_incident(self, kind, lat, lng, radius_m=400, slowdown=0.25):
        """kind 'closure' = the roads near the point cannot be used; 'jam' = they are much slower."""
        near = self.edges_near(lat, lng, radius_m)
        if kind == "closure":
            self.blocked |= near
        else:
            self.jam = np.where(near, np.minimum(self.jam, slowdown), self.jam)
        return int(near.sum())

    # -- shortest paths ---------------------------------------------------------
    def nearest(self, lats, lngs):
        d, i = self.tree.query(np.column_stack(to_xy(lats, lngs, self.lat0)))
        return i.astype(int), d

    def edge_seconds(self, hour):
        speed = (self.speed_rush if is_rush(hour) else self.speed_normal) * self.jam
        secs = self.length / (speed / 3.6)
        return np.where(self.blocked, np.inf, secs)

    def matrices(self, node_ids, hour, want_paths=False):
        """Fastest-path travel time (s) and distance (m) between all the given road nodes."""
        secs = self.edge_seconds(hour)
        ok = np.isfinite(secs)
        g = csr_matrix((secs[ok], (self.u[ok], self.v[ok])), shape=(self.n, self.n))
        lengths_d = dict(zip(zip(self.u[ok].tolist(), self.v[ok].tolist()), self.length[ok].tolist()))
        node_ids = np.asarray(node_ids, dtype=int)
        times, pred = dijkstra(g, directed=True, indices=np.unique(node_ids), return_predecessors=True)
        row_of = {nid: r for r, nid in enumerate(np.unique(node_ids))}
        k = len(node_ids)
        T = np.zeros((k, k))
        D = np.zeros((k, k))
        paths = {}
        for i, a in enumerate(node_ids):
            r = row_of[a]
            for j, b in enumerate(node_ids):
                if i == j or a == b:
                    continue
                T[i, j] = times[r, b]
                if not np.isfinite(T[i, j]):
                    D[i, j] = np.inf
                    continue
                dist, cur, nodes = 0.0, b, [b]
                while cur != a:
                    p = pred[r, cur]
                    dist += lengths_d[(p, cur)]
                    cur = p
                    if want_paths:
                        nodes.append(cur)
                D[i, j] = dist
                if want_paths:
                    paths[(i, j)] = nodes[::-1]
        return (T, D, paths) if want_paths else (T, D)

    def path_coords(self, path_nodes):
        return list(zip(self.lat[path_nodes].round(6).tolist(), self.lng[path_nodes].round(6).tolist()))

    def segments_for_drawing(self, max_segments=60000):
        """Road segments (lng list, lat list) for a background map."""
        order = np.arange(len(self.u))
        if len(order) > max_segments:
            order = order[:: len(order) // max_segments + 1]
        return [([self.lng[self.u[i]], self.lng[self.v[i]]], [self.lat[self.u[i]], self.lat[self.v[i]]]) for i in order]


def timed(fn, *args, **kwargs):
    t0 = time.time()
    out = fn(*args, **kwargs)
    return out, time.time() - t0
