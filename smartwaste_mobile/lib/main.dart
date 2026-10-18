import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'app.dart';
import 'services/session.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  FlutterError.onError = (details) {
    FlutterError.dumpErrorToConsole(details);
  };

  try {
    await Session.instance.restore().timeout(const Duration(seconds: 4));
  } catch (_) {
    // Show the login screen even if local storage is slow or broken.
  }

  runApp(
    ChangeNotifierProvider<Session>.value(
      value: Session.instance,
      child: const SmartWasteApp(),
    ),
  );
}
