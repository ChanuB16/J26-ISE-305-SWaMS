import 'dart:async';

import 'package:flutter/material.dart';

import '../../config.dart';
import '../../models/bin.dart';
import '../../services/bin_service.dart';
import '../../theme.dart';
import '../../utils/format.dart';
import '../../widgets/common.dart';
import 'bin_detail_screen.dart';

class OfficerBinsScreen extends StatefulWidget {
  const OfficerBinsScreen({super.key});
  @override
  State<OfficerBinsScreen> createState() => _OfficerBinsScreenState();
}

class _OfficerBinsScreenState extends State<OfficerBinsScreen> {
  List<BinRow> _all = [];
  String? _error;
  bool _loading = true;
  String _filter = 'all';
  String _q = '';
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
      final rows = await BinService.instance.loadAll();
      if (!mounted) return;
      setState(() {
        _all = rows;
        _loading = false;
        _error = null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = 'Could not load bins: $e';
      });
    }
  }

  List<BinRow> get _shown {
    Iterable<BinRow> rows = _all;
    switch (_filter) {
      case 'critical':
      case 'warning':
      case 'filling':
      case 'normal':
        rows = rows.where((b) => b.level == _filter);
        break;
      case 'real':
        rows = rows.where((b) => !b.synthetic);
        break;
      case 'demo':
        rows = rows.where((b) => b.synthetic);
        break;
    }
    final q = _q.trim().toLowerCase();
    if (q.isNotEmpty) {
      rows = rows.where((b) =>
          b.id.toLowerCase().contains(q) ||
          b.name.toLowerCase().contains(q) ||
          b.zone.toLowerCase().contains(q));
    }
    return rows.toList();
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) return ErrorRetry(message: _error!, onRetry: _reload);
    final rows = _shown;
    return RefreshIndicator(
      onRefresh: _reload,
      child: ListView(
        padding: const EdgeInsets.only(bottom: 24),
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 12, 12, 0),
            child: TextField(
              decoration: const InputDecoration(
                prefixIcon: Icon(Icons.search),
                labelText: 'Search id, name or zone',
              ),
              onChanged: (v) => setState(() => _q = v),
            ),
          ),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
            child: Row(
              children: [
                for (final f in const [
                  'all',
                  'critical',
                  'warning',
                  'filling',
                  'normal',
                  'real',
                  'demo',
                ])
                  Padding(
                    padding: const EdgeInsets.only(right: 6),
                    child: ChoiceChip(
                      label: Text(f),
                      selected: _filter == f,
                      onSelected: (_) => setState(() => _filter = f),
                    ),
                  ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
            child: Text('${rows.length} bins',
                style: Theme.of(context).textTheme.bodySmall),
          ),
          for (final b in rows)
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
                if (b.synthetic) 'demo',
                if (b.stale && !b.synthetic) 'stale',
              ].join(' · ')),
              trailing: LevelChip(level: b.level, extra: pct(b.fill)),
              onTap: () => Navigator.of(context).push(MaterialPageRoute(
                builder: (_) => BinDetailScreen(binId: b.id),
              )),
            ),
        ],
      ),
    );
  }
}
