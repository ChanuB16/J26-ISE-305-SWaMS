import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../config.dart';
import '../../models/route.dart';
import '../../services/route_service.dart';
import '../../services/session.dart';
import '../../theme.dart';
import '../../utils/format.dart';
import '../../widgets/common.dart';

class OfficerRoutesScreen extends StatefulWidget {
  const OfficerRoutesScreen({super.key});
  @override
  State<OfficerRoutesScreen> createState() => _OfficerRoutesScreenState();
}

class _OfficerRoutesScreenState extends State<OfficerRoutesScreen> {
  DayRoutes? _data;
  String? _error;
  bool _loading = true;
  String? _markKind; // closure | jam
  Timer? _poll;

  @override
  void initState() {
    super.initState();
    _reload();
    _poll = Timer.periodic(AppConfig.refresh, (_) => _reload());
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  Future<void> _reload() async {
    try {
      final d = await RouteService.instance.loadForDay(RouteService.todayIso());
      if (!mounted) return;
      setState(() {
        _data = d;
        _loading = false;
        _error = null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = 'Could not load routes: $e';
      });
    }
  }

  Future<void> _onMapTap(LatLng p) async {
    final kind = _markKind;
    if (kind == null) return;
    final user = context.read<Session>().user;
    if (user == null) return;
    setState(() => _markKind = null);
    try {
      await RouteService.instance.addTraffic(
        kind: kind,
        lat: p.latitude,
        lng: p.longitude,
        byUser: user.username,
      );
      await RouteService.instance.requestReplan();
      if (!mounted) return;
      showSnack(context,
          kind == 'jam' ? 'Traffic jam saved. Waiting for a new plan.' : 'Road closed. Waiting for a new plan.');
      await _reload();
    } catch (e) {
      if (!mounted) return;
      showSnack(context, 'Could not save: $e', isError: true);
    }
  }

  Future<void> _replan() async {
    try {
      await RouteService.instance.requestReplan();
      if (!mounted) return;
      showSnack(context, 'Re-plan asked. The live planner (website / r3) will pick this up.');
    } catch (e) {
      if (!mounted) return;
      showSnack(context, 'Could not ask for a re-plan: $e', isError: true);
    }
  }

  Future<void> _clearTraffic() async {
    try {
      await RouteService.instance.clearTraffic();
      await RouteService.instance.requestReplan();
      if (!mounted) return;
      showSnack(context, 'Traffic marks cleared.');
      await _reload();
    } catch (e) {
      if (!mounted) return;
      showSnack(context, 'Could not clear: $e', isError: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) return ErrorRetry(message: _error!, onRetry: _reload);
    final d = _data!;
    final s = d.summary;
    return RefreshIndicator(
      onRefresh: _reload,
      child: ListView(
        padding: const EdgeInsets.only(bottom: 24),
        children: [
          if (s != null)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
              child: Text(
                'Plan made ${timeAgo(s.madeAt)}'
                '${s.trigger == null ? "" : " (${s.trigger})"}. '
                '${s.planned ?? d.trucks.fold<int>(0, (n, t) => n + t.stops.length)} bins, '
                '${s.totalKm?.toStringAsFixed(1) ?? "-"} km, '
                'diesel ${s.fuelL?.toStringAsFixed(1) ?? "-"} L.',
              ),
            )
          else
            const Padding(
              padding: EdgeInsets.fromLTRB(16, 12, 16, 0),
              child: Text(
                'No plan for today yet. Start the route planner on the website System page.',
              ),
            ),
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
            child: Wrap(
              spacing: 8,
              children: [
                FilterChip(
                  label: const Text('Mark road closed'),
                  selected: _markKind == 'closure',
                  onSelected: (on) =>
                      setState(() => _markKind = on ? 'closure' : null),
                ),
                FilterChip(
                  label: const Text('Mark traffic jam'),
                  selected: _markKind == 'jam',
                  onSelected: (on) =>
                      setState(() => _markKind = on ? 'jam' : null),
                ),
                ActionChip(
                  label: const Text('Ask re-plan'),
                  onPressed: _replan,
                ),
                if (d.traffic.isNotEmpty)
                  ActionChip(
                    label: const Text('Clear traffic'),
                    onPressed: _clearTraffic,
                  ),
              ],
            ),
          ),
          if (_markKind != null)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
              child: Text(
                'Tap the map where the ${_markKind == 'jam' ? 'jam' : 'closure'} is.',
                style: const TextStyle(fontWeight: FontWeight.w600),
              ),
            ),
          _map(d),
          const SizedBox(height: 8),
          for (final t in d.trucks) _truckCard(t),
        ],
      ),
    );
  }

  Widget _map(DayRoutes d) {
    return Card(
      margin: const EdgeInsets.all(12),
      clipBehavior: Clip.antiAlias,
      child: SizedBox(
        height: 280,
        child: FlutterMap(
          options: MapOptions(
            initialCenter: LatLng(AppConfig.depotLat, AppConfig.depotLng),
            initialZoom: 13,
            onTap: (_, p) => _onMapTap(p),
          ),
          children: [
            TileLayer(
              urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
              userAgentPackageName: 'lk.smartwaste.mobile',
            ),
            PolylineLayer(polylines: [
              for (final t in d.trucks)
                if (t.path.length > 1)
                  Polyline(
                    points: [for (final p in t.path) LatLng(p[0], p[1])],
                    color: Theme.of(context).colorScheme.primary,
                    strokeWidth: 4,
                  ),
            ]),
            CircleLayer(circles: [
              for (final z in d.traffic)
                CircleMarker(
                  point: LatLng(z.lat, z.lng),
                  radius: z.radiusM,
                  useRadiusInMeter: true,
                  color: (z.kind == 'jam' ? FillColors.warning : FillColors.critical)
                      .withOpacity(0.2),
                  borderColor:
                      z.kind == 'jam' ? FillColors.warning : FillColors.critical,
                  borderStrokeWidth: 2,
                ),
            ]),
            MarkerLayer(markers: [
              Marker(
                point: LatLng(AppConfig.depotLat, AppConfig.depotLng),
                width: 28,
                height: 28,
                child: const Icon(Icons.home, size: 28),
              ),
              for (final t in d.trucks)
                for (var i = 0; i < t.stops.length; i++)
                  if (t.stops[i].lat != null && t.stops[i].lng != null)
                    Marker(
                      point: LatLng(t.stops[i].lat!, t.stops[i].lng!),
                      width: 24,
                      height: 24,
                      child: _pin(i + 1, t.stops[i].done),
                    ),
            ]),
          ],
        ),
      ),
    );
  }

  Widget _pin(int n, bool done) {
    return Container(
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: done ? Colors.grey : Theme.of(context).colorScheme.primary,
        shape: BoxShape.circle,
        border: Border.all(color: Colors.white, width: 2),
      ),
      child: Text('$n',
          style: const TextStyle(
              color: Colors.white, fontSize: 11, fontWeight: FontWeight.bold)),
    );
  }

  Widget _truckCard(TruckRoute t) {
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      child: ExpansionTile(
        leading: Icon(
          t.status == 'broken' ? Icons.report_problem : Icons.local_shipping,
          color: t.status == 'broken' ? FillColors.critical : null,
        ),
        title: Text(t.name),
        subtitle: Text(
          t.stops.isEmpty
              ? (t.note ?? 'no stops · ${t.status}')
              : '${t.doneCount}/${t.stops.length} emptied · ${t.status}'
                  '${t.km == null ? "" : " · ${t.km!.toStringAsFixed(1)} km"}',
        ),
        children: [
          for (var i = 0; i < t.stops.length; i++)
            ListTile(
              dense: true,
              leading: CircleAvatar(
                backgroundColor:
                    t.stops[i].done ? Colors.grey : Theme.of(context).colorScheme.primary,
                child: t.stops[i].done
                    ? const Icon(Icons.check, color: Colors.white, size: 16)
                    : Text('${i + 1}',
                        style: const TextStyle(color: Colors.white, fontSize: 12)),
              ),
              title: Text('${t.stops[i].binId}  ${t.stops[i].name}'),
              subtitle: Text([
                if (t.stops[i].eta.isNotEmpty) 'ETA ${t.stops[i].eta}',
                if (t.stops[i].fillPct != null)
                  '${t.stops[i].fillPct!.toStringAsFixed(0)}%',
                if (t.stops[i].done) 'emptied ${hhmm(t.stops[i].doneAt)}',
              ].join(' · ')),
              trailing: IconButton(
                icon: const Icon(Icons.navigation),
                onPressed: t.stops[i].lat == null
                    ? null
                    : () => launchUrl(
                          Uri.parse(
                              'https://www.google.com/maps/dir/?api=1&destination=${t.stops[i].lat},${t.stops[i].lng}&travelmode=driving'),
                          mode: LaunchMode.externalApplication,
                        ),
              ),
            ),
        ],
      ),
    );
  }
}
