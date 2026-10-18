/*
  SMART BIN - TEST 1: HELLO
  -------------------------
  Checks that:
    - your computer can upload programs to the ESP32-S3
    - the Serial Monitor works
    - the board settings are correct (Flash 16 MB, PSRAM 8 MB)

  Wiring: nothing. Only the USB cable.
  Serial Monitor: 115200 baud.
*/

void setup() {
  Serial.begin(115200);
  delay(1500);  // give the Serial Monitor time to open

  Serial.println();
  Serial.println("=== Smart Bin - Test 1: Hello ===");
  Serial.printf("Chip  : %s (revision %d), %d cores\n", ESP.getChipModel(), ESP.getChipRevision(), ESP.getChipCores());
  Serial.printf("Flash : %u MB  (should be 16)\n", (unsigned)(ESP.getFlashChipSize() / (1024 * 1024)));
  Serial.printf("PSRAM : %u MB  (should be 8; if 0, set Tools > PSRAM > OPI PSRAM)\n", (unsigned)(ESP.getPsramSize() / (1024 * 1024)));

  uint64_t mac = ESP.getEfuseMac();
  Serial.printf("Board ID (MAC): %04X%08lX\n", (unsigned int)(mac >> 32), (unsigned long)(mac & 0xFFFFFFFF));
  Serial.println("If you can read this, upload and Serial Monitor are working.");
}

void loop() {
  static uint32_t count = 0;
  count++;
  Serial.printf("Hello from your ESP32-S3!  count=%lu  uptime=%lu s\n", (unsigned long)count, (unsigned long)(millis() / 1000));
  delay(1000);
}
