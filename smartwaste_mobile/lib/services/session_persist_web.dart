// ignore: avoid_web_libraries_in_flutter
import 'dart:html' as html;

const _storageKey = 'smartwaste.user';

Future<String?> loadSessionJson() async {
  return html.window.localStorage[_storageKey];
}

Future<void> saveSessionJson(String? json) async {
  if (json == null) {
    html.window.localStorage.remove(_storageKey);
  } else {
    html.window.localStorage[_storageKey] = json;
  }
}
