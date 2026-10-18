/// Citizen report, matches /reports/<key> in Firebase (see data.REPORT_TYPES).
class CitizenReport {
  final String id;
  final String type;        // overflowing_bin | illegal_dumping | damaged_bin | other
  final String note;
  final String status;      // new | in_progress | resolved
  final String? binId;
  final String? zone;
  final int? ts;
  final double? lat;
  final double? lng;
  final bool hasPhoto;
  final int? points;        // filled in by the rewards job
  final String? pointsNote;
  final String user;
  final String reporterName;

  const CitizenReport({
    required this.id,
    required this.type,
    required this.note,
    required this.status,
    required this.binId,
    required this.zone,
    required this.ts,
    required this.lat,
    required this.lng,
    required this.hasPhoto,
    required this.points,
    required this.pointsNote,
    this.user = '',
    this.reporterName = '',
  });

  factory CitizenReport.fromMap(String id, Map<String, dynamic> m) {
    double? n(dynamic v) {
      if (v == null || v is bool) return null;
      if (v is num) return v.toDouble();
      return double.tryParse(v.toString());
    }

    return CitizenReport(
      id: id,
      type: (m['type'] as String?) ?? 'other',
      note: (m['note'] as String?) ?? '',
      status: (m['status'] as String?) ?? 'new',
      binId: m['bin_id'] as String?,
      zone: m['zone'] as String?,
      ts: n(m['ts'])?.toInt(),
      lat: n(m['lat']),
      lng: n(m['lng']),
      hasPhoto: (m['has_photo'] as bool?) ?? (m['photo'] != null),
      points: n(m['points'])?.toInt(),
      pointsNote: m['points_note'] as String?,
      user: (m['user'] as String?) ?? '',
      reporterName: (m['name'] as String?) ?? (m['user'] as String?) ?? '',
    );
  }
}

const Map<String, String> kReportTypeLabels = {
  'overflowing_bin': 'Overflowing bin',
  'illegal_dumping': 'Illegal dumping',
  'damaged_bin': 'Damaged bin',
  'other': 'Other problem',
};
