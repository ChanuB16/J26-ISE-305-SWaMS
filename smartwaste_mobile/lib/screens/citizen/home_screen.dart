import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../config.dart';
import '../../models/bin.dart';
import '../../services/bin_service.dart';
import '../../services/location_service.dart';
import '../../theme.dart';
import '../../utils/distance.dart';

/// Citizen "Find a bin" page.
///
/// Shows a map of all bins coloured by fill level and a "Nearest bin with
/// space" button that uses the phone's GPS to pick the best bin
/// (same logic as /api/nearest in the Flask app).
class CitizenHomeScreen extends StatefulWidget {
  const CitizenHomeScreen({super.key});
  @override
  State<CitizenHomeScreen> createState() => _CitizenHomeScreenState();
}

class _CitizenHomeScreenState extends State<CitizenHomeScreen> {
  late Future<List<BinRow>> _bins;
  LatLng? _me;
  BinRow? _nearest;
  double? _nearestKm;
  String? _msg;

  @override
  void initState() {
    super.initState();
    _bins = BinService.instance.loadAll();
  }

  Future<void> _refresh() async {
    setState(() {
      _bins = BinService.instance.loadAll();
    });
    await _bins;
  }

  Future<void> _findNearest() async {
    setState(() => _msg = null);
    try {
      final pos = await LocationService.instance.current();
      if (pos == null) return;
      final me = LatLng(pos.latitude, pos.longitude);
      final rows = await _bins;
      final best = BinService.instance
          .nearestWithSpace(rows, me.latitude, me.longitude, AppConfig.maxWalkKm);
      setState(() {
        _me = me;
        _nearest = best;
        _nearestKm = best == null
            ? null
            : distanceKm(me.latitude, me.longitude, best.lat!, best.lng!);
        if (best == null) {
          _msg = 'No bin with space within ${AppConfig.maxWalkKm.toStringAsFixed(1)} km.';
        }
      });
    } on LocationException catch (e) {
      setState(() => _msg = e.message);
    } catch (e) {
      setState(() => _msg = 'Could not get your location: $e');
    }
  }

  Future<void> _navigate(BinRow bin) async {
    final url = Uri.parse(
        'https://www.google.com/maps/dir/?api=1&destination=${bin.lat},${bin.lng}&travelmode=walking');
    await launchUrl(url, mode: LaunchMode.externalApplication);
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: _refresh,
      child: FutureBuilder<List<BinRow>>(
        future: _bins,
        builder: (ctx, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) {
            return _ErrorBox(
                message: 'Could not read bins: ${snap.error}',
                onRetry: _refresh);
          }
          final bins = (snap.data ?? const <BinRow>[])
              .where((b) => b.lat != null && b.lng != null)
              .toList();
          final centre = _me ??
              (bins.isNotEmpty
                  ? LatLng(bins.first.lat!, bins.first.lng!)
                  : LatLng(AppConfig.depotLat, AppConfig.depotLng));

          return ListView(
            padding: const EdgeInsets.only(bottom: 24),
            children: [
              SizedBox(
                height: 320,
                child: FlutterMap(
                  options: MapOptions(
                    initialCenter: centre,
                    initialZoom: 14,
                  ),
                  children: [
                    TileLayer(
                      urlTemplate:
                          'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                      userAgentPackageName: 'lk.smartwaste.mobile',
                    ),
                    MarkerLayer(markers: [
                      for (final b in bins)
                        Marker(
                          point: LatLng(b.lat!, b.lng!),
                          width: 36,
                          height: 36,
                          child: _BinMarker(bin: b),
                        ),
                      if (_me != null)
                        Marker(
                          point: _me!,
                          width: 24,
                          height: 24,
                          child: const Icon(Icons.my_location,
                              color: Colors.blue, size: 24),
                        ),
                    ]),
                  ],
                ),
              ),
              Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    FilledButton.icon(
                      onPressed: _findNearest,
                      icon: const Icon(Icons.near_me),
                      label: const Text('Find nearest bin with space'),
                    ),
                    if (_msg != null) ...[
                      const SizedBox(height: 12),
                      Text(_msg!, style: const TextStyle(color: Colors.red)),
                    ],
                    if (_nearest != null) ...[
                      const SizedBox(height: 16),
                      Card(
                        child: ListTile(
                          leading: CircleAvatar(
                            backgroundColor:
                                FillColors.forLevel(_nearest!.level),
                            child: Text(
                              FillColors.symbolFor(_nearest!.level),
                              style: const TextStyle(color: Colors.white),
                            ),
                          ),
                          title: Text(_nearest!.name),
                          subtitle: Text(
                            '${_nearestKm?.toStringAsFixed(2) ?? "-"} km away'
                            ' \u00B7 ${_nearest!.fill?.toStringAsFixed(0) ?? "?"}% full',
                          ),
                          trailing: IconButton(
                            icon: const Icon(Icons.directions_walk),
                            tooltip: 'Walk here',
                            onPressed: () => _navigate(_nearest!),
                          ),
                        ),
                      ),
                    ],
                    const SizedBox(height: 16),
                    Text('All bins (${bins.length})',
                        style: Theme.of(context).textTheme.titleMedium),
                    const SizedBox(height: 8),
                    ...bins.map((b) => _BinListTile(bin: b, origin: _me)),
                  ],
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _BinMarker extends StatelessWidget {
  final BinRow bin;
  const _BinMarker({required this.bin});
  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: '${bin.name}\n${bin.fill?.toStringAsFixed(0) ?? "?"}%',
      child: Container(
        decoration: BoxDecoration(
          color: FillColors.forLevel(bin.level),
          shape: BoxShape.circle,
          border: Border.all(color: Colors.white, width: 2),
        ),
        alignment: Alignment.center,
        child: Text(
          FillColors.symbolFor(bin.level),
          style: const TextStyle(color: Colors.white),
        ),
      ),
    );
  }
}

class _BinListTile extends StatelessWidget {
  final BinRow bin;
  final LatLng? origin;
  const _BinListTile({required this.bin, this.origin});
  @override
  Widget build(BuildContext context) {
    final km = origin == null
        ? null
        : distanceKm(origin!.latitude, origin!.longitude, bin.lat!, bin.lng!);
    return ListTile(
      leading: CircleAvatar(
        backgroundColor: FillColors.forLevel(bin.level),
        child: Text(FillColors.symbolFor(bin.level),
            style: const TextStyle(color: Colors.white)),
      ),
      title: Text(bin.name),
      subtitle: Text([
        if (bin.zone.isNotEmpty) bin.zone,
        '${bin.fill?.toStringAsFixed(0) ?? "?"}% full',
        FillColors.wordFor(bin.level),
        if (km != null) '${km.toStringAsFixed(2)} km',
      ].join(' \u00B7 ')),
      trailing: IconButton(
        icon: const Icon(Icons.directions_walk),
        onPressed: () async {
          final url = Uri.parse(
              'https://www.google.com/maps/dir/?api=1&destination=${bin.lat},${bin.lng}&travelmode=walking');
          await launchUrl(url, mode: LaunchMode.externalApplication);
        },
      ),
    );
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
