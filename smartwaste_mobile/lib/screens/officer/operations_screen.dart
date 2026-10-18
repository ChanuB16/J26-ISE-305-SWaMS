import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

import '../../config.dart';
import '../../models/bin.dart';
import '../../models/route.dart';
import '../../services/bin_service.dart';
import '../../services/officer_service.dart';
import '../../services/route_service.dart';
import '../../theme.dart';
import '../../utils/format.dart';
import '../../widgets/common.dart';
import 'bin_detail_screen.dart';

class OperationsScreen extends StatefulWidget {
  const OperationsScreen({super.key});
  @override
  State<OperationsScreen> createState() => _OperationsScreenState();
}

class _OperationsScreenState extends State<OperationsScreen> {
  List<BinRow>? _bins;
  DayRoutes? _routes;
  ForecastData? _forecast;
  CommunityData? _community;
  String? _error;
  bool _loading = true;
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
      final bins = await BinService.instance.loadAll();
      final routes = await RouteService.instance.loadForDay(RouteService.todayIso());
      ForecastData? fc;
      CommunityData? com;
      try {
        fc = await OfficerService.instance.loadForecast();
      } catch (_) {}
      try {
        com = await OfficerService.instance.loadCommunity();
      } catch (_) {}
      if (!mounted) return;
      setState(() {
        _bins = bins;
        _routes = routes;
        _forecast = fc;
        _community = com;
        _loading = false;
        _error = null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = 'Could not load operations: $e';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) return ErrorRetry(message: _error!, onRetry: _reload);
    final bins = _bins!;
    final trucks = _routes?.trucks ?? const <TruckRoute>[];
    final k = OfficerService.instance.kpis(bins, trucks);
    final alerts = OfficerService.instance.alerts(bins, _forecast?.totals ?? const [], trucks);
    final urgent = bins.where((b) => b.urgency != null || b.fill != null).take(8).toList();
    final newReports =
        _community?.reports.where((r) => r.status == 'new').length ?? 0;
    final points = _community?.users.fold<int>(0, (s, u) => s + u.points) ?? 0;

    return RefreshIndicator(
      onRefresh: _reload,
      child: ListView(
        padding: const EdgeInsets.only(bottom: 24),
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 12, 12, 0),
            child: Text(
              '${k.total} bins (${k.real} real, ${k.total - k.real} demo)',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(8),
            child: GridView.count(
              crossAxisCount: 2,
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              childAspectRatio: 1.55,
              children: [
                KpiTile(
                  icon: Icons.delete,
                  label: 'Total bins',
                  value: '${k.total}',
                  sub: 'average fill ${pct(k.avgFill)}',
                ),
                KpiTile(
                  icon: Icons.warning,
                  label: 'Critical (90%+)',
                  value: '${k.critical}',
                  sub: '${k.highRisk} high overflow risk',
                  color: FillColors.critical,
                ),
                KpiTile(
                  icon: Icons.trending_up,
                  label: 'Warning (75–89%)',
                  value: '${k.warning}',
                  sub: '${k.filling} filling (50–74%)',
                  color: FillColors.warning,
                ),
                KpiTile(
                  icon: Icons.local_shipping,
                  label: 'Trucks on the road',
                  value: '${k.trucksOnRoute} / ${k.trucksTotal}',
                  sub: k.trucksBroken > 0
                      ? '${k.trucksBroken} broken'
                      : 'none broken',
                ),
              ],
            ),
          ),
          _map(bins, trucks),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
            child: Text('Early warnings (${alerts.length})',
                style: Theme.of(context).textTheme.titleMedium),
          ),
          if (alerts.isEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 16),
              child: Text('No warnings right now.'),
            ),
          for (final a in alerts.take(20))
            ListTile(
              dense: true,
              leading: Icon(_alertIcon(a.level), color: _alertColor(a.level)),
              title: Text(a.title),
              subtitle: Text(a.text),
              onTap: a.binId == null
                  ? null
                  : () => Navigator.of(context).push(MaterialPageRoute(
                        builder: (_) => BinDetailScreen(binId: a.binId!),
                      )),
            ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
            child: Text('Most urgent bins',
                style: Theme.of(context).textTheme.titleMedium),
          ),
          for (final b in urgent)
            ListTile(
              leading: CircleAvatar(
                backgroundColor: FillColors.forLevel(b.level),
                child: Text(FillColors.symbolFor(b.level),
                    style: const TextStyle(color: Colors.white)),
              ),
              title: Text('${b.id}  ${b.name}'),
              subtitle: Text([
                if (b.zone.isNotEmpty) b.zone,
                'now ${pct(b.fill)}',
                '6 h ${pct(b.pred)}',
                if (b.urgency != null) 'urgency ${b.urgency!.toStringAsFixed(0)}',
                hoursLabel(b.hoursToFull),
              ].join(' · ')),
              trailing: RiskChip(risk: b.risk),
              onTap: () => Navigator.of(context).push(MaterialPageRoute(
                builder: (_) => BinDetailScreen(binId: b.id),
              )),
            ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
            child: Text('Community',
                style: Theme.of(context).textTheme.titleMedium),
          ),
          ListTile(
            leading: const Icon(Icons.report),
            title: Text('$newReports new reports'),
            subtitle: Text(
                '${_community?.reports.length ?? 0} total · $points green points'),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
            child: Text('Today\'s truck routes',
                style: Theme.of(context).textTheme.titleMedium),
          ),
          if (trucks.isEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 16),
              child: Text('No plan for today yet.'),
            ),
          for (final t in trucks)
            ListTile(
              leading: Icon(
                t.status == 'broken' ? Icons.report_problem : Icons.local_shipping,
                color: t.status == 'broken' ? FillColors.critical : null,
              ),
              title: Text(t.name),
              subtitle: Text(
                t.stops.isEmpty
                    ? (t.note ?? 'no stops')
                    : '${t.doneCount}/${t.stops.length} emptied'
                        '${t.km == null ? "" : " · ${t.km!.toStringAsFixed(1)} km"}',
              ),
              trailing: Text(t.status),
            ),
        ],
      ),
    );
  }

  Widget _map(List<BinRow> bins, List<TruckRoute> trucks) {
    final withLoc = bins.where((b) => b.lat != null && b.lng != null).toList();
    final centre = withLoc.isEmpty
        ? LatLng(AppConfig.depotLat, AppConfig.depotLng)
        : LatLng(withLoc.first.lat!, withLoc.first.lng!);
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
            MarkerLayer(markers: [
              Marker(
                point: LatLng(AppConfig.depotLat, AppConfig.depotLng),
                width: 28,
                height: 28,
                child: const Icon(Icons.home, size: 28),
              ),
              for (final b in withLoc)
                Marker(
                  point: LatLng(b.lat!, b.lng!),
                  width: 22,
                  height: 22,
                  child: GestureDetector(
                    onTap: () => Navigator.of(context).push(MaterialPageRoute(
                      builder: (_) => BinDetailScreen(binId: b.id),
                    )),
                    child: Container(
                      decoration: BoxDecoration(
                        color: FillColors.forLevel(b.level),
                        shape: BoxShape.circle,
                        border: Border.all(color: Colors.white, width: 2),
                      ),
                    ),
                  ),
                ),
              for (final t in trucks)
                if (t.truckLat != null && t.truckLng != null)
                  Marker(
                    point: LatLng(t.truckLat!, t.truckLng!),
                    width: 28,
                    height: 28,
                    child: Icon(Icons.local_shipping,
                        color: t.status == 'broken'
                            ? FillColors.critical
                            : Colors.blue.shade800),
                  ),
            ]),
          ],
        ),
      ),
    );
  }

  static IconData _alertIcon(String level) {
    switch (level) {
      case 'critical':
        return Icons.error;
      case 'warning':
        return Icons.warning;
      case 'serious':
        return Icons.priority_high;
      default:
        return Icons.info_outline;
    }
  }

  static Color _alertColor(String level) {
    switch (level) {
      case 'critical':
        return FillColors.critical;
      case 'warning':
        return FillColors.warning;
      case 'serious':
        return FillColors.filling;
      default:
        return Colors.blueGrey;
    }
  }
}
