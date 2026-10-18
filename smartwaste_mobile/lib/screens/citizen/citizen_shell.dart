import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../services/session.dart';
import '../usability_screen.dart';
import 'home_screen.dart';
import 'report_screen.dart';
import 'rewards_screen.dart';
import 'scan_screen.dart' deferred as scan;

/// Bottom-nav shell: Home / Report / Scan / Rewards.
///
/// Mirrors the citizen pages in the Flask app (templates/citizen/).
class CitizenShell extends StatefulWidget {
  const CitizenShell({super.key});
  @override
  State<CitizenShell> createState() => _CitizenShellState();
}

class _CitizenShellState extends State<CitizenShell> {
  int _tab = 0;
  bool _scanReady = false;
  Object? _scanError;

  static const _titles = <String>['Find a bin', 'Report a problem', 'Scan rubbish', 'My rewards'];

  Future<void> _ensureScan() async {
    if (_scanReady || _scanError != null) return;
    try {
      await scan.loadLibrary();
      if (mounted) setState(() => _scanReady = true);
    } catch (e) {
      if (mounted) setState(() => _scanError = e);
    }
  }

  Widget _scanTab() {
    if (_scanError != null) {
      return Padding(
        padding: const EdgeInsets.all(24),
        child: Text(
          'Scan is not available on this phone.\n\n$_scanError',
          textAlign: TextAlign.center,
        ),
      );
    }
    if (!_scanReady) {
      return const Center(child: CircularProgressIndicator());
    }
    return scan.CitizenScanScreen();
  }

  @override
  Widget build(BuildContext context) {
    final user = context.watch<Session>().user;
    return Scaffold(
      appBar: AppBar(
        title: Text(_titles[_tab]),
        actions: [
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
                child: Text('Signed in as ${user?.name ?? ''}'),
              ),
              const PopupMenuDivider(),
              const PopupMenuItem(value: 'survey', child: Text('Rate this app')),
              const PopupMenuItem(value: 'logout', child: Text('Log out')),
            ],
          ),
        ],
      ),
      body: IndexedStack(
        index: _tab,
        children: [
          const CitizenHomeScreen(),
          const CitizenReportScreen(),
          _scanTab(),
          const CitizenRewardsScreen(),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tab,
        onDestinationSelected: (i) {
          setState(() => _tab = i);
          if (i == 2) _ensureScan();
        },
        destinations: const [
          NavigationDestination(icon: Icon(Icons.home), label: 'Home'),
          NavigationDestination(icon: Icon(Icons.report), label: 'Report'),
          NavigationDestination(icon: Icon(Icons.photo_camera), label: 'Scan'),
          NavigationDestination(icon: Icon(Icons.card_giftcard), label: 'Rewards'),
        ],
      ),
    );
  }
}
