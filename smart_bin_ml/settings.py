"""
SMART BIN - ML PART SETTINGS
============================
This is the only file you need to edit.
Change the lines marked  <-- CHANGE  (only needed for steps B5 and B6).
"""

# ---------- 1. Firebase (the SAME database as the bin) ----------
# Copy it from Firebase console > Realtime Database > Data (the link at the top). No "/" at the end.
FIREBASE_DB_URL = "https://smart-bin-kaduwela-default-rtdb.asia-southeast1.firebasedatabase.app"   # <-- CHANGE

# Login. Keep False while the database is in "test mode" (the first 30 days).
# After you lock the database (guide: "Before day 30"), set True and fill in the 3 values.
USE_LOGIN = False
FIREBASE_API_KEY = "YOUR_WEB_API_KEY"
FIREBASE_EMAIL = "bin01@smartbin.test"
FIREBASE_PASSWORD = "CHANGE_THIS_PASSWORD"

# ---------- 2. Prediction ----------
HORIZON_HOURS = 6     # predict the fill level 6 hours ahead (students' project guide)
STEP_MINUTES = 15     # readings are put on a 15-minute grid before the model sees them
OVERFLOW_PCT = 90     # a bin at 90% or more counts as "overflowing"
ALERT_PCT = 75        # B0 baseline: alert when the CURRENT fill is 75% or more
SMELL_INDEX = 60      # gas_index 60 or more counts as a strong smell

# ---------- 3. Urgency score (same weights as the bin and the proposal) ----------
W_FILL = 0.5          # predicted fill level (0 to 100)
W_GAS = 0.2           # gas_index (0 to 100)
W_HUMIDITY = 0.1      # humidity_pct (0 to 100)
W_TIME = 0.2          # time since the bin was emptied (scaled to 0 to 100)
FULL_TIME_HOURS = 72  # 72 hours since emptying = time score 100

# ---------- 4. Nearest bin finder ----------
SPACE_LIMIT_PCT = 80  # a bin "has space" when its current fill is below 80%
MAX_WALK_KM = 2.0     # look for a bin with space within 2 km

# ---------- 5. Live predictions (step B5) ----------
LIVE_EVERY_MINUTES = 5  # make new predictions every 5 minutes
NO_DATA_MINUTES = 30    # no reading for 30 minutes = status "no_recent_data"

# ---------- 6. Synthetic training data (step B2) ----------
N_DAYS = 60                 # 60 days, as the students' guide asks
START_DATE = "2026-08-01"   # first day of the synthetic data
SEED = 42                   # same seed = same data and same results every time
