/*
  SMART BIN - TEST 7: WIFI + FIREBASE
  -----------------------------------
  Checks that the ESP32 can join your WiFi and write to Firebase.
  No extra wiring.

  Before uploading, fill in the 3 lines below.
    - The ESP32 only works with 2.4 GHz WiFi (not 5 GHz).
    - Phone hotspot on iPhone: turn ON "Maximise Compatibility".
    - FIREBASE_DB_URL: copy it from Firebase console > Realtime Database > Data.
      It looks like https://xxxx-default-rtdb.asia-southeast1.firebasedatabase.app
      (no "/" at the end).

  Serial Monitor: 115200 baud.
*/

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>

const char* WIFI_SSID = "YOUR_WIFI_NAME";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char* FIREBASE_DB_URL = "https://YOUR-PROJECT-default-rtdb.asia-southeast1.firebasedatabase.app";

int counter = 0;

// Writes JSON to a path in the database. Returns the HTTP status code.
int firebasePut(const String& path, const String& json) {
  WiFiClientSecure client;
  client.setInsecure();  // prototype only: skips the certificate check
  HTTPClient http;
  http.setTimeout(10000);
  String url = String(FIREBASE_DB_URL) + path + ".json";
  if (!http.begin(client, url)) return -1;
  http.addHeader("Content-Type", "application/json");
  int code = http.PUT(json);
  String reply = http.getString();
  http.end();
  Serial.printf("PUT %s -> HTTP %d\n", path.c_str(), code);
  if (code != 200) Serial.println("Reply: " + reply);
  return code;
}

void explain(int code) {
  if (code == 200) Serial.println("SUCCESS! Open Firebase console > Realtime Database > Data. You should see 'test'.");
  else if (code == 401) Serial.println("Permission denied: the database rules are not in test mode (see the guide).");
  else if (code == 404) Serial.println("Not found: the FIREBASE_DB_URL is wrong. Copy it again from the Firebase console.");
  else if (code < 0) Serial.println("Could not connect: check FIREBASE_DB_URL and that the WiFi has internet.");
  else Serial.println("Unexpected reply - read the message above.");
}

void setup() {
  Serial.begin(115200);
  delay(1500);
  Serial.println();
  Serial.println("=== Smart Bin - Test 7: WiFi + Firebase ===");

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.printf("Connecting to WiFi '%s'", WIFI_SSID);
  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();

  if (WiFi.status() != WL_CONNECTED) {
    wl_status_t s = WiFi.status();
    if (s == WL_NO_SSID_AVAIL) Serial.println("WiFi name not found. Is it 2.4 GHz? Is the name spelled exactly right?");
    else if (s == WL_CONNECT_FAILED) Serial.println("Connection failed. Check the password.");
    else Serial.printf("Could not connect (status %d). Check name and password, move closer to the router.\n", (int)s);
    return;
  }
  Serial.printf("WiFi OK. IP address: %s   Signal: %d dBm\n", WiFi.localIP().toString().c_str(), WiFi.RSSI());

  // Get the time from the internet (Sri Lanka time zone)
  configTzTime("IST-5:30", "pool.ntp.org", "time.google.com");
  struct tm now;
  if (getLocalTime(&now, 10000)) {
    char buf[32];
    strftime(buf, sizeof(buf), "%Y-%m-%d %H:%M:%S", &now);
    Serial.printf("Time OK: %s\n", buf);
  } else {
    Serial.println("Could not get the time (not a problem for this test).");
  }

  String json = "{\"message\":\"Hello from the smart bin!\",\"rssi\":" + String(WiFi.RSSI()) +
                ",\"server_time\":{\".sv\":\"timestamp\"}}";
  explain(firebasePut("/test/hello", json));
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) return;
  delay(30000);
  counter++;
  firebasePut("/test/counter", String(counter));
}
