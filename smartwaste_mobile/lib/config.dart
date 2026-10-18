/// SmartWaste LK — mobile app configuration.
///
/// Edit this one file to point the app at your Firebase Realtime Database
/// (the SAME URL the Flask website uses, so phone + website share one DB).
///
/// If your Firebase rules are in "test mode" (public read/write) leave
/// [useLogin] = false. If you locked the rules down, set [useLogin] = true
/// and fill in [firebaseApiKey], [firebaseEmail], [firebasePassword] with
/// the same service account the Flask app uses in smartwaste_app/settings.py.
library;

class AppConfig {
  AppConfig._();

  /// Firebase Realtime Database URL (no trailing slash).
  /// Same value as FIREBASE_DB_URL in smartwaste_app/settings.py.
  static const String firebaseDbUrl =
      'https://smart-bin-kaduwela-default-rtdb.asia-southeast1.firebasedatabase.app';

  /// Set to true if the DB rules require an authenticated user.
  static const bool useLogin = false;

  /// Only needed when [useLogin] is true.
  static const String firebaseApiKey = 'YOUR_WEB_API_KEY';
  static const String firebaseEmail = 'web@smartbin.test';
  static const String firebasePassword = 'CHANGE_THIS_PASSWORD';

  // --- Business numbers (keep in sync with smartwaste_app/settings.py) ---
  static const int overflowPct = 90;
  static const int alertPct = 75;
  static const int fillingPct = 50;
  static const int spaceLimitPct = 80;
  static const double maxWalkKm = 2.0;
  static const int smellIndex = 60;
  static const int lowBatteryPct = 20;
  static const int noDataMinutes = 30;
  static const double urgencyMedium = 45;
  static const double urgencyHigh = 75;
  static const double wFill = 0.5;
  static const double wGas = 0.2;
  static const double wHumidity = 0.1;
  static const double wTime = 0.2;
  static const double fullTimeHours = 72;
  static const int susTarget = 68;

  // Depot / city centre (used for default map view).
  static const double depotLat = 6.9330;
  static const double depotLng = 79.9830;
  static const String depotName = 'Council yard (Kaduwela)';

  // Reward levels (same list as data.REWARD_LEVELS in Flask app).
  static const List<MapEntry<int, String>> rewardLevels = [
    MapEntry(0, 'Eco Starter'),
    MapEntry(50, 'Eco Contributor'),
    MapEntry(150, 'Green Champion'),
    MapEntry(400, 'Kaduwela Eco Hero'),
  ];

  // Classifier settings.
  /// Minimum confidence to consider the AI "sure" (same as CLASSIFIER_SURE_LEVEL).
  static const double classifierSureLevel = 0.60;

  /// Asset path of the TensorFlow Lite model (after conversion).
  /// See scripts/convert_model_to_tflite.py.
  static const String classifierModelAsset = 'assets/waste_classifier.tflite';
  static const String classifierLabelsAsset = 'assets/labels.txt';

  // How often lists auto-refresh.
  static const Duration refresh = Duration(seconds: 15);
}
