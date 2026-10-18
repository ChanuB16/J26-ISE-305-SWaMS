/*
  SMART BIN - MAIN PROGRAM  (ESP32-S3)
  ====================================
  Every 30 seconds it measures:
    - fill level   (HC-SR04 ultrasonic sensor, for small 20 cm bins)
    - weight       (5 kg load cell + HX711, max 1 kg load in this bin, shown in GRAMS)
    - gas          (MQ-135)
    - temperature + humidity (DHT22)
    - battery voltage
  and sends them to Firebase Realtime Database:
    /bins/bin_01/latest              newest reading (overwritten each time)
    /bins/bin_01/readings/<time>     history (one entry per reading)
    /bins/bin_01/last_collected      time the bin was last emptied
    /bins/bin_01/collections/<time>  history of emptying events
    /bins/bin_01/device              firmware + calibration info

  v1.3.0 changes vs 1.2.0:
    - Ultrasonic sensor is now HC-SR04 (small bin). Change the 3 size numbers in
      config.h back to the old values if you keep the JSN-SR04T on a tall bin.
    - Serial monitor shows weight in GRAMS. The 'cal' command takes GRAMS
      ('cal 1000' with a 1 kg weight). Firebase field weight_kg is unchanged
      (stays in kilograms, so the ML and Flask app are not affected).
    - Collection detector threshold lowered to 200 g before (was 500 g).

  If WiFi is down, readings are kept in memory (up to 4 hours) and sent later.
  DS3231 clock module: keeps the time without WiFi (found automatically; the program
  still runs without it). Optional: 3 status lights (green / yellow / red) driven by
  an on-device urgency score.

  Settings: edit config.h
  Calibration: open Serial Monitor (115200 baud, "Newline") and type: help

  Libraries (Tools > Manage Libraries):
    - "HX711 Arduino Library" by Bogdan Necula
    - "DHT sensor library" by Adafruit (+ "Adafruit Unified Sensor")
    - "ArduinoJson" by Benoit Blanchon (version 7)
*/

#include <WiFi.h>
#include <Wire.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include <HX711.h>
#include <time.h>
#include <sys/time.h>
#include "esp_sntp.h"
#include "config.h"

// =====================================================================
// Types (all types are declared here, before any function)
// =====================================================================

// One set of measurements. NAN means "no valid value".
struct Reading {
  int64_t tsMs;        // UTC time in milliseconds since 1970 (0 = clock not set yet)
  uint32_t uptimeMs;   // millis() when measured (used to work out the time later)
  float distanceCm;
  float fillPct;
  float weightKg;      // internal unit is kg (Firebase expects weight_kg); displayed as grams
  float gasMv;
  float gasIndex;
  float tempC;
  float humidityPct;
  float batteryV;
  float urgency;       // on-device urgency 0-100 (from CURRENT fill)
  uint32_t seq;        // reading number since power-on (0 = not a queued reading)
  bool gasReady;
};

// Running statistics for the "stats" command (calibration tests)
struct Stat {
  int n;
  double sum;
  double sumSq;
  double minV;
  double maxV;
};

// A "bin was emptied" event waiting to be sent.
struct CollectionEvent {
  bool pending;
  int64_t tsMs;
  uint32_t uptimeMs;
  float fillBefore;
  float weightBefore;
  float fillAfter;
  float weightAfter;
};

// =====================================================================
// Global objects and settings
// =====================================================================
DHT dht(PIN_DHT, DHT22);
HX711 scale;
Preferences prefs;

// Calibration values (saved in the ESP32's memory, kept after power-off)
long calWeightOffset = 0;        // HX711 raw value with nothing on it
float calWeightScale = 0;        // raw units per kg (0 = not calibrated)
float calEmptyCm = DEFAULT_EMPTY_DISTANCE_CM;
float calFullCm = DEFAULT_FULL_DISTANCE_CM;
float calGasBaseMv = 0;          // clean-air gas reading (0 = not set)
float calBatteryFactor = 1.0f;   // correction from the "batcal" command

// Gas index: ratio 1.0 = clean air (index 0). Ratio 0.3 or lower = index 100.
const float GAS_RATIO_AT_100 = 0.30f;

// Offline buffer (ring buffer). 480 readings = 4 hours at one reading every 30 s.
const int BUFFER_SIZE = 480;
Reading buffer[BUFFER_SIZE];
int bufHead = 0;
int bufCount = 0;

// Collection (emptying) detection
Reading lastReading;
bool haveLastReading = false;
bool collectionSuspected = false;
Reading beforeCollection;
CollectionEvent collectionEvent = {false, 0, 0, NAN, NAN, NAN, NAN};

// Counters for the report (RQ1: transmission success)
uint32_t bootCount = 0;      // how many times the board has started
uint32_t seqCounter = 0;     // readings queued since power-on
int64_t lastCollectedMs = 0; // time of the last emptying (0 = unknown)

// Clock module + time sync
bool rtcFound = false;
volatile bool ntpJustSynced = false;

// Program state
uint32_t lastReadMs = 0;
uint32_t lastFlushTryMs = 0;
uint32_t lastWifiTryMs = 0;
bool forceRead = false;
bool timeStarted = false;
bool clockReported = false;
bool deviceInfoSent = false;
String idToken;
uint32_t idTokenMs = 0;
String serialLine;

// =====================================================================
// Small helpers
// =====================================================================
bool ok(float x) {
  return !isnan(x);
}

double round1(float x) {
  return round((double)x * 10.0) / 10.0;
}

double round2(float x) {
  return round((double)x * 100.0) / 100.0;
}

// Text for printing: "--" when there is no value
String fmt(float x, int decimals) {
  if (!ok(x)) return "--";
  return String(x, (unsigned int)decimals);
}

// Weight formatter: shows GRAMS to the user (kg * 1000 rounded to a whole number).
String fmtWeightG(float kg) {
  if (!ok(kg)) return "--";
  return String((long)lroundf(kg * 1000.0f)) + " g";
}

// Current time in ms since 1970 (UTC). 0 if the clock is not set yet.
int64_t nowEpochMs() {
  struct timeval tv;
  gettimeofday(&tv, nullptr);
  if (tv.tv_sec < 1700000000) return 0;
  return (int64_t)tv.tv_sec * 1000LL + tv.tv_usec / 1000;
}

// Fill in a missing time using how long ago (in millis) the reading was taken
int64_t fixTime(int64_t tsMs, uint32_t uptimeMs, int64_t nowMs) {
  if (tsMs != 0) return tsMs;
  return nowMs - (int64_t)(millis() - uptimeMs);
}

String localTimeText(int64_t tsMs) {
  if (tsMs == 0) return "time not set";
  time_t t = (time_t)(tsMs / 1000);
  struct tm tmv;
  localtime_r(&t, &tmv);
  char buf[32];
  strftime(buf, sizeof(buf), "%Y-%m-%d %H:%M:%S", &tmv);
  return String(buf);
}

// =====================================================================
// Settings (saved calibration)
// =====================================================================
void loadSettings() {
  calWeightOffset = prefs.getLong("w_off", 0);
  calWeightScale = prefs.getFloat("w_scale", 0);
  calEmptyCm = prefs.getFloat("d_empty", DEFAULT_EMPTY_DISTANCE_CM);
  calFullCm = prefs.getFloat("d_full", DEFAULT_FULL_DISTANCE_CM);
  calGasBaseMv = prefs.getFloat("gas_base", 0);
  calBatteryFactor = prefs.getFloat("bat_cal", 1.0f);
  lastCollectedMs = prefs.getLong64("last_col", 0);
}

void printSettings() {
  Serial.println("---- Calibration ----");
  Serial.printf("  Empty bin distance : %.1f cm   (command: empty)\n", calEmptyCm);
  Serial.printf("  Full line distance : %.1f cm    (command: full 5)\n", calFullCm);
  Serial.printf("  Weight zero        : %ld        (command: tare)\n", calWeightOffset);
  Serial.printf("  Weight factor      : %.1f %s (command: cal 1000  <- grams)\n",
                calWeightScale, calWeightScale == 0 ? "NOT CALIBRATED" : "");
  Serial.printf("  Gas clean-air      : %.0f mV %s (command: gasbase)\n", calGasBaseMv, calGasBaseMv == 0 ? "NOT SET" : "");
  Serial.printf("  Battery correction : x%.3f     (command: batcal 3.95)\n", calBatteryFactor);
  Serial.printf("  Sends to Firebase  : every %d s (fixed)\n", SEND_INTERVAL_SEC);
}

// =====================================================================
// Sensors
// =====================================================================

// DHT22: temperature (C) and humidity (%). Tries twice.
void readDht(float &tempC, float &humidity) {
  tempC = dht.readTemperature();
  humidity = dht.readHumidity();
  if (isnan(tempC) || isnan(humidity)) {
    delay(2100);  // DHT22 needs 2 s between reads
    tempC = dht.readTemperature();
    humidity = dht.readHumidity();
  }
}

// HC-SR04 (or JSN-SR04T): 7 pings, returns the median distance in cm (NAN if fewer than 3 echoes).
float readDistanceCm(float tempC) {
  float speedOfSound = 331.3f + 0.606f * (ok(tempC) ? tempC : 28.0f);  // m/s, depends on temperature
  float cmPerUs = speedOfSound / 10000.0f;
  float v[7];
  int n = 0;
  for (int i = 0; i < 7; i++) {
    digitalWrite(PIN_US_TRIG, LOW);
    delayMicroseconds(5);
    digitalWrite(PIN_US_TRIG, HIGH);
    delayMicroseconds(20);
    digitalWrite(PIN_US_TRIG, LOW);
    unsigned long us = pulseIn(PIN_US_ECHO, HIGH, 40000UL);
    if (us > 0) v[n++] = us * cmPerUs / 2.0f;
    delay(70);
  }
  if (n < 3) return NAN;
  for (int i = 1; i < n; i++) {  // sort
    float k = v[i];
    int j = i - 1;
    while (j >= 0 && v[j] > k) { v[j + 1] = v[j]; j--; }
    v[j + 1] = k;
  }
  return v[n / 2];
}

// Converts distance to fill %. 0% = empty bin, 100% = waste at the full line.
float fillFromDistance(float d) {
  if (!ok(d)) return NAN;
  if (d > calEmptyCm + 15.0f) return NAN;  // lid open or a bad echo
  float span = calEmptyCm - calFullCm;
  if (span < 5.0f) return NAN;             // calibration does not make sense
  float pct = (calEmptyCm - d) / span * 100.0f;
  return constrain(pct, 0.0f, 100.0f);
}

// HX711: average of n raw samples. false = HX711 not answering.
bool readRawWeight(int n, long &out) {
  long long sum = 0;
  int got = 0;
  for (int i = 0; i < n; i++) {
    if (!scale.wait_ready_timeout(300)) break;
    sum += scale.read();
    got++;
  }
  if (got == 0 || got < n / 2) return false;
  out = (long)(sum / got);
  return true;
}

float readWeightKg() {
  if (calWeightScale == 0) return NAN;
  long raw;
  if (!readRawWeight(10, raw)) return NAN;
  return (raw - calWeightOffset) / calWeightScale;
}

// MQ-135: sensor output in mV (after undoing the divider)
float readGasMv() {
  uint32_t sum = 0;
  for (int i = 0; i < 32; i++) {
    sum += analogReadMilliVolts(PIN_GAS_AO);
    delayMicroseconds(300);
  }
  return (sum / 32.0f) * GAS_DIVIDER_FACTOR;
}

// Gas index 0-100 compared with clean air. Works out the sensor resistance ratio Rs/R0.
float gasIndexFromMv(float mv) {
  if (calGasBaseMv <= 0 || !ok(mv) || mv < 5.0f) return NAN;
  const float VC = 5000.0f;  // sensor supply in mV
  float rs = (VC - mv) / mv;
  float rs0 = (VC - calGasBaseMv) / calGasBaseMv;
  if (rs0 <= 0) return NAN;
  float ratio = rs / rs0;    // 1.0 = clean air, smaller = more gas
  float idx = (1.0f - ratio) / (1.0f - GAS_RATIO_AT_100) * 100.0f;
  return constrain(idx, 0.0f, 100.0f);
}

// Battery voltage before the "batcal" correction (0 if nothing connected)
float readBatteryRawV() {
  uint32_t sum = 0;
  for (int i = 0; i < 16; i++) {
    sum += analogReadMilliVolts(PIN_BATTERY);
    delayMicroseconds(300);
  }
  return (sum / 16.0f) / 1000.0f * BATTERY_DIVIDER_FACTOR;
}

float readBatteryV() {
  float v = readBatteryRawV() * calBatteryFactor;
  return (v < 2.5f) ? NAN : v;  // below 2.5 V = switch off or not wired
}

// Approximate charge of a Li-ion 18650 cell from its voltage
int batteryPercent(float v) {
  if (!ok(v)) return -1;
  const float V[9] = {3.30f, 3.50f, 3.60f, 3.70f, 3.80f, 3.90f, 4.00f, 4.10f, 4.20f};
  const int P[9] = {0, 10, 20, 35, 50, 65, 80, 90, 100};
  if (v <= V[0]) return 0;
  if (v >= V[8]) return 100;
  for (int i = 1; i < 9; i++) {
    if (v < V[i]) return P[i - 1] + (int)((v - V[i - 1]) / (V[i] - V[i - 1]) * (P[i] - P[i - 1]));
  }
  return 100;
}

// On-device urgency 0-100: weighted mix of fill, gas, humidity and hours since the last collection
float urgencyNow(const Reading &r, int64_t nowMs) {
  if (!ok(r.fillPct)) return NAN;
  float gas = ok(r.gasIndex) ? r.gasIndex : 0.0f;
  float hum = ok(r.humidityPct) ? r.humidityPct : 0.0f;
  float hours = 0.0f;
  if (lastCollectedMs > 0 && nowMs > lastCollectedMs) hours = (float)(nowMs - lastCollectedMs) / 3600000.0f;
  float timeScore = constrain(hours / URGENCY_FULL_TIME_HOURS * 100.0f, 0.0f, 100.0f);
  float u = URGENCY_W_FILL * r.fillPct + URGENCY_W_GAS * gas + URGENCY_W_HUMIDITY * hum + URGENCY_W_TIME * timeScore;
  return constrain(u, 0.0f, 100.0f);
}

void setLeds(float urgency) {
  bool g = false, y = false, red = false;
  if (ok(urgency)) {
    if (urgency >= URGENCY_RED) red = true;
    else if (urgency >= URGENCY_YELLOW) y = true;
    else g = true;
  }
  digitalWrite(PIN_LED_GREEN, g ? HIGH : LOW);
  digitalWrite(PIN_LED_YELLOW, y ? HIGH : LOW);
  digitalWrite(PIN_LED_RED, red ? HIGH : LOW);
}

// ---------- DS3231 clock module (I2C address 0x68), times kept in UTC ----------
const uint8_t RTC_ADDR = 0x68;

uint8_t bcdToDec(uint8_t v) {
  return (uint8_t)((v >> 4) * 10 + (v & 0x0F));
}

uint8_t decToBcd(uint8_t v) {
  return (uint8_t)(((v / 10) << 4) | (v % 10));
}

// Days since 1970-01-01 for a calendar date (no time-zone functions needed)
int64_t daysFromCivil(int y, unsigned m, unsigned d) {
  y -= m <= 2;
  const int era = (y >= 0 ? y : y - 399) / 400;
  const unsigned yoe = (unsigned)(y - era * 400);
  const unsigned doy = (153 * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1;
  const unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
  return (int64_t)era * 146097 + (int64_t)doe - 719468;
}

bool rtcPresent() {
  Wire.beginTransmission(RTC_ADDR);
  return Wire.endTransmission() == 0;
}

// Reads the clock. false = no clock, or its time was lost (battery flat / never set)
bool rtcRead(time_t &out) {
  Wire.beginTransmission(RTC_ADDR);
  Wire.write((uint8_t)0x0F);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(RTC_ADDR, (uint8_t)1) != 1) return false;
  if (Wire.read() & 0x80) return false;  // oscillator-stop flag: time not valid
  Wire.beginTransmission(RTC_ADDR);
  Wire.write((uint8_t)0x00);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(RTC_ADDR, (uint8_t)7) != 7) return false;
  uint8_t sec = bcdToDec(Wire.read() & 0x7F);
  uint8_t min = bcdToDec(Wire.read() & 0x7F);
  uint8_t hour = bcdToDec(Wire.read() & 0x3F);
  Wire.read();  // day of week (not used)
  uint8_t day = bcdToDec(Wire.read() & 0x3F);
  uint8_t month = bcdToDec(Wire.read() & 0x1F);
  int year = 2000 + bcdToDec(Wire.read());
  if (month < 1 || month > 12 || day < 1 || day > 31 || hour > 23 || min > 59 || sec > 59) return false;
  out = (time_t)(daysFromCivil(year, month, day) * 86400LL + hour * 3600 + min * 60 + sec);
  return out > 1700000000;
}

void rtcWrite(time_t t) {
  struct tm u;
  gmtime_r(&t, &u);
  Wire.beginTransmission(RTC_ADDR);
  Wire.write((uint8_t)0x00);
  Wire.write(decToBcd((uint8_t)u.tm_sec));
  Wire.write(decToBcd((uint8_t)u.tm_min));
  Wire.write(decToBcd((uint8_t)u.tm_hour));  // 24-hour mode
  Wire.write(decToBcd((uint8_t)(u.tm_wday + 1)));
  Wire.write(decToBcd((uint8_t)u.tm_mday));
  Wire.write(decToBcd((uint8_t)(u.tm_mon + 1)));
  Wire.write(decToBcd((uint8_t)(u.tm_year - 100)));
  Wire.endTransmission();
  // clear the oscillator-stop flag so the time counts as valid
  Wire.beginTransmission(RTC_ADDR);
  Wire.write((uint8_t)0x0F);
  Wire.endTransmission(false);
  uint8_t status = 0;
  if (Wire.requestFrom(RTC_ADDR, (uint8_t)1) == 1) status = Wire.read();
  Wire.beginTransmission(RTC_ADDR);
  Wire.write((uint8_t)0x0F);
  Wire.write((uint8_t)(status & 0x7F));
  Wire.endTransmission();
}

void onTimeSynced(struct timeval *tv) {
  (void)tv;
  ntpJustSynced = true;  // handled in loop(): copy internet time into the clock module
}

// ---------- statistics helper for the "stats" command ----------
void statAdd(Stat &st, float v) {
  if (!ok(v)) return;
  if (st.n == 0) { st.minV = v; st.maxV = v; }
  st.n++;
  st.sum += v;
  st.sumSq += (double)v * v;
  if (v < st.minV) st.minV = v;
  if (v > st.maxV) st.maxV = v;
}

void statPrint(const char *name, const Stat &st, int total, int decimals) {
  if (st.n == 0) {
    Serial.printf("  %-14s valid 0/%d\n", name, total);
    return;
  }
  double mean = st.sum / st.n;
  double var = st.n > 1 ? (st.sumSq - st.n * mean * mean) / (st.n - 1) : 0.0;
  double sd = var > 0 ? sqrt(var) : 0.0;
  Serial.printf("  %-14s valid %d/%d  mean %.*f  sd %.*f  min %.*f  max %.*f\n", name, st.n, total,
                decimals, mean, decimals, sd, decimals, st.minV, decimals, st.maxV);
}

Reading takeReading() {
  Reading r;
  readDht(r.tempC, r.humidityPct);
  r.distanceCm = readDistanceCm(r.tempC);
  r.fillPct = fillFromDistance(r.distanceCm);
  r.weightKg = readWeightKg();
  r.gasMv = readGasMv();
  r.gasReady = millis() >= (uint32_t)GAS_WARMUP_MINUTES * 60000UL;
  r.gasIndex = r.gasReady ? gasIndexFromMv(r.gasMv) : NAN;
  r.batteryV = readBatteryV();
  r.uptimeMs = millis();   // time stamp = when the measurement finished
  r.tsMs = nowEpochMs();
  r.urgency = urgencyNow(r, r.tsMs ? r.tsMs : nowEpochMs());
  r.seq = 0;
  return r;
}

void printReading(const Reading &r) {
  String gas = String(r.gasMv, 0) + " mV";
  if (!r.gasReady) gas += " (warming up)";
  else if (ok(r.gasIndex)) gas += " index " + String(r.gasIndex, 0);
  else if (calGasBaseMv == 0) gas += " (run: gasbase)";
  String weight = (calWeightScale == 0) ? String("not calibrated") : fmtWeightG(r.weightKg);
  String battery = ok(r.batteryV) ? fmt(r.batteryV, 2) + " V " + String(batteryPercent(r.batteryV)) + "%" : String("--");
  Serial.printf("[%s] fill %s%% (%s cm) | weight %s | gas %s | %s C %s%% | battery %s | urgency %s\n",
                localTimeText(r.tsMs).c_str(), fmt(r.fillPct, 1).c_str(), fmt(r.distanceCm, 1).c_str(),
                weight.c_str(), gas.c_str(), fmt(r.tempC, 1).c_str(), fmt(r.humidityPct, 0).c_str(), battery.c_str(),
                fmt(r.urgency, 0).c_str());
}

// =====================================================================
// Bin emptied ("collection") detection
// =====================================================================
bool looksEmptied(const Reading &before, const Reading &now) {
  bool fillDrop = ok(before.fillPct) && ok(now.fillPct) &&
                  (before.fillPct - now.fillPct) >= 30.0f && now.fillPct <= 15.0f;
  const float minBeforeKg = COLLECTION_WEIGHT_MIN_G / 1000.0f;
  bool weightDrop = ok(before.weightKg) && ok(now.weightKg) &&
                    before.weightKg >= minBeforeKg && now.weightKg <= 0.25f * before.weightKg;
  return fillDrop || weightDrop;
}

void recordCollection(const Reading &before, const Reading &after) {
  collectionEvent.pending = true;
  collectionEvent.tsMs = after.tsMs;
  collectionEvent.uptimeMs = after.uptimeMs;
  collectionEvent.fillBefore = before.fillPct;
  collectionEvent.weightBefore = before.weightKg;
  collectionEvent.fillAfter = after.fillPct;
  collectionEvent.weightAfter = after.weightKg;
  int64_t ts = after.tsMs ? after.tsMs : nowEpochMs();
  if (ts != 0) {
    lastCollectedMs = ts;
    prefs.putLong64("last_col", ts);
  }
  Serial.println("[bin] COLLECTION recorded - the bin was emptied.");
}

// A drop must be seen on two readings in a row (so a hand or an open lid does not count)
void checkCollection(const Reading &r) {
  if (collectionSuspected) {
    if (looksEmptied(beforeCollection, r)) recordCollection(beforeCollection, r);
    collectionSuspected = false;
  } else if (haveLastReading && looksEmptied(lastReading, r)) {
    collectionSuspected = true;
    beforeCollection = lastReading;
    Serial.println("[bin] Level dropped - checking again on the next reading...");
    return;  // keep the "before" reading
  }
  lastReading = r;
  haveLastReading = true;
}

// =====================================================================
// Offline buffer
// =====================================================================
void addToBuffer(const Reading &r) {
  if (bufCount == BUFFER_SIZE) {  // full: forget the oldest
    bufHead = (bufHead + 1) % BUFFER_SIZE;
    bufCount--;
  }
  buffer[(bufHead + bufCount) % BUFFER_SIZE] = r;
  bufCount++;
}

// =====================================================================
// WiFi + time
// =====================================================================
void wifiStart() {
  WiFi.mode(WIFI_STA);
  WiFi.setHostname("smartbin");
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  lastWifiTryMs = millis();
  Serial.printf("[wifi] connecting to '%s'...\n", WIFI_SSID);
}

void wifiMaintain() {
  if (WiFi.status() == WL_CONNECTED) {
    if (!timeStarted) {
      Serial.printf("[wifi] connected. IP %s, signal %d dBm\n", WiFi.localIP().toString().c_str(), WiFi.RSSI());
      configTzTime(TIMEZONE, "pool.ntp.org", "time.google.com");  // get the time from the internet
      timeStarted = true;
    }
    if (!clockReported && nowEpochMs() != 0) {
      clockReported = true;
      Serial.println("[time] clock set: " + localTimeText(nowEpochMs()));
    }
    return;
  }
  if (millis() - lastWifiTryMs > 30000) {
    Serial.println("[wifi] not connected - trying again...");
    WiFi.disconnect();
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    lastWifiTryMs = millis();
  }
}

// =====================================================================
// Firebase (REST API over HTTPS)
// =====================================================================
int httpRequest(const char *method, const String &url, const String &body, String &reply) {
  WiFiClientSecure client;
  client.setInsecure();  // prototype: skip certificate check
  HTTPClient http;
  http.setTimeout(10000);
  if (!http.begin(client, url)) return -1;
  http.addHeader("Content-Type", "application/json");
  int code = http.sendRequest(method, body);
  reply = (code > 0) ? http.getString() : http.errorToString(code);
  http.end();
  return code;
}

#if FIREBASE_USE_LOGIN
// Signs in with email + password and keeps the ID token (valid 1 hour, renewed every 50 min)
bool firebaseLogin() {
  if (idToken.length() > 0 && millis() - idTokenMs < 50UL * 60UL * 1000UL) return true;
  JsonDocument req;
  req["email"] = FIREBASE_EMAIL;
  req["password"] = FIREBASE_PASSWORD;
  req["returnSecureToken"] = true;
  String body;
  serializeJson(req, body);
  String reply;
  String url = String("https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=") + FIREBASE_API_KEY;
  int code = httpRequest("POST", url, body, reply);
  if (code != 200) {
    Serial.printf("[login] failed: HTTP %d %s\n", code, reply.substring(0, 160).c_str());
    return false;
  }
  JsonDocument filter;
  filter["idToken"] = true;
  JsonDocument doc;
  deserializeJson(doc, reply, DeserializationOption::Filter(filter));
  idToken = String((const char *)(doc["idToken"] | ""));
  idTokenMs = millis();
  Serial.println(idToken.length() > 0 ? "[login] OK" : "[login] no token in reply");
  return idToken.length() > 0;
}
#endif

String firebaseUrl(const String &path) {
  String url = String(FIREBASE_DB_URL) + path + ".json?print=silent";
#if FIREBASE_USE_LOGIN
  url += "&auth=" + idToken;
#endif
  return url;
}

// Sends one write (PUT / PATCH / POST). Returns true when Firebase accepted it.
bool firebaseWrite(const char *method, const String &path, const String &json) {
  if (WiFi.status() != WL_CONNECTED) return false;
#if FIREBASE_USE_LOGIN
  if (!firebaseLogin()) return false;
#endif
  String reply;
  int code = httpRequest(method, firebaseUrl(path), json, reply);
#if FIREBASE_USE_LOGIN
  if (code == 401) {  // token expired: log in again and retry once
    idToken = "";
    if (firebaseLogin()) code = httpRequest(method, firebaseUrl(path), json, reply);
  }
#endif
  if (code == 200 || code == 204) return true;
  Serial.printf("[firebase] %s %s failed: HTTP %d %s\n", method, path.c_str(), code, reply.substring(0, 160).c_str());
  if (code == 401) Serial.println("[firebase] Permission denied: check the database rules / login settings.");
  if (code == 404) Serial.println("[firebase] Not found: check FIREBASE_DB_URL in config.h");
  return false;
}

void readingToJson(const Reading &r, JsonObject o) {
  o["bin_id"] = BIN_ID;
  o["ts"] = r.tsMs;
  o["time_local"] = localTimeText(r.tsMs);
  if (ok(r.fillPct)) o["fill_pct"] = round1(r.fillPct);
  if (ok(r.distanceCm)) o["distance_cm"] = round1(r.distanceCm);
  if (ok(r.weightKg)) o["weight_kg"] = round2(r.weightKg);     // Firebase keeps weight in kilograms
  o["gas_mv"] = (int)lround(r.gasMv);
  o["gas_ready"] = r.gasReady;
  if (ok(r.gasIndex)) o["gas_index"] = (int)lround(r.gasIndex);
  if (ok(r.tempC)) o["temp_c"] = round1(r.tempC);
  if (ok(r.humidityPct)) o["humidity_pct"] = round1(r.humidityPct);
  if (ok(r.batteryV)) {
    o["battery_v"] = round2(r.batteryV);
    o["battery_pct"] = batteryPercent(r.batteryV);
  }
  if (ok(r.urgency)) o["urgency_now"] = (int)lroundf(r.urgency);
  if (r.seq > 0) {
    o["seq"] = r.seq;
    o["boot"] = bootCount;
  }
  JsonArray errors = o["errors"].to<JsonArray>();
  if (!ok(r.distanceCm)) errors.add("ultrasonic_no_echo");
  if (calWeightScale == 0) errors.add("weight_not_calibrated");
  else if (!ok(r.weightKg)) errors.add("load_cell_no_answer");
  if (!ok(r.tempC)) errors.add("dht22_no_data");
  if (r.gasMv < 5.0f) errors.add("gas_no_signal");
  if (errors.size() == 0) o.remove("errors");
}

void sendDeviceInfo() {
  JsonDocument d;
  d["fw"] = FW_VERSION;
  d["mac"] = WiFi.macAddress();
  d["ip"] = WiFi.localIP().toString();
  d["updated"][".sv"] = "timestamp";
  d["empty_distance_cm"] = round1(calEmptyCm);
  d["full_distance_cm"] = round1(calFullCm);
  d["weight_calibrated"] = (calWeightScale != 0);
  d["gas_baseline_mv"] = round1(calGasBaseMv);
  d["send_interval_s"] = SEND_INTERVAL_SEC;
  d["boot"] = bootCount;
  d["rtc_found"] = rtcFound;
  String body;
  serializeJson(d, body);
  if (firebaseWrite("PATCH", "/bins/" BIN_ID "/device", body)) {
    deviceInfoSent = true;
    Serial.println("[firebase] device info sent");
  }
}

// Sends waiting readings (max 20 per request) + the latest reading + any collection event.
void flushToFirebase() {
  lastFlushTryMs = millis();
  if (WiFi.status() != WL_CONNECTED) return;
  int64_t nowMs = nowEpochMs();
  if (nowMs == 0) return;  // wait until the clock is set
  if (!deviceInfoSent) sendDeviceInfo();
  if (bufCount == 0 && !collectionEvent.pending) return;

  JsonDocument doc;
  char key[48];

  if (collectionEvent.pending) {
    int64_t ts = fixTime(collectionEvent.tsMs, collectionEvent.uptimeMs, nowMs);
    doc["last_collected"] = ts;
    if (lastCollectedMs == 0) {
      lastCollectedMs = ts;
      prefs.putLong64("last_col", ts);
    }
    snprintf(key, sizeof(key), "collections/%lld", (long long)ts);
    JsonObject c = doc[key].to<JsonObject>();
    c["ts"] = ts;
    c["time_local"] = localTimeText(ts);
    if (ok(collectionEvent.fillBefore)) c["fill_before_pct"] = round1(collectionEvent.fillBefore);
    if (ok(collectionEvent.weightBefore)) c["weight_before_kg"] = round2(collectionEvent.weightBefore);
    if (ok(collectionEvent.fillAfter)) c["fill_after_pct"] = round1(collectionEvent.fillAfter);
    if (ok(collectionEvent.weightAfter)) c["weight_after_kg"] = round2(collectionEvent.weightAfter);
  }

  int n = bufCount < 20 ? bufCount : 20;
  for (int i = 0; i < n; i++) {
    Reading &r = buffer[(bufHead + i) % BUFFER_SIZE];
    r.tsMs = fixTime(r.tsMs, r.uptimeMs, nowMs);
    snprintf(key, sizeof(key), "readings/%lld", (long long)r.tsMs);
    JsonObject o = doc[key].to<JsonObject>();
    readingToJson(r, o);
    o["server_ts"][".sv"] = "timestamp";               // Firebase time on arrival (for latency)
    o["queue_s"] = (uint32_t)((millis() - r.uptimeMs) / 1000);  // seconds it waited on the board
  }

  if (bufCount > 0) {
    Reading &newest = buffer[(bufHead + bufCount - 1) % BUFFER_SIZE];
    newest.tsMs = fixTime(newest.tsMs, newest.uptimeMs, nowMs);
    JsonObject latest = doc["latest"].to<JsonObject>();
    readingToJson(newest, latest);
    latest["server_ts"][".sv"] = "timestamp";
    latest["rssi"] = WiFi.RSSI();
    latest["uptime_s"] = (uint32_t)(millis() / 1000);
    latest["waiting_to_send"] = bufCount - n;
    latest["fw"] = FW_VERSION;
  }

  String body;
  serializeJson(doc, body);
  if (firebaseWrite("PATCH", "/bins/" BIN_ID, body)) {
    bufHead = (bufHead + n) % BUFFER_SIZE;
    bufCount -= n;
    collectionEvent.pending = false;
    Serial.printf("[firebase] sent %d reading(s)%s\n", n, bufCount > 0 ? " - more waiting" : "");
  }
}

// =====================================================================
// Serial Monitor commands (calibration)
// =====================================================================
void printHelp() {
  Serial.println("---- Commands (type, then press Enter) ----");
  Serial.println("  show          read all sensors once + show calibration");
  Serial.println("  tare          set weight zero (EMPTY bin on the scale)");
  Serial.println("  cal 1000      calibrate weight with a known weight in GRAMS (e.g. 1000 for 1 kg)");
  Serial.println("  empty         save the distance to the bottom of the EMPTY bin");
  Serial.println("  full 5        set the 'full' line distance in cm (4 or more with HC-SR04)");
  Serial.println("  gasbase       save clean-air gas level (after 20 min warm-up)");
  Serial.println("  batcal 3.95   correct battery reading with your multimeter value");
  Serial.println("  send          take a reading and send it now");
  Serial.println("  collected     record 'bin emptied' now (for demos)");
  Serial.println("  wifi          show WiFi / time / buffer status");
  Serial.println("  stats 20      take 20 readings, show mean and spread (calibration tests)");
  Serial.println("  rtc           show the clock module status");
  Serial.println("  resetcal      erase ALL calibration and counters");
  Serial.println("  restart       restart the ESP32");
}

void cmdTare() {
  long raw;
  if (!readRawWeight(20, raw)) {
    Serial.println(">> HX711 not responding - check wiring (DT pin 15, SCK pin 16).");
    return;
  }
  calWeightOffset = raw;
  prefs.putLong("w_off", raw);
  deviceInfoSent = false;
  Serial.printf(">> Weight zero saved (raw %ld). Now put a known weight on and type: cal <grams>\n", raw);
  Serial.println(">>   Example: 'cal 1000' with a 1 kg weight on the scale.");
}

// 'cal <grams>': the weight on the scale, in GRAMS (not kg).
void cmdCal(float grams) {
  if (grams <= 0) {
    Serial.println(">> Use like this: cal 1000   (the weight in GRAMS; e.g. 1000 for 1 kg)");
    return;
  }
  if (grams < 10.0f) {
    Serial.println(">> That looks like kilograms. In this firmware 'cal' takes GRAMS: type 'cal 1000' for a 1 kg weight.");
    return;
  }
  long raw;
  if (!readRawWeight(20, raw)) {
    Serial.println(">> HX711 not responding.");
    return;
  }
  long change = raw - calWeightOffset;
  if (labs(change) < 1000) {
    Serial.println(">> Change too small. Is the weight on the scale? Did you type 'tare' first (with no weight)?");
    return;
  }
  float kg = grams / 1000.0f;
  calWeightScale = (float)change / kg;                    // raw units per kg (Firebase unit stays kg)
  prefs.putFloat("w_scale", calWeightScale);
  deviceInfoSent = false;
  float nowKg = readWeightKg();
  Serial.printf(">> Weight calibrated. Factor %.1f per kg. Check: now reads %s\n",
                calWeightScale, fmtWeightG(nowKg).c_str());
}

void cmdEmpty() {
  float t, h;
  readDht(t, h);
  float d = readDistanceCm(t);
  if (!ok(d)) {
    Serial.println(">> No echo from the ultrasonic sensor (battery switch ON?).");
    return;
  }
  if (d < calFullCm + 3.0f) {
    Serial.printf(">> Distance %.1f cm is too short. The bin must be EMPTY.\n", d);
    return;
  }
  calEmptyCm = d;
  prefs.putFloat("d_empty", d);
  deviceInfoSent = false;
  Serial.printf(">> Empty-bin distance saved: %.1f cm\n", d);
}

void cmdFull(float cm) {
  if (cm < MIN_FULL_DISTANCE_CM || cm > calEmptyCm - 3.0f) {
    Serial.printf(">> Must be between %.0f and %.0f cm. Example: full 5\n",
                  MIN_FULL_DISTANCE_CM, calEmptyCm - 3.0f);
    return;
  }
  calFullCm = cm;
  prefs.putFloat("d_full", cm);
  deviceInfoSent = false;
  Serial.printf(">> Full line saved: %.1f cm from the sensor\n", cm);
}

void cmdGasBase(bool force) {
  uint32_t warmMs = (uint32_t)GAS_WARMUP_MINUTES * 60000UL;
  if (millis() < warmMs && !force) {
    Serial.printf(">> Gas sensor still warming up (%lu min left). Wait, or type: gasbase force\n",
                  (unsigned long)((warmMs - millis()) / 60000UL + 1));
    return;
  }
  float mv = readGasMv();
  if (mv < 5.0f) {
    Serial.println(">> No signal from MQ-135 (battery switch ON? wiring?).");
    return;
  }
  calGasBaseMv = mv;
  prefs.putFloat("gas_base", mv);
  deviceInfoSent = false;
  Serial.printf(">> Clean-air gas level saved: %.0f mV. Do this in fresh air, away from waste.\n", mv);
}

void cmdBatCal(float measured) {
  float raw = readBatteryRawV();
  if (measured < 2.5f || measured > 4.5f) {
    Serial.println(">> Measure the battery with your multimeter, then type e.g.: batcal 3.95");
    return;
  }
  if (raw < 2.0f) {
    Serial.println(">> Battery not detected on pin 10 (switch ON? divider wired?).");
    return;
  }
  calBatteryFactor = measured / raw;
  prefs.putFloat("bat_cal", calBatteryFactor);
  Serial.printf(">> Battery correction saved (x%.3f)\n", calBatteryFactor);
}

void cmdCollected() {
  Reading now = takeReading();
  Reading before = haveLastReading ? lastReading : now;
  recordCollection(before, now);
  lastReading = now;
  haveLastReading = true;
  flushToFirebase();
}

void cmdWifi() {
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf(">> WiFi: connected to '%s', IP %s, signal %d dBm\n", WIFI_SSID, WiFi.localIP().toString().c_str(), WiFi.RSSI());
  } else {
    Serial.printf(">> WiFi: NOT connected (status %d). Name '%s'. 2.4 GHz only.\n", (int)WiFi.status(), WIFI_SSID);
  }
  Serial.println(">> Time: " + localTimeText(nowEpochMs()));
  Serial.printf(">> Readings waiting to send: %d\n", bufCount);
}

void cmdStats(int n) {
  if (n < 3 || n > 200) n = 20;
  Serial.printf(">> Taking %d samples, about %d seconds. Keep everything still...\n", n, n * 3);
  Stat sDist = {0, 0, 0, 0, 0}, sFill = sDist, sWeight = sDist, sGas = sDist, sTemp = sDist, sHum = sDist;
  for (int i = 0; i < n; i++) {
    uint32_t start = millis();
    Reading r = takeReading();
    statAdd(sDist, r.distanceCm);
    statAdd(sFill, r.fillPct);
    statAdd(sWeight, ok(r.weightKg) ? r.weightKg * 1000.0f : NAN);   // stats in GRAMS
    statAdd(sGas, r.gasMv);
    statAdd(sTemp, r.tempC);
    statAdd(sHum, r.humidityPct);
    while (millis() - start < 2100) delay(10);  // DHT22 needs 2 s between reads
  }
  Serial.println(">> Results (copy these into your test table):");
  statPrint("distance_cm", sDist, n, 1);
  statPrint("fill_pct", sFill, n, 1);
  statPrint("weight_g", sWeight, n, 1);                                // report shows grams
  statPrint("gas_mv", sGas, n, 0);
  statPrint("temp_c", sTemp, n, 1);
  statPrint("humidity_pct", sHum, n, 1);
}

void cmdRtc() {
  if (!rtcFound) {
    Serial.println(">> No clock module found (SDA pin 17, SCL pin 18, VCC to the 3.3V row 40). The bin still runs on internet time.");
    return;
  }
  time_t t;
  if (rtcRead(t)) Serial.println(">> Clock module time: " + localTimeText((int64_t)t * 1000));
  else Serial.println(">> Clock module found, but its time is not set yet. It is set automatically once WiFi works.");
}

void runCommand(String line) {
  String cmd = line;
  String arg = "";
  int space = line.indexOf(' ');
  if (space > 0) {
    cmd = line.substring(0, space);
    arg = line.substring(space + 1);
    arg.trim();
  }
  cmd.toLowerCase();

  if (cmd == "help") printHelp();
  else if (cmd == "show") { printReading(takeReading()); printSettings(); }
  else if (cmd == "tare") cmdTare();
  else if (cmd == "cal") cmdCal(arg.toFloat());
  else if (cmd == "empty") cmdEmpty();
  else if (cmd == "full") cmdFull(arg.toFloat());
  else if (cmd == "gasbase") cmdGasBase(arg == "force");
  else if (cmd == "batcal") cmdBatCal(arg.toFloat());
  else if (cmd == "send") forceRead = true;
  else if (cmd == "collected") cmdCollected();
  else if (cmd == "wifi") cmdWifi();
  else if (cmd == "stats") cmdStats(arg.toInt());
  else if (cmd == "rtc") cmdRtc();
  else if (cmd == "resetcal") { prefs.clear(); loadSettings(); deviceInfoSent = false; Serial.println(">> All calibration erased."); }
  else if (cmd == "restart") ESP.restart();
  else Serial.println(">> Unknown command. Type: help");
}

void handleSerial() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      String line = serialLine;
      serialLine = "";
      line.trim();
      if (line.length() > 0) runCommand(line);
    } else if (serialLine.length() < 80) {
      serialLine += c;
    }
  }
}

// =====================================================================
// setup() runs once, loop() runs forever
// =====================================================================
void setup() {
  Serial.begin(115200);
  delay(1500);
  Serial.println();
  Serial.println("=========================================");
  Serial.printf(" SMART BIN  %s   firmware %s\n", BIN_ID, FW_VERSION);
  Serial.println("=========================================");

  pinMode(PIN_US_TRIG, OUTPUT);
  digitalWrite(PIN_US_TRIG, LOW);
  pinMode(PIN_US_ECHO, INPUT);
  pinMode(PIN_LED_GREEN, OUTPUT);
  pinMode(PIN_LED_YELLOW, OUTPUT);
  pinMode(PIN_LED_RED, OUTPUT);
  digitalWrite(PIN_LED_GREEN, HIGH);  // lamp test: all 3 lights on for 1 second
  digitalWrite(PIN_LED_YELLOW, HIGH);
  digitalWrite(PIN_LED_RED, HIGH);
  delay(1000);
  setLeds(NAN);
  dht.begin();
  scale.begin(PIN_HX711_DT, PIN_HX711_SCK);

  prefs.begin("smartbin", false);
  loadSettings();
  bootCount = prefs.getUInt("boots", 0) + 1;
  prefs.putUInt("boots", bootCount);
  Serial.printf("Start number %lu\n", (unsigned long)bootCount);
  printSettings();

  // Clock module: set the time at once, even without WiFi
  Wire.begin(PIN_RTC_SDA, PIN_RTC_SCL);
  rtcFound = rtcPresent();
  if (rtcFound) {
    time_t t;
    if (rtcRead(t)) {
      struct timeval tv = {t, 0};
      settimeofday(&tv, nullptr);
      setenv("TZ", TIMEZONE, 1);
      tzset();
      Serial.println("[rtc] clock module found - time set: " + localTimeText((int64_t)t * 1000));
    } else {
      Serial.println("[rtc] clock module found, time not set yet (it will be set from the internet)");
    }
  } else {
    Serial.println("[rtc] no clock module found - using internet time only");
  }
  sntp_set_time_sync_notification_cb(onTimeSynced);

  wifiStart();
  lastReadMs = millis() - SEND_INTERVAL_SEC * 1000UL + 8000UL;  // first reading after ~8 s
  Serial.println("Type 'help' for calibration commands.");
}

void loop() {
  handleSerial();
  wifiMaintain();

  uint32_t now = millis();
  if (forceRead || now - lastReadMs >= SEND_INTERVAL_SEC * 1000UL) {
    forceRead = false;
    lastReadMs = now;
    Reading r = takeReading();
    r.seq = ++seqCounter;
    printReading(r);
    setLeds(r.urgency);
    checkCollection(r);
    addToBuffer(r);
    flushToFirebase();
  } else if ((bufCount > 0 || collectionEvent.pending) && now - lastFlushTryMs >= 30000UL) {
    flushToFirebase();  // send readings saved while WiFi was down
  }

  if (ntpJustSynced) {  // internet time arrived: copy it into the clock module
    ntpJustSynced = false;
    if (rtcFound) {
      rtcWrite(time(nullptr));
      Serial.println("[rtc] clock module set from internet time");
    }
  }

  delay(10);
}
