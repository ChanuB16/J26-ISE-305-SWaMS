import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../models/report.dart';
import '../../services/officer_service.dart';
import '../../services/session.dart';
import '../../utils/format.dart';
import '../../widgets/common.dart';

class CommunityScreen extends StatefulWidget {
  const CommunityScreen({super.key});
  @override
  State<CommunityScreen> createState() => _CommunityScreenState();
}

class _CommunityScreenState extends State<CommunityScreen> {
  CommunityData? _data;
  String? _error;
  bool _loading = true;
  String _filter = 'open';

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
      final d = await OfficerService.instance.loadCommunity();
      if (!mounted) return;
      setState(() {
        _data = d;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = 'Could not load community: $e';
      });
    }
  }

  List<CitizenReport> get _reports {
    final all = _data?.reports ?? const <CitizenReport>[];
    switch (_filter) {
      case 'open':
        return all.where((r) => r.status != 'resolved').toList();
      case 'new':
      case 'in_progress':
      case 'resolved':
        return all.where((r) => r.status == _filter).toList();
      default:
        return all;
    }
  }

  Future<void> _setStatus(CitizenReport r, String status) async {
    final user = context.read<Session>().user;
    if (user == null) return;
    try {
      await OfficerService.instance.setReportStatus(r.id, status, user.username);
      showSnack(context, 'Status saved.');
      await _reload();
    } catch (e) {
      if (!mounted) return;
      showSnack(context, 'Could not save: $e', isError: true);
    }
  }

  Future<void> _showPhoto(String id) async {
    try {
      final raw = await OfficerService.instance.reportPhoto(id);
      if (!mounted) return;
      if (raw == null || !raw.contains(',')) {
        showSnack(context, 'No photo for this report.');
        return;
      }
      final bytes = base64Decode(raw.split(',').last);
      await showDialog<void>(
        context: context,
        builder: (ctx) => Dialog(
          child: InteractiveViewer(child: Image.memory(bytes)),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      showSnack(context, 'Could not open photo: $e', isError: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) return ErrorRetry(message: _error!, onRetry: _reload);
    final d = _data!;
    final open = d.reports.where((r) => r.status != 'resolved').length;
    final points = d.users.fold<int>(0, (s, u) => s + u.points);
    final reports = _reports;
    return RefreshIndicator(
      onRefresh: _reload,
      child: ListView(
        padding: const EdgeInsets.only(bottom: 24),
        children: [
          Padding(
            padding: const EdgeInsets.all(8),
            child: GridView.count(
              crossAxisCount: 2,
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              childAspectRatio: 1.7,
              children: [
                KpiTile(
                    icon: Icons.chat,
                    label: 'Open reports',
                    value: '$open',
                    sub: '${d.reports.where((r) => r.status == "new").length} new'),
                KpiTile(
                    icon: Icons.card_giftcard,
                    label: 'Citizens with points',
                    value: '${d.users.length}',
                    sub: '$points points in total'),
                KpiTile(
                    icon: Icons.photo_camera,
                    label: 'Waste photos',
                    value: '${d.photos.length}',
                    sub:
                        '${d.photos.where((p) => (p.confidence ?? 0) >= 0.7).length} earned points'),
                KpiTile(
                    icon: Icons.delete,
                    label: 'Full-bin reports',
                    value:
                        '${d.reports.where((r) => r.type == "overflowing_bin").length}',
                    sub: 'from citizens'),
              ],
            ),
          ),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: Row(
              children: [
                for (final f in const ['open', 'new', 'in_progress', 'resolved', 'all'])
                  Padding(
                    padding: const EdgeInsets.only(right: 6),
                    child: ChoiceChip(
                      label: Text(f.replaceAll('_', ' ')),
                      selected: _filter == f,
                      onSelected: (_) => setState(() => _filter = f),
                    ),
                  ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
            child: Text('Reports (${reports.length})',
                style: Theme.of(context).textTheme.titleMedium),
          ),
          if (reports.isEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 16),
              child: Text('No reports here.'),
            ),
          for (final r in reports)
            Card(
              margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(kReportTypeLabels[r.type] ?? r.type,
                        style: const TextStyle(fontWeight: FontWeight.bold)),
                    Text([
                      timeAgo(r.ts),
                      if (r.binId != null && r.binId!.isNotEmpty) r.binId!,
                      if (r.zone != null && r.zone!.isNotEmpty) r.zone!,
                      if (r.reporterName.isNotEmpty) r.reporterName,
                    ].join(' · ')),
                    if (r.note.isNotEmpty) Text(r.note),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        if (r.hasPhoto)
                          TextButton.icon(
                            onPressed: () => _showPhoto(r.id),
                            icon: const Icon(Icons.photo),
                            label: const Text('Photo'),
                          ),
                        const Spacer(),
                        DropdownButton<String>(
                          value: r.status,
                          items: const [
                            DropdownMenuItem(value: 'new', child: Text('New')),
                            DropdownMenuItem(
                                value: 'in_progress', child: Text('In progress')),
                            DropdownMenuItem(
                                value: 'resolved', child: Text('Resolved')),
                          ],
                          onChanged: (v) {
                            if (v != null && v != r.status) _setStatus(r, v);
                          },
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
            child: Text('Leaderboard',
                style: Theme.of(context).textTheme.titleMedium),
          ),
          if (d.users.isEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 16),
              child: Text('No points yet. Run “Give reward points” on the website.'),
            ),
          for (var i = 0; i < d.users.length && i < 10; i++)
            ListTile(
              leading: CircleAvatar(child: Text('${i + 1}')),
              title: Text(d.users[i].username),
              subtitle: Text(d.users[i].level),
              trailing: Text('${d.users[i].points}',
                  style: const TextStyle(fontWeight: FontWeight.bold)),
            ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
            child: Text('Recent scans',
                style: Theme.of(context).textTheme.titleMedium),
          ),
          if (d.photos.isEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 16),
              child: Text('No scan photos yet.'),
            ),
          for (final p in d.photos.take(15))
            ListTile(
              dense: true,
              title: Text(p.wasteType),
              subtitle: Text(
                  '${p.user.isEmpty ? "unknown" : p.user} · ${timeAgo(p.ts)}'),
              trailing: Text(p.confidence == null
                  ? ''
                  : '${(p.confidence! * 100).toStringAsFixed(0)}%'),
            ),
        ],
      ),
    );
  }
}
