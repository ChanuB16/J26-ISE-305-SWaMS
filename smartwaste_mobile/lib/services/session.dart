/// Holds the currently logged-in user and persists it on disk.
///
/// Notified via ChangeNotifier so screens can rebuild on login/logout.
library;

import 'dart:convert';

import 'package:flutter/foundation.dart';

import '../models/user.dart';
import 'session_persist.dart';

class Session extends ChangeNotifier {
  Session._();
  static final Session instance = Session._();

  SmartUser? _user;
  SmartUser? get user => _user;
  bool get isLoggedIn => _user != null;

  /// Load any previously-saved user from disk (call once from main()).
  Future<void> restore() async {
    try {
      final raw = await loadSessionJson();
      if (raw == null || raw.isEmpty) return;
      _user = SmartUser.fromJson(jsonDecode(raw) as Map<String, dynamic>);
      notifyListeners();
    } catch (_) {
      await saveSessionJson(null);
    }
  }

  Future<void> setUser(SmartUser user) async {
    _user = user;
    try {
      await saveSessionJson(jsonEncode(user.toJson()));
    } catch (_) {}
    notifyListeners();
  }

  Future<void> logout() async {
    _user = null;
    try {
      await saveSessionJson(null);
    } catch (_) {}
    notifyListeners();
  }
}
