
/*
  SMART BIN - TEST 4: HC-SR04 ULTRASONIC SENSOR
  ---------------------------------------------
  Wiring:
    HC-SR04 VCC  -> 5V rail
    HC-SR04 GND  -> GND rail
    HC-SR04 TRIG -> ESP32-S3 GPIO 5
    HC-SR04 ECHO -> voltage divider input

  Echo voltage divider (three 22k resistors):
    R1: 27-g to 31-g
    R2: 31-f to 35-f
    R3: 35-g to 39-g
    ECHO: breadboard row 27, f-j side
    GPIO 6: breadboard row 31, f-j side
    GND: breadboard row 39, f-j side

  The first 22k resistor is between ECHO and GPIO 6.
  The other two 22k resistors are in series from GPIO 6 to GND.
  This reduces the 5V echo signal to approximately 3.33V.

  Serial Monitor: 115200 baud.
*/

#define PIN_US_TRIG 5
#define PIN_US_ECHO 6

// Send one HC-SR04 trigger pulse and return echo time.
// Returns 0 if no echo is detected.
unsigned long pingOnce() {
  digitalWrite(PIN_US_TRIG, LOW);
  delayMicroseconds(2);

  digitalWrite(PIN_US_TRIG, HIGH);
  delayMicroseconds(10);  // HC-SR04 trigger pulse
  digitalWrite(PIN_US_TRIG, LOW);

  return pulseIn(PIN_US_ECHO, HIGH, 30000UL);
}

void setup() {
  Serial.begin(115200);
  delay(1500);

  Serial.println();
  Serial.println("=== Smart Bin - Test 4: HC-SR04 ===");

  pinMode(PIN_US_TRIG, OUTPUT);
  digitalWrite(PIN_US_TRIG, LOW);
  pinMode(PIN_US_ECHO, INPUT);
}

void loop() {
  float cm[5];
  int good = 0;

  // Collect five readings.
  for (int i = 0; i < 5; i++) {
    unsigned long us = pingOnce();

    if (us > 0) {
      cm[good++] = us * 0.0343f / 2.0f;
    }

    delay(70);
  }

  if (good == 0) {
    Serial.println(
      "No echo. Check 5V, GND, TRIG GPIO 5, "
      "ECHO divider, and GPIO 6."
    );
  } else {
    // Sort valid readings from smallest to largest.
    for (int i = 1; i < good; i++) {
      float key = cm[i];
      int j = i - 1;

      while (j >= 0 && cm[j] > key) {
        cm[j + 1] = cm[j];
        j--;
      }

      cm[j + 1] = key;
    }

    // Calculate the true median, including even sample counts.
    float median;

    if (good % 2 == 1) {
      median = cm[good / 2];
    } else {
      median = (cm[good / 2 - 1] + cm[good / 2]) / 2.0f;
    }

    const char* note = "";

    if (median < 2.0f) {
      note = " <- closer than ~2 cm; unreliable";
    } else if (median > 400.0f) {
      note = " <- beyond typical 400 cm range";
    }

    Serial.printf(
      "Distance: %.1f cm (%d of 5 pings answered)%s\n",
      median, good, note
    );
  }

  delay(400);
}
