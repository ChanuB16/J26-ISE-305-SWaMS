import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../services/session.dart';
import '../driver/driver_screen.dart';
import '../usability_screen.dart';
import 'bins_screen.dart';
import 'community_screen.dart';
import 'forecast_screen.dart';
import 'operations_screen.dart';
import 'routes_screen.dart';
import 'staff_screen.dart';

/// Staff (officer) shell — same jobs as the website officer pages.
class OfficerShell extends StatefulWidget {
  const OfficerShell({super.key});
  @override
  State<OfficerShell> createState() => _OfficerShellState();
}

class _OfficerShellState extends State<OfficerShell> {
  int _page = 0;

  static const _titles = [
    'Operations',
    'Bins',
    'Forecast',
    'Routes',
    'Community',
    'Staff accounts',
  ];

  @override
  Widget build(BuildContext context) {
    final user = context.watch<Session>().user;
    return Scaffold(
      appBar: AppBar(
        title: Text(_titles[_page]),
        actions: [
          IconButton(
            icon: const Icon(Icons.star_outline),
            tooltip: 'Rate this app',
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const UsabilityScreen()),
            ),
          ),
        ],
      ),
      drawer: Drawer(
        child: SafeArea(
          child: ListView(
            children: [
              DrawerHeader(
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.primary,
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    const Icon(Icons.recycling, color: Colors.white, size: 36),
                    const SizedBox(height: 8),
                    Text(user?.name ?? 'Officer',
                        style: const TextStyle(
                            color: Colors.white,
                            fontSize: 18,
                            fontWeight: FontWeight.bold)),
                    const Text('Municipal staff',
                        style: TextStyle(color: Colors.white70)),
                  ],
                ),
              ),
              _item(0, Icons.dashboard, 'Operations'),
              _item(1, Icons.delete_outline, 'Bins'),
              _item(2, Icons.calendar_month, 'Forecast'),
              _item(3, Icons.alt_route, 'Routes'),
              _item(4, Icons.groups, 'Community'),
              _item(5, Icons.badge, 'Staff accounts'),
              ListTile(
                leading: const Icon(Icons.local_shipping),
                title: const Text('Driver view'),
                onTap: () {
                  Navigator.pop(context);
                  Navigator.of(context).push(
                    MaterialPageRoute(builder: (_) => const DriverScreen()),
                  );
                },
              ),
              const Divider(),
              ListTile(
                leading: const Icon(Icons.logout),
                title: const Text('Log out'),
                onTap: () {
                  Navigator.pop(context);
                  context.read<Session>().logout();
                },
              ),
            ],
          ),
        ),
      ),
      body: IndexedStack(
        index: _page,
        children: const [
          OperationsScreen(),
          OfficerBinsScreen(),
          ForecastScreen(),
          OfficerRoutesScreen(),
          CommunityScreen(),
          StaffScreen(),
        ],
      ),
    );
  }

  Widget _item(int i, IconData icon, String label) {
    return ListTile(
      leading: Icon(icon),
      title: Text(label),
      selected: _page == i,
      onTap: () {
        setState(() => _page = i);
        Navigator.pop(context);
      },
    );
  }
}
