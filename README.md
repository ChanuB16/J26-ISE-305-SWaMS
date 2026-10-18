# SmartWaste LK — Intelligent Waste Management System

**SLIIT IT4010 · Group J26-ISE-305 · Kaduwela Municipal Council (Sri Lanka)**

An end-to-end smart waste pilot for a Sri Lankan municipality: an IoT bin that
measures itself, a Firebase cloud that stores every reading, machine-learning
models that predict fill-up and plan truck routes, a Flask dashboard for the
council, and an Android app for citizens and drivers.

---

## 1. The system in one picture

```
   ┌──────────────────────┐
   │  ESP32-S3 smart bin  │   firmware v1.3.0  (firmware/smart_bin/)
   │  HC-SR04 · HX711 ·   │   sends every 30 s
   │  DHT22 · MQ-135 ·    │
   │  DS3231 · LEDs       │
   └──────────┬───────────┘
              │ WiFi + HTTPS
              ▼
   ┌──────────────────────────────────────────────────────────────┐
   │              Firebase Realtime Database  (free tier)         │
   │                                                              │
   │  bins/            readings & devices                         │
   │  predictions/     6 h fill forecast per bin   (b5)           │
   │  forecasts/       7-day tonnage per zone      (f3)           │
   │  routes/          daily truck plans           (r3)           │
   │  trucks/          live truck status                          │
   │  traffic/         road closures & jams                       │
   │  rewards/         citizen green points        (e1)           │
   │  guidance/        crew tips                   (e2)           │
   │  classifications/ waste photos + labels       (Scan)         │
   │  reports/         citizen complaints                         │
   │  users/           staff + citizen accounts (scrypt)          │
   └──────┬──────────────────────┬───────────────────┬────────────┘
          │                      │                   │
          ▼                      ▼                   ▼
   ┌────────────┐        ┌───────────────┐   ┌────────────────┐
   │ Flask app  │        │ Flutter app   │   │ ML scripts     │
   │ (port 5000)│        │ (Android)     │   │ (background)   │
   │            │        │               │   │                │
   │ Officer +  │        │ Citizen +     │   │ b2-b6, f1-f3,  │
   │ Driver +   │        │ Driver +      │   │ r1-r4, e1, e2  │
   │ Citizen UI │        │ Officer UI    │   │                │
   └────────────┘        └───────────────┘   └────────────────┘
```

Every arrow is a Firebase read or write. There is **no custom backend between
the pieces** — the database is the integration point. If you turn off any one
component, the others keep working.

---

## 2. Folders in this repository

```
C:\D\smart bin kadu\New folder\
├── smartwaste_app\         Flask website + REST API (the main server)
├── smartwaste_mobile\      Flutter Android app
├── smart_bin_ml\           Component 2 ML: fill prediction, urgency, nearest bin
├── waste_forecast_routes\  Component 3 ML: 7-day forecast, truck routes, rewards
├── waste_classifier\       Component 1: EfficientNetB0 waste-type classifier
└── firmware\smart_bin\     ESP32-S3 Arduino sketch (v1.3.0)
```

| Folder | What it does | Language | Its own README |
|---|---|---|---|
| [`smartwaste_app/`](smartwaste_app/README.txt) | Flask website, REST API, demo DB, embedded Scan tab, user auth | Python 3.9+ | [`README.txt`](smartwaste_app/README.txt) |
| [`smartwaste_mobile/`](smartwaste_mobile/README.md) | Android app (Citizen Home/Report/Scan/Rewards; Driver + Officer coming) | Dart / Flutter | [`README.md`](smartwaste_mobile/README.md) |
| [`smart_bin_ml/`](smart_bin_ml/README.txt) | Trains & runs the fill-level models (Linear Regression, Random Forest, Gradient Boosting, MLP, optional XGBoost); urgency score; nearest bin | Python 3.10+ | [`README.txt`](smart_bin_ml/README.txt) |
| [`waste_forecast_routes/`](waste_forecast_routes/README.txt) | 7-day forecasts (LR / XGBoost / LSTM), OpenStreetMap routing (OR-Tools or built-in), rewards, crew tips | Python 3.10–3.13 | [`README.txt`](waste_forecast_routes/README.txt) |
| [`waste_classifier/`](waste_classifier/README.txt) | EfficientNetB0 Keras model + bilingual disposal guidance; loaded lazily by the Flask app | Python / Keras | [`README.txt`](waste_classifier/README.txt) |
| `firmware/smart_bin/` | ESP32-S3 Arduino sketch; reads 5 sensors, computes urgency, drives LEDs, posts to Firebase every 30 s | C++ (Arduino) | — see §4 below |

---

## 3. The research questions this project answers

| RQ | Question | Answered by |
|---|---|---|
| **RQ1** | How reliable are the bin's measurements in the real world? | Live from the ESP32 → `smartwaste_app` Analytics page (`tools/rq1_metrics.py`) |
| **RQ2** | Which ML model predicts fill level best? | `smart_bin_ml/b3_train_models.py` |
| **RQ3** | Which urgency formula ranks bins best for pick-up? | `smart_bin_ml/b4_test_urgency_and_nearest.py` (U0, U1, U2) |
| **RQ4** | Can citizens find the nearest bin with space fast? | Same script (R0, R1) |
| **RQ5** | Can the live system react to new readings in time? | `smart_bin_ml/b5_live_predictions.py` + Flask dashboard |
| **RQ6** | Which forecast + routing combination minimises km / fuel / missed bins? | `waste_forecast_routes/f2`, `r2` |
| **RQ7** | Is the UI usable? (SUS target ≥ 68) | SUS survey in the Flask app → Analytics > Usability |

---

## 4. Hardware (one bin)

### Bill of materials

| Part | Role | Notes |
|---|---|---|
| ESP32-S3 dev board | Main controller | 2.4 GHz WiFi |
| **HC-SR04** ultrasonic | Measures airgap → fill % | For a **20 cm bin**. If your bin is ≥ 30 cm you can swap to JSN-SR04T (waterproof, needs ≥ 20 cm) by editing `config.h` |
| HX711 + load cell | Measures weight | Configured for max **1 kg** load, displayed in grams |
| DHT22 | Air temperature + humidity | ±0.5 °C / ±2 % |
| MQ-135 | Air-quality / odour (gas index) | Needs 20 min warm-up on first boot |
| DS3231 RTC | Keeps time without WiFi | Auto-synced from NTP when online |
| 3× status LEDs | Local urgency indicator | Green / Yellow / Red; same thresholds as the dashboard |
| Voltage dividers (3× 22 kΩ sets) | Protects ESP32 ADC pins | 1 for battery, 1 for echo, 1 for gas |

### Pin map

```
Role                  ESP32-S3 pin   Notes
--------------------  ------------   -----------------------------
MQ-135 analog         GPIO 4         through gas divider
HC-SR04 Trig          GPIO 5
HC-SR04 Echo          GPIO 6         through echo divider
DHT22 data            GPIO 7
Battery sense         GPIO 10        through battery divider
HX711 DT              GPIO 15
HX711 SCK             GPIO 16
DS3231 SDA / SCL      GPIO 17 / 18   I²C, auto-detected
LED Green / Yel / Red GPIO 11/12/13  each through 2 kΩ to GND
```

Full wiring, picture of the breadboard and board layout live in the project's
build guide (not in this repo).

### Firebase settings for the bin

Edit **only** `firmware/smart_bin/config.h`:

```c
#define WIFI_SSID      "..."
#define WIFI_PASSWORD  "..."
#define FIREBASE_DB_URL "https://<your-project>-default-rtdb.<region>.firebasedatabase.app"
#define BIN_ID "bin_01"
```

Upload with Arduino IDE → Serial Monitor → calibrate once:

```
resetcal
tare                    (nothing on the scale)
cal 1000                (1 kg weight on the scale)
empty                   (bin empty, lid closed)
full 5                  ("full" line is 5 cm below the sensor)
gasbase                 (after 20 min warmup, lid closed, fresh air)
batcal 3.95             (whatever your multimeter shows on the battery)
show                    (confirm all four cal lines are populated)
```

After that the bin runs by itself. See `firmware/smart_bin/config.h` for every
tunable and `firmware/smart_bin/smart_bin.ino` → `printHelp()` for the full
serial command list.

---

## 5. Quick start — day-one developer

### 5.1 One-time install

```powershell
# Python 3.10 – 3.13 for every ML / Flask folder
cd smart_bin_ml           ; pip install -r requirements.txt ; cd ..
cd waste_forecast_routes  ; pip install -r requirements.txt ; cd ..
cd smartwaste_app         ; pip install -r requirements.txt ; cd ..

# (optional) PyTorch for the real LSTM forecaster — 200 MB, else a NumPy LSTM is used
pip install torch

# (optional) XGBoost — else Gradient Boosting is used
pip install xgboost
```

### 5.2 Start the website

```powershell
cd smartwaste_app
python app.py
```

Open **http://localhost:5000** . First launch asks you to create the
**first officer account**. After that:

- Officers log in on the *Municipal staff* tab.
- Citizens use the *Citizen* tab (sign up with name + password, or log in).
- The *System* page runs the ML scripts for you (one-click setup).

If no Firebase URL is configured, the app starts with the bundled **demo data**
(a yellow "DEMO DATA" badge appears on every page).

### 5.3 (Optional) Build the Android app

See [`smartwaste_mobile/README.md`](smartwaste_mobile/README.md). TL;DR:

```powershell
cd smartwaste_mobile
flutter create .
flutter pub get
flutter run
```

### 5.4 (Optional) Run a smart bin

See §4 above and `firmware/smart_bin/config.h`.

---

## 6. The web pages at a glance

(Full page list, user flow and sensor meaning are in
[`smartwaste_app/README.txt`](smartwaste_app/README.txt) sections 5 – 9.)

| Role | Pages |
|---|---|
| **Officer** | Operations · Bins · Bin detail · Forecast · Routes · Analytics · Reports · Community · Driver view · System |
| **Driver**  | My route (next stop, Navigate, Mark emptied, truck status) |
| **Citizen** | Home (nearest bin w/ space) · Report (with photo) · **Scan** (AI waste classifier, EN/SI/TA) · Rewards · Survey (SUS) |

Fill-level colours are used consistently everywhere and always paired with a
symbol + word (not colour alone):

> ✓ Normal `<50 %` · ● Filling `50–74 %` · ▲ Warning `75–89 %` · ✖ Critical `≥90 %`

---

## 7. Hosting

For an IT4010 project you don't need cloud hosting. The recommended setup:

| Component | Where it lives | Cost |
|---|---|---|
| Firebase Realtime DB | Firebase Spark (free) | $0 |
| Flask website | Your laptop (`python app.py`) | $0 |
| ESP32 bin | On the bench with battery | $0 (hardware once) |
| Flutter app | Android phone / emulator | $0 |

For the viva demo, keep everything on **localhost**. The ESP32 writes to
Firebase 24/7 regardless, so when you start the Flask app the dashboard shows
live data within 30 s.

If you ever need a public URL temporarily (e.g. for an off-site supervisor):
**Cloudflare Tunnel** exposes `localhost:5000` as `*.trycloudflare.com` in
~3 seconds for free, no credit card.

Firebase Spark alone **cannot** run the Flask backend — Firebase Hosting is
static-only, and Cloud Functions / Cloud Run require the Blaze (pay-as-you-go)
plan. See the conversation history in `.cursor/` for the full comparison of
hosting options.

---

## 8. Project credits & context

- **University**: Sri Lanka Institute of Information Technology (SLIIT)
- **Module**: IT4010 — Research Project
- **Group**: J26-ISE-305
- **Pilot area**: Kaduwela Municipal Council, Western Province, Sri Lanka
- **Built with**: Python 3 · Flask · Firebase Realtime Database · TensorFlow /
  Keras (EfficientNetB0) · scikit-learn · PyTorch (optional) · OR-Tools
  (optional) · Arduino / ESP-IDF · Flutter / Dart · OpenStreetMap · Leaflet

This is a **student prototype** meant for a local-network demonstration and
academic reporting. It is not hardened for public internet deployment —
production use would need HTTPS termination, a production WSGI server
(e.g. `waitress`), rate limiting, and locked-down Firebase security rules.

---

## 9. Where to look next

- **Running the website** → [`smartwaste_app/README.txt`](smartwaste_app/README.txt)
- **ML details (Component 2)** → [`smart_bin_ml/README.txt`](smart_bin_ml/README.txt)
- **Forecasting + routes (Component 3)** → [`waste_forecast_routes/README.txt`](waste_forecast_routes/README.txt)
- **Classifier (Component 1)** → [`waste_classifier/README.txt`](waste_classifier/README.txt)
- **Android app** → [`smartwaste_mobile/README.md`](smartwaste_mobile/README.md)
- **Firmware** → `firmware/smart_bin/config.h` (settings) and `smart_bin.ino` (code)
#   J 2 6 - I S E - 3 0 5 - S W a M S  
 #   J 2 6 - I S E - 3 0 5 - S W a M S  
 #   J 2 6 - I S E - 3 0 5 - S W a M S  
 #   S W a M S  
 #   J 2 6 - I S E - 3 0 5 - S W a M S  
 