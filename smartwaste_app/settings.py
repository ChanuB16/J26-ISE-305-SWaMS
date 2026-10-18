"""
SMARTWASTE LK WEB APP - SETTINGS
================================
This is the only file you need to edit. Change the parts marked  <-- CHANGE  if you need to.
Then start the app with:   python app.py
"""

# ---------- 1. Firebase Realtime Database ----------
# Leave these as they are to use the SAME database and login as ../smart_bin_ml/settings.py
# (the app reads that file automatically). Or paste your database URL here.
FIREBASE_DB_URL = "https://smart-bin-kaduwela-default-rtdb.asia-southeast1.firebasedatabase.app"   # <-- CHANGE (or leave)
USE_LOGIN = False
FIREBASE_API_KEY = "YOUR_WEB_API_KEY"
FIREBASE_EMAIL = "web@smartbin.test"
FIREBASE_PASSWORD = "CHANGE_THIS_PASSWORD"

# ---------- 2. Demo mode ----------
# "auto" = use the example data in demo/demo_db.json while no database URL is set.
# True   = always use the example data (works with no internet - good as a backup for the presentation).
# False  = always use Firebase.
# In demo mode, everything you change lives only until you stop the app.
DEMO_MODE = "auto"

# ---------- 3. Web server ----------
HOST = "127.0.0.1"      # "0.0.0.0" = phones on the same WiFi can open the app too (see README)
PORT = 5000
REFRESH_SECONDS = 15    # pages fetch new data this often

# ---------- 4. The two ML project folders (results + live jobs) ----------
# Paths are relative to this folder. Default: the three folders sit side by side.
SMART_BIN_ML_DIR = "../smart_bin_ml"
WASTE_FORECAST_DIR = "../waste_forecast_routes"
PYTHON = ""             # empty = the same Python that runs this app

# Jobs to start by themselves when the app starts (names from the System page), e.g.
# AUTO_START_JOBS = ["predictions", "routes"]
AUTO_START_JOBS = []

# ---------- 4b. Component 1 (waste classifier) ----------
# The classifier is built into this app. The model and the translations live
# in ../waste_classifier (keep that folder next to this one). Set
# CLASSIFIER_MODEL = "" to switch off the Scan tab (useful when TensorFlow is
# not installed on this computer).
WASTE_CLASSIFIER_DIR = "../waste_classifier"
CLASSIFIER_MODEL = "best_model.keras"   # file inside <WASTE_CLASSIFIER_DIR>/models/
CLASSIFIER_SURE_LEVEL = 0.60            # below this the AI says "not sure"

# ---------- 5. Numbers (same as the ML settings.py files) ----------
OVERFLOW_PCT = 90       # 90% or more = critical / overflowing
ALERT_PCT = 75          # 75% or more = warning
FILLING_PCT = 50        # 50% or more = filling
SPACE_LIMIT_PCT = 80    # a bin "has space" below 80% (nearest-bin search)
MAX_WALK_KM = 2.0       # nearest-bin search radius
SMELL_INDEX = 60        # gas_index 60 or more = strong smell
LOW_BATTERY_PCT = 20
NO_DATA_MINUTES = 30    # a real bin with no reading for 30 minutes = "no recent data"
W_FILL, W_GAS, W_HUMIDITY, W_TIME = 0.5, 0.2, 0.1, 0.2   # urgency score weights (proposal)
FULL_TIME_HOURS = 72
URGENCY_MEDIUM, URGENCY_HIGH = 45, 75

DEPOT = (6.9330, 79.9830)
DEPOT_NAME = "Council yard (Kaduwela)"
DIESEL_PRICE_LKR = 392
SUS_TARGET = 68         # usability target (proposal)
