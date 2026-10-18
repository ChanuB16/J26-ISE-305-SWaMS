/// Represents a user document stored at /users/<username>.
///
/// Must stay compatible with smartwaste_app/users.py so the SAME account
/// can log in on the website and in the mobile app.
class SmartUser {
  final String username;
  final String name;
  final String role; // officer | driver | citizen
  final String truck; // only meaningful for drivers
  final bool active;

  const SmartUser({
    required this.username,
    required this.name,
    required this.role,
    this.truck = '',
    this.active = true,
  });

  bool get isOfficer => role == 'officer';
  bool get isDriver => role == 'driver';
  bool get isCitizen => role == 'citizen';

  factory SmartUser.fromMap(String username, Map<String, dynamic> m) {
    return SmartUser(
      username: username,
      name: (m['name'] as String?)?.trim().isNotEmpty == true
          ? m['name'] as String
          : username,
      role: (m['role'] as String?) ?? 'citizen',
      truck: (m['truck'] as String?) ?? '',
      active: (m['active'] as bool?) ?? true,
    );
  }

  Map<String, dynamic> toJson() => {
        'username': username,
        'name': name,
        'role': role,
        'truck': truck,
        'active': active,
      };

  factory SmartUser.fromJson(Map<String, dynamic> j) => SmartUser(
        username: j['username'] as String,
        name: j['name'] as String,
        role: j['role'] as String,
        truck: (j['truck'] as String?) ?? '',
        active: (j['active'] as bool?) ?? true,
      );
}
