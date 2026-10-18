/*
  SMART BIN - TEST 2: DHT22 (temperature + humidity)
  --------------------------------------------------
  Wiring (DHT22 module -> breadboard):
    VCC (or +)  -> ESP32 3V3 pin (the FIRST 3V3 pin) - NOT the red 5V rail
    GND (or -)  -> blue (-) GND rail
    DAT (or OUT)-> ESP32 pin 7  (the free hole beside pin 7)

  Library needed: "DHT sensor library" by Adafruit
                  (also install "Adafruit Unified Sensor" when asked)
  Serial Monitor: 115200 baud.
*/

#include <DHT.h>

#define PIN_DHT 7

DHT dht(PIN_DHT, DHT22);

void setup() {
  Serial.begin(115200);
  delay(1500);
  Serial.println();
  Serial.println("=== Smart Bin - Test 2: DHT22 ===");
  dht.begin();
}

void loop() {
  delay(2500);  // the DHT22 can only be read once every 2 seconds

  float tempC = dht.readTemperature();
  float humidity = dht.readHumidity();

  if (isnan(tempC) || isnan(humidity)) {
    Serial.println("No data from DHT22. Check: VCC -> ESP32 3V3 pin, GND -> blue rail, DAT -> pin 7.");
    return;
  }

  Serial.printf("Temperature: %.1f C   Humidity: %.1f %%\n", tempC, humidity);
}
