"""
Runs the Python scripts of the two ML projects for you, so you never need a terminal for them:

  - FIRST-TIME SETUP: make the data, train the models, run the tests (System page, one button).
  - LIVE JOBS: predictions, route planner (keep running), forecast, rewards, tips (run now and then).
  - AUTOMATIC MODE: starts the live jobs when the app starts, restarts them if they stop,
    makes the forecast + crew tips every day, and gives reward points every few minutes.

Each script runs as its own process with the script files unchanged. Its printed output is kept
and shown on the System page. In demo mode the scripts read and write the app's demo data.
"""
import atexit
import collections
import json
import os
import subprocess
import sys
import threading
import time
from datetime import date, datetime

import settings as S

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(HERE, "instance")

# Runs a script with the database settings replaced - the script files are not changed.
WRAPPER = (
    "import os, sys, runpy\n"
    "sys.path.insert(0, os.getcwd())\n"
    "url = os.environ.get('SMARTWASTE_FIREBASE_URL')\n"
    "if url:\n"
    "    import settings\n"
    "    settings.FIREBASE_DB_URL = url\n"
    "    settings.USE_LOGIN = os.environ.get('SMARTWASTE_USE_LOGIN') == '1'\n"
    "    if settings.USE_LOGIN:\n"
    "        settings.FIREBASE_API_KEY = os.environ.get('SMARTWASTE_API_KEY', '')\n"
    "        settings.FIREBASE_EMAIL = os.environ.get('SMARTWASTE_EMAIL', '')\n"
    "        settings.FIREBASE_PASSWORD = os.environ.get('SMARTWASTE_PASSWORD', '')\n"
    "sys.argv = sys.argv[1:]\n"
    "runpy.run_path(sys.argv[0], run_name='__main__')\n"
)

# ---- first-time setup steps (in this order). "makes" = the file that shows the step is done ----
SETUP = {
    "c2_data": {"title": "Make the training data", "component": "C2", "dir": "ml", "script": "b2_make_data.py",
                "args": [], "makes": "data/readings.csv", "minutes": "under 1",
                "what": "60 days of bin readings (synthetic, plus your real bin's data if it has sent some)."},
    "c2_train": {"title": "Train the fill prediction models", "component": "C2", "dir": "ml",
                 "script": "b3_train_models.py", "args": [], "makes": "results/model.joblib", "minutes": "1-3",
                 "what": "Trains and compares the models (RQ2), saves the best one for the live predictions."},
    "c2_test": {"title": "Test urgency ranking and nearest bin", "component": "C2", "dir": "ml",
                "script": "b4_test_urgency_and_nearest.py", "args": [], "makes": "results/rq4_nearest.csv",
                "minutes": "under 1", "what": "RQ3 (which bins to collect first) and RQ4 (nearest bin with space)."},
    "c3_data": {"title": "Make the waste history data", "component": "C3", "dir": "wf", "script": "f1_make_data.py",
                "args": [], "makes": "data/waste_daily.csv", "minutes": "under 1",
                "what": "2 years of daily waste per area with holidays, festivals, events and weather."},
    "c3_train": {"title": "Train the forecast models", "component": "C3", "dir": "wf", "script": "f2_train_forecast.py",
                 "args": [], "makes": "results/forecast_model.joblib", "minutes": "2-6",
                 "what": "Compares moving average, last week, linear regression, gradient boosting and LSTM; "
                         "saves the best."},
    "c3_roads": {"title": "Download the road map", "component": "C3", "dir": "wf", "script": "r1_road_map.py",
                 "args": [], "makes": "data/roads_info.json", "minutes": "1-3", "internet": True,
                 "what": "Real roads of Kaduwela from OpenStreetMap (needs internet once)."},
    "c3_test": {"title": "Test the route methods (30 days)", "component": "C3", "dir": "wf",
                "script": "r2_test_routes.py", "args": [], "makes": "results/r2_methods.csv", "minutes": "2-5",
                "what": "Fixed schedule vs reactive vs predictive routes, re-planning speed."},
}
SETUP_EXTRA = {
    "c3_roads_demo": {"title": "Road map without internet (made-up grid)", "component": "C3", "dir": "wf",
                      "script": "r1_road_map.py", "args": ["--demo"], "makes": "data/roads_info.json",
                      "minutes": "under 1",
                      "what": "ONLY if the real road map cannot be downloaded. Routes are then on made-up roads."},
}
PIPELINES = {"c2": ["c2_data", "c2_train", "c2_test"], "c3": ["c3_data", "c3_train", "c3_roads", "c3_test"]}
PIPELINES["all"] = PIPELINES["c2"] + PIPELINES["c3"]

# ---- live jobs ----
LIVE = {
    "predictions": {"title": "Live bin predictions", "component": "C2", "dir": "ml", "script": "b5_live_predictions.py",
                    "args": [], "service": True, "needs": [("ml", "results/model.joblib", "c2_train")],
                    "what": "Every 5 minutes: predicts each bin's fill in 6 hours, the overflow risk and the urgency "
                            "score (writes predictions/)."},
    "routes": {"title": "Live route planner", "component": "C3", "dir": "wf", "script": "r3_live_routes.py",
               "args": [], "service": True, "needs": [("wf", "data/roads_info.json", "c3_roads")],
               "what": "Plans the truck routes and re-plans them when a road closes, a truck breaks or bins fill up "
                       "(writes routes/)."},
    "forecast": {"title": "7-day waste forecast", "component": "C3", "dir": "wf",
                 "script": "f3_forecasts_to_firebase.py", "args": [], "service": False,
                 "needs": [("wf", "results/forecast_model.joblib", "c3_train")],
                 "what": "Forecasts the tonnes of waste per area for the next 7 days (writes forecasts/)."},
    "tips": {"title": "Crew tips", "component": "C3", "dir": "wf", "script": "e2_crew_tips.py", "args": [],
             "service": False, "needs": [], "what": "Tips for the collection crews for the next busy days (writes guidance/)."},
    "rewards": {"title": "Give reward points", "component": "C3", "dir": "wf", "script": "e1_rewards.py",
                "args": [], "service": False, "needs": [],
                "what": "Gives points for waste photos (Component 1) and confirmed full-bin reports."},
    "demo_bins": {"title": "Add 20 demo bins", "component": "C2", "dir": "ml", "script": "b6_demo_bins.py",
                  "args": ["--add"], "service": False, "needs": [("ml", "data/readings.csv", "c2_data")],
                  "what": "Adds 20 example bins around Kaduwela (sim_01 … sim_20) so the map and routes have bins."},
    "demo_bins_remove": {"title": "Remove the demo bins", "component": "C2", "dir": "ml", "script": "b6_demo_bins.py",
                         "args": ["--remove"], "service": False, "needs": [], "what": "Removes sim_01 … sim_20 again."},
    "trucks": {"title": "Truck simulator (demo)", "component": "C3", "dir": "wf", "script": "r4_truck_simulator.py",
               "args": ["--speed", "20"], "service": True, "needs": [],
               "what": "Moves the trucks along their routes (20x faster than real time) and empties the demo bins. "
                       "Only for demos - real trucks use the driver page."},
}
ALL = {**SETUP, **SETUP_EXTRA, **LIVE}

DEFAULT_AUTO_LIVE = {"autostart": True, "forecast_daily": True, "forecast_time": "05:00", "rewards_minutes": 10}
DEFAULT_AUTO_DEMO = {"autostart": False, "forecast_daily": False, "forecast_time": "05:00", "rewards_minutes": 0}


def project_dir(which):
    base = S.SMART_BIN_ML_DIR if which == "ml" else S.WASTE_FORECAST_DIR
    return os.path.normpath(os.path.join(HERE, base))


def file_info(which, rel):
    p = os.path.join(project_dir(which), rel)
    if os.path.isfile(p):
        return {"exists": True, "updated": int(os.path.getmtime(p) * 1000)}
    return {"exists": False, "updated": None}


def roads_are_made_up():
    try:
        with open(os.path.join(project_dir("wf"), "data", "roads_info.json"), encoding="utf-8") as f:
            return "DEMO" in str(json.load(f).get("source", "")).upper()
    except (OSError, ValueError):
        return False


def _read_json(name, default):
    try:
        with open(os.path.join(STATE_DIR, name), encoding="utf-8") as f:
            return {**default, **json.load(f)}
    except (OSError, ValueError):
        return dict(default)


def _write_json(name, value):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = os.path.join(STATE_DIR, name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(value, f, indent=1)
    os.replace(tmp, os.path.join(STATE_DIR, name))


class Job:
    def __init__(self, name, spec):
        self.name, self.spec = name, spec
        self.proc = None
        self.log = collections.deque(maxlen=500)
        self.started = self.ended = None
        self.exit_code = None
        self.stopped_by_user = False
        self.fails = []          # times it failed (automatic restarts give up after 3 in 30 min)
        self.by = ""             # "you", "automatic", "setup"

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def state(self):
        d = project_dir(self.spec["dir"])
        script = os.path.join(d, self.spec["script"])
        if self.running():
            st = "running"
        elif self.proc is None:
            st = "missing" if not os.path.isfile(script) else "not started"
        elif self.stopped_by_user:
            st = "stopped"
        else:
            st = "finished" if self.exit_code == 0 else "failed"
        out = {"name": self.name, **{k: v for k, v in self.spec.items() if k not in ("dir", "needs")},
               "folder": d, "state": st, "started": self.started, "ended": self.ended, "exit_code": self.exit_code,
               "by": self.by,
               "last_line": next((x for x in reversed(self.log) if not x.startswith("[finished")
                                  and not x.startswith("[stopped")), "")}
        if "makes" in self.spec:
            out["done"] = file_info(self.spec["dir"], self.spec["makes"])
            if self.name in ("c3_roads", "c3_roads_demo") and out["done"]["exists"]:
                made_up = roads_are_made_up()
                if made_up != (self.name == "c3_roads_demo"):
                    out["done"] = {"exists": False, "updated": None}
        missing = [m for m in self.missing_needs()]
        out["blocked"] = missing[0] if missing else None
        return out

    def missing_needs(self):
        for which, rel, step in self.spec.get("needs", []):
            if not file_info(which, rel)["exists"]:
                yield f"needs first-time setup: “{SETUP[step]['title']}”"


class Pipeline:
    def __init__(self, name, steps):
        self.name, self.steps = name, steps
        self.state, self.current, self.stop_asked = "running", None, False
        self.started, self.ended = int(time.time() * 1000), None
        self.log = collections.deque(maxlen=100)

    def info(self):
        return {"name": self.name, "steps": self.steps, "state": self.state, "current": self.current,
                "started": self.started, "ended": self.ended, "log": list(self.log)}


class JobRunner:
    def __init__(self):
        self.jobs = {n: Job(n, s) for n, s in ALL.items()}
        self.lock = threading.Lock()
        self.demo_url = None   # demo mode: the app's own Firebase-like door
        self.db = None         # live mode: dict(url, use_login, api_key, email, password) given to the jobs
        self.pipelines = {}
        self.before_setup = None      # function run before the C2 setup (copies the real bin's data)
        self.forecast_missing = None  # function: True when the database has no forecast for today
        self.auto = None
        self.auto_state = _read_json("automation_state.json", {"forecast_day": "", "forecast_try": 0,
                                                               "rewards_last": 0})
        self._sched = None
        atexit.register(self.stop_all)

    # ---------------- single jobs ----------------
    def start(self, name, by="you"):
        job = self.jobs.get(name)
        if not job:
            raise ValueError("Unknown job.")
        with self.lock:
            if job.running():
                raise ValueError(f"{job.spec['title']} is already running.")
            d = project_dir(job.spec["dir"])
            script = os.path.join(d, job.spec["script"])
            if not os.path.isfile(script):
                raise ValueError(f"Cannot find {job.spec['script']} in {d}. Check SMART_BIN_ML_DIR / "
                                 "WASTE_FORECAST_DIR in settings.py.")
            need = next(job.missing_needs(), None)
            if need:
                raise ValueError(f"{job.spec['title']} {need}. Run it on the System page first.")
            env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1", MPLBACKEND="Agg")
            for k in ("SMARTWASTE_FIREBASE_URL", "SMARTWASTE_USE_LOGIN", "SMARTWASTE_API_KEY", "SMARTWASTE_EMAIL",
                      "SMARTWASTE_PASSWORD"):
                env.pop(k, None)
            if self.demo_url:
                env["SMARTWASTE_FIREBASE_URL"] = self.demo_url
                env["NO_PROXY"] = ",".join(x for x in (env.get("NO_PROXY", ""), "127.0.0.1,localhost") if x)
            elif self.db and self.db.get("url"):
                env["SMARTWASTE_FIREBASE_URL"] = self.db["url"]
                if self.db.get("use_login"):
                    env.update(SMARTWASTE_USE_LOGIN="1", SMARTWASTE_API_KEY=self.db.get("api_key") or "",
                               SMARTWASTE_EMAIL=self.db.get("email") or "", SMARTWASTE_PASSWORD=self.db.get("password") or "")
            python = S.PYTHON or sys.executable
            cmd = [python, "-u", "-c", WRAPPER, job.spec["script"], *job.spec["args"]]
            job.log.clear()
            job.log.append(f"$ python {job.spec['script']} {' '.join(job.spec['args'])}".rstrip()
                           + f"   (started by {by}"
                           + ("; demo mode: uses the app's demo data)" if self.demo_url else
                              "; uses the app's database)" if self.db else ")"))
            flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            job.proc = subprocess.Popen(cmd, cwd=d, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                                        bufsize=1, creationflags=flags)
            job.started, job.ended, job.exit_code = int(time.time() * 1000), None, None
            job.stopped_by_user, job.by = False, by
            threading.Thread(target=self._read, args=(job, job.proc), daemon=True).start()
        return job.state()

    def _read(self, job, proc):
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                job.log.append(line)
        proc.wait()
        if job.proc is proc:
            job.exit_code = proc.returncode
            job.ended = int(time.time() * 1000)
            if proc.returncode != 0 and not job.stopped_by_user:
                job.fails = [t for t in job.fails if time.time() - t < 1800] + [time.time()]
            job.log.append("[stopped]" if job.stopped_by_user else f"[finished, exit code {proc.returncode}]")

    def stop(self, name, by_user=True):
        job = self.jobs.get(name)
        if not job:
            raise ValueError("Unknown job.")
        if job.running():
            job.stopped_by_user = by_user
            job.proc.terminate()
            try:
                job.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                job.proc.kill()
        elif by_user:
            job.stopped_by_user = True
        return job.state()

    def stop_all(self):
        for p in self.pipelines.values():
            p.stop_asked = True
        for job in self.jobs.values():
            if job.running():
                job.stopped_by_user = True
                try:
                    job.proc.terminate()
                except OSError:
                    pass

    def states(self):
        return [j.state() for j in self.jobs.values()]

    def log(self, name):
        job = self.jobs.get(name)
        return list(job.log) if job else []

    def running(self, name):
        j = self.jobs.get(name)
        return bool(j and j.running())

    # ---------------- several jobs one after the other ----------------
    def busy_pipeline(self):
        return next((p for p in self.pipelines.values() if p.state == "running"), None)

    def run_pipeline(self, name, steps=None, by="you"):
        steps = steps or PIPELINES.get(name)
        if not steps:
            raise ValueError("Unknown setup.")
        with self.lock:
            busy = self.busy_pipeline()
            if busy:
                raise ValueError("Another set of steps is still running. Wait until it finishes.")
            p = Pipeline(name, steps)
            self.pipelines[name] = p
        threading.Thread(target=self._pipeline, args=(p, by), daemon=True).start()
        return p.info()

    def _pipeline(self, p, by):
        def say(text):
            p.log.append(datetime.now().strftime("%H:%M:%S ") + text)
        if p.steps and p.steps[0].startswith("c2") and self.before_setup:
            try:
                for line in self.before_setup():
                    say(line)
            except Exception as e:  # never stop the setup because of this optional step
                say(f"Could not copy the real bin's data ({e}). Training uses synthetic data only.")
        for i, step in enumerate(p.steps, 1):
            if p.stop_asked:
                p.state = "stopped"
                break
            job = self.jobs[step]
            p.current = step
            m = job.spec.get("minutes", "1")
            say(f"Step {i}/{len(p.steps)}: {job.spec['title']} ({m if m.startswith('under') else 'about ' + m} min)…")
            try:
                self.start(step, by=by)
            except ValueError as e:
                say(f"Could not start: {e}")
                p.state = "failed"
                break
            while job.running():
                if p.stop_asked:
                    self.stop(step)
                time.sleep(1)
            if p.stop_asked:
                p.state = "stopped"
                say("Stopped.")
                break
            if job.exit_code != 0:
                p.state = "failed"
                hint = " No internet? Use “Road map without internet” instead, then run the next steps." \
                    if step == "c3_roads" else ""
                say(f"FAILED: {job.spec['title']} (exit code {job.exit_code}). Open its output.{hint}")
                break
            say(f"Done: {job.spec['title']}")
        else:
            p.state = "finished"
            say("All steps finished.")
        p.current, p.ended = None, int(time.time() * 1000)

    def stop_pipeline(self, name):
        p = self.pipelines.get(name)
        if p and p.state == "running":
            p.stop_asked = True
        return p.info() if p else None

    # ---------------- automatic mode ----------------
    def automation(self):
        if self.auto is None:
            self.auto = _read_json("automation.json", DEFAULT_AUTO_DEMO if self.demo_url else DEFAULT_AUTO_LIVE)
        return dict(self.auto)

    def set_automation(self, changes):
        a = self.automation()
        if "autostart" in changes:
            a["autostart"] = bool(changes["autostart"])
            if a["autostart"]:
                for n in ("predictions", "routes"):
                    self.jobs[n].stopped_by_user = False
                    self.jobs[n].fails = []
        if "forecast_daily" in changes:
            a["forecast_daily"] = bool(changes["forecast_daily"])
        if "forecast_time" in changes:
            t = str(changes["forecast_time"])
            try:
                datetime.strptime(t, "%H:%M")
            except ValueError:
                raise ValueError("Time like 05:00.")
            a["forecast_time"] = t
        if "rewards_minutes" in changes:
            m = int(changes["rewards_minutes"])
            if m < 0 or m > 1440:
                raise ValueError("Minutes: 0 (off) to 1440.")
            a["rewards_minutes"] = m
        self.auto = a
        _write_json("automation.json", a)
        return a

    def start_scheduler(self):
        if self._sched:
            return
        self.automation()
        self._sched = threading.Thread(target=self._loop, daemon=True)
        self._sched.start()

    def _loop(self):
        time.sleep(2)
        while True:
            try:
                self.tick()
            except Exception as e:  # keep the scheduler alive whatever happens
                print("Automatic mode problem:", e)
            time.sleep(15)

    def tick(self):
        a = self.automation()
        if self.busy_pipeline():
            return  # never disturb the first-time setup
        now = time.time()
        if a["autostart"]:
            for n in ("predictions", "routes"):
                job = self.jobs[n]
                if job.running() or job.stopped_by_user or next(job.missing_needs(), None):
                    continue
                if len(job.fails) >= 3:
                    continue  # failed 3 times in 30 min: wait for a person (the System page shows it)
                if job.ended and now - job.ended / 1000 < 60:
                    continue  # wait a minute before a restart
                try:
                    self.start(n, by="automatic")
                except ValueError:
                    pass
        st = self.auto_state
        if a["forecast_daily"] and not self.running("forecast") and not next(self.jobs["forecast"].missing_needs(), None):
            today = date.today().isoformat()
            due = False
            if st["forecast_day"] != today and now - st.get("forecast_try", 0) > 1800:
                due = datetime.now().strftime("%H:%M") >= a["forecast_time"]
                if not due and self.forecast_missing:
                    try:
                        due = self.forecast_missing()   # no forecast for today yet: make it now
                    except Exception:
                        due = False
            if due:
                st["forecast_try"] = now
                _write_json("automation_state.json", st)
                threading.Thread(target=self._daily_forecast, args=(today,), daemon=True).start()
        if a["rewards_minutes"] and not self.running("rewards") and now - st.get("rewards_last", 0) > a["rewards_minutes"] * 60:
            st["rewards_last"] = now
            _write_json("automation_state.json", st)
            try:
                self.start("rewards", by="automatic")
            except ValueError:
                pass

    def _daily_forecast(self, today):
        try:
            self.start("forecast", by="automatic")
        except ValueError:
            return
        job = self.jobs["forecast"]
        while job.running():
            time.sleep(1)
        if job.exit_code == 0:
            self.auto_state["forecast_day"] = today
            _write_json("automation_state.json", self.auto_state)
            try:
                if not self.running("tips"):
                    self.start("tips", by="automatic")
            except ValueError:
                pass
