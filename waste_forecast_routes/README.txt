WASTE FORECASTING AND ROUTES (COMPONENT 3) + DASHBOARD
=====================================================

Python 3.10 to 3.13. Follow Part C of the build guide; this is the short version.

1. Install once (in this folder):    pip install -r requirements.txt
   Optional, for the official LSTM:  pip install torch          (about 200 MB; without it a NumPy LSTM is used)
2. Make the waste data:               python f1_make_data.py
3. Train and compare the forecasts:   python f2_train_forecast.py       (2-4 minutes)
4. Get the road map (internet):       python r1_road_map.py             (1-3 minutes, once)
5. Test the routes for 30 days:       python r2_test_routes.py          (2-5 minutes)
6. Forecasts for the next 7 days:     python f3_forecasts_to_firebase.py (edit settings.py first)
7. Live routes (keep running):        python r3_live_routes.py
   Truck simulator (demo, optional):  python r4_truck_simulator.py
8. Citizen rewards:                   python e1_rewards.py   (first time: --demo)
9. Crew tips:                         python e2_crew_tips.py
10. Dashboard:                        edit dashboard/config.js, then  python dashboard/open_dashboard.py

Files
  settings.py               the only Python file you edit (Firebase URL, trucks, costs, thresholds)
  holidays_lk.csv           Sri Lankan public holidays and Poya days 2024-2027 (check new years in the gazette)
  events.csv                planned events and road closures - the rows are EXAMPLES, replace them
  wastelib.py               shared code: calendar, weather, Firebase
  forecasting.py            features, Linear Regression, XGBoost, LSTM (PyTorch or NumPy), 7-day forecasts
  roads.py                  OpenStreetMap roads, rush hours, road closures, fastest paths
  routing.py                which bins to collect, the route solver (OR-Tools or built-in), the 30-day test
  maps.py, charts.py        maps (HTML) and charts (PNG) for the report
  f1 ... f3                 forecasting steps          r1 ... r4   route steps
  e1, e2                    rewards and crew tips      dashboard/  the web dashboard (C2 + C3)

Made by the scripts
  data/      waste_daily.csv, weather.csv, calendar.csv, zones.csv, bins.csv, roads_*.csv
  results/   forecast_model.joblib, f2_*.csv, r2_*.csv, chart_*.png, map_*.html, forecast_next7.csv

Firebase (written by these scripts)
  forecasts/<area>/<date>   forecast_t, normal_t, change_pct, high_waste, holiday, rain_mm
  routes/<date>/<truck>     stops (bin, arrival time, fill), km, minutes, fuel_l, cost_lkr, path
  routes/<date>/_summary    planned, skipped (+ reason), replan_seconds, solver, roads
  trucks/<truck>            status (available / on_route / broken), lat, lng, ts
  traffic/<id>              kind (closure / jam), lat, lng, radius_m, until, note   (dashboard writes these)
  rewards/<user>            points, history          guidance/<date>/<area>   crew tips

Real data: put the council's records in data/council_waste.csv (date, zone, waste_t) and run f1 again.
Tested here with Python 3.13, pandas 3.0, scikit-learn 1.9 (XGBoost, OR-Tools and PyTorch were not
available in the test machine - the scripts then use Gradient Boosting, the built-in solver and the NumPy LSTM).
