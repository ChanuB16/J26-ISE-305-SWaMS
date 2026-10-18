# Component 1 — AI waste image classification

**SLIIT IT4010 · J26-ISE-305 · Kaduwela Municipal Council**

Citizens photograph **one waste item** (bottle, can, paper, food scrap, etc.). A deep-learning model predicts which **recycling category** it belongs to, shows **disposal tips** in English / Sinhala / Tamil, and (when confidence is high enough) saves the result to Firebase so officers can review it and the citizen can earn **green points**.

This document explains **what the component does**, **how the model was trained** (Colab notebook), and **how it runs inside the main SmartWaste app today**.

---

## 1. Role in the full system

```
Citizen phone (Scan tab)
        │
        ▼  POST /api/classify  (JPEG, language)
┌───────────────────┐
│  smartwaste_app   │  classifier.py loads best_model.keras (lazy)
│  Flask            │  resize 224×224 → predict → guidance text
└─────────┬─────────┘
          │ if confidence ≥ CLASSIFIER_SURE_LEVEL (default 60%)
          ▼
Firebase  classifications/<id>  { user, waste_type, confidence, ts, zone }
          │
          ├─► Officer → Community page (recent scans)
          └─► e1_rewards.py (every ~10 min) → +10 points if confidence ≥ 70%
```

There is **no separate FastAPI / Next.js server** any more. Component 1 is a **folder of model files + guidance JSON**, loaded by `smartwaste_app/classifier.py`.

The **Flutter Android app** can run the same model **on the phone** after converting to `.tflite` (see §8).

---

## 2. What the AI predicts (5 classes)

| Class ID   | Meaning        | Example items                          |
|-----------|----------------|----------------------------------------|
| `plastic` | Plastic waste  | bottles, bags, packaging               |
| `paper`   | Paper / cardboard | newspapers, boxes                   |
| `glass`   | Glass          | bottles, jars (broken = wrap safely)   |
| `metal`   | Metal          | cans, foil                             |
| `organic` | Food / garden  | peels, leftovers, compostable waste    |

Class order is fixed in `models/class_names.json`:

```json
["plastic", "paper", "glass", "metal", "organic"]
```

The model outputs **five probabilities** (softmax). The highest score is the predicted class.

---

## 3. Training — where and how

### 3.1 Main artifact

| File | Purpose |
|------|---------|
| `notebooks/Waste_Classification_Colab.ipynb` | End-to-end training on **Google Colab** (GPU recommended) |
| `models/results.csv` | Saved comparison table (accuracy / precision / recall / F1) |
| `models/best_model.keras` | **Production model** (EfficientNetB0) — often **not in git** (see `.gitignore`) |
| `models/class_names.json` | Class list for inference |
| `backend/guidance.json` | Labels + disposal tips in **en / si / ta** |

Train on Colab, then copy `best_model.keras` and `class_names.json` into `waste_classifier/models/` on the laptop that runs `python app.py`.

### 3.2 Datasets used in the notebook

The notebook builds one **unified image folder** from several sources:

1. **Hugging Face** — `omasteam/waste-garbage-management-dataset` (downloaded automatically in Colab).
2. **TrashNet** — you upload `trashnet.zip` (project `data/trashnet.zip`; large file, gitignored).
3. **Optional local Sri Lankan photos** — when prompted, upload `local.zip` with subfolders named `plastic`, `paper`, `glass`, `metal`, `organic`.

All images are resized to **224×224 JPEG** and sorted into:

- `public/` — international / TrashNet-style photos  
- `local/` — Sri Lankan photos (optional)

### 3.3 Train / validation / test split

For **each class**, photos are split (fixed seed `42`):

- **70%** → train  
- **15%** → validation  
- **15%** → test  

`tf.keras.utils.image_dataset_from_directory` loads batches of **32** images.

### 3.4 Data augmentation (training only)

A Keras `Sequential` block applies random transforms so the model generalises better:

- horizontal flip  
- small rotation  
- zoom  
- contrast adjustment  

Augmentation runs **during training**, not at inference time in the web app (inference only resizes to 224×224).

### 3.5 Models compared (research / RQ for Component 1)

The notebook trains **three** architectures and picks the best on the **test set**:

| Model | Idea | Typical role |
|-------|------|----------------|
| **Baseline CNN** | Small custom conv network from scratch | Baseline to beat |
| **MobileNetV2** | Transfer learning, ImageNet weights, lighter | Fast, mobile-friendly |
| **EfficientNetB0** | Transfer learning, ImageNet weights, stronger | **Chosen as `best_model`** |

Transfer-learning models use **two phases**:

1. **Frozen backbone** — only the new classification head trains (~10 epochs).  
2. **Fine-tuning** — last layers of the backbone unfrozen, lower learning rate (~10 epochs).

Early stopping watches validation loss so training does not overfit.

### 3.6 Results saved in this repo

From `models/results.csv` (your Colab run may differ slightly):

| model | accuracy | precision | recall | F1 |
|-------|----------|-----------|--------|-----|
| Baseline CNN | 0.779 | 0.751 | 0.749 | 0.747 |
| MobileNetV2 | 0.927 | 0.909 | 0.928 | 0.918 |
| **EfficientNetB0** | **0.938** | **0.933** | **0.934** | **0.933** |

The notebook also reports metrics on **Sri Lankan-only** test images (`local_*` filenames) when that folder was used — useful for the viva (“does it work on local waste?”).

### 3.7 Export at the end of the notebook

Colab saves:

- `saved_models/best_model.keras`  
- `saved_models/class_names.json`  
- optional `best_model.tflite` (for mobile)  
- a zip `component1_results.zip` for download  

Copy into this project:

```
waste_classifier/models/best_model.keras
waste_classifier/models/class_names.json
```

Keep `backend/guidance.json` in the repo (human-written tips, not learned by the network).

---

## 4. How inference works in the web app

### 4.1 Configuration (`smartwaste_app/settings.py`)

```python
WASTE_CLASSIFIER_DIR = "../waste_classifier"
CLASSIFIER_MODEL     = "best_model.keras"   # "" = Scan tab disabled
CLASSIFIER_SURE_LEVEL = 0.60              # below → "not sure"
```

### 4.2 Code path (`smartwaste_app/classifier.py`)

1. **Lazy load** — TensorFlow and the `.keras` file load on the **first** classify request (so `python app.py` starts quickly).  
2. **Preprocess** — decode JPEG → RGB → resize **224×224** → float32 array → batch size 1.  
3. **Predict** — `model.predict()` → 5 probabilities.  
4. **Decide** — if top probability ≥ `CLASSIFIER_SURE_LEVEL` → `reliable: true` and category = top class; else `category: "unsure"`.  
5. **Guidance** — read `backend/guidance.json` for label + tip in the requested language (`en`, `si`, `ta`).  
6. **Response** — JSON with `category`, `label`, `confidence`, `guidance`, `top3`, `inference_seconds`.

### 4.3 API (`POST /api/classify`)

- **Who:** logged-in **citizen** only.  
- **Body:** `{ "photo": "data:image/jpeg;base64,...", "lang": "en"|"si"|"ta", "zone": "<optional>" }`  
- **Size limit:** ~600 KB (browser shrinks photo first in `citizen_scan.js`).  

If `reliable` is true, Flask writes:

```json
classifications/<auto-id> = {
  "user": "<username>",
  "waste_type": "plastic",
  "confidence": 0.91,
  "ts": <server timestamp>,
  "zone": "",
  "source": "web app"
}
```

### 4.4 Citizen UI (`Scan` tab)

- Pick photo → client resizes to max 1024 px JPEG.  
- First inference may take **5–10 s** (model load + CPU). Later calls are faster.  
- Shows confidence bar, top-3 classes, disposal tip, and whether **+10 points** will apply (see §5).

---

## 5. Two confidence thresholds (common viva question)

| Threshold | Value | Effect |
|-----------|-------|--------|
| `CLASSIFIER_SURE_LEVEL` | **60%** (0.60) | App shows a **named** class + tip; row saved to `classifications/` |
| Rewards (`e1_rewards.py`) | **70%** (0.70) | Citizen gets **+10 green points** |

So a scan at **65%** can appear on the Community page but **no points** until confidence ≥ 70%. The Scan tab explains this to the user.

---

## 6. Folder layout

```
waste_classifier/
├── COMPONENT1.md              ← this guide
├── README.txt                 ← short pointer to Flask Scan tab
├── notebooks/
│   └── Waste_Classification_Colab.ipynb
├── models/
│   ├── best_model.keras       ← train in Colab; copy here (gitignored if large)
│   ├── class_names.json
│   └── results.csv
├── backend/
│   └── guidance.json          ← EN / SI / TA labels and tips
└── data/                      ← optional local data (often gitignored)
    ├── trashnet.zip
    └── raw/local/             ← Sri Lankan photos by class
```

---

## 7. How to retrain (step list for students)

1. Open `notebooks/Waste_Classification_Colab.ipynb` in **Google Colab**.  
2. Runtime → **GPU** (T4).  
3. Run **Step 1** (install libs, set `CLASSES`, `IMG_SIZE`, `SEED`).  
4. Run **Step 2** — download HF dataset; upload `trashnet.zip` when asked.  
5. Run sorting / split cells until train/val/test counts look reasonable.  
6. Train **baseline**, **MobileNetV2**, **EfficientNetB0**; compare metrics.  
7. Export **best** model; download zip.  
8. Copy `best_model.keras` + `class_names.json` into `waste_classifier/models/`.  
9. On the dev PC: `pip install tensorflow "keras>=3.12" "numpy<2.1" pillow` (already in `smartwaste_app/requirements.txt`).  
10. Restart `python app.py` → log in as citizen → **Scan** → test with a clear single-item photo.

To **disable** the scanner (e.g. PC without TensorFlow): set `CLASSIFIER_MODEL = ""` in `settings.py`.

---

## 8. Mobile app (same model, on-device)

`smartwaste_mobile/scripts/convert_model_to_tflite.py` converts `models/best_model.keras` to:

- `smartwaste_mobile/assets/waste_classifier.tflite`  
- `smartwaste_mobile/assets/labels.txt`  

The Flutter **Scan** tab runs inference locally (no `/api/classify` needed on the phone), but still can write to Firebase `classifications/` so officers and rewards see the same data.

---

## 9. Simple explanation for classmates (30 seconds)

> “We trained EfficientNetB0 on thousands of labelled waste photos from public datasets plus optional Sri Lankan pictures. It outputs one of five material types. When a citizen scans an item, the Flask app runs the same model, shows recycling advice in three languages, and stores confident scans in Firebase. Officers see them under Community; a background job adds reward points if the AI is at least 70% sure.”

---

## 10. Viva-style Q&A

**Q: Why transfer learning instead of training from scratch?**  
A: ImageNet weights already understand edges, textures, and shapes. We need fewer photos and less GPU time to reach high accuracy (baseline ~78% vs EfficientNet ~94% on our test split).

**Q: Why 224×224?**  
A: Standard input size for EfficientNetB0 and MobileNetV2 on ImageNet; matches training and inference.

**Q: What if the photo has many items?**  
A: The model was trained on **one dominant object per image**. Mixed piles → low confidence → “not sure” and no false points.

**Q: Does the model run on the ESP32 bin?**  
A: **No.** The bin measures fill, weight, gas, etc. Classification runs on the **server** (web) or **phone** (TFLite), not on the microcontroller.

**Q: Where is the “AI” in the proposal diagram?**  
A: Component 1 = **image classification**. Component 2 = **fill-level time-series ML** (`smart_bin_ml`). Component 3 = **forecast + routes** (`waste_forecast_routes`).

**Q: Is guidance text generated by ChatGPT / the neural network?**  
A: **No.** Disposal tips are **curated** in `backend/guidance.json`. Only the **class name** comes from the network.

---

## 11. Related files in the main app

| File | Role |
|------|------|
| `smartwaste_app/classifier.py` | Load model, classify, push to Firebase |
| `smartwaste_app/app.py` | `/api/classify`, citizen Scan route |
| `smartwaste_app/templates/citizen/scan.html` | Scan page layout |
| `smartwaste_app/static/js/pages/citizen_scan.js` | Photo shrink + API call + UI |
| `waste_forecast_routes/e1_rewards.py` | Points for `classifications/` ≥ 70% |
| `smartwaste_app` Community / officer pages | List recent classifications |

---

*Last aligned with integrated Flask Scan tab and firmware v1.3.0 project layout.*
