import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:image/image.dart' as img;
import 'package:image_picker/image_picker.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../../models/bin.dart';
import '../../models/report.dart';
import '../../services/bin_service.dart';
import '../../services/firebase_rest.dart';
import '../../services/location_service.dart';
import '../../services/session.dart';

/// Citizen "Report a problem" page.
///
/// Posts a document under /reports/<auto-id> in Firebase. The rewards job
/// (e1_rewards.py) picks it up and awards points once it is resolved.
class CitizenReportScreen extends StatefulWidget {
  const CitizenReportScreen({super.key});
  @override
  State<CitizenReportScreen> createState() => _CitizenReportScreenState();
}

class _CitizenReportScreenState extends State<CitizenReportScreen> {
  String _type = 'overflowing_bin';
  String? _binId;
  final _note = TextEditingController();
  Uint8List? _photo;
  double? _lat, _lng;
  bool _busy = false;
  String? _msg;
  List<BinRow> _bins = [];
  Future<List<CitizenReport>>? _myReports;

  @override
  void initState() {
    super.initState();
    _loadBins();
    _loadMyReports();
    _grabLocation();
  }

  Future<void> _loadBins() async {
    try {
      final rows = await BinService.instance.loadAll();
      if (!mounted) return;
      setState(() {
        _bins = rows.where((b) => b.lat != null).toList();
        _binId ??= _bins.isNotEmpty ? _bins.first.id : null;
      });
    } catch (_) {}
  }

  Future<void> _grabLocation() async {
    try {
      final pos = await LocationService.instance.current();
      if (!mounted || pos == null) return;
      setState(() {
        _lat = pos.latitude;
        _lng = pos.longitude;
      });
    } catch (_) {
      // ignore; location is optional for a report
    }
  }

  void _loadMyReports() {
    final user = Session.instance.user;
    if (user == null) return;
    _myReports = _fetchMyReports(user.username);
    setState(() {});
  }

  Future<List<CitizenReport>> _fetchMyReports(String username) async {
    final raw = await FirebaseRest.instance.get('reports');
    final rows = <CitizenReport>[];
    if (raw is Map) {
      raw.forEach((k, v) {
        if (v is Map && v['user'] == username) {
          rows.add(CitizenReport.fromMap(k.toString(),
              Map<String, dynamic>.from(v)));
        }
      });
    }
    rows.sort((a, b) => (b.ts ?? 0).compareTo(a.ts ?? 0));
    return rows.take(10).toList();
  }

  Future<void> _pickPhoto(ImageSource source) async {
    final picker = ImagePicker();
    final x = await picker.pickImage(
        source: source, maxWidth: 1024, maxHeight: 1024, imageQuality: 70);
    if (x == null) return;
    final bytes = await x.readAsBytes();
    setState(() => _photo = bytes);
  }

  Future<String?> _photoAsBase64() async {
    if (_photo == null) return null;
    final decoded = img.decodeImage(_photo!);
    if (decoded == null) return null;
    final resized = decoded.width > 1024
        ? img.copyResize(decoded, width: 1024)
        : decoded;
    final jpeg = img.encodeJpg(resized, quality: 70);
    final b64 = base64Encode(jpeg);
    // The Flask /api/reports endpoint rejects photos over 600_000 chars.
    if (b64.length > 580000) return null;
    return 'data:image/jpeg;base64,$b64';
  }

  Future<void> _submit() async {
    final user = context.read<Session>().user;
    if (user == null) return;
    setState(() {
      _busy = true;
      _msg = null;
    });
    try {
      if (_type == 'overflowing_bin' && (_binId == null || _binId!.isEmpty)) {
        throw 'Choose the bin that is overflowing.';
      }
      final photoB64 = await _photoAsBase64();
      final report = <String, dynamic>{
        'user': user.username,
        'name': user.name,
        'type': _type,
        'ts': FirebaseRest.serverTimestamp(),
        'note': _note.text.trim(),
        'status': 'new',
        'source': 'mobile app',
      };
      if (_binId != null && _binId!.isNotEmpty) {
        report['bin_id'] = _binId;
        final b = _bins.firstWhere(
          (x) => x.id == _binId,
          orElse: () => _bins.isEmpty ? _dummy() : _bins.first,
        );
        if (b.zone.isNotEmpty) report['zone'] = b.zone;
      }
      if (_lat != null && _lng != null) {
        report['lat'] = double.parse(_lat!.toStringAsFixed(6));
        report['lng'] = double.parse(_lng!.toStringAsFixed(6));
      }
      if (photoB64 != null) report['has_photo'] = true;

      final key = await FirebaseRest.instance.post('reports', report);
      if (photoB64 != null) {
        await FirebaseRest.instance.put('report_photos/$key', photoB64);
      }

      if (!mounted) return;
      setState(() {
        _note.clear();
        _photo = null;
        _msg = 'Thanks! Your report has been sent.';
      });
      _loadMyReports();
    } catch (e) {
      setState(() => _msg = 'Could not send: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  BinRow _dummy() => BinRow(
        id: '', name: '', zone: '', type: '',
        lat: null, lng: null, fill: null, pred: null, weightKg: null,
        gasIndex: null, tempC: null, humidity: null, batteryPct: null,
        ts: null, lastCollected: null, synthetic: false,
      );

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('What is the problem?',
              style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          DropdownButtonFormField<String>(
            value: _type,
            isExpanded: true,
            items: [
              for (final e in kReportTypeLabels.entries)
                DropdownMenuItem(
                  value: e.key,
                  child: Text(e.value, overflow: TextOverflow.ellipsis),
                ),
            ],
            onChanged: (v) => setState(() => _type = v ?? 'overflowing_bin'),
          ),
          const SizedBox(height: 12),
          if (_type == 'overflowing_bin')
            DropdownButtonFormField<String>(
              value: _binId,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'Which bin?'),
              items: [
                for (final b in _bins)
                  DropdownMenuItem(
                    value: b.id,
                    child: Text(
                      '${b.name} (${b.id})',
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
              ],
              onChanged: (v) => setState(() => _binId = v),
            ),
          if (_type == 'overflowing_bin') const SizedBox(height: 12),
          TextField(
            controller: _note,
            minLines: 2,
            maxLines: 4,
            maxLength: 500,
            decoration: const InputDecoration(
                labelText: 'Note (optional)',
                hintText: 'A few words about what happened'),
          ),
          const SizedBox(height: 12),
          _PhotoRow(file: _photo, onPick: _pickPhoto),
          const SizedBox(height: 12),
          Row(
            children: [
              const Icon(Icons.place),
              const SizedBox(width: 8),
              Expanded(
                child: Text(_lat != null
                    ? 'Location: ${_lat!.toStringAsFixed(5)}, ${_lng!.toStringAsFixed(5)}'
                    : 'Location not available (optional)'),
              ),
              TextButton(onPressed: _grabLocation, child: const Text('Refresh')),
            ],
          ),
          if (_msg != null) ...[
            const SizedBox(height: 12),
            Text(_msg!,
                style: TextStyle(
                    color: _msg!.startsWith('Thanks')
                        ? Colors.green
                        : Colors.red)),
          ],
          const SizedBox(height: 16),
          FilledButton.icon(
            onPressed: _busy ? null : _submit,
            icon: _busy
                ? const SizedBox(
                    height: 20,
                    width: 20,
                    child: CircularProgressIndicator(
                        strokeWidth: 2, color: Colors.white))
                : const Icon(Icons.send),
            label: Text(_busy ? 'Sending...' : 'Send report'),
          ),
          const Divider(height: 32),
          Text('My recent reports',
              style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          FutureBuilder<List<CitizenReport>>(
            future: _myReports,
            builder: (ctx, snap) {
              if (snap.connectionState != ConnectionState.done) {
                return const Padding(
                  padding: EdgeInsets.all(16),
                  child: Center(child: CircularProgressIndicator()),
                );
              }
              final rows = snap.data ?? const <CitizenReport>[];
              if (rows.isEmpty) {
                return const Text('No reports yet.');
              }
              return Column(
                children: [
                  for (final r in rows) _ReportTile(r: r),
                ],
              );
            },
          ),
        ],
      ),
    );
  }
}

class _PhotoRow extends StatelessWidget {
  final Uint8List? file;
  final Future<void> Function(ImageSource) onPick;
  const _PhotoRow({required this.file, required this.onPick});
  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (file != null)
          ClipRRect(
            borderRadius: BorderRadius.circular(8),
            child: Image.memory(file!, height: 160, fit: BoxFit.cover),
          ),
        if (file != null) const SizedBox(height: 8),
        Row(
          children: [
            Expanded(
              child: OutlinedButton.icon(
                onPressed: () => onPick(ImageSource.camera),
                icon: const Icon(Icons.photo_camera),
                label: const Text('Camera'),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: OutlinedButton.icon(
                onPressed: () => onPick(ImageSource.gallery),
                icon: const Icon(Icons.photo_library),
                label: const Text('Gallery'),
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class _ReportTile extends StatelessWidget {
  final CitizenReport r;
  const _ReportTile({required this.r});
  @override
  Widget build(BuildContext context) {
    final label = kReportTypeLabels[r.type] ?? r.type;
    final when = r.ts == null
        ? ''
        : DateFormat('yyyy-MM-dd HH:mm')
            .format(DateTime.fromMillisecondsSinceEpoch(r.ts!));
    Color colour() {
      switch (r.status) {
        case 'resolved':
          return Colors.green;
        case 'in_progress':
          return Colors.orange;
        default:
          return Colors.grey;
      }
    }

    return Card(
      child: ListTile(
        leading: Icon(Icons.report, color: colour()),
        title: Text(label),
        subtitle: Text([
          r.status.replaceAll('_', ' '),
          if (r.binId != null) r.binId!,
          if (when.isNotEmpty) when,
          if (r.points != null) '+${r.points} pts',
        ].join(' \u00B7 ')),
      ),
    );
  }
}
