import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../../config.dart';
import '../../services/firebase_rest.dart';
import '../../services/session.dart';

/// Citizen "My rewards" page.
///
/// Reads /rewards/<username>, /rewards/<username>/history, and the global
/// leaderboard built from /rewards.
class CitizenRewardsScreen extends StatefulWidget {
  const CitizenRewardsScreen({super.key});
  @override
  State<CitizenRewardsScreen> createState() => _CitizenRewardsScreenState();
}

class _CitizenRewardsScreenState extends State<CitizenRewardsScreen> {
  Future<_RewardsData>? _data;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  void _reload() {
    final user = Session.instance.user;
    if (user == null) return;
    _data = _loadRewards(user.username);
    setState(() {});
  }

  Future<_RewardsData> _loadRewards(String username) async {
    final db = FirebaseRest.instance;
    final mine = await db.get('rewards/$username');
    final all = await db.get('rewards');
    final leaderboard = <_LeaderRow>[];
    if (all is Map) {
      all.forEach((k, v) {
        if (v is Map) {
          leaderboard.add(_LeaderRow(
            username: k.toString(),
            name: (v['name'] as String?) ?? k.toString(),
            points: (v['points'] as num?)?.toInt() ?? 0,
          ));
        }
      });
    }
    leaderboard.sort((a, b) => b.points.compareTo(a.points));

    int points = 0;
    List<_HistoryRow> history = const [];
    if (mine is Map) {
      points = (mine['points'] as num?)?.toInt() ?? 0;
      final h = mine['history'];
      if (h is Map) {
        history = h.entries.map((e) {
          final v = e.value as Map? ?? {};
          return _HistoryRow(
            id: e.key.toString(),
            points: (v['points'] as num?)?.toInt() ?? 0,
            note: (v['note'] as String?) ?? '',
            ts: (v['ts'] as num?)?.toInt(),
            source: (v['source'] as String?) ?? '',
          );
        }).toList()
          ..sort((a, b) => (b.ts ?? 0).compareTo(a.ts ?? 0));
      }
    }
    return _RewardsData(
      points: points,
      history: history.take(20).toList(),
      leaderboard: leaderboard.take(10).toList(),
    );
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: () async => _reload(),
      child: FutureBuilder<_RewardsData>(
        future: _data,
        builder: (ctx, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) {
            return ListView(
              children: [
                const SizedBox(height: 48),
                Center(child: Text('${snap.error}')),
              ],
            );
          }
          final d = snap.data ?? const _RewardsData(points: 0);
          final level = _levelFor(d.points);
          final next = _nextLevel(d.points);
          final progress = next == null
              ? 1.0
              : (d.points - level.key) / (next.key - level.key);

          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Card(
                color: Theme.of(context).colorScheme.primaryContainer,
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('${d.points} green points',
                          style: Theme.of(context).textTheme.headlineMedium),
                      Text('Level: ${level.value}'),
                      const SizedBox(height: 12),
                      LinearProgressIndicator(value: progress.clamp(0.0, 1.0)),
                      const SizedBox(height: 4),
                      Text(next == null
                          ? 'Top level reached — thank you!'
                          : '${next.key - d.points} more points to ${next.value}'),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 16),
              Text('Recent activity',
                  style: Theme.of(context).textTheme.titleMedium),
              if (d.history.isEmpty)
                const Padding(
                  padding: EdgeInsets.all(16),
                  child: Text('No points earned yet. Try scanning rubbish '
                      'or sending a report!'),
                )
              else
                for (final h in d.history) _HistoryTile(row: h),
              const SizedBox(height: 16),
              Text('Top citizens',
                  style: Theme.of(context).textTheme.titleMedium),
              if (d.leaderboard.isEmpty)
                const Padding(
                  padding: EdgeInsets.all(16),
                  child: Text('Leaderboard is empty.'),
                )
              else
                for (var i = 0; i < d.leaderboard.length; i++)
                  ListTile(
                    leading: CircleAvatar(child: Text('${i + 1}')),
                    title: Text(d.leaderboard[i].name),
                    trailing: Text('${d.leaderboard[i].points} pts'),
                  ),
              const SizedBox(height: 24),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: const [
                      Text('How to earn points',
                          style: TextStyle(fontWeight: FontWeight.bold)),
                      SizedBox(height: 8),
                      Text('• Scan a photo of rubbish  +10'),
                      Text('• Send a report that is confirmed  +15'),
                      Text('• Use a bin with space (over time)  bonus'),
                    ],
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  MapEntry<int, String> _levelFor(int points) {
    MapEntry<int, String> current = AppConfig.rewardLevels.first;
    for (final e in AppConfig.rewardLevels) {
      if (points >= e.key) current = e;
    }
    return current;
  }

  MapEntry<int, String>? _nextLevel(int points) {
    for (final e in AppConfig.rewardLevels) {
      if (points < e.key) return e;
    }
    return null;
  }
}

class _RewardsData {
  final int points;
  final List<_HistoryRow> history;
  final List<_LeaderRow> leaderboard;
  const _RewardsData({
    required this.points,
    this.history = const [],
    this.leaderboard = const [],
  });
}

class _HistoryRow {
  final String id;
  final int points;
  final String note;
  final int? ts;
  final String source;
  const _HistoryRow({
    required this.id,
    required this.points,
    required this.note,
    required this.ts,
    required this.source,
  });
}

class _LeaderRow {
  final String username;
  final String name;
  final int points;
  const _LeaderRow({required this.username, required this.name, required this.points});
}

class _HistoryTile extends StatelessWidget {
  final _HistoryRow row;
  const _HistoryTile({required this.row});
  @override
  Widget build(BuildContext context) {
    final when = row.ts == null
        ? ''
        : DateFormat('yyyy-MM-dd HH:mm')
            .format(DateTime.fromMillisecondsSinceEpoch(row.ts!));
    return ListTile(
      leading: const Icon(Icons.eco, color: Colors.green),
      title: Text('${row.points >= 0 ? "+" : ""}${row.points} points'),
      subtitle: Text([
        if (row.note.isNotEmpty) row.note,
        if (row.source.isNotEmpty) row.source,
        if (when.isNotEmpty) when,
      ].join(' \u00B7 ')),
    );
  }
}
