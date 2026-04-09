// GTD3D Sensor Service — will receive accelerometer/gyro/magnetometer from main.dart
class SensorService {
  static final SensorService _instance = SensorService._();
  factory SensorService() => _instance;
  SensorService._();
}
