"""
Database access for the web app.

RestDB  - your real Firebase Realtime Database (REST API, same as the other scripts).
DemoDB  - example data from demo/demo_db.json, kept in memory. All times are moved so the
          data looks "live" (the newest reading = now). Changes are lost when the app stops.

Both have the same methods: get, put, patch, post, delete.
"""
import copy
import json
import re
import threading
import time
from datetime import date, datetime, timedelta

import requests


class DBError(Exception):
    """A readable error for the web page (no stack trace)."""


def _query(shallow=False, start=None, end=None, first=None, last=None):
    q = {}
    if shallow:
        q["shallow"] = "true"
    if any(v is not None for v in (start, end, first, last)):
        q["orderBy"] = '"$key"'
        if start is not None:
            q["startAt"] = json.dumps(str(start))
        if end is not None:
            q["endAt"] = json.dumps(str(end))
        if first is not None:
            q["limitToFirst"] = str(int(first))
        if last is not None:
            q["limitToLast"] = str(int(last))
    return q


class RestDB:
    demo = False

    def __init__(self, url, use_login=False, api_key="", email="", password=""):
        self.url = url.rstrip("/")
        self.use_login = use_login
        self.api_key, self.email, self.password = api_key, email, password
        self.token, self.token_time = None, 0.0
        self.lock = threading.Lock()
        self.http = requests.Session()

    def _auth(self, params):
        if not self.use_login:
            return params
        with self.lock:
            if self.token is None or time.time() - self.token_time > 50 * 60:
                try:
                    r = self.http.post("https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key="
                                       + self.api_key, json={"email": self.email, "password": self.password,
                                                             "returnSecureToken": True}, timeout=20)
                except requests.RequestException:
                    raise DBError("Cannot reach Firebase login. Check the internet.")
                if r.status_code != 200:
                    raise DBError("Firebase login failed. Check FIREBASE_API_KEY, FIREBASE_EMAIL and "
                                  "FIREBASE_PASSWORD in settings.py.")
                self.token, self.token_time = r.json()["idToken"], time.time()
            params["auth"] = self.token
        return params

    def _url(self, path):
        path = str(path).strip("/")
        return f"{self.url}/{path}.json" if path else f"{self.url}/.json"

    def _do(self, method, path, params=None, body=None):
        params = self._auth(dict(params or {}))
        try:
            r = self.http.request(method, self._url(path), params=params,
                                  data=None if body is None else json.dumps(body), timeout=20)
        except requests.RequestException:
            raise DBError("Cannot reach Firebase. Check the internet and FIREBASE_DB_URL in settings.py.")
        if r.status_code in (401, 403):
            raise DBError("Firebase said 'permission denied'. The database test mode has ended, or the "
                          "login in settings.py is wrong (see README, part 'Lock the database').")
        if r.status_code == 404:
            raise DBError("Firebase said 404 - FIREBASE_DB_URL in settings.py is wrong.")
        if r.status_code >= 300:
            raise DBError(f"Firebase error {r.status_code}: {r.text[:200]}")
        try:
            return r.json()
        except ValueError:
            return None

    def get(self, path, **q):
        return self._do("GET", path, _query(**q))

    def put(self, path, value):
        self._do("PUT", path, {"print": "silent"}, value)

    def patch(self, path, value):
        self._do("PATCH", path, {"print": "silent"}, value)

    def post(self, path, value):
        out = self._do("POST", path, None, value)
        return (out or {}).get("name")

    def delete(self, path):
        self._do("DELETE", path)

    def describe(self):
        return self.url.replace("https://", "").replace("http://", "")


# ---------------------------------------------------------------------------
# Demo database
# ---------------------------------------------------------------------------
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MS = re.compile(r"^\d{13}$")


def _shift_day(s, days):
    return (date.fromisoformat(s) + timedelta(days=days)).isoformat()


def _shift(node, ms, days):
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            key = k
            if _MS.match(k):
                key = str(int(k) + ms)
            elif _DAY.match(k):
                key = _shift_day(k, days)
            out[key] = _shift(v, ms, days)
        return out
    if isinstance(node, list):
        return [_shift(v, ms, days) for v in node]
    if isinstance(node, (int, float)) and not isinstance(node, bool) and 1.5e12 < node < 2.5e12:
        return type(node)(node + ms)
    if isinstance(node, str) and _DAY.match(node):
        return _shift_day(node, days)
    if isinstance(node, str) and re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", node):
        try:
            t = datetime.strptime(node, "%Y-%m-%d %H:%M:%S") + timedelta(milliseconds=ms)
            return t.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            return node
    return node


def _key_order(k):
    # Firebase order: integer-looking keys first (as numbers), then text keys.
    if re.match(r"^-?\d{1,9}$", k):
        return (0, int(k), "")
    return (1, 0, k)


def _resolve_server_values(v):
    if isinstance(v, dict):
        if v.get(".sv") == "timestamp":
            return int(time.time() * 1000)
        return {k: _resolve_server_values(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_resolve_server_values(x) for x in v]
    return v


def _clean(v):
    """Firebase drops empty objects and None values (an empty object means: delete)."""
    if isinstance(v, dict):
        out = {k: _clean(x) for k, x in v.items() if x is not None}
        out = {k: x for k, x in out.items() if x is not None}
        return out or None
    if isinstance(v, list):
        out = [_clean(x) for x in v]
        return out if any(x is not None for x in out) else None
    return v


class DemoDB:
    demo = True

    def __init__(self, path):
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        made = int((raw.get("_meta") or {}).get("made_at") or time.time() * 1000)
        now = int(time.time() * 1000)
        days = (date.fromtimestamp(now / 1000) - date.fromtimestamp(made / 1000)).days
        self.data = _shift(raw, now - made, days)
        self.data.pop("_meta", None)
        self.lock = threading.RLock()
        self.count = 0

    @staticmethod
    def _parts(path):
        return [p for p in str(path or "").split("/") if p]

    def _node(self, path):
        n = self.data
        for p in self._parts(path):
            if isinstance(n, list) and p.isdigit() and int(p) < len(n):
                n = n[int(p)]
            elif isinstance(n, dict) and p in n:
                n = n[p]
            else:
                return None
        return n

    def get(self, path, shallow=False, start=None, end=None, first=None, last=None):
        with self.lock:
            n = self._node(path)
            if n is None:
                return None
            if shallow:
                if isinstance(n, dict):
                    return {k: True for k in n}
                if isinstance(n, list):
                    return {str(i): True for i in range(len(n))}
                return n
            if not isinstance(n, (dict, list)) or all(v is None for v in (start, end, first, last)):
                return copy.deepcopy(n)
            items = n.items() if isinstance(n, dict) else ((str(i), v) for i, v in enumerate(n))
            keys = sorted((k for k, _ in items), key=_key_order)
            if start is not None:
                keys = [k for k in keys if _key_order(k) >= _key_order(str(start))]
            if end is not None:
                keys = [k for k in keys if _key_order(k) <= _key_order(str(end))]
            if first is not None:
                keys = keys[:int(first)]
            if last is not None:
                keys = keys[-int(last):] if int(last) else []
            src = n if isinstance(n, dict) else {str(i): v for i, v in enumerate(n)}
            out = {k: copy.deepcopy(src[k]) for k in keys}
            return out or None

    def _set(self, path, value):
        parts = self._parts(path)
        if not parts:
            self.data = value if isinstance(value, dict) else {}
            return
        n = self.data
        for p in parts[:-1]:
            if isinstance(n, list) and p.isdigit() and int(p) < len(n):
                if not isinstance(n[int(p)], (dict, list)):
                    n[int(p)] = {}
                n = n[int(p)]
                continue
            if not isinstance(n.get(p), (dict, list)):
                n[p] = {}
            n = n[p]
        last = parts[-1]
        if isinstance(n, list) and last.isdigit() and int(last) < len(n):
            n[int(last)] = value
        elif isinstance(n, dict):
            if value is None:
                n.pop(last, None)
            else:
                n[last] = value
        if value is None:
            self._prune(parts)

    def _prune(self, parts):
        """Like Firebase: a parent that became empty disappears too."""
        chain, n = [self.data], self.data
        for p in parts[:-1]:
            if isinstance(n, dict) and p in n:
                n = n[p]
            elif isinstance(n, list) and p.isdigit() and int(p) < len(n):
                n = n[int(p)]
            else:
                return
            chain.append(n)
        for i in range(len(chain) - 1, 0, -1):
            node = chain[i]
            empty = (isinstance(node, dict) and not node) or (isinstance(node, list) and all(x is None for x in node))
            if not empty:
                return
            parent = chain[i - 1]
            if isinstance(parent, dict):
                parent.pop(parts[i - 1], None)
            elif isinstance(parent, list):
                parent[int(parts[i - 1])] = None

    def put(self, path, value):
        with self.lock:
            self._set(path, _clean(_resolve_server_values(copy.deepcopy(value))))

    def patch(self, path, value):
        with self.lock:
            for k, v in (value or {}).items():
                self._set("/".join(self._parts(path) + self._parts(k)),
                          _clean(_resolve_server_values(copy.deepcopy(v))))

    def post(self, path, value):
        with self.lock:
            self.count += 1
            key = "-demo" + format(int(time.time() * 1000), "x") + format(self.count, "04x")
            self._set("/".join(self._parts(path) + [key]), _clean(_resolve_server_values(copy.deepcopy(value))))
            return key

    def delete(self, path):
        with self.lock:
            self._set(path, None)

    def describe(self):
        return "demo data (in memory)"

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.data)
