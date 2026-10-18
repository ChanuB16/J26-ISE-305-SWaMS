import '../config.dart';

/// Snapshot of a bin from the live tree /bins/<id>/latest + /predictions/<id>.
///
/// Equivalent of data.make_row() in smartwaste_app/data.py.
class BinRow {
  final String id;
  final String name;
  final String zone;
  final String type;
  final double? lat;
  final double? lng;
  final double? fill; // percent 0-100
  final double? pred; // predicted fill 6h, percent
  final double? weightKg;
  final double? gasIndex;
  final double? tempC;
  final double? humidity;
  final int? batteryPct;
  final int? ts;
  final int? lastCollected;
  final bool synthetic;
  final String risk; // high | medium | low | ""
  final double? urgency;
  final double? hoursToFull;
  final double? hoursSince;
  final bool? gasReady;
  final bool stale;
  final List<String> errors;
  final double? batteryV;

  const BinRow({
    required this.id,
    required this.name,
    required this.zone,
    required this.type,
    required this.lat,
    required this.lng,
    required this.fill,
    required this.pred,
    required this.weightKg,
    required this.gasIndex,
    required this.tempC,
    required this.humidity,
    required this.batteryPct,
    required this.ts,
    required this.lastCollected,
    required this.synthetic,
    this.risk = '',
    this.urgency,
    this.hoursToFull,
    this.hoursSince,
    this.gasReady,
    this.stale = false,
    this.errors = const [],
    this.batteryV,
  });

  String get level {
    final f = fill;
    if (f == null) return 'none';
    if (f >= AppConfig.overflowPct) return 'critical';
    if (f >= AppConfig.alertPct) return 'warning';
    if (f >= AppConfig.fillingPct) return 'filling';
    return 'normal';
  }

  bool get hasSpace => (fill ?? 100) < AppConfig.spaceLimitPct;

  factory BinRow.fromFirebase(
    String id,
    Map<String, dynamic>? info,
    Map<String, dynamic>? latest,
    Map<String, dynamic>? pred,
    dynamic lastCollected,
  ) {
    final known = _knownBins[id] ?? const {};
    final i = {...known, ...?info};
    final l = latest ?? const {};
    final p = pred ?? const {};
    double? n(dynamic v) {
      if (v == null || v == '' || v is bool) return null;
      if (v is num) return v.toDouble();
      return double.tryParse(v.toString());
    }

    int? ni(dynamic v) => n(v)?.toInt();

    final ts = ni(l['ts']) ?? ni(p['based_on_ts']);
    var lc = ni(lastCollected);
    var hoursSince = n(p['hours_since_collection']);
    if (lc == null && hoursSince != null && ts != null) {
      lc = (ts - hoursSince * 3600000).round();
    }
    final now = DateTime.now().millisecondsSinceEpoch;
    if (lc != null && (hoursSince == null || lc > (ts ?? 0))) {
      hoursSince = ((now - lc) / 3600000).clamp(0.0, double.infinity);
    }

    final errs = <String>[];
    final rawErr = l['errors'];
    if (rawErr is List) {
      for (final e in rawErr) {
        if (e != null && e.toString().isNotEmpty) errs.add(e.toString());
      }
    } else if (rawErr is Map) {
      for (final e in rawErr.values) {
        if (e != null && e.toString().isNotEmpty) errs.add(e.toString());
      }
    }

    final bool synthetic = (i['synthetic'] == true) ||
        (p['synthetic'] == true) ||
        (l['synthetic'] == true) ||
        id.startsWith('sim_');

    return BinRow(
      id: id,
      name: (i['name'] as String?) ?? id,
      zone: (i['zone'] as String?) ?? (p['zone'] as String?) ?? '',
      type: (i['type'] as String?) ?? '',
      lat: n(i['lat']) ?? n(p['lat']),
      lng: n(i['lng']) ?? n(p['lng']),
      fill: n(l['fill_pct']) ?? n(p['current_fill_pct']),
      pred: n(p['predicted_fill_6h']),
      weightKg: n(l['weight_kg']),
      gasIndex: n(l['gas_index']) ?? n(p['gas_index']),
      tempC: n(l['temp_c']),
      humidity: n(l['humidity_pct']) ?? n(p['humidity_pct']),
      batteryPct: ni(l['battery_pct']),
      ts: ts,
      lastCollected: lc,
      synthetic: synthetic,
      risk: (p['overflow_risk'] as String?) ?? '',
      urgency: n(p['urgency_score']),
      hoursToFull: n(p['hours_to_full']),
      hoursSince: hoursSince,
      gasReady: l['gas_ready'] as bool?,
      stale: ts == null || (now - ts) > AppConfig.noDataMinutes * 60000,
      errors: errs,
      batteryV: n(l['battery_v']),
    );
  }
}

const Map<String, Map<String, Object>> _knownBins = {
  'bin_01': {
    'name': 'SLIIT Malabe (real smart bin)',
    'zone': 'Malabe',
    'type': 'school',
    'lat': 6.9147,
    'lng': 79.9729,
  },
};
