import 'package:flutter/material.dart';

import '../theme.dart';

class ErrorRetry extends StatelessWidget {
  final String message;
  final Future<void> Function() onRetry;
  const ErrorRetry({super.key, required this.message, required this.onRetry});

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

class KpiTile extends StatelessWidget {
  final String label;
  final String value;
  final String sub;
  final Color? color;
  final IconData icon;
  const KpiTile({
    super.key,
    required this.label,
    required this.value,
    this.sub = '',
    this.color,
    this.icon = Icons.analytics,
  });

  @override
  Widget build(BuildContext context) {
    final c = color ?? Theme.of(context).colorScheme.primary;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              Icon(icon, size: 18, color: c),
              const SizedBox(width: 6),
              Expanded(
                child: Text(label,
                    style: Theme.of(context).textTheme.labelMedium,
                    overflow: TextOverflow.ellipsis),
              ),
            ]),
            const SizedBox(height: 6),
            Text(value,
                style: Theme.of(context)
                    .textTheme
                    .headlineSmall
                    ?.copyWith(fontWeight: FontWeight.bold, color: c)),
            if (sub.isNotEmpty)
              Text(sub, style: Theme.of(context).textTheme.bodySmall),
          ],
        ),
      ),
    );
  }
}

class LevelChip extends StatelessWidget {
  final String level;
  final String? extra;
  const LevelChip({super.key, required this.level, this.extra});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: FillColors.forLevel(level),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Text(
        '${FillColors.symbolFor(level)} ${extra ?? FillColors.wordFor(level)}',
        style: const TextStyle(
            color: Colors.white, fontWeight: FontWeight.bold, fontSize: 12),
      ),
    );
  }
}

class RiskChip extends StatelessWidget {
  final String risk;
  const RiskChip({super.key, required this.risk});

  @override
  Widget build(BuildContext context) {
    final r = risk.toLowerCase();
    final color = r == 'high'
        ? FillColors.critical
        : r == 'medium'
            ? FillColors.warning
            : r == 'low'
                ? FillColors.normal
                : Colors.grey;
    return Chip(
      visualDensity: VisualDensity.compact,
      backgroundColor: color.withOpacity(0.15),
      label: Text(risk.isEmpty ? 'no risk' : '$risk overflow',
          style: TextStyle(color: color, fontSize: 12)),
    );
  }
}

void showSnack(BuildContext context, String msg, {bool isError = false}) {
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
    content: Text(msg),
    backgroundColor: isError ? Colors.red : null,
  ));
}
