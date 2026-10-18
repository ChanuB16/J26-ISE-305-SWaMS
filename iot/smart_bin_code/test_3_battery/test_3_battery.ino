/*
  SMART BIN - TEST 3: BATTERY VOLTAGE
  -----------------------------------
  Checks the battery-voltage divider (rows 55 to 63 on the breadboard).

  Wiring:
    Battery wire (from the switch output / MT3608 VIN+) -> breadboard hole 55-h
    22k resistor R7: 55-g to 59-g
    22k resistor R8: 59-f to 63-f
    Jumper: 59-j -> ESP32 pin 10 (the free hole beside pin 10)
    Black jumper: 63-j -> blue (-) GND rail

  Turn the battery switch ON. Compare the number with your multimeter
  (multimeter on DCV 20, probes on TP4056 OUT+ and OUT-).
  A difference of up to about 0.2 V is normal - the final program can correct it
  with the "batcal" command.
  Serial Monitor: 115200 baud.
*/

#define PIN_BATTERY 10
#define BATTERY_DIVIDER_FACTOR 2.0f  // 22k on top, 22k below

void setup() {
  Serial.begin(115200);
  delay(1500);
  Serial.println();
  Serial.println("=== Smart Bin - Test 3: Battery voltage ===");
}

void loop() {
  uint32_t sum = 0;
  for (int i = 0; i < 16; i++) {
    sum += analogReadMilliVolts(PIN_BATTERY);
    delay(2);
  }
  float pinVolts = sum / 16.0f / 1000.0f;
  float batteryVolts = pinVolts * BATTERY_DIVIDER_FACTOR;

  if (batteryVolts < 2.5f) {
    Serial.printf("Battery: not detected (pin reads %.2f V). Is the switch ON? Is the divider wired?\n", pinVolts);
  } else {
    Serial.printf("Battery: %.2f V   (pin 10 reads %.2f V)\n", batteryVolts, pinVolts);
  }
  delay(1000);
}
