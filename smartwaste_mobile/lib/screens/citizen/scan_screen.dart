import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';

import '../../services/firebase_rest.dart';
import '../../services/session.dart';
import '../../services/waste_classifier.dart';

/// Citizen "Scan rubbish" page.
///
/// On Android / Windows this runs TensorFlow Lite on-device. Chrome/web
/// cannot load that library, so the tab explains how to run it on a phone.
class CitizenScanScreen extends StatefulWidget {
  const CitizenScanScreen({super.key});
  @override
  State<CitizenScanScreen> createState() => _CitizenScanScreenState();
}

class _CitizenScanScreenState extends State<CitizenScanScreen> {
  bool _loading = true;
  String? _loadError;
  Uint8List? _photo;
  ClassifyResult? _result;
  String? _runError;
  bool _running = false;

  @override
  void initState() {
    super.initState();
    _loadModel();
  }

  Future<void> _loadModel() async {
    await WasteClassifier.load();
    if (!mounted) return;
    setState(() {
      _loading = false;
      _loadError = WasteClassifier.loadError;
    });
  }

  Future<void> _pick(ImageSource src) async {
    final picker = ImagePicker();
    final x = await picker.pickImage(
        source: src, maxWidth: 512, maxHeight: 512, imageQuality: 85);
    if (x == null) return;
    final bytes = await x.readAsBytes();
    setState(() {
      _photo = bytes;
      _result = null;
      _runError = null;
    });
    await _classify();
  }

  Future<void> _classify() async {
    if (_photo == null || !WasteClassifier.ready) return;
    setState(() => _running = true);
    try {
      final result = await WasteClassifier.run(_photo!);
      if (!mounted) return;
      setState(() => _result = result);
      if (result.reliable) {
        final user = context.read<Session>().user;
        if (user != null) {
          try {
            await FirebaseRest.instance.post('classifications', {
              'user': user.username,
              'name': user.name,
              'waste_type': result.category,
              'confidence': result.confidence,
              'ts': FirebaseRest.serverTimestamp(),
              'source': 'mobile app',
            });
          } catch (_) {}
        }
      }
    } catch (e) {
      setState(() => _runError = 'Could not classify: $e');
    } finally {
      if (mounted) setState(() => _running = false);
    }
  }

  @override
  void dispose() {
    WasteClassifier.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_loadError != null) {
      return Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.info_outline, size: 48, color: Colors.grey),
            const SizedBox(height: 12),
            Text(_loadError!, textAlign: TextAlign.center),
          ],
        ),
      );
    }
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text(
            'Take or choose a photo of ONE item. The AI will say what '
            'type of rubbish it is.',
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 16),
          if (_photo != null)
            ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: Image.memory(_photo!, height: 220, fit: BoxFit.cover),
            ),
          const SizedBox(height: 12),
          Row(children: [
            Expanded(
              child: FilledButton.icon(
                onPressed: _running ? null : () => _pick(ImageSource.camera),
                icon: const Icon(Icons.photo_camera),
                label: const Text('Camera'),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: OutlinedButton.icon(
                onPressed: _running ? null : () => _pick(ImageSource.gallery),
                icon: const Icon(Icons.photo_library),
                label: const Text('Gallery'),
              ),
            ),
          ]),
          const SizedBox(height: 16),
          if (_running) const Center(child: CircularProgressIndicator()),
          if (_runError != null)
            Card(
              color: Colors.red.shade50,
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Text(_runError!),
              ),
            ),
          if (_result != null) _ResultCard(result: _result!),
        ],
      ),
    );
  }
}

class _ResultCard extends StatelessWidget {
  final ClassifyResult result;
  const _ResultCard({required this.result});
  @override
  Widget build(BuildContext context) {
    final conf = (result.confidence * 100).toStringAsFixed(0);
    return Card(
      color: result.reliable ? Colors.green.shade50 : Colors.orange.shade50,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              result.category.toUpperCase(),
              style: Theme.of(context).textTheme.titleLarge,
            ),
            Text('Confidence: $conf%'),
            const SizedBox(height: 8),
            Text(result.tip),
            const SizedBox(height: 8),
            Text(
              result.reliable
                  ? '+10 green points added after an officer confirms.'
                  : 'The AI is not sure. Try a clearer photo of a single item.',
              style: TextStyle(
                  color: result.reliable ? Colors.green : Colors.orange),
            ),
          ],
        ),
      ),
    );
  }
}
