/// Thin wrapper around the Firebase Realtime Database REST API.
///
/// Mirrors the operations used by the Flask app (`fb.py::RestDB`): get, put,
/// patch, post, delete, plus the "shallow" and "limit" query parameters.
///
/// Keeping it REST-based means the mobile app does NOT need the FlutterFire
/// native plugins or google-services.json — any Flutter target can talk to
/// the same database with just an HTTP client.
library;

import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config.dart';

class DbError implements Exception {
  final String message;
  DbError(this.message);
  @override
  String toString() => 'DbError: $message';
}

class FirebaseRest {
  FirebaseRest._();
  static final FirebaseRest instance = FirebaseRest._();

  final http.Client _client = http.Client();
  String? _idToken; // present only when AppConfig.useLogin is true
  DateTime? _tokenExpires;

  Uri _uri(String path, {Map<String, String>? query}) {
    final clean = path.startsWith('/') ? path.substring(1) : path;
    final url = '${AppConfig.firebaseDbUrl}/$clean.json';
    final q = <String, String>{...?query};
    if (_idToken != null) q['auth'] = _idToken!;
    return Uri.parse(url).replace(queryParameters: q.isEmpty ? null : q);
  }

  Future<void> _ensureAuth() async {
    if (!AppConfig.useLogin) return;
    if (_idToken != null &&
        _tokenExpires != null &&
        _tokenExpires!.isAfter(DateTime.now().add(const Duration(minutes: 1)))) {
      return;
    }
    final url = Uri.parse(
      'https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword'
      '?key=${AppConfig.firebaseApiKey}',
    );
    final res = await _client.post(
      url,
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'email': AppConfig.firebaseEmail,
        'password': AppConfig.firebasePassword,
        'returnSecureToken': true,
      }),
    );
    if (res.statusCode >= 400) {
      throw DbError('Firebase login failed (${res.statusCode}).');
    }
    final j = jsonDecode(res.body) as Map<String, dynamic>;
    _idToken = j['idToken'] as String;
    final expiresInSec = int.parse(j['expiresIn'] as String);
    _tokenExpires = DateTime.now().add(Duration(seconds: expiresInSec));
  }

  /// Read a path. Set [shallow] = true to get only top-level keys.
  Future<dynamic> get(
    String path, {
    bool shallow = false,
    String? orderBy,
    int? limitToLast,
    int? limitToFirst,
    dynamic startAt,
    dynamic endAt,
  }) async {
    await _ensureAuth();
    final q = <String, String>{};
    if (shallow) q['shallow'] = 'true';
    if (orderBy != null) q['orderBy'] = jsonEncode(orderBy);
    if (limitToLast != null) q['limitToLast'] = limitToLast.toString();
    if (limitToFirst != null) q['limitToFirst'] = limitToFirst.toString();
    if (startAt != null) q['startAt'] = jsonEncode(startAt);
    if (endAt != null) q['endAt'] = jsonEncode(endAt);
    final res = await _client.get(_uri(path, query: q));
    _check(res);
    if (res.body.isEmpty || res.body == 'null') return null;
    return jsonDecode(res.body);
  }

  Future<void> put(String path, dynamic value) async {
    await _ensureAuth();
    final res = await _client.put(_uri(path),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(value));
    _check(res);
  }

  Future<void> patch(String path, Map<String, dynamic> value) async {
    await _ensureAuth();
    final res = await _client.patch(_uri(path),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(value));
    _check(res);
  }

  /// Appends a child under [path] and returns the new key.
  Future<String> post(String path, dynamic value) async {
    await _ensureAuth();
    final res = await _client.post(_uri(path),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(value));
    _check(res);
    final j = jsonDecode(res.body) as Map<String, dynamic>;
    return j['name'] as String;
  }

  Future<void> delete(String path) async {
    await _ensureAuth();
    final res = await _client.delete(_uri(path));
    _check(res);
  }

  /// Firebase server-side timestamp placeholder, same as the Flask app.
  static Map<String, String> serverTimestamp() => const {'.sv': 'timestamp'};

  void _check(http.Response res) {
    if (res.statusCode >= 200 && res.statusCode < 300) return;
    throw DbError('Firebase returned ${res.statusCode}: '
        '${res.body.isEmpty ? "no body" : res.body}');
  }
}
