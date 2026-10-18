import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../models/user.dart';
import '../../services/auth_service.dart';
import '../../services/session.dart';
import '../../widgets/common.dart';

class StaffScreen extends StatefulWidget {
  const StaffScreen({super.key});
  @override
  State<StaffScreen> createState() => _StaffScreenState();
}

class _StaffScreenState extends State<StaffScreen> {
  List<SmartUser> _users = [];
  List<String> _trucks = [];
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
      final users = await AuthService.instance.listStaff();
      final trucks = await AuthService.instance.truckIds();
      if (!mounted) return;
      setState(() {
        _users = users;
        _trucks = trucks;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = 'Could not load staff: $e';
      });
    }
  }

  Future<void> _add() async {
    final user = context.read<Session>().user;
    if (user == null) return;
    final name = TextEditingController();
    final username = TextEditingController();
    final password = TextEditingController();
    var role = 'driver';
    var truck = _trucks.isEmpty ? '' : _trucks.first;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setLocal) => AlertDialog(
          title: const Text('Add staff account'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                    controller: name,
                    decoration: const InputDecoration(labelText: 'Name')),
                const SizedBox(height: 8),
                TextField(
                    controller: username,
                    decoration: const InputDecoration(labelText: 'User name')),
                const SizedBox(height: 8),
                TextField(
                    controller: password,
                    obscureText: true,
                    decoration:
                        const InputDecoration(labelText: 'Password (8+ chars)')),
                const SizedBox(height: 8),
                DropdownButtonFormField<String>(
                  value: role,
                  decoration: const InputDecoration(labelText: 'Role'),
                  items: const [
                    DropdownMenuItem(value: 'driver', child: Text('Truck driver')),
                    DropdownMenuItem(
                        value: 'officer', child: Text('Municipal officer')),
                  ],
                  onChanged: (v) => setLocal(() => role = v ?? 'driver'),
                ),
                if (role == 'driver' && _trucks.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  DropdownButtonFormField<String>(
                    value: truck.isEmpty ? _trucks.first : truck,
                    decoration: const InputDecoration(labelText: 'Truck'),
                    items: [
                      for (final t in _trucks)
                        DropdownMenuItem(value: t, child: Text(t)),
                    ],
                    onChanged: (v) => setLocal(() => truck = v ?? ''),
                  ),
                ],
              ],
            ),
          ),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(ctx, false),
                child: const Text('Cancel')),
            FilledButton(
                onPressed: () => Navigator.pop(ctx, true),
                child: const Text('Create')),
          ],
        ),
      ),
    );
    if (ok != true) return;
    try {
      await AuthService.instance.createStaff(
        username: username.text,
        password: password.text,
        displayName: name.text,
        role: role,
        truck: truck,
      );
      if (!mounted) return;
      showSnack(context, 'Account created.');
      await _reload();
    } on AuthException catch (e) {
      if (!mounted) return;
      showSnack(context, e.message, isError: true);
    } catch (e) {
      if (!mounted) return;
      showSnack(context, 'Could not create: $e', isError: true);
    }
  }

  Future<void> _toggle(SmartUser u) async {
    final me = context.read<Session>().user?.username ?? '';
    try {
      await AuthService.instance.updateStaff(
        u.username,
        active: !u.active,
        actor: me,
      );
      await _reload();
    } on AuthException catch (e) {
      if (!mounted) return;
      showSnack(context, e.message, isError: true);
    }
  }

  Future<void> _password(SmartUser u) async {
    final me = context.read<Session>().user?.username ?? '';
    final pass = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('New password for ${u.username}'),
        content: TextField(
          controller: pass,
          obscureText: true,
          decoration: const InputDecoration(labelText: 'Password (8+ chars)'),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Save')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await AuthService.instance.updateStaff(
        u.username,
        password: pass.text,
        actor: me,
      );
      if (!mounted) return;
      showSnack(context, 'Password changed.');
    } on AuthException catch (e) {
      if (!mounted) return;
      showSnack(context, e.message, isError: true);
    }
  }

  Future<void> _remove(SmartUser u) async {
    final me = context.read<Session>().user?.username ?? '';
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Remove ${u.username}?'),
        content: const Text('This staff account will be deleted.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Remove')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await AuthService.instance.deleteStaff(u.username, actor: me);
      if (!mounted) return;
      showSnack(context, 'Removed.');
      await _reload();
    } on AuthException catch (e) {
      if (!mounted) return;
      showSnack(context, e.message, isError: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) return ErrorRetry(message: _error!, onRetry: _reload);
    return RefreshIndicator(
      onRefresh: _reload,
      child: ListView(
        padding: const EdgeInsets.only(bottom: 24),
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: FilledButton.icon(
              onPressed: _add,
              icon: const Icon(Icons.person_add),
              label: const Text('Add officer or driver'),
            ),
          ),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 16),
            child: Text(
              'ML jobs (forecast, live routes, rewards) still start from the website System page. '
              'This screen only manages staff logins.',
            ),
          ),
          const SizedBox(height: 8),
          for (final u in _users)
            ListTile(
              leading: Icon(u.role == 'driver'
                  ? Icons.local_shipping
                  : Icons.admin_panel_settings),
              title: Text('${u.name}  (${u.username})'),
              subtitle: Text([
                u.role,
                if (u.truck.isNotEmpty) 'truck ${u.truck}',
                u.active ? 'active' : 'switched off',
              ].join(' · ')),
              trailing: PopupMenuButton<String>(
                onSelected: (v) {
                  if (v == 'toggle') _toggle(u);
                  if (v == 'password') _password(u);
                  if (v == 'delete') _remove(u);
                },
                itemBuilder: (ctx) => [
                  PopupMenuItem(
                    value: 'toggle',
                    child: Text(u.active ? 'Switch off' : 'Switch on'),
                  ),
                  const PopupMenuItem(
                      value: 'password', child: Text('Change password')),
                  const PopupMenuItem(value: 'delete', child: Text('Remove')),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
