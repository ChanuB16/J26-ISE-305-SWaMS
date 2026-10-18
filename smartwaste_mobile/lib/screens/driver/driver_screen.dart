import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:intl/intl.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../config.dart';
import '../../models/route.dart';
import '../../services/location_service.dart';
import '../../services/route_service.dart';
import '../../services/session.dart';
import '../../theme.dart';
import '../../utils/distance.dart';
import '../usability_screen.dart';

/// Driver screen — today's route for the logged-in driver's truck.
///
/// Mirrors templates/driver.html + static/js/pages/driver.js in the Flask app.
class DriverScreen extends StatefulWidget {
  const DriverScreen({super.key});
  @override
  State<DriverScreen> createState() => _DriverScreenState();
}

class _DriverScreenState extends State<DriverScreen> {
  DayRoutes? _data;
  String? _selectedTruckId;
  String? _error;
  bool _loading = true;
  Timer? _poll;
  LatLng? _me;

  @override
  void initState() {
    super.initState();
    _reload();
    _poll = Timer.periodic(const Duration(seconds: 15), (_) => _reload());
    _grabLocation();
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  Future<void> _grabLocation() async {
    try {
      final pos = await LocationService.instance.current();
      if (!mounted || pos == null) return;
      setState(() => _me = LatLng(pos.latitude, pos.longitude));
    } catch (_) {
      // optional
    }
  }

  Future<void> _reload() async {
    try {
      final day = RouteService.todayIso();
      final d = await RouteService.instance.loadForDay(day);
      if (!mounted) return;

      // Pick the truck: user's assigned truck, else last-selected, else first.
      final user = context.read<Session>().user;
      String? pick = _selectedTruckId;
      if (user?.truck.isNotEmpty == true &&
          d.trucks.any((t) => t.id == user!.truck)) {
        pick ??= user!.truck;
      }
      if (pick == null || !d.trucks.any((t) => t.id == pick)) {
        pick = d.trucks.isEmpty ? null : d.trucks.first.id;
      }
      setState(() {
        _data = d;
        _selectedTruckId = pick;
        _loading = false;
        _error = null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = 'Could not load today\'s route: $e';
      });
    }
  }

  TruckRoute? get _truck {
    if (_data == null || _selectedTruckId == null) return null;
    for (final t in _data!.trucks) {
      if (t.id == _selectedTruckId) return t;
    }
    return null;
  }

  Future<void> _markNextDone() async {
    final t = _truck;
    final day = _data?.date;
    if (t == null || day == null) return;
    final idx = t.nextIndex;
    if (idx < 0) return;
    final binId = t.stops[idx].binId;
    final ok = await _confirm(
      'Mark bin $binId as emptied?',
      'This records the collection and moves to the next stop.',
    );
    if (!ok) return;
    try {
      await RouteService.instance.markStopDone(day, t.id, idx);
      _snack('$binId marked as emptied.');
      await _reload();
    } catch (e) {
      _snack('Could not mark done: $e', isError: true);
    }
  }

  Future<void> _toggleBroken() async {
    final user = context.read<Session>().user;
    final t = _truck;
    if (t == null || user == null) return;
    final want = t.status == 'broken' ? 'available' : 'broken';
    final msg = want == 'broken'
        ? 'Report this truck as broken? Your bins will be moved to other trucks.'
        : 'Mark this truck as fixed?';
    final ok = await _confirm(want == 'broken' ? 'Truck broken' : 'Truck fixed', msg);
    if (!ok) return;
    try {
      await RouteService.instance.setTruckStatus(t.id, want, user.username);
      _snack(want == 'broken'
          ? 'Reported. The planner will move your bins.'
          : 'Marked as fixed.');
      await _reload();
    } catch (e) {
      _snack('Could not update: $e', isError: true);
    }
  }

  Future<void> _navigate(double lat, double lng) async {
    final url = Uri.parse(
        'https://www.google.com/maps/dir/?api=1&destination=$lat,$lng&travelmode=driving');
    await launchUrl(url, mode: LaunchMode.externalApplication);
  }

  Future<bool> _confirm(String title, String body) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(title),
        content: Text(body),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('OK')),
        ],
      ),
    );
    return ok ?? false;
  }

  void _snack(String msg, {bool isError = false}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(msg),
      backgroundColor: isError ? Colors.red : null,
    ));
  }

  @override
  Widget build(BuildContext context) {
    final user = context.watch<Session>().user;
    return Scaffold(
      appBar: AppBar(
        title: const Text('My route'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _reload,
            tooltip: 'Refresh',
          ),
          PopupMenuButton<String>(
            icon: const Icon(Icons.account_circle),
            onSelected: (v) async {
              if (v == 'logout') await context.read<Session>().logout();
              if (v == 'survey' && context.mounted) {
                Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => const UsabilityScreen()),
                );
              }
            },
            itemBuilder: (ctx) => [
              PopupMenuItem(
                enabled: false,
                child: Text('${user?.name ?? ""} '
                    '(${user?.truck.isEmpty == true ? "no truck" : "truck ${user?.truck}"})'),
              ),
              const PopupMenuDivider(),
              const PopupMenuItem(value: 'survey', child: Text('Rate this app')),
              const PopupMenuItem(value: 'logout', child: Text('Log out')),
            ],
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? _ErrorBox(message: _error!, onRetry: _reload)
              : _buildBody(),
    );
  }

  Widget _buildBody() {
    final data = _data!;
    if (data.trucks.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Text(
            'No route planned for today yet.\nCheck back soon.',
            textAlign: TextAlign.center,
          ),
        ),
      );
    }
    final t = _truck!;
    return RefreshIndicator(
      onRefresh: _reload,
      child: ListView(
        padding: const EdgeInsets.only(bottom: 32),
        children: [
          if (data.trucks.length > 1)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
              child: DropdownButtonFormField<String>(
                value: _selectedTruckId,
                decoration: const InputDecoration(labelText: 'Truck'),
                items: [
                  for (final truck in data.trucks)
                    DropdownMenuItem(
                      value: truck.id,
                      child: Text('${truck.name} (${truck.id})'),
                    ),
                ],
                onChanged: (v) => setState(() => _selectedTruckId = v),
              ),
            ),
          _NextStopCard(
            truck: t,
            myPos: _me,
            depotName: AppConfig.depotName,
            depotLat: AppConfig.depotLat,
            depotLng: AppConfig.depotLng,
            onMarkDone: _markNextDone,
            onNavigate: _navigate,
          ),
          const SizedBox(height: 8),
          _RouteMap(truck: t, me: _me),
          const SizedBox(height: 8),
          _StopsTimeline(truck: t, onNavigate: _navigate),
          const SizedBox(height: 8),
          _EmptiedTodayCard(truck: t),
          const SizedBox(height: 8),
          _TruckBrokenCard(truck: t, onToggle: _toggleBroken),
        ],
      ),
    );
  }
}

// ---------- Next-stop big card ----------

class _NextStopCard extends StatelessWidget {
  final TruckRoute truck;
  final LatLng? myPos;
  final String depotName;
  final double depotLat;
  final double depotLng;
  final Future<void> Function() onMarkDone;
  final Future<void> Function(double lat, double lng) onNavigate;

  const _NextStopCard({
    required this.truck,
    required this.myPos,
    required this.depotName,
    required this.depotLat,
    required this.depotLng,
    required this.onMarkDone,
    required this.onNavigate,
  });

  @override
  Widget build(BuildContext context) {
    if (truck.status == 'broken') {
      return _wrap(
        context,
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('TRUCK REPORTED BROKEN',
                style: TextStyle(color: Colors.white70, letterSpacing: 1.2)),
            const SizedBox(height: 8),
            Text('${truck.name} is out of service',
                style: const TextStyle(
                    color: Colors.white, fontSize: 22, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            const Text(
              'Your bins were given to the other trucks (if the planner is running). '
              'Press "Truck fixed" below when it works again.',
              style: TextStyle(color: Colors.white70),
            ),
          ],
        ),
      );
    }
    if (truck.stops.isEmpty) {
      return _wrap(
        context,
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(truck.name,
                style: const TextStyle(color: Colors.white70, letterSpacing: 1.2)),
            const SizedBox(height: 8),
            const Text('No stops for you today',
                style: TextStyle(
                    color: Colors.white, fontSize: 22, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            Text(
              truck.note ?? 'Stay at the depot until the planner sends a route.',
              style: const TextStyle(color: Colors.white70),
            ),
          ],
        ),
      );
    }
    final idx = truck.nextIndex;
    if (idx < 0) {
      return _wrap(
        context,
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('${truck.name}  ·  all ${truck.stops.length} bins emptied',
                style: const TextStyle(color: Colors.white70)),
            const SizedBox(height: 8),
            const Text('Route finished',
                style: TextStyle(
                    color: Colors.white, fontSize: 22, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            Text('Drive back to the depot ($depotName).',
                style: const TextStyle(color: Colors.white70)),
            const SizedBox(height: 12),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                style: FilledButton.styleFrom(backgroundColor: Colors.white),
                onPressed: () => onNavigate(depotLat, depotLng),
                icon: const Icon(Icons.navigation, color: Colors.black87),
                label: const Text('Navigate to depot',
                    style: TextStyle(color: Colors.black87)),
              ),
            ),
          ],
        ),
      );
    }
    final s = truck.stops[idx];
    final from = myPos ??
        (truck.truckLat != null && truck.truckLng != null
            ? LatLng(truck.truckLat!, truck.truckLng!)
            : null);
    final away = (from != null && s.lat != null && s.lng != null)
        ? distanceKm(from.latitude, from.longitude, s.lat!, s.lng!)
        : null;
    final done = truck.doneCount;
    final total = truck.stops.length;
    final progress = total == 0 ? 0.0 : done / total;

    return _wrap(
      context,
      Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text('NEXT STOP · ${idx + 1} of $total',
                  style: const TextStyle(
                      color: Colors.white70, letterSpacing: 1.2)),
              _FillPill(fillPct: s.fillPct),
            ],
          ),
          const SizedBox(height: 6),
          Text('${s.binId}  ·  ${s.name}',
              style: const TextStyle(
                  color: Colors.white, fontSize: 20, fontWeight: FontWeight.bold)),
          const SizedBox(height: 6),
          Row(
            children: [
              const Icon(Icons.schedule, color: Colors.white70, size: 16),
              const SizedBox(width: 4),
              Text('arrive about ', style: const TextStyle(color: Colors.white70)),
              Text(s.eta.isEmpty ? '-' : s.eta,
                  style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
              if (away != null) ...[
                const SizedBox(width: 10),
                const Icon(Icons.place, color: Colors.white70, size: 16),
                const SizedBox(width: 4),
                Text('${away.toStringAsFixed(2)} km away',
                    style: const TextStyle(color: Colors.white70)),
              ],
            ],
          ),
          const SizedBox(height: 10),
          LinearProgressIndicator(
            value: progress,
            backgroundColor: Colors.white24,
            valueColor: const AlwaysStoppedAnimation<Color>(Colors.white),
          ),
          const SizedBox(height: 4),
          Text(
              '$done of $total bins emptied'
              '${truck.km == null ? "" : "  ·  ${truck.km!.toStringAsFixed(1)} km route"}',
              style: const TextStyle(color: Colors.white70, fontSize: 12)),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  style: OutlinedButton.styleFrom(
                    foregroundColor: Colors.white,
                    side: const BorderSide(color: Colors.white54),
                    minimumSize: const Size.fromHeight(48),
                  ),
                  onPressed: s.lat == null || s.lng == null
                      ? null
                      : () => onNavigate(s.lat!, s.lng!),
                  icon: const Icon(Icons.navigation),
                  label: const Text('Navigate'),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: FilledButton.icon(
                  style: FilledButton.styleFrom(
                    backgroundColor: Colors.white,
                    minimumSize: const Size.fromHeight(48),
                  ),
                  onPressed: onMarkDone,
                  icon: const Icon(Icons.check, color: Colors.black87),
                  label: const Text('Mark as emptied',
                      style: TextStyle(color: Colors.black87)),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _wrap(BuildContext context, Widget child) {
    return Container(
      margin: const EdgeInsets.all(12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.primary,
        borderRadius: BorderRadius.circular(12),
      ),
      child: child,
    );
  }
}

// ---------- Map ----------

class _RouteMap extends StatelessWidget {
  final TruckRoute truck;
  final LatLng? me;
  const _RouteMap({required this.truck, required this.me});

  @override
  Widget build(BuildContext context) {
    final points = <LatLng>[];
    for (final s in truck.stops) {
      if (s.lat != null && s.lng != null) points.add(LatLng(s.lat!, s.lng!));
    }
    LatLng centre;
    if (me != null) {
      centre = me!;
    } else if (points.isNotEmpty) {
      centre = points.first;
    } else {
      centre = LatLng(AppConfig.depotLat, AppConfig.depotLng);
    }
    final idx = truck.nextIndex;
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 12),
      clipBehavior: Clip.antiAlias,
      child: SizedBox(
        height: 240,
        child: FlutterMap(
          options: MapOptions(initialCenter: centre, initialZoom: 13),
          children: [
            TileLayer(
              urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
              userAgentPackageName: 'lk.smartwaste.mobile',
            ),
            if (truck.path.length > 1)
              PolylineLayer(polylines: [
                Polyline(
                  points: [for (final p in truck.path) LatLng(p[0], p[1])],
                  color: Theme.of(context).colorScheme.primary,
                  strokeWidth: 4,
                ),
              ]),
            MarkerLayer(markers: [
              Marker(
                point: LatLng(AppConfig.depotLat, AppConfig.depotLng),
                width: 28,
                height: 28,
                child: const Icon(Icons.home, color: Colors.black87, size: 28),
              ),
              for (var k = 0; k < truck.stops.length; k++)
                if (truck.stops[k].lat != null && truck.stops[k].lng != null)
                  Marker(
                    point: LatLng(truck.stops[k].lat!, truck.stops[k].lng!),
                    width: 28,
                    height: 28,
                    child: _NumPin(
                      n: k + 1,
                      colour: truck.stops[k].done
                          ? Colors.grey
                          : (k == idx
                              ? FillColors.critical
                              : FillColors.forLevel(_levelFromFill(
                                  truck.stops[k].fillPct))),
                    ),
                  ),
              if (me != null)
                Marker(
                  point: me!,
                  width: 20,
                  height: 20,
                  child: const Icon(Icons.my_location,
                      color: Colors.blue, size: 20),
                ),
            ]),
          ],
        ),
      ),
    );
  }

  static String _levelFromFill(double? f) {
    if (f == null) return 'none';
    if (f >= AppConfig.overflowPct) return 'critical';
    if (f >= AppConfig.alertPct) return 'warning';
    if (f >= AppConfig.fillingPct) return 'filling';
    return 'normal';
  }
}

class _NumPin extends StatelessWidget {
  final int n;
  final Color colour;
  const _NumPin({required this.n, required this.colour});
  @override
  Widget build(BuildContext context) {
    return Container(
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: colour,
        shape: BoxShape.circle,
        border: Border.all(color: Colors.white, width: 2),
      ),
      child: Text('$n',
          style: const TextStyle(
              color: Colors.white, fontSize: 12, fontWeight: FontWeight.bold)),
    );
  }
}

// ---------- Timeline list ----------

class _StopsTimeline extends StatelessWidget {
  final TruckRoute truck;
  final Future<void> Function(double, double) onNavigate;
  const _StopsTimeline({required this.truck, required this.onNavigate});

  @override
  Widget build(BuildContext context) {
    final idx = truck.nextIndex;
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 12),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('All stops  (${truck.stops.length})',
                style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            if (truck.stops.isEmpty) const Text('No stops.'),
            for (var k = 0; k < truck.stops.length; k++)
              _StopTile(
                index: k,
                stop: truck.stops[k],
                isNext: k == idx,
                onNavigate: () {
                  final s = truck.stops[k];
                  if (s.lat != null && s.lng != null) onNavigate(s.lat!, s.lng!);
                },
              ),
          ],
        ),
      ),
    );
  }
}

class _StopTile extends StatelessWidget {
  final int index;
  final RouteStop stop;
  final bool isNext;
  final VoidCallback onNavigate;
  const _StopTile({
    required this.index,
    required this.stop,
    required this.isNext,
    required this.onNavigate,
  });
  @override
  Widget build(BuildContext context) {
    final bg = stop.done
        ? Colors.grey.shade100
        : isNext
            ? Colors.green.shade50
            : null;
    return Container(
      color: bg,
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: stop.done
              ? Colors.grey
              : (isNext ? FillColors.critical : Theme.of(context).colorScheme.primary),
          child: stop.done
              ? const Icon(Icons.check, color: Colors.white)
              : Text('${index + 1}',
                  style: const TextStyle(color: Colors.white)),
        ),
        title: Text('${stop.binId}  ${stop.name}'),
        subtitle: Text([
          if (stop.eta.isNotEmpty) 'ETA ${stop.eta}',
          if (stop.fillPct != null) '${stop.fillPct!.toStringAsFixed(0)}%',
          if (stop.done) 'emptied',
        ].join(' \u00B7 ')),
        trailing: IconButton(
          icon: const Icon(Icons.navigation),
          onPressed: stop.lat != null && stop.lng != null ? onNavigate : null,
        ),
      ),
    );
  }
}

// ---------- Emptied today ----------

class _EmptiedTodayCard extends StatelessWidget {
  final TruckRoute truck;
  const _EmptiedTodayCard({required this.truck});
  @override
  Widget build(BuildContext context) {
    final done = truck.stops.where((s) => s.done).toList()
      ..sort((a, b) => (b.doneAt ?? 0).compareTo(a.doneAt ?? 0));
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 12),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Emptied today  (${done.length})',
                style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            if (done.isEmpty) const Text('None yet.'),
            for (final s in done)
              ListTile(
                dense: true,
                leading: const Icon(Icons.check_circle, color: Colors.green),
                title: Text('${s.binId}  ${s.name}'),
                trailing: Text(s.doneAt == null
                    ? ''
                    : DateFormat('HH:mm').format(
                        DateTime.fromMillisecondsSinceEpoch(s.doneAt!))),
              ),
          ],
        ),
      ),
    );
  }
}

// ---------- Truck broken button ----------

class _TruckBrokenCard extends StatelessWidget {
  final TruckRoute truck;
  final Future<void> Function() onToggle;
  const _TruckBrokenCard({required this.truck, required this.onToggle});
  @override
  Widget build(BuildContext context) {
    final broken = truck.status == 'broken';
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Problem with the truck?',
                style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            const Text('The planner will move your bins to the other trucks.',
                style: TextStyle(color: Colors.grey)),
            const SizedBox(height: 12),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                style: FilledButton.styleFrom(
                  backgroundColor: broken ? Colors.green : Colors.red,
                ),
                onPressed: onToggle,
                icon: Icon(broken ? Icons.check : Icons.report_problem),
                label: Text(broken ? 'Truck fixed' : 'Report truck broken'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ---------- Shared helpers ----------

class _FillPill extends StatelessWidget {
  final double? fillPct;
  const _FillPill({required this.fillPct});
  @override
  Widget build(BuildContext context) {
    final lvl = _levelFromFill(fillPct);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: FillColors.forLevel(lvl),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Text(
        '${fillPct?.toStringAsFixed(0) ?? "?"}%',
        style: const TextStyle(
            color: Colors.white, fontWeight: FontWeight.bold, fontSize: 12),
      ),
    );
  }

  static String _levelFromFill(double? f) {
    if (f == null) return 'none';
    if (f >= AppConfig.overflowPct) return 'critical';
    if (f >= AppConfig.alertPct) return 'warning';
    if (f >= AppConfig.fillingPct) return 'filling';
    return 'normal';
  }
}

class _ErrorBox extends StatelessWidget {
  final String message;
  final Future<void> Function() onRetry;
  const _ErrorBox({required this.message, required this.onRetry});
  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, size: 48, color: Colors.red),
            const SizedBox(height: 12),
            Text(message, textAlign: TextAlign.center),
            const SizedBox(height: 16),
            FilledButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh),
              label: const Text('Try again'),
            ),
          ],
        ),
      ),
    );
  }
}
