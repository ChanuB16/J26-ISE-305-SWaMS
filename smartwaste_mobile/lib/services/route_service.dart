/// Reads /routes/<yyyy-mm-dd> and /trucks from Firebase for driver screens.
///
/// Keeps the Flask semantics: route for today, same stop-done side effects
/// as data.mark_stop_done().
library;

import 'package:intl/intl.dart';

import '../models/route.dart';
import 'firebase_rest.dart';

class RouteService {
  RouteService._();
  static final RouteService instance = RouteService._();

  final _db = FirebaseRest.instance;

  static String todayIso() => DateFormat('yyyy-MM-dd').format(DateTime.now());

  Future<DayRoutes> loadForDay(String day) async {
    final routesRaw = await _db.get('routes/$day');
    final trucksRaw = await _db.get('trucks');
    final trafficRaw = await _db.get('traffic');

    final routes = <String, Map<String, dynamic>>{};
    int? summaryMadeAt;
    String? summaryTrigger;
    RouteSummary? summary;
    if (routesRaw is Map) {
      routesRaw.forEach((k, v) {
        final key = k.toString();
        if (key.startsWith('_')) {
          if (key == '_summary' && v is Map) {
            final s = Map<String, dynamic>.from(v);
            summaryMadeAt = (s['made_at'] as num?)?.toInt();
            summaryTrigger = s['trigger'] as String?;
            final skipped = <String>[];
            final sk = s['skipped'];
            if (sk is List) {
              for (final x in sk) {
                if (x != null) skipped.add(x.toString());
              }
            }
            summary = RouteSummary(
              madeAt: summaryMadeAt,
              trigger: summaryTrigger,
              planned: (s['planned'] as num?)?.toInt(),
              totalKm: (s['total_km'] as num?)?.toDouble(),
              fuelL: (s['fuel_l'] as num?)?.toDouble(),
              costLkr: (s['cost_lkr'] as num?)?.toDouble(),
              replanSeconds: (s['replan_seconds'] as num?)?.toDouble(),
              roads: s['roads'] as String?,
              solver: s['solver'] as String?,
              skipped: skipped,
            );
          }
          return;
        }
        if (v is Map) routes[key] = Map<String, dynamic>.from(v);
      });
    }

    final trucks = <String, Map<String, dynamic>>{};
    if (trucksRaw is Map) {
      trucksRaw.forEach((k, v) {
        if (v is Map) trucks[k.toString()] = Map<String, dynamic>.from(v);
      });
    }

    final allIds = <String>{...routes.keys, ...trucks.keys}.toList()..sort();
    final out = <TruckRoute>[];
    for (final id in allIds) {
      final r = routes[id] ?? const <String, dynamic>{};
      final t = trucks[id] ?? const <String, dynamic>{};
      final stopsRaw = r['stops'];
      final stops = <RouteStop>[];
      if (stopsRaw is List) {
        for (final s in stopsRaw) {
          if (s is Map) {
            stops.add(RouteStop.fromMap(Map<String, dynamic>.from(s)));
          }
        }
      } else if (stopsRaw is Map) {
        final keys = stopsRaw.keys
            .map((k) => int.tryParse(k.toString()) ?? 0)
            .toList()
          ..sort();
        for (final i in keys) {
          final s = stopsRaw[i.toString()];
          if (s is Map) {
            stops.add(RouteStop.fromMap(Map<String, dynamic>.from(s)));
          }
        }
      }

      final pathRaw = r['path'];
      final path = <List<double>>[];
      if (pathRaw is List) {
        for (final p in pathRaw) {
          if (p is List && p.length >= 2) {
            final a = (p[0] as num?)?.toDouble();
            final b = (p[1] as num?)?.toDouble();
            if (a != null && b != null) path.add([a, b]);
          }
        }
      }

      out.add(TruckRoute(
        id: id,
        name: (r['truck'] as String?) ??
            (t['name'] as String?) ??
            id,
        status: (t['status'] as String?) ??
            (stops.isNotEmpty ? 'available' : 'at_depot'),
        truckLat: (t['lat'] as num?)?.toDouble(),
        truckLng: (t['lng'] as num?)?.toDouble(),
        stops: stops,
        km: (r['km'] as num?)?.toDouble(),
        minutes: (r['minutes'] as num?)?.toDouble(),
        note: r['note'] as String?,
        madeAt: (r['made_at'] as num?)?.toInt(),
        path: path,
      ));
    }

    final now = DateTime.now().millisecondsSinceEpoch;
    final traffic = <TrafficZone>[];
    if (trafficRaw is Map) {
      trafficRaw.forEach((k, v) {
        if (v is! Map) return;
        final m = Map<String, dynamic>.from(v);
        final lat = (m['lat'] as num?)?.toDouble();
        final lng = (m['lng'] as num?)?.toDouble();
        if (lat == null || lng == null) return;
        final until = (m['until'] as num?)?.toInt();
        if (until != null && until <= now) return;
        traffic.add(TrafficZone(
          id: k.toString(),
          kind: (m['kind'] as String?) ?? 'closure',
          lat: lat,
          lng: lng,
          radiusM: (m['radius_m'] as num?)?.toDouble() ?? 300,
          note: (m['note'] as String?) ?? '',
          until: until,
        ));
      });
    }

    return DayRoutes(
      date: day,
      trucks: out,
      summaryMadeAt: summaryMadeAt,
      summaryTrigger: summaryTrigger,
      summary: summary,
      traffic: traffic,
    );
  }

  /// Marks stop [index] as emptied. Matches data.mark_stop_done() in Flask:
  /// patches the done flag + done_at timestamp. For sim_* bins it also
  /// resets the live sensor data (so the next overview shows them empty).
  Future<void> markStopDone(String day, String truckId, int index) async {
    final now = DateTime.now().millisecondsSinceEpoch;
    await _db.patch('routes/$day/$truckId/stops/$index', {
      'done': true,
      'done_at': now,
    });

    // Find the stop so we know the bin id (same read-after-write as Python).
    final stopRaw = await _db.get('routes/$day/$truckId/stops/$index');
    if (stopRaw is! Map) return;
    final binId = (stopRaw['bin_id'] as String?) ?? '';
    if (binId.startsWith('sim_')) {
      await _db.patch('bins/$binId/latest', {
        'fill_pct': 2.0,
        'ts': now,
      });
      await _db.put('bins/$binId/last_collected', now);
      await _db.patch('predictions/$binId', {
        'current_fill_pct': 2.0,
        'predicted_fill_6h': 8.0,
        'overflow_risk': 'low',
        'urgency_score': 0,
        'based_on_ts': now + 1,
      });
    }
  }

  Future<void> setTruckStatus(String truckId, String status, String byUser) async {
    final now = DateTime.now().millisecondsSinceEpoch;
    await _db.patch('trucks/$truckId', {
      'status': status,
      'status_by': byUser,
      'status_ts': now,
    });
  }

  Future<void> addTraffic({
    required String kind,
    required double lat,
    required double lng,
    required String byUser,
  }) async {
    final now = DateTime.now().millisecondsSinceEpoch;
    await _db.post('traffic', {
      'kind': kind,
      'lat': double.parse(lat.toStringAsFixed(6)),
      'lng': double.parse(lng.toStringAsFixed(6)),
      'radius_m': 300,
      'note': (kind == 'closure' ? 'road closed' : 'traffic jam') + ' (mobile app)',
      'created_at': FirebaseRest.serverTimestamp(),
      'until': now + 3 * 3600000,
      'by': byUser,
    });
  }

  Future<void> clearTraffic([String? id]) async {
    await _db.delete(id == null ? 'traffic' : 'traffic/$id');
  }

  Future<void> requestReplan() async {
    await _db.put('control/replan', FirebaseRest.serverTimestamp());
  }
}
