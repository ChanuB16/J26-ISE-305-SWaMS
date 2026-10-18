import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../config.dart';
import '../services/firebase_rest.dart';
import '../services/session.dart';

/// SUS questionnaire — same 10 questions as the website /usability page.
class UsabilityScreen extends StatefulWidget {
  const UsabilityScreen({super.key});
  @override
  State<UsabilityScreen> createState() => _UsabilityScreenState();
}

class _UsabilityScreenState extends State<UsabilityScreen> {
  static const _qs = [
    'I think that I would like to use this app frequently.',
    'I found the app unnecessarily complex.',
    'I thought the app was easy to use.',
    'I think that I would need the support of a technical person to be able to use this app.',
    'I found the various functions in this app were well integrated.',
    'I thought there was too much inconsistency in this app.',
    'I would imagine that most people would learn to use this app very quickly.',
    'I found the app very cumbersome to use.',
    'I felt very confident using the app.',
    'I needed to learn a lot of things before I could get going with this app.',
  ];

  final _answers = List<int?>.filled(10, null);
  final _comment = TextEditingController();
  bool _busy = false;
  double? _score;
  String? _msg;

  @override
  void dispose() {
    _comment.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final miss = _answers.indexWhere((a) => a == null);
    if (miss >= 0) {
      setState(() => _msg = 'Please answer question ${miss + 1}.');
      return;
    }
    setState(() {
      _busy = true;
      _msg = null;
    });
    try {
      final answers = _answers.map((a) => a!).toList();
      var raw = 0.0;
      for (var i = 0; i < answers.length; i++) {
        raw += i.isEven ? (answers[i] - 1) : (5 - answers[i]);
      }
      final score = raw * 2.5;
      final user = context.read<Session>().user;
      await FirebaseRest.instance.post('sus', {
        'ts': FirebaseRest.serverTimestamp(),
        'role': user?.role ?? '',
        'user': user?.username ?? '',
        'answers': answers,
        'score': score,
        'comment': _comment.text.trim().length > 500
            ? _comment.text.trim().substring(0, 500)
            : _comment.text.trim(),
      });
      if (!mounted) return;
      setState(() {
        _score = score;
        _msg = 'Thank you! Your answers were saved.';
      });
    } catch (e) {
      setState(() => _msg = 'Could not save: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  String _band(double s) {
    if (s >= 80.3) return 'Excellent';
    if (s >= AppConfig.susTarget) return 'Good – above average';
    if (s >= 51) return 'OK – below average';
    return 'Poor';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Rate this app')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(
            '10 short questions. 1 = strongly disagree, 5 = strongly agree. '
            'Target score: ${AppConfig.susTarget}+.',
            style: Theme.of(context).textTheme.bodyMedium,
          ),
          const SizedBox(height: 12),
          for (var i = 0; i < _qs.length; i++) ...[
            Text('${i + 1}. ${_qs[i]}',
                style: const TextStyle(fontWeight: FontWeight.w600)),
            const SizedBox(height: 6),
            SegmentedButton<int>(
              segments: const [
                ButtonSegment(value: 1, label: Text('1')),
                ButtonSegment(value: 2, label: Text('2')),
                ButtonSegment(value: 3, label: Text('3')),
                ButtonSegment(value: 4, label: Text('4')),
                ButtonSegment(value: 5, label: Text('5')),
              ],
              emptySelectionAllowed: true,
              selected: {
                if (_answers[i] != null) _answers[i]!,
              },
              onSelectionChanged: _score != null
                  ? null
                  : (s) => setState(() => _answers[i] = s.isEmpty ? null : s.first),
            ),
            const SizedBox(height: 16),
          ],
          TextField(
            controller: _comment,
            enabled: _score == null,
            maxLines: 3,
            decoration: const InputDecoration(
              labelText: 'Anything else? (optional)',
            ),
          ),
          if (_msg != null) ...[
            const SizedBox(height: 12),
            Text(_msg!,
                style: TextStyle(
                    color: _score != null ? Colors.green.shade800 : Colors.red)),
          ],
          if (_score != null) ...[
            const SizedBox(height: 12),
            Text('Your score: ${_score!.toStringAsFixed(1)}',
                style: Theme.of(context).textTheme.headlineSmall),
            Text(_band(_score!)),
          ],
          const SizedBox(height: 16),
          FilledButton(
            onPressed: _busy || _score != null ? null : _submit,
            child: _busy
                ? const SizedBox(
                    height: 20,
                    width: 20,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('Send answers'),
          ),
        ],
      ),
    );
  }
}
