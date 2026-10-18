"""
Convert the Keras waste classifier (best_model.keras) to TensorFlow Lite so
the Flutter app can run it on-device (no server needed for the Scan tab).

Usage (from the smartwaste_mobile folder):

    python scripts/convert_model_to_tflite.py

It writes:
    assets/waste_classifier.tflite
    assets/labels.txt

The Flutter app picks these up automatically (see lib/config.dart).

Requirements:
    pip install tensorflow pillow
"""

import os
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent.parent
# ../.. because this script sits inside smartwaste_mobile/scripts
PROJECT_ROOT = HERE.parent
CLASSIFIER_DIR = PROJECT_ROOT / "waste_classifier"
MODEL_PATH = CLASSIFIER_DIR / "models" / "best_model.keras"
LABELS_PATH_CANDIDATES = [
    CLASSIFIER_DIR / "labels.txt",
    CLASSIFIER_DIR / "models" / "labels.txt",
]
OUT_DIR = HERE / "assets"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def main() -> int:
    if not MODEL_PATH.exists():
        print(f"ERROR: Keras model not found at {MODEL_PATH}", file=sys.stderr)
        print("Set CLASSIFIER_DIR in this script to your waste_classifier folder.")
        return 1

    try:
        import tensorflow as tf  # noqa: F401
    except Exception as e:
        print(
            "TensorFlow is not installed. Install with:\n"
            "    pip install tensorflow\n"
            f"(details: {e})",
            file=sys.stderr,
        )
        return 1
    import tensorflow as tf  # type: ignore  # re-import after check

    print(f"Loading model from {MODEL_PATH} ...")
    model = tf.keras.models.load_model(str(MODEL_PATH))
    print("Model loaded. Converting to TensorFlow Lite ...")

    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    # Default optimisations: smaller and faster on-device.
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    tflite_bytes = converter.convert()

    out_model = OUT_DIR / "waste_classifier.tflite"
    out_model.write_bytes(tflite_bytes)
    print(f"Wrote {out_model} ({out_model.stat().st_size // 1024} KB)")

    # ---- labels ----
    labels = None
    for p in LABELS_PATH_CANDIDATES:
        if p.exists():
            labels = [
                line.strip() for line in p.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            print(f"Using labels from {p}")
            break
    if not labels:
        # Fallback: the categories used by the SmartWaste classifier.
        labels = ["plastic", "paper", "glass", "metal", "organic"]
        print("Could not find labels.txt — writing default 5-class list.")

    out_labels = OUT_DIR / "labels.txt"
    out_labels.write_text("\n".join(labels), encoding="utf-8")
    print(f"Wrote {out_labels} ({len(labels)} classes)")

    print("\nDone. Run:  flutter pub get  &&  flutter run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
