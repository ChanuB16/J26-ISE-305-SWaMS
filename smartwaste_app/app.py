"""
SMARTWASTE LK - WEB APP (Kaduwela Municipal Council)
====================================================
One program: the website + the live ML jobs (started from the System page).

Start:   python app.py
Open:    http://localhost:5000

Component 2 (IoT + ML smart bin) and Component 3 (waste forecast + truck routes).
Settings: settings.py
"""
import base64
import binascii
import csv
import functools
import io
import json
import os
import re
import secrets
import sys
import time
from datetime import date, datetime, timedelta

from flask import (Flask, Response, abort, g, jsonify, redirect, render_template, request, send_file, session,
                   url_for)

import data as D
import jobs as J
import results as R
import settings as S
import users as U
from fb import DBError, DemoDB, RestDB

HERE = os.path.dirname(os.path.abspath(__file__))
VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# database: settings.py, or the same database as ../smart_bin_ml/settings.py
# ---------------------------------------------------------------------------
def _db_settings():
    own = {"url": S.FIREBASE_DB_URL, "use_login": S.USE_LOGIN, "api_key": S.FIREBASE_API_KEY,
           "email": S.FIREBASE_EMAIL, "password": S.FIREBASE_PASSWORD, "from": "settings.py"}
    if own["url"] and "YOUR-PROJECT" not in own["url"]:
        return own
    import runpy
    for folder in (S.SMART_BIN_ML_DIR, S.WASTE_FORECAST_DIR):
        path = os.path.normpath(os.path.join(HERE, folder, "settings.py"))
        if not os.path.isfile(path):
            continue
        try:
            o = runpy.run_path(path)
        except Exception:  # their settings file has a mistake - ignore it here
            continue
        url = str(o.get("FIREBASE_DB_URL") or "")
        if url and "YOUR-PROJECT" not in url:
            return {"url": url, "use_login": bool(o.get("USE_LOGIN")), "api_key": o.get("FIREBASE_API_KEY", ""),
                    "email": o.get("FIREBASE_EMAIL", ""), "password": o.get("FIREBASE_PASSWORD", ""),
                    "from": os.path.relpath(path, HERE)}
    return {**own, "url": ""}


DBS = _db_settings()
DEMO = S.DEMO_MODE is True or (S.DEMO_MODE == "auto" and not DBS["url"])
if DEMO:
    db = DemoDB(os.path.join(HERE, "demo", "demo_db.json"))
else:
    db = RestDB(DBS["url"], DBS["use_login"], DBS["api_key"], DBS["email"], DBS["password"])
U.init(db)                              # user accounts live in the same database
results = R.Results()
runner = J.JobRunner()
if DEMO:
    runner.demo_url = f"http://127.0.0.1:{S.PORT}/fb"
else:
    runner.db = DBS   # the jobs use the same database as the app (set the URL in ONE place)


def copy_real_bin_data():
    """Before training (C2): copy the real bin's readings to smart_bin_ml/data/smart-bin-export.json,
    so b2_make_data.py learns the real sensor noise. Same as a Firebase console export."""
    if DEMO:
        yield "Demo mode: the demo bin's history is made up, so it is not used for training."
        return
    ids = [k for k in (db.get("bins", shallow=True) or {}) if not k.startswith("sim_") and not k.startswith("_")]
    out, n = {"bins": {}}, 0
    for i in ids:
        readings = db.get(f"bins/{i}/readings") or {}
        if readings:
            out["bins"][i] = {"readings": readings, "collections": db.get(f"bins/{i}/collections") or {}}
            n += len(readings)
    if not n:
        yield "Your real bin has not sent readings yet, so training uses synthetic data only."
        return
    path = os.path.join(J.project_dir("ml"), "data", "smart-bin-export.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f)
    yield f"Copied {n} real readings ({', '.join(out['bins'])}) to smart_bin_ml/data/smart-bin-export.json."


def forecast_missing_today():
    zones = [z for z in (db.get("forecasts", shallow=True) or {}) if not z.startswith("_")]
    return not zones or not db.get(f"forecasts/{zones[0]}/{D.today()}")


runner.before_setup = copy_real_bin_data
runner.forecast_missing = forecast_missing_today


# ---------------------------------------------------------------------------
# Flask app, login, CSRF protection
# ---------------------------------------------------------------------------
def _secret_key():
    path = os.path.join(HERE, "instance", "secret_key")
    try:
        with open(path, encoding="ascii") as f:
            key = f.read().strip()
            if len(key) >= 32:
                return key
    except OSError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    key = secrets.token_hex(32)
    with open(path, "w", encoding="ascii") as f:
        f.write(key)
    return key


app = Flask(__name__)
app.config.update(SECRET_KEY=_secret_key(), SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  PERMANENT_SESSION_LIFETIME=timedelta(days=14), MAX_CONTENT_LENGTH=2 * 1024 * 1024,
                  JSON_SORT_KEYS=False)
app.json.sort_keys = False

SAFE_ID = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
SAFE_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")

NAV = {
    "officer": [
        ("Operations", "/officer", "home"), ("Bins", "/officer/bins", "bin"), ("Forecast", "/officer/forecast", "chart"),
        ("Routes", "/officer/routes", "route"), ("Analytics", "/officer/analytics", "lab"),
        ("Reports", "/officer/reports", "file"), ("Community", "/officer/community", "people"),
        ("Driver view", "/driver", "truck"), ("System", "/officer/system", "gear"),
    ],
    "driver": [("My route", "/driver", "truck"), ("Usability survey", "/usability", "star")],
    "citizen": [("Home", "/citizen", "home"), ("Report", "/citizen/report", "alert"),
                ("Scan", "/citizen/scan", "camera"), ("Rewards", "/citizen/rewards", "gift"),
                ("Survey", "/usability", "star")],
}
HOME = {"officer": "/officer", "driver": "/driver", "citizen": "/citizen"}


def current_user():
    return session.get("user")


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(24)
    return session["csrf"]


@app.before_request
def protect():
    g.user = current_user()
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and not request.path.startswith("/fb/"):
        sent = request.headers.get("X-CSRF-Token") or request.form.get("csrf")
        if not sent or not secrets.compare_digest(str(sent), str(session.get("csrf", ""))):
            if request.path.startswith("/api/"):
                return jsonify(error="Your page is out of date. Reload it and try again."), 400
            return redirect(url_for("login_page", msg="Please try again."))


def page(*roles):
    def deco(f):
        @functools.wraps(f)
        def inner(*a, **kw):
            u = g.user
            if not u:
                return redirect(url_for("login_page", next=request.path))
            if roles and u["role"] not in roles and u["role"] != "officer":
                return redirect(HOME.get(u["role"], "/login"))
            return f(*a, **kw)
        return inner
    return deco


def api(*roles):
    def deco(f):
        @functools.wraps(f)
        def inner(*a, **kw):
            u = g.user
            if not u:
                return jsonify(error="Please log in again."), 401
            if roles and u["role"] not in roles and u["role"] != "officer":
                return jsonify(error="Your account cannot do this."), 403
            try:
                return f(*a, **kw)
            except DBError as e:
                return jsonify(error=str(e)), 503
            except ValueError as e:
                return jsonify(error=str(e)), 400
        return inner
    return deco


def body():
    return request.get_json(silent=True) or {}


def check_id(v, what="id"):
    if not v or not SAFE_ID.match(str(v)):
        raise ValueError(f"Bad {what}.")
    return str(v)


def render(template, title, active="", **ctx):
    u = g.user
    cfg = {"demo": DEMO, "refresh": S.REFRESH_SECONDS, "depot": list(S.DEPOT), "depot_name": S.DEPOT_NAME,
           "overflow": S.OVERFLOW_PCT, "alert": S.ALERT_PCT, "filling": S.FILLING_PCT, "space": S.SPACE_LIMIT_PCT,
           "smell": S.SMELL_INDEX, "maxKm": S.MAX_WALK_KM, "lowBattery": S.LOW_BATTERY_PCT,
           "urgencyMedium": S.URGENCY_MEDIUM, "urgencyHigh": S.URGENCY_HIGH, "susTarget": S.SUS_TARGET,
           "weights": {"fill": S.W_FILL, "gas": S.W_GAS, "humidity": S.W_HUMIDITY, "time": S.W_TIME},
           "fullTimeHours": S.FULL_TIME_HOURS, "user": u, "today": date.today().isoformat()}
    nav = NAV.get(u["role"], []) if u else []
    return render_template(template, title=title, active=active, nav=nav, user=u, demo=DEMO, cfg=cfg,
                           csrf=csrf_token(), version=VERSION, **ctx)


# ---------------------------------------------------------------------------
# pages
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    u = g.user
    return redirect(HOME.get(u["role"], "/login") if u else url_for("login_page"))


@app.route("/login", methods=["GET", "POST"])
def login_page():
    msg = request.args.get("msg", "")
    tab = request.args.get("tab", "citizen")
    nxt = request.args.get("next") or request.form.get("next") or ""
    if not nxt.startswith("/") or nxt.startswith("//"):
        nxt = ""
    if request.method == "POST":
        kind = request.form.get("kind")
        if kind == "citizen":
            u = U.login(request.form.get("username"), request.form.get("password"))
            if not u or u["role"] != "citizen":
                msg, tab = "Wrong user name or password.", "citizen"
                time.sleep(0.5)
            else:
                session.clear()
                session.permanent = True
                session["user"] = {"role": "citizen", "name": u["name"], "username": u["username"]}
                return redirect(nxt if nxt.startswith("/citizen") or nxt == "/usability" else "/citizen")
        elif kind == "citizen_signup":
            try:
                if request.form.get("password") != request.form.get("password2"):
                    raise ValueError("The two passwords are not the same.")
                u = U.create(request.form.get("username"), request.form.get("password"), "citizen",
                             request.form.get("name"))
                session.clear()
                session.permanent = True
                session["user"] = {"role": "citizen", "name": u["name"], "username": u["username"]}
                return redirect(nxt if nxt.startswith("/citizen") or nxt == "/usability" else "/citizen")
            except ValueError as e:
                msg, tab = str(e), "citizen_signup"
        elif kind == "staff":
            u = U.login(request.form.get("username"), request.form.get("password"))
            if not u:
                msg, tab = "Wrong user name or password (or the account is switched off).", "staff"
                time.sleep(0.5)
            else:
                session.clear()
                session.permanent = True
                session["user"] = {"role": u["role"], "name": u["name"], "username": u["username"], "truck": u["truck"]}
                return redirect(nxt or HOME[u["role"]])
        elif kind == "setup":
            if U.has_officer():
                msg = "An officer account already exists. Log in with it."
            else:
                try:
                    if request.form.get("password") != request.form.get("password2"):
                        raise ValueError("The two passwords are not the same.")
                    u = U.create(request.form.get("username"), request.form.get("password"), "officer",
                                 request.form.get("name"))
                    session.clear()
                    session.permanent = True
                    session["user"] = {"role": "officer", "name": u["name"], "username": u["username"], "truck": ""}
                    return redirect("/officer")
                except ValueError as e:
                    msg, tab = str(e), "setup"
    if not U.has_officer() and tab != "citizen":
        tab = "setup"
    return render("login.html", "Log in", msg=msg, tab=tab, next=nxt, first_run=not U.has_officer())


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login_page"))


OFFICER_PAGES = {
    "": ("officer/home.html", "Operations"), "bins": ("officer/bins.html", "Bin fleet"),
    "forecast": ("officer/forecast.html", "Waste forecast"), "routes": ("officer/routes.html", "Truck routes"),
    "analytics": ("officer/analytics.html", "Analytics"), "reports": ("officer/reports.html", "Report centre"),
    "community": ("officer/community.html", "Community"), "system": ("officer/system.html", "System"),
}


@app.route("/officer", defaults={"name": ""})
@app.route("/officer/<name>")
@page("officer")
def officer_page(name):
    if name not in OFFICER_PAGES:
        abort(404)
    tpl, title = OFFICER_PAGES[name]
    extra = {}
    if name == "system":
        extra = {"db_from": DBS["from"], "db_url": db.describe(), "results_info": results.info()}
    return render(tpl, title, active="/officer" + (f"/{name}" if name else ""), **extra)


@app.route("/officer/bins/<bin_id>")
@page("officer")
def bin_page(bin_id):
    if not SAFE_ID.match(bin_id):
        abort(404)
    return render("officer/bin.html", f"Bin {bin_id}", active="/officer/bins", bin_id=bin_id)


@app.route("/driver")
@page("driver")
def driver_page():
    return render("driver.html", "My route", active="/driver")


@app.route("/citizen", defaults={"name": ""})
@app.route("/citizen/<name>")
@page("citizen")
def citizen_page(name):
    pages = {"": ("citizen/home.html", "Find a bin"), "report": ("citizen/report.html", "Report a problem"),
             "rewards": ("citizen/rewards.html", "My green rewards"),
             "scan": ("citizen/scan.html", "Scan rubbish")}
    if name not in pages:
        abort(404)
    tpl, title = pages[name]
    return render(tpl, title, active="/citizen" + (f"/{name}" if name else ""))


@app.route("/usability")
@page()
def usability_page():
    return render("usability.html", "Usability survey", active="/usability")


@app.route("/results/<comp>/<name>")
@page("officer")
def result_chart(comp, name):
    if comp not in ("c2", "c3"):
        abort(404)
    p = results.chart_path(comp, name)
    if not p:
        abort(404)
    return send_file(p, mimetype="image/png", max_age=60)


# ---------------------------------------------------------------------------
# API (JSON) - the pages call these every few seconds
# ---------------------------------------------------------------------------
@app.route("/api/status")
@api()
def api_status():
    return jsonify(demo=DEMO, db=db.describe(), now=D.now_ms(),
                   jobs_running=[j["name"] for j in runner.states() if j["state"] == "running"])


@app.route("/api/overview")
@api("officer")
def api_overview():
    rows = D.bins(db)
    rt = D.routes(db, D.today())
    try:
        fc = D.forecasts(db, results)
    except DBError:
        fc = {"totals": [], "info": {}, "source": "none"}
    com = D.community(db)
    alerts = D.alerts(rows, fc["totals"][:2], rt["trucks"])
    return jsonify(kpis=D.kpis(rows, rt["trucks"]), alerts=alerts, bins=rows, forecast=fc["totals"],
                   forecast_info=fc["info"], forecast_source=fc["source"], routes=rt,
                   community={"reports_new": sum(1 for r in com["reports"] if r["status"] == "new"),
                              "reports": len(com["reports"]), "citizens": len(com["users"]),
                              "points": sum(u["points"] for u in com["users"])},
                   synthetic=any(r["synthetic"] for r in rows), at=D.now_ms())


@app.route("/api/bins")
@api("officer")
def api_bins():
    rows = D.bins(db)
    return jsonify(bins=rows, kpis=D.kpis(rows, []), alerts=D.alerts(rows), at=D.now_ms())


@app.route("/api/bins/<bin_id>")
@api("officer")
def api_bin(bin_id):
    out = D.bin_detail(db, check_id(bin_id, "bin"))
    if out is None:
        return jsonify(error=f"There is no bin called {bin_id}."), 404
    out["alerts"] = D.alerts([out["bin"]])
    return jsonify(out)


RANGES = {"6h": 6 * 3600, "24h": 24 * 3600, "3d": 3 * 86400, "7d": 7 * 86400}


def _range():
    day = request.args.get("day", "")
    if day:
        if not SAFE_DAY.match(day):
            raise ValueError("Bad date.")
        start = datetime.fromisoformat(day)
        a = int(start.timestamp() * 1000)
        return a, a + 86400000 - 1, f"day {day}", 86400
    rng = request.args.get("range", "24h")
    secs = RANGES.get(rng, RANGES["24h"])
    now = D.now_ms()
    return now - secs * 1000, None, rng, secs


@app.route("/api/bins/<bin_id>/readings")
@api("officer")
def api_readings(bin_id):
    bin_id = check_id(bin_id, "bin")
    a, b, label, secs = _range()
    rows = D.readings(db, bin_id, a, b)
    raw = len(rows)
    size = 0
    if raw > 1500:
        size = next((s for s in (300, 600, 900, 1800, 3600, 7200) if secs / s <= 1000), 14400)
        rows = D.bucket(rows, size)
    return jsonify(rows=rows, raw_count=raw, bucket_seconds=size, stats=D.reading_stats(rows), label=label,
                   start=a, end=b or D.now_ms())


@app.route("/api/bins/<bin_id>/readings.csv")
@api("officer")
def api_readings_csv(bin_id):
    bin_id = check_id(bin_id, "bin")
    a, b, label, _ = _range()
    rows = D.readings(db, bin_id, a, b)
    cols = ["time"] + D.READING_FIELDS
    for r in rows:
        r["time"] = datetime.fromtimestamp(r["ts"] / 1000).strftime("%Y-%m-%d %H:%M:%S")
        r["errors"] = " ".join(r.get("errors") or [])
    return csv_response(f"{bin_id}_readings_{label.replace(' ', '_')}.csv", rows, cols)


@app.route("/api/nearest")
@api()
def api_nearest():
    try:
        lat, lng = float(request.args["lat"]), float(request.args["lng"])
    except (KeyError, ValueError):
        raise ValueError("Bad location.")
    return jsonify(D.nearest_with_space(D.bins(db), lat, lng))


@app.route("/api/forecast")
@api("officer")
def api_forecast():
    return jsonify(D.forecasts(db, results))


@app.route("/api/routes")
@api("officer", "driver")
def api_routes():
    day = request.args.get("date") or D.today()
    if not SAFE_DAY.match(day):
        raise ValueError("Bad date.")
    out = dict(D.routes(db, day))
    live = {r["id"]: r for r in D.bins(db)}
    out["bins"] = [{k: r[k] for k in ("id", "name", "lat", "lng", "fill", "level", "pred", "risk", "urgency", "zone")}
                   for r in live.values() if r["lat"] is not None]
    if day == D.today():
        midnight = datetime.combine(date.today(), datetime.min.time()).timestamp() * 1000
        out["emptied_today"] = sorted(({"id": r["id"], "name": r["name"], "at": r["collected_recorded"]} for r in live.values()
                                       if r["collected_recorded"] and r["collected_recorded"] >= midnight), key=lambda x: -x["at"])
    if g.user["role"] == "driver" and g.user.get("truck"):
        out["my_truck"] = g.user["truck"]
    return jsonify(out)


@app.route("/api/route-days")
@api("officer")
def api_route_days():
    return jsonify(days=sorted((db.get("routes", shallow=True) or {}).keys(), reverse=True)[:60])


@app.route("/api/traffic", methods=["POST"])
@api("officer")
def api_traffic_add():
    b = body()
    kind = b.get("kind")
    if kind not in ("closure", "jam"):
        raise ValueError("Choose road closed or traffic jam.")
    lat, lng = float(b.get("lat")), float(b.get("lng"))
    note = str(b.get("note") or ("road closed" if kind == "closure" else "traffic jam"))[:120] + " (web app)"
    key = db.post("traffic", {"kind": kind, "lat": round(lat, 6), "lng": round(lng, 6), "radius_m": 300, "note": note,
                              "created_at": {".sv": "timestamp"}, "until": D.now_ms() + 3 * 3600000,
                              "by": g.user["username"]})
    D.cache.clear()
    return jsonify(ok=True, id=key)


@app.route("/api/traffic", methods=["DELETE"])
@app.route("/api/traffic/<tid>", methods=["DELETE"])
@api("officer")
def api_traffic_clear(tid=None):
    db.delete("traffic/" + check_id(tid) if tid else "traffic")
    D.cache.clear()
    return jsonify(ok=True)


@app.route("/api/replan", methods=["POST"])
@api("officer")
def api_replan():
    db.put("control/replan", {".sv": "timestamp"})
    D.cache.clear()
    return jsonify(ok=True, planner_running=any(j["name"] == "routes" and j["state"] == "running"
                                                for j in runner.states()))


@app.route("/api/trucks/<truck_id>/status", methods=["POST"])
@api("officer", "driver")
def api_truck_status(truck_id):
    truck_id = check_id(truck_id, "truck")
    st = body().get("status")
    if st not in ("available", "broken", "on_route", "at_depot"):
        raise ValueError("Bad status.")
    if g.user["role"] == "driver" and st not in ("broken", "available"):
        raise ValueError("Drivers can only report broken / fixed.")
    db.patch(f"trucks/{truck_id}", {"status": st, "status_by": g.user["username"], "status_ts": D.now_ms()})
    D.cache.clear()
    return jsonify(ok=True)


@app.route("/api/routes/<day>/<truck_id>/stops/<int:index>/done", methods=["POST"])
@api("officer", "driver")
def api_stop_done(day, truck_id, index):
    if not SAFE_DAY.match(day):
        raise ValueError("Bad date.")
    stop = D.mark_stop_done(db, day, check_id(truck_id, "truck"), index)
    return jsonify(ok=True, stop=stop)


@app.route("/api/community")
@api("officer")
def api_community():
    c = D.community(db)
    fc = D.forecasts(db, results)
    return jsonify(**c, guidance=fc["guidance"])


@app.route("/api/reports", methods=["POST"])
@api()
def api_report_add():
    b = body()
    kind = b.get("type")
    if kind not in D.REPORT_TYPES:
        raise ValueError("Choose what the problem is.")
    note = str(b.get("note") or "").strip()[:500]
    bin_id = b.get("bin_id") or ""
    if bin_id:
        check_id(bin_id, "bin")
    if kind == "overflowing_bin" and not bin_id:
        raise ValueError("Choose the bin that is overflowing.")
    rep = {"user": g.user["username"], "name": g.user["name"], "type": kind, "ts": {".sv": "timestamp"},
           "note": note, "status": "new", "source": "web app"}
    if bin_id:
        rep["bin_id"] = bin_id
        row = next((r for r in D.bins(db) if r["id"] == bin_id), None)
        if row and row["zone"]:
            rep["zone"] = row["zone"]
    try:
        if b.get("lat") is not None and b.get("lng") is not None:
            rep["lat"], rep["lng"] = round(float(b["lat"]), 6), round(float(b["lng"]), 6)
    except (TypeError, ValueError):
        pass
    photo = b.get("photo")
    if photo:
        if not isinstance(photo, str) or not photo.startswith("data:image/jpeg;base64,") or len(photo) > 600_000:
            raise ValueError("The photo is too big or not a JPEG. Try another photo.")
        try:
            base64.b64decode(photo.split(",", 1)[1], validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("The photo could not be read.")
        rep["has_photo"] = True
    key = db.post("reports", rep)
    if photo:
        db.put(f"report_photos/{key}", photo)
    D.cache.clear()
    return jsonify(ok=True, id=key)


@app.route("/api/reports/<rid>/status", methods=["POST"])
@api("officer")
def api_report_status(rid):
    st = body().get("status")
    if st not in D.REPORT_STATUS:
        raise ValueError("Bad status.")
    db.patch(f"reports/{check_id(rid, 'report')}", {"status": st, "status_by": g.user["username"],
                                                    "status_ts": D.now_ms()})
    D.cache.clear()
    return jsonify(ok=True)


@app.route("/api/reports/<rid>/photo")
@api()
def api_report_photo(rid):
    rid = check_id(rid, "report")
    if g.user["role"] != "officer":
        owner = db.get(f"reports/{rid}/user")
        if owner != g.user["username"]:
            abort(403)
    photo = db.get(f"report_photos/{rid}")
    if not isinstance(photo, str) or "," not in photo:
        abort(404)
    raw = base64.b64decode(photo.split(",", 1)[1])
    return Response(raw, mimetype="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


@app.route("/api/classify", methods=["POST"])
@api("citizen")
def api_classify():
    """Component 1 - the citizen Scan tab calls this.

    JSON body: {"photo": "data:image/jpeg;base64,...", "lang": "en"|"si"|"ta", "zone": "<opt>"}
    When the AI is confident the row is saved under classifications/<key> so the
    Officer Community page shows it and e1_rewards.py gives the citizen +10 points.
    """
    import classifier
    if not classifier.enabled():
        return jsonify(error="The waste scanner is switched off (CLASSIFIER_MODEL is empty "
                             "in settings.py)."), 503
    b = body()
    lang = (b.get("lang") or "en").strip()
    photo = b.get("photo") or ""
    if not isinstance(photo, str) or not photo.startswith("data:image/jpeg;base64,") \
            or len(photo) > 600_000:
        raise ValueError("The photo is too big or not a JPEG. Try another photo.")
    try:
        raw = base64.b64decode(photo.split(",", 1)[1], validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("The photo could not be read.")
    try:
        out = classifier.classify(raw, lang)
    except ImportError:
        return jsonify(error="The AI model is not installed on this computer. "
                             "Run: pip install tensorflow 'keras>=3.12' 'numpy<2.1' pillow"), 503
    except FileNotFoundError:
        return jsonify(error="The AI model file was not found. Check WASTE_CLASSIFIER_DIR "
                             "and CLASSIFIER_MODEL in settings.py."), 503
    if out["reliable"]:
        try:
            classifier.push(db, user=g.user["username"], waste_type=out["category"],
                            confidence=out["confidence"], zone=(b.get("zone") or ""))
            D.cache.clear()
        except DBError:
            pass   # the classification itself still goes back to the citizen
    return jsonify(**out)


@app.route("/api/citizen")
@api("citizen")
def api_citizen():
    out = D.citizen_view(db, g.user["username"])
    rows = D.bins(db)
    out["bins"] = [{k: r[k] for k in ("id", "name", "zone", "lat", "lng", "fill", "level", "pred")}
                   for r in rows if r["lat"] is not None]
    hist = {h["id"]: h for h in out["history"]}
    for r in out["reports"]:
        h = hist.get(r["id"])
        r["points"] = h.get("points") if h else None
        r["points_note"] = h.get("note") if h else None
    try:
        fc = D.forecasts(db, results)
        out["tips"] = fc["guidance"].get(D.today(), {})
        out["busy_today"] = next((t for t in fc["totals"] if t["date"] == D.today() and t["busy"]), None)
    except DBError:
        out["tips"], out["busy_today"] = {}, None
    return jsonify(out)


@app.route("/api/analytics")
@api("officer")
def api_analytics():
    return jsonify(R.analytics(results))


@app.route("/api/rq1")
@api("officer")
def api_rq1():
    days = {"1": 1, "7": 7, "30": 30, "all": 3650}.get(request.args.get("days", "7"), 7)
    rows = D.bins(db)
    real = [r["id"] for r in rows if not r["synthetic"]]
    bin_id = request.args.get("bin") or (real[0] if real else "bin_01")
    out = D.rq1(db, check_id(bin_id, "bin"), D.now_ms() - days * 86400000)
    out.update(bins=real, days=days)
    return jsonify(out)


@app.route("/api/sus", methods=["POST"])
@api()
def api_sus_add():
    answers = body().get("answers")
    if not isinstance(answers, list) or len(answers) != 10 or any(a not in (1, 2, 3, 4, 5) for a in answers):
        raise ValueError("Please answer all 10 questions.")
    score = sum((a - 1) if i % 2 == 0 else (5 - a) for i, a in enumerate(answers)) * 2.5
    db.post("sus", {"ts": {".sv": "timestamp"}, "role": g.user["role"], "user": g.user["username"],
                    "answers": answers, "score": score, "comment": str(body().get("comment") or "")[:500]})
    return jsonify(ok=True, score=score)


@app.route("/api/sus")
@api("officer")
def api_sus():
    data = db.get("sus") or {}
    rows = sorted((v for v in data.values() if isinstance(v, dict)), key=lambda r: r.get("ts") or 0)
    return jsonify(rows=rows, target=S.SUS_TARGET)


# ---- exports for the report centre ----
def csv_response(filename, rows, cols):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    for r in rows:
        w.writerow(["" if r.get(c) is None else (json.dumps(r[c]) if isinstance(r.get(c), (dict, list)) else r[c])
                    for c in cols])
    return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _t(ms):
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M") if ms else ""


@app.route("/api/export/<kind>.csv")
@api("officer")
def api_export(kind):
    today = D.today()
    if kind == "bins":
        rows = [dict(r) for r in D.bins(db)]
        for r in rows:
            r["last_reading"], r["last_emptied"] = _t(r["ts"]), _t(r["last_collected"])
            r["errors"] = " ".join(r["errors"])
        cols = ["id", "name", "zone", "type", "level", "fill", "pred", "risk", "hours_to_full", "urgency", "weight_kg",
                "gas_index", "temp_c", "humidity", "battery_pct", "last_reading", "last_emptied", "errors", "synthetic"]
        return csv_response(f"bins_{today}.csv", rows, cols)
    if kind == "alerts":
        rows = D.alerts(D.bins(db))
        return csv_response(f"alerts_{today}.csv", rows, ["level", "bin", "title", "text"])
    if kind == "collections":
        out = []
        for r in D.bins(db):
            cols_ = db.get(f"bins/{r['id']}/collections", last=200) or {}
            for k, c in cols_.items():
                c = c or {}
                out.append({"bin_id": r["id"], "name": r["name"], "zone": r["zone"],
                            "time": _t(D.num(c.get("ts")) or D.num(k)), "fill_before_pct": c.get("fill_before_pct"),
                            "weight_before_kg": c.get("weight_before_kg"), "fill_after_pct": c.get("fill_after_pct")})
            if not cols_ and r["last_collected"]:
                out.append({"bin_id": r["id"], "name": r["name"], "zone": r["zone"], "time": _t(r["last_collected"])})
        out.sort(key=lambda x: x["time"], reverse=True)
        return csv_response(f"collections_{today}.csv", out,
                            ["time", "bin_id", "name", "zone", "fill_before_pct", "weight_before_kg", "fill_after_pct"])
    if kind == "forecast":
        fc = D.forecasts(db, results)
        rows = [{"date": d, "zone": z, **fc["by_zone"][z][d]} for z in fc["zones"] for d in fc["days"]
                if d in fc["by_zone"][z]]
        return csv_response(f"forecast_{today}.csv", rows,
                            ["date", "zone", "forecast_t", "normal_t", "change_pct", "high_waste", "holiday", "rain_mm"])
    if kind == "routes":
        day = request.args.get("date") or today
        if not SAFE_DAY.match(day):
            raise ValueError("Bad date.")
        rt = D.routes(db, day)
        rows = [{"truck": t["name"], "stop": i + 1, **s} for t in rt["trucks"] for i, s in enumerate(t["stops"])]
        return csv_response(f"routes_{day}.csv", rows, ["truck", "stop", "eta", "bin_id", "name", "fill_pct", "done",
                                                       "lat", "lng"])
    if kind == "reports":
        c = D.community(db)
        rows = [{**r, "time": _t(D.num(r.get("ts")))} for r in c["reports"]]
        return csv_response(f"citizen_reports_{today}.csv", rows,
                            ["time", "type_label", "bin_id", "zone", "user", "status", "note", "has_photo"])
    if kind == "rewards":
        c = D.community(db)
        return csv_response(f"rewards_{today}.csv", c["users"], ["user", "points", "level"])
    if kind == "sus":
        data = db.get("sus") or {}
        rows = [{**v, "time": _t(D.num(v.get("ts"))), **{f"q{i + 1}": a for i, a in enumerate(v.get("answers") or [])}}
                for v in data.values() if isinstance(v, dict)]
        return csv_response(f"sus_{today}.csv", rows, ["time", "role", "user", "score"] + [f"q{i}" for i in range(1, 11)]
                            + ["comment"])
    abort(404)


# ---- users and jobs (System page) ----
@app.route("/api/users", methods=["GET", "POST"])
@api("officer")
def api_users():
    if request.method == "POST":
        b = body()
        if b.get("role") not in U.STAFF_ROLES:
            raise ValueError("Role must be officer or driver.")
        U.create(b.get("username"), b.get("password"), b.get("role"), b.get("name"), b.get("truck"))
    return jsonify(users=U.list_users(), roles=U.STAFF_ROLES,
                   trucks=sorted((db.get("trucks", shallow=True) or {}).keys()))


@app.route("/api/users/<username>", methods=["PATCH", "DELETE"])
@api("officer")
def api_user(username):
    if username == g.user["username"]:
        raise ValueError("You cannot change or remove your own account here.")
    existing = U.get(username)
    if not existing or existing["role"] not in U.STAFF_ROLES:
        raise ValueError("Only staff accounts can be changed here.")
    if request.method == "DELETE":
        U.delete(username)
    else:
        b = body()
        if "role" in b and b["role"] not in U.STAFF_ROLES:
            raise ValueError("Role must be officer or driver.")
        U.update(username, **{k: b[k] for k in ("name", "truck", "active", "role", "password") if k in b})
    return jsonify(users=U.list_users())


@app.route("/api/jobs")
@api("officer")
def api_jobs():
    states = runner.states()
    return jsonify(setup=[s for s in states if s["name"] in J.SETUP or s["name"] in J.SETUP_EXTRA],
                   jobs=[s for s in states if s["name"] in J.LIVE], pipelines={k: p.info() for k, p in runner.pipelines.items()},
                   automation=runner.automation(), demo=DEMO)


@app.route("/api/jobs/<name>/<action>", methods=["POST"])
@api("officer")
def api_job(name, action):
    if action == "start":
        if runner.busy_pipeline() and name in J.SETUP:
            raise ValueError("The first-time setup is running. Wait until it finishes.")
        st = runner.start(name)
    elif action == "stop":
        st = runner.stop(name)
    else:
        abort(404)
    D.cache.clear()
    return jsonify(job=st)


@app.route("/api/setup/<name>/<action>", methods=["POST"])
@api("officer")
def api_setup(name, action):
    if action == "run":
        return jsonify(pipeline=runner.run_pipeline(name))
    if action == "stop":
        return jsonify(pipeline=runner.stop_pipeline(name))
    abort(404)


@app.route("/api/automation", methods=["POST"])
@api("officer")
def api_automation():
    return jsonify(automation=runner.set_automation(body()))


@app.route("/api/health")
@api("officer")
def api_health():
    return jsonify(checks=health_checks())


def health_checks():
    """The "Is everything working?" list on the System page. Each item can have a fix button."""
    out = []

    def add(key, ok, title, detail, fix=None):
        out.append({"key": key, "ok": ok, "title": title, "detail": detail, "fix": fix})
    try:
        rows = D.bins(db)
        add("db", True, "Database", "Demo data (in memory)" if DEMO else f"Firebase {db.describe()} answers")
    except DBError as e:
        add("db", False, "Database", str(e))
        rows = []
    real = [r for r in rows if not r["synthetic"]]
    if not real:
        add("bin", False, "Smart bin sending", "No real bin has sent data yet. Switch the bin on (battery switch) "
            "and check its WiFi (Serial Monitor: type wifi).")
    else:
        for r in real:
            fresh = not r["stale"]
            add("bin_" + r["id"], fresh, f"Smart bin {r['id']} sending",
                f"Last reading {_ago(r['ts'])}." + ("" if fresh else " Check power and WiFi (Serial Monitor: type wifi)."))
    st = {s["name"]: s for s in runner.states()}

    def setup_item(step, label):
        s = st[step]
        if s["done"]["exists"]:
            add(step, True, label, f"Done ({_t(s['done']['updated'])}).")
        else:
            add(step, False, label, "Not done yet (first-time setup).",
                {"pipeline": "c2" if step.startswith("c2") else "c3", "label": "Run setup"})
    setup_item("c2_train", "Fill prediction model trained (Component 2)")
    setup_item("c2_test", "Urgency and nearest-bin tests (Component 2)")
    setup_item("c3_train", "Forecast model trained (Component 3)")
    roads = {"done": J.file_info("wf", "data/roads_info.json")}
    if roads["done"]["exists"]:
        try:
            with open(os.path.join(J.project_dir("wf"), "data", "roads_info.json"), encoding="utf-8") as f:
                src = json.load(f).get("source", "")
        except (OSError, ValueError):
            src = ""
        demo_roads = "DEMO" in src.upper()
        add("c3_roads", "warn" if demo_roads else True, "Road map",
            ("Made-up road grid (no internet when it was made). Run “Download the road map” when you have internet."
             if demo_roads else f"{src or 'Real roads'} ({_t(roads['done']['updated'])})."),
            {"job": "c3_roads", "label": "Download roads"} if demo_roads else None)
    else:
        add("c3_roads", False, "Road map", "Not downloaded yet.", {"job": "c3_roads", "label": "Download roads"})
    setup_item("c3_test", "Route method test (Component 3)")
    a = runner.automation()
    for n, label in (("predictions", "Live bin predictions"), ("routes", "Live route planner")):
        s = st[n]
        if s["state"] == "running":
            add(n, True, label, f"Running (started {_ago(s['started'])} by {s['by']}).")
        elif s["blocked"]:
            add(n, False, label, f"Waiting: {s['blocked']}.")
        else:
            why = "failed 3 times – open its output" if len(runner.jobs[n].fails) >= 3 else \
                "stopped by you" if runner.jobs[n].stopped_by_user else \
                "automatic mode will start it in a moment" if a["autostart"] else "not running"
            add(n, False, label, f"Not running ({why}).", {"job": n, "label": "Start"})
    preds = [r for r in real if r["pred"] is not None]
    if real:
        if preds and all(r["pred_at"] and D.now_ms() - r["pred_at"] < 20 * 60000 for r in preds):
            add("pred_fresh", True, "Predictions up to date", f"Newest {_ago(max(r['pred_at'] for r in preds))}.")
        else:
            add("pred_fresh", False, "Predictions up to date", "No new prediction in the last 20 minutes "
                "(the live predictions need about 1 hour of readings from the bin).")
    try:
        missing = forecast_missing_today()
    except DBError:
        missing = True
    fc_blocked = st["forecast"]["blocked"]
    add("forecast_today", not missing, "Forecast for today",
        "In the database." if not missing else f"Not made yet – {fc_blocked}." if fc_blocked else
        "Running now." if st["forecast"]["state"] == "running" else
        "Not made yet." + (" Automatic mode makes it soon." if a["forecast_daily"] else ""),
        None if not missing or st["forecast"]["state"] == "running" else
        {"pipeline": "c3", "label": "Run setup"} if fc_blocked else {"job": "forecast", "label": "Make forecast"})
    rt = D.routes(db, D.today())
    add("routes_today", bool(rt["summary"]), "Routes for today",
        f"{rt['summary']['planned']} bins planned, made {_ago(rt['summary']['made_at'])}." if rt["summary"]
        else "No plan yet (the route planner makes it when it runs).")
    return out


def _ago(ms):
    if not ms:
        return "never"
    m = (D.now_ms() - ms) / 60000
    return "just now" if m < 1 else f"{m:.0f} min ago" if m < 90 else f"{m / 60:.1f} h ago" if m < 2880 else f"{m / 1440:.0f} days ago"


@app.route("/api/jobs/<name>/log")
@api("officer")
def api_job_log(name):
    return jsonify(lines=runner.log(name))


# ---------------------------------------------------------------------------
# Demo mode: a small Firebase-like REST door so the ML jobs can use the demo data.
# Only from this computer, only in demo mode.
# ---------------------------------------------------------------------------
@app.route("/fb/", defaults={"path": ".json"}, methods=["GET", "PUT", "PATCH", "POST", "DELETE"])
@app.route("/fb/<path:path>", methods=["GET", "PUT", "PATCH", "POST", "DELETE"])
def fake_firebase(path):
    if not DEMO or request.remote_addr not in ("127.0.0.1", "::1"):
        abort(404)
    if not path.endswith(".json"):
        abort(404)
    p = path[:-5].strip("/")
    a = request.args

    def unq(v):
        return json.loads(v) if v is not None else None
    if request.method == "GET":
        out = db.get(p, shallow=a.get("shallow") == "true", start=unq(a.get("startAt")), end=unq(a.get("endAt")),
                     first=a.get("limitToFirst"), last=a.get("limitToLast"))
        return Response(json.dumps(out), mimetype="application/json")
    value = request.get_json(force=True, silent=True) if request.data else None
    if request.method == "PUT":
        db.put(p, value)
    elif request.method == "PATCH":
        db.patch(p, value or {})
    elif request.method == "POST":
        return Response(json.dumps({"name": db.post(p, value)}), mimetype="application/json")
    elif request.method == "DELETE":
        db.delete(p)
    D.cache.clear()
    if a.get("print") == "silent":
        return Response(status=204)
    return Response(json.dumps(value), mimetype="application/json")


@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return jsonify(error="Not found."), 404
    return render("error.html", "Not found", message="This page does not exist."), 404


@app.errorhandler(413)
def too_big(e):
    return jsonify(error="The upload is too big (2 MB max)."), 413


# ---------------------------------------------------------------------------
def main():
    print("=" * 64)
    print(" SmartWaste LK web app", VERSION)
    if DEMO:
        print(" Data: DEMO data (demo/demo_db.json). Changes are lost when you stop the app.")
        if S.DEMO_MODE == "auto":
            print(" To use Firebase: set FIREBASE_DB_URL in settings.py (or in ../smart_bin_ml/settings.py).")
    else:
        print(" Data: Firebase", db.describe(), f"(from {DBS['from']})")
    for name in S.AUTO_START_JOBS:
        try:
            runner.start(name, by="settings.py")
            print(" Started job:", name)
        except ValueError as e:
            print(" Could not start job", name, "-", e)
    a = runner.automation()
    print(" Automatic mode:", "ON (starts the live jobs, daily forecast, rewards)" if a["autostart"] or a["forecast_daily"]
          else "OFF (turn it on on the System page)")
    runner.start_scheduler()
    host = "localhost" if S.HOST in ("127.0.0.1", "localhost") else S.HOST
    print(f" Open: http://{host}:{S.PORT}")
    if S.HOST == "0.0.0.0":
        print(" Phones on the same WiFi: http://<this computer's IP address>:%d" % S.PORT)
    if not U.has_officer():
        print(" First time: open the page and create the first officer account.")
    print(" Stop: Ctrl+C")
    print("=" * 64)
    app.run(host=S.HOST, port=S.PORT, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    main()
