"""
WASTE FORECASTING AND ROUTES (COMPONENT 3) - SETTINGS
=====================================================
This is the only file you need to edit.
Change the lines marked  <-- CHANGE  (only needed for the Firebase steps F3, R3, R4, E1 and E2).
"""

# ---------- 1. Firebase (the SAME database as the bin and Part B) ----------
FIREBASE_DB_URL = "https://YOUR-PROJECT-default-rtdb.asia-southeast1.firebasedatabase.app"   # <-- CHANGE
USE_LOGIN = False                      # same meaning as in Part B (keep False in test mode)
FIREBASE_API_KEY = "YOUR_WEB_API_KEY"
FIREBASE_EMAIL = "routes@smartbin.test"
FIREBASE_PASSWORD = "CHANGE_THIS_PASSWORD"

# ---------- 2. The council area ----------
# 6 areas (zones) of the Kaduwela Municipal Council. Centre point and number of people.
# The whole council had 264,451 people in 2018 (UTS waste fact sheet). The split between the
# areas is our estimate - replace it with ward numbers from the council if you get them.
ZONES = {
    #  name           lat      lng      people
    "Malabe":       (6.9061, 79.9696, 52000),
    "Kaduwela":     (6.9358, 79.9840, 40000),
    "Battaramulla": (6.9000, 79.9180, 58000),
    "Athurugiriya": (6.8731, 79.9970, 46000),
    "Thalangama":   (6.9150, 79.9330, 32000),
    "Hokandara":    (6.8890, 79.9690, 36451),
}
# Where the trucks start and finish (council yard). Approximate: Kaduwela MC building,
# New Kandy Road, Kaduwela. Move it to the real yard if you know it.
DEPOT = (6.9330, 79.9830)
DEPOT_NAME = "Council yard (Kaduwela)"
# The real smart bin from Part A (if it has no location in Firebase yet). SLIIT Malabe campus.
REAL_BIN = {"bin_id": "bin_01", "lat": 6.9147, "lng": 79.9729, "zone": "Malabe", "type": "school"}

# ---------- 3. Waste data (step F1) ----------
HISTORY_START = "2024-10-01"   # 2 years of daily data per area
HISTORY_END = "2026-09-30"
TONNES_PER_DAY = 71.0          # waste collected per day by the council (UTS fact sheet, 2018)
SEED = 42                      # same seed = same data and same results every time

# ---------- 4. Forecasting (step F2) ----------
LOOKBACK_DAYS = 28             # the LSTM looks at the last 28 days
FORECAST_DAYS = 7              # forecasts for the next 7 days (step F3)
HIGH_WASTE_PERCENTILE = 90     # a "high-waste day" = more than 90% of the area's normal days

# ---------- 5. Trucks and costs (steps R2, R3) ----------
N_TRUCKS = 2                   # trucks available for the smart bins
TRUCK_CAPACITY_KG = 3000       # small compactor truck
SHIFT_START = "06:00"          # the collection round starts at 6 am
SHIFT_HOURS = 4.0              # each truck must be back within 4 hours
SERVICE_MINUTES = 4            # time to empty one bin
FUEL_L_PER_KM = 0.5            # diesel per km in stop-and-go collection (our assumption; big European
                               # collection trucks use about 1 L/km - Sousa et al., 2023)
DIESEL_PRICE_LKR = 392         # Rs per litre (CPC price from 1 Oct 2026 - update it)
BIN_LITRES = 240               # the route test treats every bin as a 240-litre public bin
SOLVER_SECONDS = 3             # time limit for the route solver (the proposal asks for < 5 s)

# ---------- 6. Which bins to collect (steps R2, R3) ----------
REACTIVE_FILL_PCT = 70         # "reactive" method: collect bins that are 70% full or more NOW
PREDICT_FILL_PCT = 90          # "predictive" method: collect bins that WILL be 90% or more by the next round
OPTIONAL_FILL_PCT = 70         # bins above this are collected too if they are almost on the way (5 min)
URGENT_SCORE = 60              # bins with a Part B urgency score of 60+ are always collected
MAX_DAYS_WITHOUT_EMPTYING = 3  # food waste bins are emptied at least every 3 days (smell)

# ---------- 7. Route test (step R2) ----------
ROUTE_TEST_START = "2026-04-06"  # 30 days that include Sinhala and Tamil New Year and Vesak
ROUTE_TEST_DAYS = 30

# ---------- 8. Traffic (steps R1 to R3) ----------
# Normal driving speed (km/h) on each road type, and how much slower the main roads get at rush hour.
ROAD_SPEED_KMH = {"trunk": 35, "primary": 32, "secondary": 28, "tertiary": 25, "unclassified": 20,
                  "residential": 18, "living_street": 10, "service": 12, "other": 18}
RUSH_HOURS = [(7.0, 9.5), (16.5, 19.0)]   # morning and evening rush hours
RUSH_SLOWDOWN = 0.55           # main roads at rush hour: 55% of the normal speed

# ---------- 9. Live routes (step R3) ----------
LIVE_EVERY_MINUTES = 5         # check Firebase for changes every 5 minutes

# ---------- 10. Rewards (step E1) ----------
POINTS_SEGREGATION_PHOTO = 10  # a waste photo classified by Component 1 (confidence 70%+)
POINTS_OVERFLOW_REPORT = 5     # a report of a full bin, confirmed by the bin's sensor (80%+ full)
HIGH_WASTE_DAY_BONUS = 2       # points x2 on forecast high-waste days (festivals)
