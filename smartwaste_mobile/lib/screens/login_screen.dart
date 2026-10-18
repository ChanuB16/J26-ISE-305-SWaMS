import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/auth_service.dart';
import '../services/firebase_rest.dart';
import '../services/session.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabs;
  bool _hasOfficer = true;
  bool _checked = false;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 3, vsync: this);
    _checkOfficer();
  }

  Future<void> _checkOfficer() async {
    try {
      final ok = await AuthService.instance.hasOfficer();
      if (!mounted) return;
      setState(() {
        _hasOfficer = ok;
        _checked = true;
        if (!ok) _tabs.animateTo(2); // jump to Setup tab first time
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _checked = true);
    }
  }

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            const SizedBox(height: 24),
            Icon(Icons.recycling, size: 64, color: theme.colorScheme.primary),
            const SizedBox(height: 8),
            Text('SmartWaste LK',
                style: theme.textTheme.headlineSmall
                    ?.copyWith(fontWeight: FontWeight.bold)),
            const Text('Kaduwela Municipal Council'),
            const SizedBox(height: 16),
            TabBar(
              controller: _tabs,
              labelColor: theme.colorScheme.primary,
              tabs: const [
                Tab(text: 'Citizen'),
                Tab(text: 'Staff'),
                Tab(text: 'First setup'),
              ],
            ),
            if (!_checked) const LinearProgressIndicator(),
            Expanded(
              child: TabBarView(
                controller: _tabs,
                children: [
                  const _CitizenLogin(),
                  const _StaffLogin(),
                  _SetupTab(disabled: _hasOfficer),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ---------- Citizen tab (login + signup toggle) ----------

class _CitizenLogin extends StatefulWidget {
  const _CitizenLogin();
  @override
  State<_CitizenLogin> createState() => _CitizenLoginState();
}

class _CitizenLoginState extends State<_CitizenLogin> {
  bool _signUp = false;
  final _user = TextEditingController();
  final _pass = TextEditingController();
  final _pass2 = TextEditingController();
  final _name = TextEditingController();
  bool _busy = false;
  String? _msg;

  @override
  void dispose() {
    _user.dispose();
    _pass.dispose();
    _pass2.dispose();
    _name.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() {
      _busy = true;
      _msg = null;
    });
    try {
      if (_signUp) {
        if (_pass.text != _pass2.text) {
          throw AuthException('The two passwords are not the same.');
        }
        final u = await AuthService.instance.signUp(
          username: _user.text,
          password: _pass.text,
          displayName: _name.text,
          role: 'citizen',
        );
        await context.read<Session>().setUser(u);
      } else {
        final u = await AuthService.instance.login(_user.text, _pass.text);
        if (u.role != 'citizen') {
          throw AuthException(
              'Use the Staff tab for driver/officer accounts.');
        }
        await context.read<Session>().setUser(u);
      }
    } on AuthException catch (e) {
      setState(() => _msg = e.message);
    } on DbError catch (e) {
      setState(() => _msg = e.message);
    } catch (e) {
      setState(() => _msg = 'Unexpected error: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        children: [
          SegmentedButton<bool>(
            segments: const [
              ButtonSegment(value: false, label: Text('Log in')),
              ButtonSegment(value: true, label: Text('Sign up')),
            ],
            selected: {_signUp},
            onSelectionChanged: (s) => setState(() => _signUp = s.first),
          ),
          const SizedBox(height: 16),
          if (_signUp)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: TextField(
                controller: _name,
                decoration: const InputDecoration(
                    labelText: 'Your name', prefixIcon: Icon(Icons.badge)),
              ),
            ),
          TextField(
            controller: _user,
            autocorrect: false,
            decoration: const InputDecoration(
                labelText: 'User name', prefixIcon: Icon(Icons.person)),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _pass,
            obscureText: true,
            decoration: const InputDecoration(
                labelText: 'Password', prefixIcon: Icon(Icons.lock)),
          ),
          if (_signUp) ...[
            const SizedBox(height: 12),
            TextField(
              controller: _pass2,
              obscureText: true,
              decoration: const InputDecoration(
                  labelText: 'Password again',
                  prefixIcon: Icon(Icons.lock_outline)),
            ),
          ],
          if (_msg != null) ...[
            const SizedBox(height: 12),
            Text(_msg!, style: const TextStyle(color: Colors.red)),
          ],
          const SizedBox(height: 16),
          FilledButton(
            onPressed: _busy ? null : _submit,
            child: _busy
                ? const SizedBox(
                    height: 20, width: 20,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : Text(_signUp ? 'Create account' : 'Log in'),
          ),
        ],
      ),
    );
  }
}

// ---------- Staff tab (officer or driver) ----------

class _StaffLogin extends StatefulWidget {
  const _StaffLogin();
  @override
  State<_StaffLogin> createState() => _StaffLoginState();
}

class _StaffLoginState extends State<_StaffLogin> {
  final _user = TextEditingController();
  final _pass = TextEditingController();
  bool _busy = false;
  String? _msg;

  @override
  void dispose() {
    _user.dispose();
    _pass.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() {
      _busy = true;
      _msg = null;
    });
    try {
      final u = await AuthService.instance.login(_user.text, _pass.text);
      if (u.role == 'citizen') {
        throw AuthException('Use the Citizen tab for your account.');
      }
      await context.read<Session>().setUser(u);
    } on AuthException catch (e) {
      setState(() => _msg = e.message);
    } on DbError catch (e) {
      setState(() => _msg = e.message);
    } catch (e) {
      setState(() => _msg = 'Unexpected error: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        children: [
          const SizedBox(height: 8),
          const Text(
            'Municipal officers and truck drivers.\n'
            'Officers can add staff accounts from the Staff page in this app.',
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _user,
            autocorrect: false,
            decoration: const InputDecoration(
                labelText: 'User name', prefixIcon: Icon(Icons.badge)),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _pass,
            obscureText: true,
            decoration: const InputDecoration(
                labelText: 'Password', prefixIcon: Icon(Icons.lock)),
          ),
          if (_msg != null) ...[
            const SizedBox(height: 12),
            Text(_msg!, style: const TextStyle(color: Colors.red)),
          ],
          const SizedBox(height: 16),
          FilledButton(
            onPressed: _busy ? null : _submit,
            child: _busy
                ? const SizedBox(
                    height: 20, width: 20,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('Log in'),
          ),
        ],
      ),
    );
  }
}

// ---------- First-time setup tab (make the first officer) ----------

class _SetupTab extends StatefulWidget {
  final bool disabled;
  const _SetupTab({required this.disabled});
  @override
  State<_SetupTab> createState() => _SetupTabState();
}

class _SetupTabState extends State<_SetupTab> {
  final _user = TextEditingController();
  final _pass = TextEditingController();
  final _pass2 = TextEditingController();
  final _name = TextEditingController();
  bool _busy = false;
  String? _msg;

  @override
  void dispose() {
    _user.dispose();
    _pass.dispose();
    _pass2.dispose();
    _name.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() {
      _busy = true;
      _msg = null;
    });
    try {
      if (_pass.text != _pass2.text) {
        throw AuthException('The two passwords are not the same.');
      }
      final u = await AuthService.instance.signUp(
        username: _user.text,
        password: _pass.text,
        displayName: _name.text,
        role: 'officer',
      );
      await context.read<Session>().setUser(u);
    } on AuthException catch (e) {
      setState(() => _msg = e.message);
    } on DbError catch (e) {
      setState(() => _msg = e.message);
    } catch (e) {
      setState(() => _msg = 'Unexpected error: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (widget.disabled) {
      return const Padding(
        padding: EdgeInsets.all(24),
        child: Text(
          'An officer account already exists. Use the Staff tab to log in.',
          textAlign: TextAlign.center,
        ),
      );
    }
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        children: [
          const SizedBox(height: 8),
          const Text(
            'No officer account exists yet. Create the first one here. '
            'From then on, officers add more accounts from the website System page.',
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _name,
            decoration: const InputDecoration(
                labelText: 'Officer name', prefixIcon: Icon(Icons.badge)),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _user,
            autocorrect: false,
            decoration: const InputDecoration(
                labelText: 'User name', prefixIcon: Icon(Icons.person)),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _pass,
            obscureText: true,
            decoration: const InputDecoration(
                labelText: 'Password (8+ chars)',
                prefixIcon: Icon(Icons.lock)),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _pass2,
            obscureText: true,
            decoration: const InputDecoration(
                labelText: 'Password again',
                prefixIcon: Icon(Icons.lock_outline)),
          ),
          if (_msg != null) ...[
            const SizedBox(height: 12),
            Text(_msg!, style: const TextStyle(color: Colors.red)),
          ],
          const SizedBox(height: 16),
          FilledButton(
            onPressed: _busy ? null : _submit,
            child: _busy
                ? const SizedBox(
                    height: 20, width: 20,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('Create officer account'),
          ),
        ],
      ),
    );
  }
}
