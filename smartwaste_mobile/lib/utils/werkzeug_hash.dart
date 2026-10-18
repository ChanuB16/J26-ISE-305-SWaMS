/// Verifies passwords stored in Firebase under /users/<name>/password by
/// werkzeug.security.generate_password_hash() in the Flask backend.
///
/// Supported formats (both are werkzeug defaults):
///   scrypt:N:r:p$<salt>$<hex_hash>              (werkzeug >= 2.3, default)
///   pbkdf2:sha256:<iterations>$<salt>$<hex>     (older werkzeug default)
///
/// Returns true when the plain-text [password] matches the stored [hash].
library;

import 'dart:convert';
import 'dart:typed_data';

import 'package:pointycastle/digests/sha256.dart';
import 'package:pointycastle/key_derivators/api.dart';
import 'package:pointycastle/key_derivators/pbkdf2.dart';
import 'package:pointycastle/key_derivators/scrypt.dart';
import 'package:pointycastle/macs/hmac.dart';

bool verifyWerkzeugHash(String? storedHash, String password) {
  if (storedHash == null || storedHash.isEmpty) return false;

  // Format is  method$salt$hashhex .
  final parts = storedHash.split(r'$');
  if (parts.length != 3) return false;
  final method = parts[0];
  final salt = parts[1];
  final storedHex = parts[2].toLowerCase();

  final saltBytes = Uint8List.fromList(utf8.encode(salt));
  final pwBytes = Uint8List.fromList(utf8.encode(password));

  try {
    if (method.startsWith('scrypt:')) {
      final mp = method.split(':'); // scrypt : N : r : p
      final n = int.parse(mp[1]);
      final r = int.parse(mp[2]);
      final p = int.parse(mp[3]);
      const dkLen = 64; // werkzeug uses 64 bytes
      final scrypt = Scrypt()
        ..init(ScryptParameters(n, r, p, dkLen, saltBytes));
      final out = Uint8List(dkLen);
      scrypt.deriveKey(pwBytes, 0, out, 0);
      return _ctEqualHex(_toHex(out), storedHex);
    }

    if (method.startsWith('pbkdf2:')) {
      final mp = method.split(':'); // pbkdf2 : hashname : iterations
      final hashName = mp[1];
      final iterations = int.parse(mp[2]);
      if (hashName != 'sha256') return false; // only sha256 supported here
      const dkLen = 32;
      final pbkdf2 = PBKDF2KeyDerivator(HMac(SHA256Digest(), 64))
        ..init(Pbkdf2Parameters(saltBytes, iterations, dkLen));
      final out = pbkdf2.process(pwBytes);
      return _ctEqualHex(_toHex(out), storedHex);
    }
  } catch (_) {
    return false;
  }
  return false;
}

String _toHex(List<int> bytes) =>
    bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();

/// Constant-time string comparison (both lowercase hex).
bool _ctEqualHex(String a, String b) {
  if (a.length != b.length) return false;
  var diff = 0;
  for (var i = 0; i < a.length; i++) {
    diff |= a.codeUnitAt(i) ^ b.codeUnitAt(i);
  }
  return diff == 0;
}
