"""
Accounts for every user (municipal officers, truck drivers AND citizens).

Stored in the same database as the rest of the app (Firebase Realtime Database,
or the demo in-memory DB), under:

    users/<username> = {name, role, password: <salted hash>, truck, active,
                        created, last_login}

Passwords are kept only as werkzeug salted hashes. The app's own backend is the
only reader of the hashes - browsers never see them.

The main app calls init(db) once at startup. After that, all functions here
use that database handle.

Legacy: if an older instance/users.json file is still on disk and the Firebase
"users/" node is empty, those accounts are copied over on first start.
"""
import json
import os
import re
import threading
import time

from werkzeug.security import check_password_hash, generate_password_hash

HERE = os.path.dirname(os.path.abspath(__file__))
LEGACY_PATH = os.path.join(HERE, "instance", "users.json")
STAFF_ROLES = {"officer": "Municipal officer", "driver": "Truck driver"}
ROLES = {**STAFF_ROLES, "citizen": "Citizen"}
NODE = "users"
NAME_RE = re.compile(r"^[a-z0-9_.\-]{3,30}$")

_db = None                        # set by init()
_lock = threading.RLock()


# ---------------------------------------------------------------------------
# init + legacy migration
# ---------------------------------------------------------------------------
def init(db):
    """Called once by app.py after the database is ready."""
    global _db
    _db = db
    _migrate_legacy()


def _migrate_legacy():
    """If instance/users.json has accounts and the DB has none, copy them over."""
    if _db is None or not os.path.exists(LEGACY_PATH):
        return
    try:
        with open(LEGACY_PATH, encoding="utf-8") as f:
            legacy = (json.load(f) or {}).get("users") or {}
    except (OSError, ValueError):
        return
    if not legacy:
        return
    try:
        existing = _db.get(NODE, shallow=True) or {}
    except Exception:
        return
    if existing:
        return                                                    # DB already has users; do nothing
    try:
        for username, u in legacy.items():
            if not isinstance(u, dict):
                continue
            _db.put(f"{NODE}/{username}", {
                "name": u.get("name") or username,
                "role": u.get("role") or "officer",
                "password": u.get("password") or "",
                "truck": u.get("truck") or "",
                "active": bool(u.get("active", True)),
                "created": int(u.get("created") or time.time() * 1000),
                "last_login": int(u.get("last_login") or 0) or None,
            })
        try:
            os.replace(LEGACY_PATH, LEGACY_PATH + ".migrated")
        except OSError:
            pass
        print(f" Migrated {len(legacy)} user account(s) from instance/users.json to the database.")
    except Exception as e:
        print(" Could not migrate instance/users.json:", e)


# ---------------------------------------------------------------------------
# low-level helpers
# ---------------------------------------------------------------------------
def _require():
    if _db is None:
        raise RuntimeError("users.init(db) was not called yet.")
    return _db


def _get_raw(username):
    db = _require()
    return db.get(f"{NODE}/{username}") if username else None


def _put_raw(username, u):
    _require().put(f"{NODE}/{username}", u)


def _patch_raw(username, changes):
    _require().patch(f"{NODE}/{username}", changes)


def public(u, username):
    """A safe view (never includes the password hash)."""
    return {"username": username, "name": u.get("name") or username, "role": u.get("role"),
            "truck": u.get("truck") or "", "active": bool(u.get("active", True)),
            "created": u.get("created"), "last_login": u.get("last_login")}


# ---------------------------------------------------------------------------
# queries
# ---------------------------------------------------------------------------
def list_users(include_citizens=False):
    """Default: only officers + drivers (used by the System page account manager)."""
    db = _require()
    users = db.get(NODE) or {}
    rows = []
    for username, u in sorted(users.items()):
        if not isinstance(u, dict):
            continue
        if not include_citizens and u.get("role") == "citizen":
            continue
        rows.append(public(u, username))
    return rows


def has_officer():
    db = _require()
    users = db.get(NODE) or {}
    return any(isinstance(u, dict) and u.get("role") == "officer" and u.get("active", True)
               for u in users.values())


def get(username):
    u = _get_raw(username)
    return public(u, username) if isinstance(u, dict) else None


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------
def check_new(username, password, role):
    if not NAME_RE.fullmatch(username or ""):
        return "User name: 3 to 30 small letters, numbers, dot, dash or underscore."
    if role not in ROLES:
        return "Choose a role."
    if len(password or "") < 8:
        return "Password: at least 8 characters."
    return None


# ---------------------------------------------------------------------------
# create / update / delete / login
# ---------------------------------------------------------------------------
def create(username, password, role, name="", truck=""):
    username = (username or "").strip().lower()
    err = check_new(username, password, role)
    if err:
        raise ValueError(err)
    with _lock:
        if _get_raw(username):
            raise ValueError("That user name is already taken.")
        u = {
            "name": (name or username).strip()[:60],
            "role": role,
            "truck": (truck or "").strip()[:30],
            "password": generate_password_hash(password),
            "active": True,
            "created": int(time.time() * 1000),
        }
        _put_raw(username, u)
    return public(u, username)


def update(username, **changes):
    with _lock:
        u = _get_raw(username)
        if not isinstance(u, dict):
            raise ValueError("No such user.")
        patch = {}
        if "password" in changes:
            if len(changes["password"] or "") < 8:
                raise ValueError("Password: at least 8 characters.")
            patch["password"] = generate_password_hash(changes.pop("password"))
        for k in ("name", "truck", "active", "role"):
            if k in changes:
                if k == "role" and changes[k] not in ROLES:
                    raise ValueError("Unknown role.")
                patch[k] = changes[k]
        if patch:
            _patch_raw(username, patch)
            u.update(patch)
        return public(u, username)


def delete(username):
    with _lock:
        _require().delete(f"{NODE}/{username}")


def login(username, password):
    """Returns the public user dict on success, None on failure."""
    username = (username or "").strip().lower()
    with _lock:
        u = _get_raw(username)
        if not isinstance(u, dict):
            return None
        if not check_password_hash(u.get("password", ""), password or ""):
            return None
        if not u.get("active", True):
            return None
        try:
            _patch_raw(username, {"last_login": int(time.time() * 1000)})
        except Exception:
            pass                                                   # not fatal; let the user in
        return public(u, username)
