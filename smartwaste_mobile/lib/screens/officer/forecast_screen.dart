import 'package:flutter/material.dart';

import '../../services/officer_service.dart';
import '../../theme.dart';
import '../../utils/format.dart';
import '../../widgets/common.dart';

class ForecastScreen extends StatefulWidget {
  const ForecastScreen({super.key});
  @override
  State<ForecastScreen> createState() => _ForecastScreenState();
}

class _ForecastScreenState extends State<ForecastScreen> {
  ForecastData? _data;
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
      final d = await OfficerService.instance.loadForecast();
      if (!mounted) return;
      setState(() {
        _data = d;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = 'Could not load forecast: $e';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) return ErrorRetry(message: _error!, onRetry: _reload);
    final d = _data!;
    return RefreshIndicator(
      onRefresh: _reload,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(
            d.totals.isEmpty
                ? 'No 7-day forecast in Firebase yet. Run the forecast job on the website System page.'
                : 'Tonnes for all areas.${d.model.isEmpty ? "" : " Model: ${d.model}"}',
          ),
          const SizedBox(height: 12),
          for (final t in d.totals)
            Card(
              color: t.busy.isNotEmpty ? Colors.orange.shade50 : null,
              child: ListTile(
                title: Text(t.label),
                subtitle: Text([
                  'normal ${t.normal.toStringAsFixed(1)} t',
                  '${t.change >= 0 ? "+" : ""}${t.change.toStringAsFixed(0)}%',
                  if (t.busy.isNotEmpty) 'busy: ${t.busy.join(", ")}',
                  if (t.holiday.isNotEmpty) t.holiday,
                  if (t.rainMm != null) 'rain ${t.rainMm!.toStringAsFixed(1)} mm',
                ].join(' · ')),
                trailing: Text(
                  '${t.forecast.toStringAsFixed(1)} t',
                  style: TextStyle(
                    fontWeight: FontWeight.bold,
                    color: t.busy.isNotEmpty
                        ? FillColors.warning
                        : Theme.of(context).colorScheme.primary,
                  ),
                ),
              ),
            ),
          if (d.zones.isNotEmpty) ...[
            const SizedBox(height: 16),
            Text('By zone', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            for (final z in d.zones)
              ExpansionTile(
                title: Text(z),
                children: [
                  for (final day in d.days)
                    if (d.byZone[z]?[day] != null)
                      ListTile(
                        dense: true,
                        title: Text(dayLabel(day)),
                        trailing: Text(
                          '${(d.byZone[z]![day]!['forecast_t'] as num?)?.toStringAsFixed(2) ?? "-"} t',
                        ),
                        subtitle: Text(
                          d.byZone[z]![day]!['high_waste'] == true
                              ? 'high waste day'
                              : 'normal',
                        ),
                      ),
                ],
              ),
          ],
          if (d.guidance.isNotEmpty) ...[
            const SizedBox(height: 16),
            Text('Crew tips', style: Theme.of(context).textTheme.titleMedium),
            for (final e in d.guidance.entries)
              ListTile(
                title: Text(dayLabel(e.key)),
                subtitle: Text(e.value.join('\n')),
              ),
          ],
        ],
      ),
    );
  }
}
