import 'package:intl/intl.dart';

String timeAgo(int? ms) {
  if (ms == null) return '-';
  final d = DateTime.now().difference(DateTime.fromMillisecondsSinceEpoch(ms));
  if (d.inMinutes < 1) return 'just now';
  if (d.inMinutes < 60) return '${d.inMinutes} min ago';
  if (d.inHours < 24) return '${d.inHours} h ago';
  return '${d.inDays} d ago';
}

String hhmm(int? ms) {
  if (ms == null) return '-';
  return DateFormat('HH:mm').format(DateTime.fromMillisecondsSinceEpoch(ms));
}

String dayLabel(String iso) {
  try {
    return DateFormat('EEE d MMM').format(DateTime.parse(iso));
  } catch (_) {
    return iso;
  }
}

String pct(double? v) => v == null ? '-' : '${v.toStringAsFixed(0)}%';

String hoursLabel(double? h) {
  if (h == null) return '-';
  if (h < 1) return 'under 1 h';
  if (h < 48) return 'in about ${h.toStringAsFixed(1)} h';
  return 'in ${h.toStringAsFixed(0)} h';
}
