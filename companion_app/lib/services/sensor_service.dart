import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:sensors_plus/sensors_plus.dart';

class SensorService {
  static final SensorService _instance = SensorService._();
  factory SensorService() => _instance;
  SensorService._();

  static SensorService get instance => _instance;

  static const double _smoothingFactor = 0.15;

  final ValueNotifier<double> pitch = ValueNotifier(0.0);
  final ValueNotifier<double> roll = ValueNotifier(0.0);

  double _filteredPitch = 0.0;
  double _filteredRoll = 0.0;

  final Map<String, dynamic> latestValues = {};

  StreamSubscription<AccelerometerEvent>? _subscription;

  void start() {
    _subscription?.cancel();
    _subscription = accelerometerEventStream().listen((event) {
      _filteredPitch += (event.y - _filteredPitch) * _smoothingFactor;
      _filteredRoll += (event.x - _filteredRoll) * _smoothingFactor;
      pitch.value = _filteredPitch;
      roll.value = _filteredRoll;
      latestValues['accel_x'] = event.x;
      latestValues['accel_y'] = event.y;
      latestValues['accel_z'] = event.z;
    });
  }

  void stop() {
    _subscription?.cancel();
    _subscription = null;
  }

  void dispose() {
    stop();
    pitch.dispose();
    roll.dispose();
  }
}
