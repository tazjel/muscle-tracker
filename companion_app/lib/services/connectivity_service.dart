import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import '../config.dart';
import 'api_service.dart';

class ConnectivityService {
  static final ConnectivityService _instance = ConnectivityService._();
  factory ConnectivityService() => _instance;
  ConnectivityService._();

  static ConnectivityService get instance => _instance;

  final ValueNotifier<bool> isOnline = ValueNotifier(true);
  Timer? _timer;

  void start() {
    _timer?.cancel();
    _timer = Timer.periodic(const Duration(seconds: 15), (_) => _check());
    // Run an immediate check instead of waiting 15 s
    _check();
  }

  void stop() {
    _timer?.cancel();
    _timer = null;
  }

  Future<void> _check() async {
    final wasOnline = isOnline.value;
    try {
      await http
          .get(Uri.parse('${AppConfig.serverBaseUrl}/api/health'))
          .timeout(const Duration(seconds: 5));
      isOnline.value = true;
      // Transitioned offline → online: flush queued requests
      if (!wasOnline) {
        ApiService.instance.flushQueue();
      }
    } catch (_) {
      isOnline.value = false;
    }
  }
}
