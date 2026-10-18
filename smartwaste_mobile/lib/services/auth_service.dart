/// Logs a user in by reading /users/<username> from Firebase and verifying
/// the password hash with the werkzeug algorithm used by the Flask backend.
///
/// This way the SAME accounts work on the website and in the mobile app
/// — no migration, no Firebase Auth setup, no extra screens.
library;

import 'dart:convert';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:pointycastle/key_derivators/api.dart';
import 'package:pointycastle/key_derivators/scrypt.dart';

import '../models/user.dart';
import '../utils/werkzeug_hash.dart';
import 'firebase_rest.dart';

class AuthException implements Exception {
  final String message;
  AuthException(this.message);
  @override
  String toString() => message;
}

class AuthService {
  AuthService._();
  static final AuthService instance = AuthService._();

  final _db = FirebaseRest.instance;
  final math.Random _rand = math.Random.secure();

  static final RegExp _nameRe = RegExp(r'^[a-z0-9_.\-]{3,30}$');

  // --- validation ---

  String? validateUsername(String username) {
    if (!_nameRe.hasMatch(username)) {
      return 'User name: 3-30 small letters, numbers, dot, dash or underscore.';
    }
    return null;
  }

  String? validatePassword(String password) {
    if (password.length < 8) return 'Password: at least 8 characters.';
    return null;
  }

  // --- login ---

  /// Returns the public user profile on success, or throws [AuthException].
  Future<SmartUser> login(String username, String password) async {
    final name = username.trim().toLowerCase();
    if (name.isEmpty) throw AuthException('Please type a user name.');
    final raw = await _db.get('users/$name');
    if (raw is! Map) throw AuthException('Wrong user name or password.');
    final map = Map<String, dynamic>.from(raw);
    final hash = map['password'] as String?;
    if (!verifyWerkzeugHash(hash, password)) {
      throw AuthException('Wrong user name or password.');
    }
    if ((map['active'] as bool? ?? true) == false) {
      throw AuthException('This account is switched off.');
    }
    // Best-effort last_login stamp (ignore errors).
    try {
      await _db.patch('users/$name',
          {'last_login': DateTime.now().millisecondsSinceEpoch});
    } catch (_) {}
    return SmartUser.fromMap(name, map);
  }

  /// Returns true when at least one officer account exists. The login
  /// screen uses this to decide whether to show the first-time setup tab.
  Future<bool> hasOfficer() async {
    final raw = await _db.get('users');
    if (raw is! Map) return false;
    for (final v in raw.values) {
      if (v is Map &&
          v['role'] == 'officer' &&
          (v['active'] as bool? ?? true)) {
        return true;
      }
    }
    return false;
  }

  // --- sign-up (citizen + first-time officer) ---

  Future<SmartUser> signUp({
    required String username,
    required String password,
    required String displayName,
    required String role, // 'citizen' or 'officer' (first-time only)
  }) async {
    final name = username.trim().toLowerCase();
    final uErr = validateUsername(name);
    if (uErr != null) throw AuthException(uErr);
    final pErr = validatePassword(password);
    if (pErr != null) throw AuthException(pErr);
    if (role != 'citizen' && role != 'officer') {
      throw AuthException('Unknown role.');
    }

    final existing = await _db.get('users/$name');
    if (existing is Map) throw AuthException('That user name is already taken.');

    final hash = _hashPassword(password);
    final user = {
      'name': displayName.trim().isEmpty ? name : displayName.trim(),
      'role': role,
      'password': hash,
      'truck': '',
      'active': true,
      'created': DateTime.now().millisecondsSinceEpoch,
    };
    await _db.put('users/$name', user);
    return SmartUser.fromMap(name, user);
  }

  Future<List<SmartUser>> listStaff() async {
    final raw = await _db.get('users');
    final out = <SmartUser>[];
    if (raw is Map) {
      raw.forEach((k, v) {
        if (v is Map) {
          final u = SmartUser.fromMap(k.toString(), Map<String, dynamic>.from(v));
          if (u.role == 'officer' || u.role == 'driver') out.add(u);
        }
      });
    }
    out.sort((a, b) => a.username.compareTo(b.username));
    return out;
  }

  Future<List<String>> truckIds() async {
    final raw = await _db.get('trucks', shallow: true);
    if (raw is! Map) return const [];
    final ids = raw.keys.map((k) => k.toString()).where((k) => !k.startsWith('_')).toList()
      ..sort();
    return ids;
  }

  Future<SmartUser> createStaff({
    required String username,
    required String password,
    required String displayName,
    required String role,
    String truck = '',
  }) async {
    final name = username.trim().toLowerCase();
    final uErr = validateUsername(name);
    if (uErr != null) throw AuthException(uErr);
    final pErr = validatePassword(password);
    if (pErr != null) throw AuthException(pErr);
    if (role != 'officer' && role != 'driver') {
      throw AuthException('Role must be officer or driver.');
    }
    final existing = await _db.get('users/$name');
    if (existing is Map) throw AuthException('That user name is already taken.');
    final user = {
      'name': displayName.trim().isEmpty ? name : displayName.trim(),
      'role': role,
      'password': _hashPassword(password),
      'truck': role == 'driver' ? truck.trim() : '',
      'active': true,
      'created': DateTime.now().millisecondsSinceEpoch,
    };
    await _db.put('users/$name', user);
    return SmartUser.fromMap(name, user);
  }

  Future<void> updateStaff(
    String username, {
    String? displayName,
    String? role,
    String? truck,
    bool? active,
    String? password,
    required String actor,
  }) async {
    final name = username.trim().toLowerCase();
    if (name == actor) {
      throw AuthException('You cannot change your own account here.');
    }
    final existing = await _db.get('users/$name');
    if (existing is! Map) throw AuthException('No such user.');
    final roleNow = (existing['role'] as String?) ?? '';
    if (roleNow != 'officer' && roleNow != 'driver') {
      throw AuthException('Only staff accounts can be changed here.');
    }
    final patch = <String, dynamic>{};
    if (displayName != null) patch['name'] = displayName.trim();
    if (role != null) {
      if (role != 'officer' && role != 'driver') {
        throw AuthException('Role must be officer or driver.');
      }
      patch['role'] = role;
    }
    if (truck != null) patch['truck'] = truck.trim();
    if (active != null) patch['active'] = active;
    if (password != null) {
      final pErr = validatePassword(password);
      if (pErr != null) throw AuthException(pErr);
      patch['password'] = _hashPassword(password);
    }
    if (patch.isEmpty) return;
    await _db.patch('users/$name', patch);
  }

  Future<void> deleteStaff(String username, {required String actor}) async {
    final name = username.trim().toLowerCase();
    if (name == actor) {
      throw AuthException('You cannot remove your own account here.');
    }
    await _db.delete('users/$name');
  }

  // --- werkzeug-compatible scrypt hashing ---

  /// Produces a string that werkzeug's check_password_hash can verify:
  ///   scrypt:32768:8:1$<salt>$<hex>
  String _hashPassword(String password) {
    const n = 32768, r = 8, p = 1, dkLen = 64;
    final salt = _randomSalt(16);
    final out = Uint8List(dkLen);
    final scrypt = Scrypt()
      ..init(ScryptParameters(n, r, p, dkLen,
          Uint8List.fromList(utf8.encode(salt))));
    scrypt.deriveKey(
        Uint8List.fromList(utf8.encode(password)), 0, out, 0);
    final hex = out
        .map((b) => b.toRadixString(16).padLeft(2, '0'))
        .join();
    return 'scrypt:$n:$r:$p\$$salt\$$hex';
  }

  /// Werkzeug default salt: 16 chars of [A-Za-z0-9].
  String _randomSalt(int length) {
    const alphabet =
        'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    final sb = StringBuffer();
    for (var i = 0; i < length; i++) {
      sb.write(alphabet[_rand.nextInt(alphabet.length)]);
    }
    return sb.toString();
  }
}
