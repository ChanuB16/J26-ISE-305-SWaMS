SMART BIN - IoT CODE (ESP32-S3 N16R8)
=====================================

Put this whole folder in your Arduino sketchbook (Documents/Arduino).
Open each program with File > Open > (folder) > (same-name .ino file).

Run them in this order (one stage at a time - see the build guide):

  test_1_hello          upload works, Serial Monitor works, board settings OK
  test_2_dht22          temperature + humidity            (pin 7)
  test_3_battery        battery voltage                   (pin 10, divider rows 55-63)
  test_4_ultrasonic     JSN-SR04T distance                (Trig 5, Echo 6 via divider rows 27-39)
  test_5_gas            MQ-135 gas sensor                 (pin 4 via divider rows 41-53)
  test_6_load_cell      load cell + HX711                 (DT 15, SCK 16)
  test_7_wifi_firebase  WiFi + Firebase write test        (edit the 3 lines at the top first)
  test_8_clock_and_lights  DS3231 clock (SDA 17, SCL 18, VCC row 40)
                        + status lights if built (pins 11, 12, 13)
  smart_bin             FINAL PROGRAM                     (edit config.h first)
                        Sends a reading to Firebase every 30 seconds (fixed).
                        Calibrate once in the Serial Monitor, then it runs by itself.

  tools/rq1_metrics.py  optional: the web app (Analytics page) shows the same RQ1
                        numbers live. Or run on your laptop with an export:
                        python rq1_metrics.py smart-bin-export.json

Arduino IDE settings (Tools menu):
  Board ............... ESP32S3 Dev Module   (install "esp32 by Espressif Systems")
  USB CDC On Boot ..... Disabled  (if you use the COM / UART USB-C port)
                        Enabled   (if you use the other "USB" port)
  Flash Size .......... 16MB (128Mb)
  Partition Scheme .... 16M Flash (3MB APP/9.9MB FATFS)
  PSRAM ............... OPI PSRAM
  Upload Speed ........ 921600 (use 115200 if uploads fail)

Libraries (Tools > Manage Libraries):
  HX711 Arduino Library  - by Bogdan Necula
  DHT sensor library     - by Adafruit  (choose "Install all" to add Adafruit Unified Sensor)
  ArduinoJson            - by Benoit Blanchon (version 7)

Serial Monitor: 115200 baud, line ending "Newline". In smart_bin type: help

All programs were compiled with esp32 core 3.3.12, ArduinoJson 7.4.3,
DHT sensor library 1.4.7 and HX711 0.7.5.
