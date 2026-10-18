import 'dart:io';

import 'package:path_provider/path_provider.dart';

const _fileName = 'smartwaste_session.json';

Future<String?> loadSessionJson() async {
  final dir = await getApplicationDocumentsDirectory();
  final file = File('${dir.path}/$_fileName');
  if (!await file.exists()) return null;
  return file.readAsString();
}

Future<void> saveSessionJson(String? json) async {
  final dir = await getApplicationDocumentsDirectory();
  final file = File('${dir.path}/$_fileName');
  if (json == null) {
    if (await file.exists()) await file.delete();
    return;
  }
  await file.writeAsString(json, flush: true);
}
