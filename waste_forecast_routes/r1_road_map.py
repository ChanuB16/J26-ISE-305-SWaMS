"""
R1 - GET THE ROAD MAP OF THE AREA
=================================
Downloads the real roads of the Kaduwela area from OpenStreetMap (free, no key) and finds the
road point nearest to every bin and to the depot. The route planner (R2, R3) drives on these roads.

The bins: the 20 synthetic bins of Part B (read from ../smart_bin_ml/data/bins.csv if that folder
is next to this one - otherwise the same 20 places are made here) + your real bin (bin_01).

Run:  python r1_road_map.py            (needs internet once; about 1-3 minutes)
      python r1_road_map.py --again    (download the roads again)
      python r1_road_map.py --demo     (NO internet: a made-up road grid, ONLY for testing -
                                        the distances are not the real roads)
Makes: data/roads_nodes.csv, data/roads_edges.csv, data/roads_info.json, data/bins.csv,
       results/chart_r1_map.png, results/map_r1.html (open it in a web browser)
"""
import argparse
import os

import numpy as np
import pandas as pd

import charts
import maps
import settings as S
from roads import EDGES_CSV, NODES_CSV, RoadNetwork, area_bbox, download_osm_roads, make_demo_roads, save_roads
from wastelib import DATA_DIR, RESULTS_DIR, ensure_dirs

PART_B_BINS = os.path.join("..", "smart_bin_ml", "data", "bins.csv")
# the same 20 places as Part B (b2_make_data.py)
BIN_PLAN = [
    ("Malabe", "market"), ("Malabe", "bus_stop"), ("Malabe", "residential"), ("Malabe", "school"),
    ("Malabe", "office"), ("Kaduwela", "market"), ("Kaduwela", "bus_stop"), ("Kaduwela", "residential"),
    ("Kaduwela", "temple"), ("Battaramulla", "office"), ("Battaramulla", "residential"),
    ("Battaramulla", "market"), ("Battaramulla", "school"), ("Athurugiriya", "residential"),
    ("Athurugiriya", "bus_stop"), ("Athurugiriya", "temple"), ("Thalangama", "residential"),
    ("Thalangama", "school"), ("Hokandara", "residential"), ("Hokandara", "market"),
]


def make_bins():
    if os.path.exists(PART_B_BINS):
        b = pd.read_csv(PART_B_BINS)[["bin_id", "name", "zone", "type", "lat", "lng"]]
        source = f"Part B ({PART_B_BINS})"
    else:
        rng = np.random.default_rng(S.SEED)
        rows = []
        for i, (zone, kind) in enumerate(BIN_PLAN, start=1):
            lat0, lng0 = S.ZONES[zone][0], S.ZONES[zone][1]
            rows.append({"bin_id": f"sim_{i:02d}", "name": f"{zone} {kind.replace('_', ' ')}", "zone": zone,
                         "type": kind, "lat": round(lat0 + rng.normal(0, 0.006), 6),
                         "lng": round(lng0 + rng.normal(0, 0.006), 6)})
        b = pd.DataFrame(rows)
        source = "made here (Part B folder not found next to this one)"
    real = dict(S.REAL_BIN)
    real["name"] = "Real smart bin (Part A)"
    b = pd.concat([b[b.bin_id != real["bin_id"]], pd.DataFrame([real])], ignore_index=True)
    b["synthetic"] = b["bin_id"].str.startswith("sim_")
    return b, source


def main():
    ap = argparse.ArgumentParser(description="Download the road map")
    ap.add_argument("--again", action="store_true", help="download the roads again")
    ap.add_argument("--demo", action="store_true", help="made-up road grid (no internet, testing only)")
    args = ap.parse_args()
    ensure_dirs()
    print("R1 - get the road map of the area")
    bins, source = make_bins()
    bins.to_csv(os.path.join(DATA_DIR, "bins.csv"), index=False)
    print(f"Bins: {len(bins)} ({int(bins.synthetic.sum())} synthetic from {source} + the real bin) -> data/bins.csv")

    points = [(v[0], v[1]) for v in S.ZONES.values()] + [S.DEPOT] + list(zip(bins.lat, bins.lng))
    bbox = area_bbox(points, margin_km=2.0)
    if args.demo:
        nodes, edges = make_demo_roads(bbox, S.SEED)
        info = {"source": "DEMO grid (made up, NOT real roads)", "bbox": bbox}
        save_roads(nodes, edges, info)
        print("Roads: DEMO grid made up for testing - distances are NOT the real roads. "
              "Run again without --demo when you have internet.")
    elif os.path.exists(NODES_CSV) and os.path.exists(EDGES_CSV) and not args.again:
        print("Roads: already downloaded (use --again to download them again)")
    else:
        print(f"Roads: downloading OpenStreetMap roads for the area "
              f"(lat {bbox[0]:.3f} to {bbox[2]:.3f}, lng {bbox[1]:.3f} to {bbox[3]:.3f})")
        try:
            nodes, edges = download_osm_roads(bbox)
        except Exception as e:
            raise SystemExit(f"Could not download the roads ({e}).\nCheck the internet connection and try again "
                             "later, or test with:  python r1_road_map.py --demo")
        save_roads(nodes, edges, {"source": "OpenStreetMap (Overpass API)", "bbox": bbox,
                                  "downloaded": pd.Timestamp.now(tz="Asia/Colombo").strftime("%Y-%m-%d %H:%M")})
        print(f"  saved {len(nodes):,} road points and {len(edges):,} road pieces")

    net = RoadNetwork()
    print(f"Road network: {net.n:,} points, {len(net.u):,} one-way pieces, "
          f"{net.length.sum() / 2000:,.0f} km of road ({net.info.get('source')})")
    lats = [S.DEPOT[0]] + list(bins.lat)
    lngs = [S.DEPOT[1]] + list(bins.lng)
    ids, snap = net.nearest(lats, lngs)
    far = [(name, d) for name, d in zip(["Depot"] + list(bins.bin_id), snap) if d > 300]
    print(f"Nearest road point: on average {np.mean(snap):.0f} m from a bin"
          + (f"; far from a road (check the location): {', '.join(f'{n} {d:.0f} m' for n, d in far)}" if far else ""))
    T6, D6 = net.matrices(ids, 6.0)
    T8, D8 = net.matrices(ids, 8.0)
    from_depot = pd.DataFrame({"bin": bins.bin_id, "min": T6[0, 1:] / 60, "km": D6[0, 1:] / 1000})
    slow = np.nanmean(T8[T6 > 0] / T6[T6 > 0])
    print(f"From the depot at 6 am: nearest bin {from_depot['min'].min():.0f} min, farthest "
          f"{from_depot['min'].max():.0f} min ({from_depot.loc[from_depot['min'].idxmax(), 'bin']}, "
          f"{from_depot['km'].max():.1f} km)")
    print(f"At 8 am (rush hour) the same trips take {100 * (slow - 1):.0f}% longer on average")

    # pictures
    title = "Road map and bins" + (" (DEMO grid - not real roads)" if "DEMO" in net.info.get("source", "") else "")
    charts.route_map(net.segments_for_drawing(), {}, [dict(lng=r.lng, lat=r.lat, label=r.bin_id, collected=True)
                                                    for r in bins.itertuples()],
                     S.DEPOT, os.path.join(RESULTS_DIR, "chart_r1_map.png"), title,
                     f"{len(bins)} bins and the depot, {net.info.get('source')}")
    maps.write_map(os.path.join(RESULTS_DIR, "map_r1.html"), "Kaduwela smart bins and depot",
                   f"{len(bins)} bins ({int(bins.synthetic.sum())} synthetic) - click a bin for details",
                   S.DEPOT, S.DEPOT_NAME,
                   [dict(lat=r.lat, lng=r.lng, label=f"{r.bin_id} - {r.name}", fill=None,
                         extra=f"{r.zone}, {r.type.replace('_', ' ')}"
                               + (" (synthetic)" if r.synthetic else " (real bin)")) for r in bins.itertuples()])
    print("Saved: results/chart_r1_map.png, results/map_r1.html (open it in a web browser)")
    print("Done. Next: python r2_test_routes.py")


if __name__ == "__main__":
    main()
