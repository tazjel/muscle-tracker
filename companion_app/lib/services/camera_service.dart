// GTD3D Camera Service — will receive shared CameraController from main.dart
class CameraService {
  static final CameraService _instance = CameraService._();
  factory CameraService() => _instance;
  CameraService._();
}
