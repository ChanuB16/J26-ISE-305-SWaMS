/// Reads /bins and /predictions from Firebase and produces [BinRow] rows
/// in the same shape the Flask backend uses (data.bins()).
library;

import '../models/bin.dart';
import '../utils/distance.dart';
import 'firebase_rest.dart';

class BinService {
  BinService._();
  static final BinService instance = BinService._();

  final _db = FirebaseRest.instance;

  Future<List<BinRow>> loadAll() async {
    final keysResp = await _db.get('bins', shallow: true);
    final preds = (await _db.get('predictions')) as Map? ?? {};
    final keys = <String>{};
    if (keysResp is Map) {
      for (final k in keysResp.keys) {
        final s = k.toString();
        if (!s.startsWith('_')) keys.add(s);
      }
    }
    for (final k in preds.keys) {
      final s = k.toString();
      if (!s.startsWith('_')) keys.add(s);
    }

    final rows = <BinRow>[];
    for (final id in keys) {
      Map<String, dynamic>? info;
      Map<String, dynamic>? latest;
      dynamic lastCollected;
      // skip reads when the key is predictions-only
      final infoResp = await _db.get('bins/$id/info');
      if (infoResp is Map) {
        info = Map<String, dynamic>.from(infoResp);
      }
      final latestResp = await _db.get('bins/$id/latest');
      if (latestResp is Map) {
        latest = Map<String, dynamic>.from(latestResp);
      }
      lastCollected = await _db.get('bins/$id/last_collected');
      final predRaw = preds[id];
      final pred = predRaw is Map ? Map<String, dynamic>.from(predRaw) : null;
      rows.add(BinRow.fromFirebase(id, info, latest, pred, lastCollected));
    }
    rows.sort((a, b) {
      final ua = a.urgency ?? -1;
      final ub = b.urgency ?? -1;
      if (ub != ua) return ub.compareTo(ua);
      final fa = a.fill ?? -1;
      final fb = b.fill ?? -1;
      return fb.compareTo(fa);
    });
    return rows;
  }

  /// Nearest bin with [fill] < spaceLimitPct, within [maxKm].
  BinRow? nearestWithSpace(
      List<BinRow> rows, double lat, double lng, double maxKm) {
    BinRow? best;
    double bestKm = double.infinity;
    for (final r in rows) {
      if (r.lat == null || r.lng == null) continue;
      if (!r.hasSpace) continue;
      final d = distanceKm(lat, lng, r.lat!, r.lng!);
      if (d < bestKm && d <= maxKm) {
        bestKm = d;
        best = r;
      }
    }
    return best;
  }

  /// All bins sorted by distance (ascending), closest first.
  List<MapEntry<BinRow, double>> sortByDistance(
      List<BinRow> rows, double lat, double lng) {
    final out = <MapEntry<BinRow, double>>[];
    for (final r in rows) {
      if (r.lat == null || r.lng == null) continue;
      out.add(MapEntry(r, distanceKm(lat, lng, r.lat!, r.lng!)));
    }
    out.sort((a, b) => a.value.compareTo(b.value));
    return out;
  }
}
