/*
  SMART BIN - TEST 8: CLOCK MODULE (DS3231) + STATUS LIGHTS
  ---------------------------------------------------------
  Clock module: part of the C2 proposal - connect it.
  Status lights: optional (if time). The test runs either way.

  Clock module wiring (use the 4 pins GND, VCC, SDA, SCL):
    ESP32 3V3 (second 3V3 pin) -> 40-j   (already done in Stage 6: row 40 f-j is the 3.3V row)
    Clock VCC -> 40-g      (3.3V - NOT the red 5V rail)
    Clock GND -> blue (-) GND rail
    Clock SDA -> ESP32 pin 17
    Clock SCL -> ESP32 pin 18

  Status lights (each: ESP32 pin -> 2k resistor -> LED long leg; LED short leg -> GND):
    Green : pin 11 -> 30-e, 2k 30-d to 33-d, LED long leg 33-c, short leg 34-c, 34-a -> bottom blue rail
    Yellow: pin 12 -> 37-e, 2k 37-d to 40-d, LED long leg 40-c, short leg 41-c, 41-a -> bottom blue rail
    Red   : pin 13 -> 44-e, 2k 44-d to 47-d, LED long leg 47-c, short leg 48-c, 48-a -> bottom blue rail
    Bridge: top blue rail (row 62) -> bottom blue rail (row 62), black

  The clock's time is set automatically by the final program once WiFi works.
  Serial Monitor: 115200 baud.
*/

#include <Wire.h>

#define PIN_RTC_SDA 17
#define PIN_RTC_SCL 18
#define PIN_LED_GREEN 11
#define PIN_LED_YELLOW 12
#define PIN_LED_RED 13

const uint8_t RTC_ADDR = 0x68;

uint8_t bcdToDec(uint8_t v) {
  return (uint8_t)((v >> 4) * 10 + (v & 0x0F));
}

// Reads one register of the clock module. Returns -1 if it does not answer.
int readReg(uint8_t reg) {
  Wire.beginTransmission(RTC_ADDR);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return -1;
  if (Wire.requestFrom(RTC_ADDR, (uint8_t)1) != 1) return -1;
  return Wire.read();
}

void setup() {
  Serial.begin(115200);
  delay(1500);
  Serial.println();
  Serial.println("=== Smart Bin - Test 8: Clock module + status lights ===");
  pinMode(PIN_LED_GREEN, OUTPUT);
  pinMode(PIN_LED_YELLOW, OUTPUT);
  pinMode(PIN_LED_RED, OUTPUT);
  Wire.begin(PIN_RTC_SDA, PIN_RTC_SCL);
}

void loop() {
  // 1. Clock module
  int sec1 = readReg(0x00);
  if (sec1 < 0) {
    Serial.println("Clock module: not found. Check VCC -> row 40 (3.3V), GND, SDA -> pin 17, SCL -> pin 18.");
  } else {
    int status = readReg(0x0F);
    Serial.printf("Clock module: found. Seconds counter = %d%s\n", bcdToDec(sec1 & 0x7F),
                  (status >= 0 && (status & 0x80)) ? "  (time not set yet - the final program sets it from the internet)" : "");
  }

  // 2. Status lights: green, yellow, red, one after the other
  const int pins[3] = {PIN_LED_GREEN, PIN_LED_YELLOW, PIN_LED_RED};
  const char *names[3] = {"green", "yellow", "red"};
  for (int i = 0; i < 3; i++) {
    digitalWrite(pins[i], HIGH);
    Serial.printf("  light %s ON\n", names[i]);
    delay(700);
    digitalWrite(pins[i], LOW);
  }
  delay(500);
}
