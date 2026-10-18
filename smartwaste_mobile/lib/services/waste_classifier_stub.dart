import 'dart:typed_data';

import 'classify_result.dart';

const bool supported = false;
bool get ready => false;
const String? loadError =
    'On-device Scan needs an Android phone (or Windows desktop).\n'
    'Chrome cannot run the TensorFlow Lite model.\n\n'
    'Use the other tabs here, or run:  flutter run -d windows';

Future<void> load() async {}

Future<ClassifyResult> run(Uint8List bytes) {
  throw UnsupportedError(loadError!);
}

void close() {}
