import 'package:flutter/material.dart';

/// Fill-level colours — same meaning as the Flask app so the two UIs match.
class FillColors {
  static const Color normal = Color(0xFF2E7D32);   // green
  static const Color filling = Color(0xFFF9A825);  // yellow
  static const Color warning = Color(0xFFEF6C00);  // orange
  static const Color critical = Color(0xFFC62828); // red
  static const Color none = Color(0xFF9E9E9E);     // grey (no data)

  static Color forLevel(String level) {
    switch (level) {
      case 'critical':
        return critical;
      case 'warning':
        return warning;
      case 'filling':
        return filling;
      case 'normal':
        return normal;
      default:
        return none;
    }
  }

  static String symbolFor(String level) {
    switch (level) {
      case 'critical':
        return '\u2716'; // ✖
      case 'warning':
        return '\u25B2'; // ▲
      case 'filling':
        return '\u25CF'; // ●
      case 'normal':
        return '\u2713'; // ✓
      default:
        return '-';
    }
  }

  static String wordFor(String level) {
    switch (level) {
      case 'critical':
        return 'Critical';
      case 'warning':
        return 'Warning';
      case 'filling':
        return 'Filling';
      case 'normal':
        return 'Normal';
      default:
        return 'No data';
    }
  }
}

ThemeData buildAppTheme() {
  final scheme = ColorScheme.fromSeed(
    seedColor: const Color(0xFF2E7D32),
    brightness: Brightness.light,
  );
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    appBarTheme: AppBarTheme(
      backgroundColor: scheme.primary,
      foregroundColor: scheme.onPrimary,
      elevation: 0,
    ),
    inputDecorationTheme: const InputDecorationTheme(
      border: OutlineInputBorder(),
      filled: true,
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size.fromHeight(48),
      ),
    ),
  );
}
