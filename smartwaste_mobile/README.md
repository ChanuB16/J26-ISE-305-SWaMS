# SmartWaste LK — Android app (Flutter)

Kaduwela Municipal Council · SLIIT IT4010 · companion app for the Flask website.

This is a mobile Flutter app that talks **directly** to the same Firebase
Realtime Database the website uses. Nothing is duplicated — the ESP32 bin, the
Python ML scripts, the website, and this app all read/write the same tree.

```
Flutter app ─┐
Website ─────┼──► Firebase Realtime Database ◄── ESP32 bin
ML scripts ──┘                                       (writes readings)
```

## What is included today (Stage 1 + 2)

**All roles:** Login + sign-up (same `/users/<username>` as the website —
werkzeug-compatible scrypt hashes)

**Citizen** (bottom-nav shell)
- **Home** — map of all bins, "Find nearest bin with space" (GPS), walk directions via Google Maps
- **Report** — type + bin picker + photo + GPS; writes to `/reports` and uploads the photo to `/report_photos/<id>`
- **Scan** — on-device TensorFlow Lite waste classifier; writes to `/classifications` so officers + the rewards job see it
- **Rewards** — points, level, activity, leaderboard

**Driver**
- Big "Next stop" card with ETA, distance, fill-level pill, progress bar
- Navigate (opens Google Maps driving directions)
- Mark as emptied (patches the stop + simulates fill drop for `sim_*` bins)
- Full stops timeline + emptied-today list
- Report truck broken / fixed (patches `/trucks/<id>/status`)
- Auto-refresh every 15 s + manual pull-to-refresh

**Officer** screens are a placeholder for Stage 3 — officers can still use the
full website in the meantime.

## 1. Install the tools (once per computer)

1. **Flutter SDK** — https://docs.flutter.dev/get-started/install/windows
   - Unzip to e.g. `C:\src\flutter`
   - Add `C:\src\flutter\bin` to your `PATH`
   - Verify in a new terminal:
     ```powershell
     flutter --version
     flutter doctor
     ```
2. **Android Studio** — https://developer.android.com/studio
   - Install the Android SDK (default options)
   - Open Android Studio once; accept the SDK licences
   - Install the "Flutter" and "Dart" plugins
   - In a terminal:
     ```powershell
     flutter doctor --android-licenses
     ```
3. **A test phone** (easiest) — enable Developer Mode + USB Debugging and plug
   it in. Verify:
   ```powershell
   flutter devices
   ```
   Or create an emulator from Android Studio (Device Manager).

## 2. Generate the Android project scaffolding

From inside this folder:
```powershell
cd smartwaste_mobile
flutter create .
```
This fills in the `android/` Gradle wrapper, resource files and
`MainActivity.kt` **without overwriting** our custom
`lib/`, `pubspec.yaml`, `assets/` or `android/app/src/main/AndroidManifest.xml`.

## 3. Point the app at your Firebase project

Open `lib/config.dart`. The `firebaseDbUrl` is already set to the same URL as
`smartwaste_app/settings.py`:

```dart
static const String firebaseDbUrl =
    'https://smart-bin-kaduwela-default-rtdb.asia-southeast1.firebasedatabase.app';
```

If your Realtime Database rules are **in test mode** (public read/write), you
are done. If they are locked down, set `useLogin = true` and fill in
`firebaseApiKey`, `firebaseEmail`, `firebasePassword` — same values as the
Flask app.

Suggested rules for development are in `firebase_rules_example.json`.

## 4. Build the on-device waste classifier (optional but recommended)

The Scan tab uses a TensorFlow Lite model file. Convert your existing Keras
model with the included script (needs Python + TensorFlow on your machine):

```powershell
cd scripts
python convert_model_to_tflite.py
```

This writes `assets/waste_classifier.tflite` and `assets/labels.txt`. The
Flutter app picks them up automatically.

Skip this step if you don't need the Scan feature yet — the app runs, the Scan
tab just shows a short message.

## 5. Install dependencies and run

```powershell
flutter pub get
flutter run
```

Choose your device/emulator when prompted. First build is slow (~5 min);
subsequent builds take 10-30 s.

## 6. Build a release APK (for your demo)

```powershell
flutter build apk --release
```
Resulting file: `build/app/outputs/flutter-apk/app-release.apk`.
Copy it to the demo phone and tap-install.

## Stage 3 — Officer screens (coming next)
- Operations dashboard (KPIs, alerts, live bins)
- Bins fleet (filter, map, bin detail with sensors + history)
- Forecast (7-day tonnage by zone)
- Routes (today's plan, mark road closed, re-plan)
- Analytics (ML results)
- Reports (CSV exports)
- Community moderation
- System health

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| "Firebase returned 401" | Rules are locked down. Set `useLogin = true` in config.dart |
| Login fails for a known user | Password hash format mismatch — see "Hashing notes" below |
| Map tiles don't load | No internet (OpenStreetMap tiles) or the phone blocks HTTP |
| Scan tab says "model not installed" | Run `scripts/convert_model_to_tflite.py` and `flutter pub get` again |
| Camera / location permission denied | Allow it in Android Settings > Apps > SmartWaste LK |

## Hashing notes

The Flask backend uses `werkzeug.security.generate_password_hash` which, by
default, produces either `scrypt:N:r:p$salt$hex` (werkzeug ≥ 2.3) or
`pbkdf2:sha256:iterations$salt$hex` (older werkzeug). The Flutter app
supports **both** — see `lib/utils/werkzeug_hash.dart`.

New accounts created from the Flutter sign-up form use scrypt with the same
defaults (`N=32768, r=8, p=1, dkLen=64`), so Python can verify them without
any change on the server side.
