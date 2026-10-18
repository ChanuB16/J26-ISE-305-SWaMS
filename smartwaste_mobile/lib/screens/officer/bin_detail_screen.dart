import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../models/bin.dart';
import '../../services/bin_service.dart';
import '../../services/officer_service.dart';
import '../../theme.dart';
import '../../utils/format.dart';
import '../../widgets/common.dart';

class BinDetailScreen extends StatefulWidget {
  final String binId;
  const BinDetailScreen({super.key, required this.binId});
  @override
  State<BinDetailScreen> createState() => _BinDetailScreenState();
}

class _BinDetailScreenState extends State<BinDetailScreen> {
  BinRow? _bin;
  Map<String, dynamic>? _device;
  List<BinReading> _readings = const [];
  String? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  Future<void> _reload() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final rows = await BinService.instance.loadAll();
      BinRow? bin;
      for (final r in rows) {
        if (r.id == widget.binId) bin = r;
      }
      if (bin == null) throw Exception('There is no bin called ${widget.binId}.');
      final device = await OfficerService.instance.device(widget.binId);
      final readings = await OfficerService.instance.recentReadings(widget.binId);
      if (!mounted) return;
      setState(() {
        _bin = bin;
        _device = device;
        _readings = readings;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = '$e';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('Bin ${widget.binId}')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? ErrorRetry(message: _error!, onRetry: _reload)
              : _body(),
    );
  }

  Widget _body() {
    final b = _bin!;
    final parts = OfficerService.instance.urgencyParts(b);
    return RefreshIndicator(
      onRefresh: _reload,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Row(
            children: [
              LevelChip(level: b.level, extra: '${pct(b.fill)} now'),
              const SizedBox(width: 8),
              RiskChip(risk: b.risk),
            ],
          ),
          const SizedBox(height: 8),
          Text(b.name, style: Theme.of(context).textTheme.headlineSmall),
          Text([
            if (b.zone.isNotEmpty) b.zone,
            if (b.type.isNotEmpty) b.type,
            if (b.synthetic) 'demo bin',
          ].join(' · ')),
          const SizedBox(height: 12),
          Wrap(
            spacing: 12,
            runSpacing: 8,
            children: [
              _stat('Fill now', pct(b.fill)),
              _stat('In 6 hours', pct(b.pred)),
              _stat('Urgency', b.urgency?.toStringAsFixed(0) ?? '-'),
              _stat('Full', hoursLabel(b.hoursToFull)),
              _stat('Weight',
                  b.weightKg == null ? '-' : '${b.weightKg!.toStringAsFixed(2)} kg'),
              _stat('Gas', b.gasIndex?.toStringAsFixed(0) ?? '-'),
              _stat('Temp',
                  b.tempC == null ? '-' : '${b.tempC!.toStringAsFixed(1)} °C'),
              _stat('Humidity',
                  b.humidity == null ? '-' : '${b.humidity!.toStringAsFixed(0)}%'),
              _stat('Battery',
                  b.batteryPct == null ? '-' : '${b.batteryPct}%'),
              _stat('Last reading', timeAgo(b.ts)),
              _stat('Last emptied', timeAgo(b.lastCollected)),
            ],
          ),
          if (b.lat != null && b.lng != null) ...[
            const SizedBox(height: 12),
            OutlinedButton.icon(
              onPressed: () => launchUrl(
                Uri.parse(
                    'https://www.google.com/maps/dir/?api=1&destination=${b.lat},${b.lng}&travelmode=driving'),
                mode: LaunchMode.externalApplication,
              ),
              icon: const Icon(Icons.navigation),
              label: const Text('Navigate to bin'),
            ),
          ],
          const SizedBox(height: 16),
          Text('Why this urgency',
              style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          for (final p in parts)
            ListTile(
              dense: true,
              title: Text(p['label'] as String),
              subtitle: Text(
                  'value ${(p['value'] as num).toStringAsFixed(1)} · weight ${(p['weight'] as num)}'),
              trailing: Text((p['points'] as num).toStringAsFixed(1)),
            ),
          if (_device != null) ...[
            const SizedBox(height: 8),
            Text('Device', style: Theme.of(context).textTheme.titleMedium),
            ListTile(
              dense: true,
              title: Text('Firmware ${_device!['fw'] ?? '-'}'),
              subtitle: Text([
                if (_device!['ip'] != null) 'IP ${_device!['ip']}',
                if (_device!['mac'] != null) 'MAC ${_device!['mac']}',
                if (_device!['rssi'] != null) 'RSSI ${_device!['rssi']}',
              ].join(' · ')),
            ),
          ],
          const SizedBox(height: 8),
          Text('Recent readings (${_readings.length})',
              style: Theme.of(context).textTheme.titleMedium),
          if (_readings.isEmpty) const Text('No readings stored yet.'),
          for (final r in _readings.take(40))
            ListTile(
              dense: true,
              title: Text(DateFormat('d MMM HH:mm')
                  .format(DateTime.fromMillisecondsSinceEpoch(r.ts))),
              subtitle: Text([
                'fill ${pct(r.fillPct)}',
                if (r.weightKg != null) '${r.weightKg!.toStringAsFixed(2)} kg',
                if (r.gasIndex != null) 'gas ${r.gasIndex!.toStringAsFixed(0)}',
                if (r.tempC != null) '${r.tempC!.toStringAsFixed(1)} °C',
              ].join(' · ')),
            ),
        ],
      ),
    );
  }

  Widget _stat(String k, String v) {
    return SizedBox(
      width: 150,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(k, style: Theme.of(context).textTheme.labelSmall),
          Text(v, style: const TextStyle(fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }
}
