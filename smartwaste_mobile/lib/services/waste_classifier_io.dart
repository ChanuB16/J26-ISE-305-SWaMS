import 'package:flutter/services.dart';
import 'package:image/image.dart' as img;
import 'package:tflite_flutter/tflite_flutter.dart';

import '../config.dart';
import 'classify_result.dart';

const bool supported = true;

Interpreter? _interp;
List<String> _labels = const [];
String? _loadError;

bool get ready => _interp != null;
String? get loadError => _loadError;

Future<void> load() async {
  _loadError = null;
  try {
    _interp = await Interpreter.fromAsset(AppConfig.classifierModelAsset);
    final labelsRaw = await rootBundle.loadString(AppConfig.classifierLabelsAsset);
    _labels = labelsRaw
        .split('\n')
        .map((s) => s.trim())
        .where((s) => s.isNotEmpty)
        .toList();
  } catch (e) {
    _interp = null;
    _loadError =
        'The scan model is not installed on this build.\n'
        'See scripts/convert_model_to_tflite.py.\n\nDetails: $e';
  }
}

Future<ClassifyResult> run(Uint8List bytes) async {
  final interp = _interp;
  if (interp == null) throw StateError('Classifier is not loaded.');
  final decoded = img.decodeImage(bytes);
  if (decoded == null) throw StateError('Could not read the photo.');
  final resized = img.copyResize(decoded, width: 224, height: 224);
  final input = [
    List.generate(224, (y) {
      return List.generate(224, (x) {
        final p = resized.getPixel(x, y);
        return [
          p.rNormalized.toDouble(),
          p.gNormalized.toDouble(),
          p.bNormalized.toDouble(),
        ];
      });
    }),
  ];
  final output = List.filled(_labels.length, 0.0).reshape([1, _labels.length]);
  interp.run(input, output);
  final probs = (output[0] as List).cast<double>();
  var bestIdx = 0;
  var bestP = probs[0];
  for (var i = 1; i < probs.length; i++) {
    if (probs[i] > bestP) {
      bestP = probs[i];
      bestIdx = i;
    }
  }
  final label = _labels[bestIdx];
  return ClassifyResult(
    category: label,
    confidence: bestP,
    reliable: bestP >= AppConfig.classifierSureLevel,
    tip: _tip(label),
  );
}

void close() {
  _interp?.close();
  _interp = null;
}

String _tip(String label) {
  switch (label.toLowerCase()) {
    case 'plastic':
      return 'Rinse, flatten and put in the recycling bin (green).';
    case 'paper':
      return 'Keep dry, flatten and put in the paper collection.';
    case 'glass':
      return 'Rinse carefully, remove the cap, put in the glass bin.';
    case 'metal':
      return 'Rinse cans and put in the metal collection.';
    case 'organic':
      return 'Compost at home or put in the food-waste bin.';
    default:
      return 'Put it in the general-waste bin if you are not sure.';
  }
}
