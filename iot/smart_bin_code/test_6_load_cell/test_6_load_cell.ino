/*
  SMART BIN - TEST 6: LOAD CELL + HX711
  -------------------------------------
  Wiring:
    Load cell wires -> HX711 (soldered):
      Red   -> E+
      Black -> E-
      White -> A-
      Green -> A+
    3.3V row first: orange jumper from the SECOND ESP32 3V3 pin (22-j) to 40-j
    HX711 -> breadboard:
      VCC -> 40-h (the 3.3V row) - NOT the red 5V rail
      GND -> blue (-) GND rail
      DT  -> ESP32 pin 15
      SCK -> ESP32 pin 16

  How to test without the bin:
    Hold one end of the load cell firmly on the table (or screw it to a piece
    of wood) and let the other end stick out. Press the free end gently -
    the "change" number must move. If it goes NEGATIVE when you press,
    that is OK (the calibration handles it).

  Commands (type in the Serial Monitor box, press Enter):
    tare       -> remove all weight first, then type this to set zero
    cal 1.0    -> put a known weight on (1 litre water bottle = about 1.0 kg) and type this

  Library needed: "HX711 Arduino Library" by Bogdan Necula
  Serial Monitor: 115200 baud, line ending "Newline".
*/

#include <HX711.h>

#define PIN_HX711_DT 15
#define PIN_HX711_SCK 16

HX711 scale;
long zeroRaw = 0;
float factor = 0;  // raw units per kg (0 = not calibrated yet)
String line;

// Reads n samples and returns the average. Returns false if the HX711 does not answer.
bool readRaw(int n, long &out) {
  long long sum = 0;
  int got = 0;
  for (int i = 0; i < n; i++) {
    if (!scale.wait_ready_timeout(300)) break;
    sum += scale.read();
    got++;
  }
  if (got == 0) return false;
  out = (long)(sum / got);
  return true;
}

void doTare() {
  long raw;
  if (readRaw(20, raw)) {
    zeroRaw = raw;
    Serial.printf(">> Zero saved (raw %ld)\n", raw);
  } else {
    Serial.println(">> HX711 not responding");
  }
}

void doCal(float kg) {
  long raw;
  if (kg <= 0) { Serial.println(">> Use like this: cal 1.0"); return; }
  if (!readRaw(20, raw)) { Serial.println(">> HX711 not responding"); return; }
  long change = raw - zeroRaw;
  if (labs(change) < 1000) { Serial.println(">> Change too small. Is the weight on the free end? Did you tare first?"); return; }
  factor = change / kg;
  Serial.printf(">> Calibration factor = %.1f raw units per kg (write this down)\n", factor);
}

void setup() {
  Serial.begin(115200);
  delay(1500);
  Serial.println();
  Serial.println("=== Smart Bin - Test 6: Load cell + HX711 ===");
  scale.begin(PIN_HX711_DT, PIN_HX711_SCK);
  if (!scale.wait_ready_timeout(2000)) {
    Serial.println("HX711 not found. Check: VCC -> 40-h (3.3V row, fed from the 2nd 3V3 pin), GND -> blue rail, DT -> pin 15, SCK -> pin 16.");
  }
  Serial.println("Keep the load cell EMPTY. Taking zero reading in 3 seconds...");
  delay(3000);
  doTare();
  Serial.println("Commands: tare | cal 1.0");
}

void loop() {
  // read commands typed in the Serial Monitor
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      line.trim();
      if (line == "tare") doTare();
      else if (line.startsWith("cal")) doCal(line.substring(3).toFloat());
      else if (line.length() > 0) Serial.println(">> Unknown command. Use: tare | cal 1.0");
      line = "";
    } else if (line.length() < 40) {
      line += c;
    }
  }

  long raw;
  if (!readRaw(5, raw)) {
    Serial.println("HX711 not responding - check wiring.");
    delay(1000);
    return;
  }
  long change = raw - zeroRaw;
  if (factor != 0) {
    Serial.printf("raw: %9ld   change: %8ld   weight: %6.3f kg\n", raw, change, change / factor);
  } else {
    Serial.printf("raw: %9ld   change: %8ld   (type 'cal 1.0' with 1 kg on it)\n", raw, change);
  }
  delay(300);
}
