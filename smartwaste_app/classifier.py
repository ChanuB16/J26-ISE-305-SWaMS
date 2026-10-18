"""Component 1 - AI waste classifier, built into the main Flask app.

The Keras model is loaded ONCE, on the first request (lazy), so starting
`python app.py` stays fast and so the app still runs on computers that have
not installed TensorFlow yet (the Scan tab shows a friendly 503 instead).

Settings (../smartwaste_app/settings.py):
    WASTE_CLASSIFIER_DIR    folder with models/ and backend/guidance.json
    CLASSIFIER_MODEL        file inside <WASTE_CLASSIFIER_DIR>/models/
                            ("" = classifier disabled)
    CLASSIFIER_SURE_LEVEL   below this the AI says "not sure"
"""
import io
import json
import time
from pathlib import Path

import settings as S

LANGS = ("en", "si", "ta")

_state = {"model": None, "classes": None, "guidance": None}


def _dir() -> Path:
    """Absolute path of the waste_classifier folder."""
    return (Path(__file__).resolve().parent / S.WASTE_CLASSIFIER_DIR).resolve()


def enabled() -> bool:
    """True if an operator asked for the classifier (model name set)."""
    return bool(getattr(S, "CLASSIFIER_MODEL", "") or "")


def available() -> bool:
    """True if the model actually loads (TensorFlow present, files there)."""
    if not enabled():
        return False
    try:
        _load()
        return True
    except Exception:
        return False


def _load():
    if _state["model"] is not None:
        return
    if not enabled():
        raise RuntimeError("CLASSIFIER_MODEL is empty in settings.py")
    base = _dir()
    _state["classes"] = json.loads((base / "models" / "class_names.json").read_text())
    _state["guidance"] = json.loads((base / "backend" / "guidance.json").read_text(encoding="utf-8"))
    from tensorflow import keras                                   # heavy import deferred
    _state["model"] = keras.models.load_model(base / "models" / S.CLASSIFIER_MODEL, compile=False)


def classify(image_bytes: bytes, lang: str = "en") -> dict:
    """Classify one photo. Returns the same dict shape the old FastAPI endpoint used."""
    if lang not in LANGS:
        raise ValueError(f"lang must be one of {LANGS}")
    _load()
    from PIL import Image, UnidentifiedImageError                  # deferred too
    import numpy as np

    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB").resize((224, 224))
    except (UnidentifiedImageError, OSError):
        raise ValueError("Could not read the file as an image.")

    t0 = time.perf_counter()
    chances = _state["model"].predict(np.asarray(img, dtype="float32")[None], verbose=0)[0]
    secs = time.perf_counter() - t0

    order = chances.argsort()[::-1]
    best = _state["classes"][order[0]]
    conf = float(chances[order[0]])
    sure = conf >= float(getattr(S, "CLASSIFIER_SURE_LEVEL", 0.60))
    g = _state["guidance"]
    return {
        "category": best if sure else "unsure",
        "label": g["_labels"][best][lang] if sure else None,
        "confidence": round(conf, 4),
        "reliable": sure,
        "guidance": g[best][lang] if sure else g["_unsure"][lang],
        "top3": [{"category": _state["classes"][i], "confidence": round(float(chances[i]), 4)}
                 for i in order[:3]],
        "language": lang,
        "inference_seconds": round(secs, 3),
    }


def push(db, user: str, waste_type: str, confidence: float, zone: str = "") -> str:
    """Save a classified photo under classifications/<key>.

    Works for RestDB (real Firebase) and DemoDB (in-memory) the same way, so the
    Officer Community page and the +10 pts reward loop (e1_rewards.py) light up
    even when the app is in demo mode.
    """
    return db.post("classifications", {
        "user": user,
        "waste_type": waste_type,
        "confidence": round(float(confidence), 4),
        "ts": {".sv": "timestamp"},
        "zone": zone or "",
        "source": "web app",
    })
