SMART BIN - ML PART (C2: fill-level prediction, overflow risk, urgency score, nearest bin)
=======================================================================================

Python 3.10 or newer. Follow Part B of the build guide; this is the short version.

1. Install once (in this folder):      pip install -r requirements.txt
2. Make the training data:            python b2_make_data.py
3. Train and compare the models:      python b3_train_models.py            (about 1 minute)
4. Test urgency + nearest bin:        python b4_test_urgency_and_nearest.py
5. Live predictions (bin running):    python b5_live_predictions.py        (edit settings.py first)
6. Citizen nearest bin:               python b6_nearest_bin.py 6.9061 79.9696
   Demo bins for the team:            python b6_demo_bins.py --add   /   --remove

Files
  settings.py                 the only file you edit (Firebase URL, login, thresholds, weights)
  binlib.py                   shared code: 15-minute grid, features, urgency score, Firebase
  charts.py                   the report charts
  b2_make_data.py             60 days x 20 synthetic bins (+ your real bin, if data/smart-bin-export.json exists)
  b3_train_models.py          RQ2: baselines vs Linear Regression, Random Forest, Gradient Boosting, MLP;
                              feature test B1-B4; overflow test vs the 75% threshold (B0)
                              optional: --xgboost (after: pip install xgboost)
  b4_test_urgency_and_nearest.py   RQ3: U0 / U1 / U2 ranking;  RQ4: R0 / R1 nearest bin
  b5_live_predictions.py      RQ5: reads the bin from Firebase, writes predictions/<bin_id>
  b6_nearest_bin.py           nearest bin with space for a citizen (from Firebase)
  b6_demo_bins.py             copies the 20 synthetic bins into Firebase for the team (marked synthetic)

Made by the scripts
  data/      readings.csv, collections.csv, bins.csv (+ real_readings.csv, real_collections.csv)
  results/   model.joblib, rq2_models.csv, rq2_feature_test.csv, rq2_overflow.csv, rq2_inputs.csv,
             rq3_urgency.csv, rq4_nearest.csv, chart_models.png, chart_example.png, chart_inputs.png,
             chart_urgency.png

Firebase output: predictions/<bin_id>
  current_fill_pct, predicted_fill_6h, overflow_risk (low/medium/high), hours_to_full, urgency_score,
  gas_index, humidity_pct, hours_since_collection, lat, lng, zone, status (ok/warming_up/no_recent_data),
  based_on_ts, updated_at, model

Tested with Python 3.13, pandas 3.0, scikit-learn 1.9. Same settings and seed = same results.
