import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'screens/citizen/citizen_shell.dart';
import 'screens/driver/driver_screen.dart';
import 'screens/login_screen.dart';
import 'screens/officer/officer_shell.dart';
import 'services/session.dart';
import 'theme.dart';

class SmartWasteApp extends StatelessWidget {
  const SmartWasteApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'SmartWaste LK',
      debugShowCheckedModeBanner: false,
      theme: buildAppTheme(),
      home: const _RootRouter(),
    );
  }
}

class _RootRouter extends StatelessWidget {
  const _RootRouter();

  @override
  Widget build(BuildContext context) {
    final session = context.watch<Session>();
    final user = session.user;
    if (user == null) return const LoginScreen();
    switch (user.role) {
      case 'officer':
        return const OfficerShell();
      case 'driver':
        return const DriverScreen();
      case 'citizen':
      default:
        return const CitizenShell();
    }
  }
}
