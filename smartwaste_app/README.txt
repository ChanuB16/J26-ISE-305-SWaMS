SMARTWASTE LK - WEB APP
=======================
SLIIT IT4010 · J26-ISE-305 Intelligent Waste Management System · Kaduwela Municipal Council
Component 2 (IoT smart bin + ML) and Component 3 (waste forecast + truck routes) in one website.

It is ONE Python program (Flask). It shows the website and can also start the ML scripts for you.
No Node.js, and no second server, are needed.


1. WHAT YOU NEED
----------------
- Python 3.9 or newer (the same Python you use for smart_bin_ml and waste_forecast_routes).
- The four folders side by side, like this:

      my_project/
          smart_bin_ml/             (Component 2 ML - you already have it)
          waste_forecast_routes/    (Component 3 - you already have it)
          waste_classifier/         (Component 1 - the AI model + translations)
          smartwaste_app/           (this app)

  If your folders are somewhere else, change SMART_BIN_ML_DIR, WASTE_FORECAST_DIR and
  WASTE_CLASSIFIER_DIR in settings.py.


2. INSTALL (only once)
----------------------
Open a terminal (Command Prompt on Windows) in the smartwaste_app folder and type:

    pip install -r requirements.txt

That also installs TensorFlow + Pillow for the built-in waste scanner (Component 1).
If you do NOT want the scanner on this computer, set CLASSIFIER_MODEL = "" in
settings.py BEFORE installing, and delete the 4 lines under "Component 1" in
requirements.txt. The Scan tab will then show a short "not available" message
and the rest of the app runs normally.

(The ML scripts need their own packages too. You installed them before with
 pip install -r requirements.txt inside smart_bin_ml and waste_forecast_routes.)


3. START
--------
    python app.py

Then open  http://localhost:5000  in Chrome or Edge.
Stop the app with Ctrl+C in the terminal.

The first time, the login page asks you to make the FIRST OFFICER ACCOUNT (user name + password).
After that:
- Officers log in on the "Municipal staff" tab.
- Officers add driver accounts (and more officers) on the System page.
- Citizens only type their name (no password).

FIRST TIME ONLY: open the System page and click "Run all setup steps" (about 10-15 minutes).
It makes the training data, trains the models and runs the tests (scripts b2, b3, b4, f1, f2, r1, r2).
Then "Automatic mode" (on by default with Firebase) runs everything else by itself.


4. DEMO DATA OR YOUR FIREBASE?
------------------------------
DEMO DATA (no setup, no internet needed):
  If no Firebase URL is set, the app uses the example data in demo/demo_db.json.
  A yellow "DEMO DATA" badge is shown on every page. Changes are lost when you stop the app.
  The jobs on the System page also work in demo mode - they read and write the demo data.
  Automatic mode is OFF in demo mode (the demo data is already complete); turn it on if you want.
  The demo data was made by the real scripts (b6, b5, f3, r3, e1, e2) on SYNTHETIC data, and the
  history of bin_01 is made up. Never present demo numbers as real measurements.
  The demo times are moved to "now" when the app starts. Nothing new arrives in demo mode, so after
  30 minutes bin_01 shows "No data" - restart the app to make the demo data fresh again.

YOUR FIREBASE (the real system):
  The app reads the database URL from ../smart_bin_ml/settings.py automatically.
  Or put it in settings.py of this app (FIREBASE_DB_URL). Then restart:  python app.py
  The ML jobs started by the app always use the same database as the app, so you set the URL once.

  If you "locked the database" (test mode ended), set USE_LOGIN = True and fill in FIREBASE_API_KEY,
  FIREBASE_EMAIL and FIREBASE_PASSWORD (make a user like web@smartbin.test in Firebase Authentication).
  Only this app talks to Firebase - the browsers never see the database password.

  DEMO_MODE = True in settings.py forces demo data (a good backup if the internet fails in the
  presentation).


5. THE PAGES
------------
OFFICER (municipal staff)
  Operations     KPI tiles, live map of all bins coloured by fill level, early warnings, most urgent
                 bins, bins by level, forecast for 7 days, today's truck routes.
  Bins           Every bin with colour filters (Normal / Filling / Warning / Critical), area filter,
                 search, sort, map, CSV.
  Bin detail     (click a bin) Fill ring, ML prediction 6 hours ahead, overflow risk, time until full,
                 urgency score with its 4 parts, all sensors (weight, temperature, humidity, gas,
                 battery, WiFi), nearest bin with space, warnings, HISTORY of all readings
                 (6 h / 24 h / 3 days / 7 days / any day) as charts and a colour-coded table,
                 CSV of every reading, emptying history, device and calibration.
  Forecast       Tonnes per area for the next 7 days (daily and weekly view), busy days, holidays,
                 rain, why a day is busy, crew tips, a chart for each area, CSV.
  Routes         Route map with numbered stops, trucks, depot. Buttons: Road closed / Traffic jam
                 (then click the road on the map), Open all roads, Re-plan now, Truck broken / fixed.
                 Stop timelines, bins not collected (and why), bins emptied today, earlier days, CSV.
  Analytics      All ML results from the results folders: Component 2 (RQ1 data reliability
                 measured live from the real bin, RQ2 models, overflow
                 warnings, extra sensors, useful inputs, RQ3 ranking, RQ4 nearest bin),
                 Component 3 (forecast models, forecast vs real, holidays/weather, busy-day warnings,
                 days ahead, rolling check, route methods, trade-off, re-planning speed, km per day),
                 Usability (SUS) results, and the PNG charts the scripts saved.
  Reports        CSV downloads (bins, warnings, emptying history, forecast, routes, citizen reports,
                 rewards, readings of one bin, SUS) and a printable summary (Print / save as PDF).
  Community      Citizen reports with photos (set New / In progress / Resolved), green points
                 leaderboard, waste photos from Component 1, latest points, crew tips.
  Driver view    The driver's screen (to show it in the presentation).
  System         "Is everything working?" checklist with fix buttons, Automatic mode, FIRST-TIME
                 SETUP (one button), LIVE JOBS (start/stop, see their output), database info,
                 USERS AND ACCESS (add officer/driver accounts, roles, truck, switch off, new password).

DRIVER
  My route       Next stop (bin, time, fill level), Navigate (Google Maps), Mark as emptied,
                 route map, stop list, bins emptied today, Report truck broken / Truck fixed.

CITIZEN
  Home           Find the nearest bin WITH SPACE (use my location, or tap the map), map of bins with
                 colours, nearby bins, my points, tips.
  Report         Overflowing bin / illegal dumping / damaged bin / other, with photo and location.
                 My reports with status and points.
  Scan           Take or choose a photo of ONE item. The built-in AI (Component 1) says what type it is
                 (plastic / paper / glass / metal / organic) in English / Sinhala / Tamil and gives short
                 disposal tips. +10 points when the AI is 70%+ sure (added by the rewards job).
  Rewards        Points, level, progress, activity, leaderboard, how to earn points.
  Survey         The 10 SUS questions (usability). Officers see the results under Analytics.

Fill level colours (everywhere, always with a symbol and a word, not colour only):
  ✓ Normal  below 50%  (green)    ● Filling  50-74%  (yellow)
  ▲ Warning 75-89%     (orange)   ✖ Critical 90% or more (red)


6. YOU DO NOT RUN THE PYTHON SCRIPTS BY HAND
--------------------------------------------
Everything that you ran in a terminal before is done by the app (System page):

  What                                   Script(s)                     How it runs now
  -------------------------------------  ----------------------------  -----------------------------------
  Training data, models, tests (RQ1-4)   b2, b3, b4, f1, f2, r1, r2    "Run all setup steps" - once
  Your real bin's data for training      (Firebase export)             copied automatically before b2
  Live bin predictions (every 5 min)     b5_live_predictions.py        Automatic mode: always running
  Live route planner + re-planning       r3_live_routes.py             Automatic mode: always running
  7-day forecast + crew tips             f3, e2                        Automatic mode: every day (05:00)
  Reward points                          e1_rewards.py                 Automatic mode: every 10 minutes
  RQ1 numbers (valid rate, delay)        tools/rq1_metrics.py          Analytics page, live
  Nearest bin with space                 b6_nearest_bin.py             Citizen page and bin page
  20 demo bins / truck simulator         b6_demo_bins.py, r4           buttons on the System page (demos)

The System page also shows "Is everything working?" with a button next to anything that is red,
the output of every script, and the Automatic mode switches.
If a job stops with an error, Automatic mode starts it again after 1 minute (3 times, then it
waits for you - open its output to see why).

Component 1 (the AI waste classifier) is NOT a separate server any more. It is built into this
app and shows up as the "Scan" tab for citizens. There is nothing to start by hand - the model
is loaded the first time a citizen taps "Classify" (about 5-10 seconds the first time only).

So in daily use you only:
  1. switch on the smart bin (it sends by itself - the Arduino program runs on the ESP32), and
  2. start  python app.py  on the computer that acts as the server (it must stay on and online).

The bin's program is uploaded only once with the Arduino IDE, and calibrated only once in the
Serial Monitor (tare, cal 1.0, empty, full, gasbase, batcal). It sends every 30 seconds by itself.
You can still run any script in a terminal yourself, exactly as before.


7. USING IT ON A PHONE
----------------------
In settings.py set  HOST = "0.0.0.0"  and restart. Find the computer's IP address
(Windows: type ipconfig, look for IPv4, e.g. 192.168.1.20). On a phone on the SAME WiFi open
http://192.168.1.20:5000 . If it does not open, allow Python through the Windows firewall.
Phones only share their location with https pages, so on the phone tap the map instead of
"Use my location" (on the computer itself, localhost works).


8. HOW TO SHOW IT IN THE PRESENTATION (about 6 minutes)
--------------------------------------------------------
 1. Log in as officer. Operations: the bins in colours, KPI tiles, early warnings.
 2. Bins: click "Critical". Open bin_01: live sensors, the ML prediction for 6 hours and the
    urgency parts. Scroll to History: switch 24 h / 7 days, show the coloured table, download CSV.
 3. Put rubbish in the real bin. Within 30 seconds (the bin sends every 30 s) the fill ring and the
    history change.
 4. Forecast: busy days and why. Analytics: the model comparison charts (they answer the RQs).
 5. Routes: click "Road closed" and click a road on the route. The planner makes new routes in
    under a second (Re-plan time tile). Click "Truck broken" - its bins move to the other truck.
 6. Driver view (or a phone logged in as driver): Navigate and Mark as emptied.
 7. Citizen (phone): find the nearest bin with space, send a report with a photo. Back as officer:
    Community shows it; set it to Resolved.
 8. Ask 5+ people to fill in the Survey. Analytics > Usability shows the SUS score (target 68+).
 9. System: show "Is everything working?" all green and the jobs running by themselves.


9. FILES
--------
  app.py          the web server (pages + JSON API + the demo database door for the jobs)
  settings.py     the only file to edit
  fb.py           Firebase (REST) and the demo database
  data.py         combines the data for the pages (levels, urgency parts, nearest bin, alerts)
  jobs.py         starts/stops the ML scripts
  results.py      reads the CSV/PNG results of the ML scripts
  users.py        staff accounts (instance/users.json, passwords stored as hashes)
  classifier.py   Component 1 - loads the AI model on the first request (lazy)
  templates/      the HTML pages            static/   CSS, JavaScript, charts, maps
  demo/           demo_db.json and a sample copy of the results (used if the ML folders are missing)
  instance/       made by the app: users.json, the secret key and the Automatic mode settings -
                  do not share this folder


10. PROBLEMS
------------
  "Firebase said permission denied"  -> test mode ended: see part 4 (USE_LOGIN).
  "Cannot reach Firebase"             -> internet, or wrong FIREBASE_DB_URL.
  Map shows "Simple map (no internet…)" -> no internet for the street map; the points are still
                                         right. Everything else works.
  A job says "script not found"       -> the ML folders are not next to this folder (part 1).
  A job "failed"                      -> click "Show output" and read the last lines.
  "Download the road map" failed      -> no internet. Use "Road map without internet" (made-up
                                         roads, testing only), then run "Test the route methods".
  Forgot the officer password         -> stop the app, delete instance/users.json, start again
                                         (you can make a new first officer account).
  Port 5000 in use                    -> change PORT in settings.py.

This is a student prototype for a local network. For use on the internet it would need https and
a production server (for example waitress), not "python app.py".
