/// On-device waste classifier.
///
/// TensorFlow Lite uses dart:ffi, which Chrome/web does not have.
/// Android and Windows use the real model; web gets a stub.
library;

import 'dart:typed_data';

import 'classify_result.dart';
import 'waste_classifier_stub.dart'
    if (dart.library.ffi) 'waste_classifier_io.dart' as impl;

export 'classify_result.dart';

class WasteClassifier {
  WasteClassifier._();

  static bool get supported => impl.supported;
  static bool get ready => impl.ready;
  static String? get loadError => impl.loadError;

  static Future<void> load() => impl.load();
  static Future<ClassifyResult> run(Uint8List bytes) => impl.run(bytes);
  static void close() => impl.close();
}
