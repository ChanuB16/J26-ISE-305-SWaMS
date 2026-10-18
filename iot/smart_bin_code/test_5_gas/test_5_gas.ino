/*
  SMART BIN - TEST 5: GAS SENSOR (MQ-135)
  ---------------------------------------
  Wiring (MQ-135 module):
    VCC -> red (+) 5V rail
    GND -> blue (-) GND rail
    AO  -> breadboard hole 41-h  (start of the gas voltage divider)
    DO  -> not connected
  Gas voltage divider (all three resistors are 22k):
    R4: 41-g to 45-g,  R5: 45-f to 49-f,  R6: 49-g to 53-g
    Jumper: 45-j -> ESP32 pin 4
    Black jumper: 53-j -> blue (-) GND rail

  IMPORTANT:
    - The battery switch must be ON (the sensor heater runs on the 5V rail).
    - The sensor gets warm. That is normal.
    - Readings are only stable after about 20 minutes. A NEW sensor needs
      24 hours of total running time before its readings settle.
  Serial Monitor: 115200 baud.
*/

#define PIN_GAS_AO 4
#define GAS_DIVIDER_FACTOR 1.5f  // 22k on top, 22k + 22k below

void setup() {
  Serial.begin(115200);
  delay(1500);
  Serial.println();
  Serial.println("=== Smart Bin - Test 5: Gas sensor (MQ-135) ===");
  Serial.println("Tip: after warm-up, hold a cotton bud with a little hand sanitizer near the sensor - the number should go up.");
}

void loop() {
  uint32_t sum = 0;
  for (int i = 0; i < 32; i++) {
    sum += analogReadMilliVolts(PIN_GAS_AO);
    delay(2);
  }
  float pinMv = sum / 32.0f;
  float sensorMv = pinMv * GAS_DIVIDER_FACTOR;

  unsigned long minutes = millis() / 60000UL;
  if (sensorMv < 5.0f) {
    Serial.println("Gas: no signal. Check: battery switch ON? VCC -> red 5V rail? AO -> 41-h? Divider resistors?");
  } else {
    Serial.printf("Gas sensor output: %4.0f mV   (pin 4: %4.0f mV)   running %lu min%s\n",
                  sensorMv, pinMv, minutes, minutes < 20 ? "  [warming up]" : "");
  }
  delay(1000);
}
