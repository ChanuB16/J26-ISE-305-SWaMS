/// Officer-side reads/writes that sit on top of Firebase (same tree as Flask).
library;

import '../config.dart';
import '../models/bin.dart';
import '../models/report.dart';
import '../models/route.dart';
import 'firebase_rest.dart';

class OfficerAlert {
  final String level; // critical | warning | serious | info
  final String? binId;
  final String title;
  final String text;
  const OfficerAlert({
    required this.level,
    this.binId,
    required this.title,
    required this.text,
  });
}

class OfficerKpis {
  final int total;
  final int real;
  final int critical;
  final int warning;
  final int filling;
  final int normal;
  final int highRisk;
  final double? avgFill;
  final int trucksTotal;
  final int trucksOnRoute;
  final int trucksBroken;
  const OfficerKpis({
    required this.total,
    required this.real,
    required this.critical,
    required this.warning,
    required this.filling,
    required this.normal,
    required this.highRisk,
    required this.avgFill,
    required this.trucksTotal,
    required this.trucksOnRoute,
    required this.trucksBroken,
  });
}

class ForecastDay {
  final String date;
  final String label;
  final double forecast;
  final double normal;
  final double change;
  final List<String> busy;
  final String holiday;
  final double? rainMm;
  const ForecastDay({
    required this.date,
    required this.label,
    required this.forecast,
    required this.normal,
    required this.change,
    required this.busy,
    required this.holiday,
    this.rainMm,
  });
}

class ForecastData {
  final List<String> zones;
  final List<String> days;
  final List<ForecastDay> totals;
  final Map<String, Map<String, Map<String, dynamic>>> byZone;
  final String model;
  final Map<String, List<String>> guidance;
  const ForecastData({
    required this.zones,
    required this.days,
    required this.totals,
    required this.byZone,
    required this.model,
    required this.guidance,
  });
}

class RewardUser {
  final String username;
  final int points;
  final String level;
  const RewardUser({
    required this.username,
    required this.points,
    required this.level,
  });
}

class ScanPhoto {
  final String id;
  final String wasteType;
  final double? confidence;
  final String user;
  final int? ts;
  const ScanPhoto({
    required this.id,
    required this.wasteType,
    required this.confidence,
    required this.user,
    required this.ts,
  });
}

class CommunityData {
  final List<CitizenReport> reports;
  final List<RewardUser> users;
  final List<ScanPhoto> photos;
  const CommunityData({
    required this.reports,
    required this.users,
    required this.photos,
  });
}

class BinReading {
  final int ts;
  final double? fillPct;
  final double? weightKg;
  final double? gasIndex;
  final double? tempC;
  final double? humidity;
  final double? batteryPct;
  const BinReading({
    required this.ts,
    this.fillPct,
    this.weightKg,
    this.gasIndex,
    this.tempC,
    this.humidity,
    this.batteryPct,
  });
}

class OfficerService {
  OfficerService._();
  static final OfficerService instance = OfficerService._();

  final _db = FirebaseRest.instance;

  OfficerKpis kpis(List<BinRow> rows, List<TruckRoute> trucks) {
    final withFill = rows.where((r) => r.fill != null).toList();
    return OfficerKpis(
      total: rows.length,
      real: rows.where((r) => !r.synthetic).length,
      critical: withFill.where((r) => r.fill! >= AppConfig.overflowPct).length,
      warning: withFill
          .where((r) =>
              r.fill! >= AppConfig.alertPct && r.fill! < AppConfig.overflowPct)
          .length,
      filling: withFill
          .where((r) =>
              r.fill! >= AppConfig.fillingPct && r.fill! < AppConfig.alertPct)
          .length,
      normal: withFill.where((r) => r.fill! < AppConfig.fillingPct).length,
      highRisk: rows.where((r) => r.risk == 'high').length,
      avgFill: withFill.isEmpty
          ? null
          : withFill.fold<double>(0, (s, r) => s + r.fill!) / withFill.length,
      trucksTotal: trucks.length,
      trucksOnRoute: trucks.where((t) => t.status == 'on_route').length,
      trucksBroken: trucks.where((t) => t.status == 'broken').length,
    );
  }

  List<OfficerAlert> alerts(
      List<BinRow> rows, List<ForecastDay> fcDays, List<TruckRoute> trucks) {
    final out = <OfficerAlert>[];
    for (final r in rows) {
      final name = r.name != r.id ? '${r.id} (${r.name})' : r.id;
      if (r.fill != null && r.fill! >= AppConfig.overflowPct) {
        out.add(OfficerAlert(
          level: 'critical',
          binId: r.id,
          title: '$name is full',
          text:
              '${r.fill!.toStringAsFixed(0)}% full now. Collect it as soon as possible.',
        ));
      } else if (r.risk == 'high' ||
          (r.pred != null && r.pred! >= AppConfig.overflowPct)) {
        final h = r.hoursToFull;
        final when = (h != null && h < 48)
            ? 'in about ${h.toStringAsFixed(1)} hours'
            : 'within 6 hours';
        out.add(OfficerAlert(
          level: 'warning',
          binId: r.id,
          title: '$name will overflow $when',
          text:
              'ML prediction: ${r.pred?.toStringAsFixed(0) ?? "?"}% in 6 hours (now ${r.fill?.toStringAsFixed(0) ?? 0}%).',
        ));
      } else if (r.fill != null && r.fill! >= AppConfig.alertPct) {
        out.add(OfficerAlert(
          level: 'serious',
          binId: r.id,
          title: '$name is nearly full',
          text: '${r.fill!.toStringAsFixed(0)}% full now.',
        ));
      }
      if (r.gasIndex != null &&
          r.gasIndex! >= AppConfig.smellIndex &&
          r.gasReady != false) {
        out.add(OfficerAlert(
          level: 'serious',
          binId: r.id,
          title: 'Strong smell at $name',
          text:
              'Gas index ${r.gasIndex!.toStringAsFixed(0)} (limit ${AppConfig.smellIndex}). Food waste may be rotting.',
        ));
      }
      if (!r.synthetic) {
        if (r.stale) {
          out.add(OfficerAlert(
            level: 'info',
            binId: r.id,
            title: 'No data from $name',
            text:
                'No reading for more than ${AppConfig.noDataMinutes} minutes. Check power and WiFi.',
          ));
        }
        if (r.batteryPct != null && r.batteryPct! < AppConfig.lowBatteryPct) {
          out.add(OfficerAlert(
            level: 'serious',
            binId: r.id,
            title: 'Low battery at $name',
            text:
                'Battery ${r.batteryPct}% (${r.batteryV?.toStringAsFixed(2) ?? "?"} V). Charge it.',
          ));
        }
        for (final e in r.errors) {
          out.add(OfficerAlert(
            level: 'info',
            binId: r.id,
            title: 'Sensor problem at $name',
            text: e,
          ));
        }
      }
    }
    for (final d in fcDays) {
      if (d.busy.isNotEmpty) {
        out.add(OfficerAlert(
          level: 'info',
          title: 'Busy day ${d.label}: ${d.busy.join(", ")}',
          text:
              'Forecast ${d.forecast.toStringAsFixed(1)} t in all areas (${d.change >= 0 ? "+" : ""}${d.change.toStringAsFixed(0)}% vs a normal day).${d.holiday.isNotEmpty ? " ${d.holiday}." : ""}',
        ));
      }
    }
    for (final t in trucks) {
      if (t.status == 'broken') {
        out.add(OfficerAlert(
          level: 'critical',
          title: '${t.name} is broken',
          text:
              'Its bins were moved to the other trucks by the route planner (if it is running).',
        ));
      }
    }
    const order = {'critical': 0, 'warning': 1, 'serious': 2, 'info': 3};
    out.sort((a, b) => (order[a.level] ?? 9).compareTo(order[b.level] ?? 9));
    return out;
  }

  Future<ForecastData> loadForecast() async {
    final keys = await _db.get('forecasts', shallow: true);
    final info = await _db.get('forecasts/_info');
    final zones = <String>[];
    if (keys is Map) {
      for (final k in keys.keys) {
        final s = k.toString();
        if (!s.startsWith('_')) zones.add(s);
      }
    }
    zones.sort();
    final today = DateTime.now();
    final start =
        DateTime(today.year, today.month, today.day).toIso8601String().substring(0, 10);
    final byZone = <String, Map<String, Map<String, dynamic>>>{};
    for (final z in zones) {
      final raw = await _db.get('forecasts/$z');
      final days = <String, Map<String, dynamic>>{};
      if (raw is Map) {
        raw.forEach((k, v) {
          final d = k.toString();
          if (d.compareTo(start) < 0 || v is! Map) return;
          days[d] = Map<String, dynamic>.from(v);
        });
      }
      byZone[z] = days;
    }
    final daySet = <String>{};
    for (final z in byZone.values) {
      daySet.addAll(z.keys);
    }
    final days = daySet.toList()..sort();
    final week = days.take(7).toList();
    final totals = <ForecastDay>[];
    for (final d in week) {
      var t = 0.0, n = 0.0;
      final busy = <String>[];
      var hol = '';
      double? rain;
      for (final z in zones) {
        final f = byZone[z]?[d];
        if (f == null) continue;
        t += (f['forecast_t'] as num?)?.toDouble() ?? 0;
        n += (f['normal_t'] as num?)?.toDouble() ?? 0;
        if (f['high_waste'] == true) busy.add(z);
        if ((f['holiday'] as String?)?.isNotEmpty == true) {
          hol = f['holiday'] as String;
        }
        final r = (f['rain_mm'] as num?)?.toDouble();
        if (r != null) rain = r;
      }
      totals.add(ForecastDay(
        date: d,
        label: _dayLabel(d),
        forecast: double.parse(t.toStringAsFixed(2)),
        normal: double.parse(n.toStringAsFixed(2)),
        change: n == 0 ? 0 : double.parse(((t - n) / n * 100).toStringAsFixed(1)),
        busy: busy,
        holiday: hol,
        rainMm: rain,
      ));
    }

    final guidance = <String, List<String>>{};
    final gRaw = await _db.get('guidance');
    if (gRaw is Map) {
      gRaw.forEach((k, v) {
        final d = k.toString();
        if (d.startsWith('_') || d.compareTo(start) < 0 || v is! Map) return;
        final tips = <String>[];
        v.forEach((zone, tip) {
          if (tip is List) {
            for (final x in tip) {
              tips.add('${zone.toString()}: $x');
            }
          } else if (tip is Map) {
            for (final x in tip.values) {
              tips.add('${zone.toString()}: $x');
            }
          } else if (tip != null) {
            tips.add('${zone.toString()}: $tip');
          }
        });
        if (tips.isNotEmpty) guidance[d] = tips;
      });
    }

    final model = (info is Map ? info['model'] as String? : null) ?? '';
    return ForecastData(
      zones: zones,
      days: week,
      totals: totals,
      byZone: byZone,
      model: model,
      guidance: guidance,
    );
  }

  Future<CommunityData> loadCommunity() async {
    final rewards = await _db.get('rewards');
    final reports = await _db.get('reports');
    final photos = await _db.get('classifications');

    String levelName(int pts) {
      var name = AppConfig.rewardLevels.first.value;
      for (final lv in AppConfig.rewardLevels) {
        if (pts >= lv.key) name = lv.value;
      }
      return name;
    }

    final users = <RewardUser>[];
    if (rewards is Map) {
      rewards.forEach((k, v) {
        if (k.toString().startsWith('_') || v is! Map) return;
        final pts = (v['points'] as num?)?.toInt() ?? 0;
        users.add(RewardUser(
          username: k.toString(),
          points: pts,
          level: levelName(pts),
        ));
      });
    }
    users.sort((a, b) => b.points.compareTo(a.points));

    final reps = <CitizenReport>[];
    if (reports is Map) {
      reports.forEach((k, v) {
        if (v is Map) {
          reps.add(CitizenReport.fromMap(k.toString(), Map<String, dynamic>.from(v)));
        }
      });
    }
    reps.sort((a, b) => (b.ts ?? 0).compareTo(a.ts ?? 0));

    final ph = <ScanPhoto>[];
    if (photos is Map) {
      photos.forEach((k, v) {
        if (v is! Map) return;
        ph.add(ScanPhoto(
          id: k.toString(),
          wasteType: (v['waste_type'] as String?) ?? '?',
          confidence: (v['confidence'] as num?)?.toDouble(),
          user: (v['user'] as String?) ?? '',
          ts: (v['ts'] as num?)?.toInt(),
        ));
      });
    }
    ph.sort((a, b) => (b.ts ?? 0).compareTo(a.ts ?? 0));

    return CommunityData(reports: reps, users: users, photos: ph);
  }

  Future<void> setReportStatus(String id, String status, String by) async {
    await _db.patch('reports/$id', {
      'status': status,
      'status_by': by,
      'status_ts': DateTime.now().millisecondsSinceEpoch,
    });
  }

  Future<String?> reportPhoto(String id) async {
    final raw = await _db.get('report_photos/$id');
    return raw is String ? raw : null;
  }

  Future<List<BinReading>> recentReadings(String binId) async {
    final raw = await _db.get('bins/$binId/readings',
        orderBy: r'$key', limitToLast: 80);
    final out = <BinReading>[];
    if (raw is Map) {
      raw.forEach((k, v) {
        if (v is! Map) return;
        final m = Map<String, dynamic>.from(v);
        final ts = (m['ts'] as num?)?.toInt() ?? int.tryParse(k.toString());
        if (ts == null) return;
        double? n(dynamic x) => x is num ? x.toDouble() : null;
        out.add(BinReading(
          ts: ts,
          fillPct: n(m['fill_pct']),
          weightKg: n(m['weight_kg']),
          gasIndex: n(m['gas_index']),
          tempC: n(m['temp_c']),
          humidity: n(m['humidity_pct']),
          batteryPct: n(m['battery_pct']),
        ));
      });
    }
    out.sort((a, b) => b.ts.compareTo(a.ts));
    return out;
  }

  Future<Map<String, dynamic>?> device(String binId) async {
    final raw = await _db.get('bins/$binId/device');
    return raw is Map ? Map<String, dynamic>.from(raw) : null;
  }

  List<Map<String, dynamic>> urgencyParts(BinRow row) {
    final fill = row.pred ?? row.fill ?? 0;
    final gas = row.gasReady == false ? 0.0 : (row.gasIndex ?? 0);
    final hum = row.humidity ?? 0;
    final tsc = row.hoursSince == null
        ? 0.0
        : (row.hoursSince! / AppConfig.fullTimeHours * 100).clamp(0.0, 100.0);
    return [
      {
        'label': row.pred != null ? 'Predicted fill in 6 h' : 'Fill now',
        'value': fill,
        'weight': AppConfig.wFill,
      },
      {
        'label': 'Gas / smell index',
        'value': gas,
        'weight': AppConfig.wGas,
      },
      {
        'label': 'Humidity',
        'value': hum,
        'weight': AppConfig.wHumidity,
      },
      {
        'label': 'Time since emptied',
        'value': tsc,
        'weight': AppConfig.wTime,
      },
    ]
        .map((p) => {
              ...p,
              'points': ((p['value'] as num) * (p['weight'] as num)).toDouble(),
            })
        .toList();
  }

  static String _dayLabel(String iso) {
    try {
      final d = DateTime.parse(iso);
      const names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
      const months = [
        'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'
      ];
      return '${names[d.weekday - 1]} ${d.day} ${months[d.month - 1]}';
    } catch (_) {
      return iso;
    }
  }
}
