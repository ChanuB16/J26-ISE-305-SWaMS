/// Data model for a route document stored at /routes/<day>/<truck_id>.
///
/// Equivalent of what data.routes() returns in the Flask backend.
library;

class RouteStop {
  final String binId;
  final String name;
  final double? lat;
  final double? lng;
  final double? fillPct;
  final String eta; // "HH:MM" or ""
  final bool done;
  final int? doneAt;

  const RouteStop({
    required this.binId,
    required this.name,
    required this.lat,
    required this.lng,
    required this.fillPct,
    required this.eta,
    required this.done,
    required this.doneAt,
  });

  factory RouteStop.fromMap(Map<String, dynamic> m) {
    double? n(dynamic v) {
      if (v == null || v is bool) return null;
      if (v is num) return v.toDouble();
      return double.tryParse(v.toString());
    }

    return RouteStop(
      binId: (m['bin_id'] as String?) ?? '',
      name: (m['name'] as String?) ?? '',
      lat: n(m['lat']),
      lng: n(m['lng']),
      fillPct: n(m['fill_pct']),
      eta: (m['eta'] as String?) ?? '',
      done: (m['done'] as bool?) ?? false,
      doneAt: n(m['done_at'])?.toInt(),
    );
  }
}

class TruckRoute {
  final String id;
  final String name;
  final String status; // available | on_route | at_depot | broken
  final double? truckLat;
  final double? truckLng;
  final List<RouteStop> stops;
  final double? km;
  final double? minutes;
  final String? note;
  final int? madeAt;
  final List<List<double>> path; // list of [lat, lng]

  const TruckRoute({
    required this.id,
    required this.name,
    required this.status,
    required this.truckLat,
    required this.truckLng,
    required this.stops,
    required this.km,
    required this.minutes,
    required this.note,
    required this.madeAt,
    required this.path,
  });

  int get doneCount => stops.where((s) => s.done).length;
  int get nextIndex => stops.indexWhere((s) => !s.done);
}

class TrafficZone {
  final String id;
  final String kind; // closure | jam
  final double lat;
  final double lng;
  final double radiusM;
  final String note;
  final int? until;

  const TrafficZone({
    required this.id,
    required this.kind,
    required this.lat,
    required this.lng,
    required this.radiusM,
    required this.note,
    required this.until,
  });
}

class RouteSummary {
  final int? madeAt;
  final String? trigger;
  final int? planned;
  final double? totalKm;
  final double? fuelL;
  final double? costLkr;
  final double? replanSeconds;
  final String? roads;
  final String? solver;
  final List<String> skipped;

  const RouteSummary({
    this.madeAt,
    this.trigger,
    this.planned,
    this.totalKm,
    this.fuelL,
    this.costLkr,
    this.replanSeconds,
    this.roads,
    this.solver,
    this.skipped = const [],
  });
}

class DayRoutes {
  final String date;
  final List<TruckRoute> trucks;
  final int? summaryMadeAt;
  final String? summaryTrigger;
  final RouteSummary? summary;
  final List<TrafficZone> traffic;

  const DayRoutes({
    required this.date,
    required this.trucks,
    required this.summaryMadeAt,
    required this.summaryTrigger,
    this.summary,
    this.traffic = const [],
  });
}
