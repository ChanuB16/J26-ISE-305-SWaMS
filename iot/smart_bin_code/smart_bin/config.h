/*
  SMART BIN - SETTINGS
  ====================
  This is the ONLY file you need to edit.
  Change the parts marked  <-- CHANGE  and upload again.

  v1.3.0 (small bin): HC-SR04 ultrasonic sensor + 20 cm bin + weight in grams.
*/
#pragma once

// ---------- 1. WiFi (2.4 GHz only) ----------
#define WIFI_SSID      "xxxxxx"        // <-- CHANGE
#define WIFI_PASSWORD  "xxxxxxx"      // <-- CHANGE

// ---------- 2. Firebase Realtime Database ----------
// Copy from Firebase console > Realtime Database > Data (the link at the top).
// Example: "https://smart-bin-1234-default-rtdb.asia-southeast1.firebasedatabase.app"
// No "/" at the end.
#define FIREBASE_DB_URL "https://smart-bin-kaduwela-default-rtdb.asia-southeast1.firebasedatabase.app"   // <-- CHANGE

// Login. Keep 0 while the database is in "test mode".
// Set to 1 before test mode ends (30 days) - see the guide, part "Lock the database".
#define FIREBASE_USE_LOGIN 0
#define FIREBASE_API_KEY   "YOUR_WEB_API_KEY"      // Project settings > General > Web API key
#define FIREBASE_EMAIL     "bin01@smartbin.test"   // the user you add in Authentication > Users
#define FIREBASE_PASSWORD  "CHANGE_THIS_PASSWORD"

// ---------- 3. This bin ----------
#define BIN_ID "bin_01"   // data goes to /bins/bin_01 in Firebase

// ---------- 4. Timing (fixed - no need to change) ----------
#define SEND_INTERVAL_SEC   30   // one reading every 30 seconds, sent to Firebase at once
#define GAS_WARMUP_MINUTES  20   // gas sensor needs this long after power-on

// ---------- 5. Bin size: 20 cm tall bin + HC-SR04 sensor ----------
// Sensor must be HC-SR04 (NOT the waterproof JSN-SR04T). HC-SR04 can measure
// down to about 4 cm; JSN-SR04T cannot see anything closer than ~20 cm, so it
// cannot sense a 20 cm tall bin at all. Same 4 wires, same 3 resistors.
//
// If your bin is tall (30+ cm) and you keep the JSN-SR04T, change these back to:
//     DEFAULT_EMPTY_DISTANCE_CM 60.0f
//     DEFAULT_FULL_DISTANCE_CM  25.0f
//     MIN_FULL_DISTANCE_CM      20.0f
#define DEFAULT_EMPTY_DISTANCE_CM 20.0f   // sensor at the lid -> bottom of an EMPTY 20 cm bin
#define DEFAULT_FULL_DISTANCE_CM  5.0f    // "full" line is 5 cm below the sensor (bin fills 15 cm)
#define MIN_FULL_DISTANCE_CM      4.0f    // HC-SR04 minimum reliable range

// ---------- 5b. Weight: max 1 kg load, DISPLAYED and CALIBRATED in grams ----------
// Everything on the serial monitor shows grams; the 'cal' command takes grams:
//   cal 1000      means "there is 1000 g (1 kg) on the scale right now"
// Firebase still stores weight_kg in kilograms (0.000 to 1.000), so the ML
// pipeline, the Flask app, the dashboard and the demo DB do NOT change.
#define WEIGHT_SENSOR_FULL_G    1000.0f   // 1 kg = your bin's max load (just a note; not enforced)
#define COLLECTION_WEIGHT_MIN_G  200.0f   // trigger "emptied" only if before >= 200 g

// ---------- 6. Pins - must match the wiring diagram. Do not change unless you rewire. ----------
#define PIN_GAS_AO    4    // MQ-135 AO, through the gas divider (jumper from 45-j)
#define PIN_US_TRIG   5    // HC-SR04 Trig (same hole as the old JSN-SR04T Trig)
#define PIN_US_ECHO   6    // HC-SR04 Echo, through the echo divider (jumper from 31-j)
#define PIN_DHT       7    // DHT22 DAT
#define PIN_BATTERY   10   // battery voltage, through the battery divider (jumper from 59-j)
#define PIN_HX711_DT  15   // HX711 DT
#define PIN_HX711_SCK 16   // HX711 SCK

// Clock module DS3231 (found automatically). Powered from the 3.3V row (row 40, holes f-j).
#define PIN_RTC_SDA   17
#define PIN_RTC_SCL   18

// Status lights (optional, if time): each LED through a 2k resistor to GND
#define PIN_LED_GREEN  11
#define PIN_LED_YELLOW 12
#define PIN_LED_RED    13

// ---------- On-device urgency score (drives the status lights) ----------
// Same weights as the students' guide. It uses the CURRENT fill level;
// the prediction part (Component 2 ML) computes the urgency from the PREDICTED fill.
#define URGENCY_W_FILL      0.5f
#define URGENCY_W_GAS       0.2f
#define URGENCY_W_HUMIDITY  0.1f
#define URGENCY_W_TIME      0.2f
#define URGENCY_FULL_TIME_HOURS 72.0f   // this many hours since last collection = 100
#define URGENCY_YELLOW 45               // green below 45, yellow from 45
#define URGENCY_RED    75               // red from 75

// ---------- 7. Voltage dividers (all resistors 22k) ----------
#define GAS_DIVIDER_FACTOR     1.5f   // 22k on top, 22k + 22k below
#define BATTERY_DIVIDER_FACTOR 2.0f   // 22k on top, 22k below

// ---------- 8. Other ----------
#define TIMEZONE   "IST-5:30"   // Sri Lanka (UTC+5:30)
#define FW_VERSION "1.3.0"
