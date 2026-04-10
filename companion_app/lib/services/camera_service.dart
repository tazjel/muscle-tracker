import 'package:camera/camera.dart';

class CameraService {
  static final CameraService _instance = CameraService._();
  factory CameraService() => _instance;
  CameraService._();

  static CameraService get instance => _instance;

  CameraController? _controller;

  CameraController? get controller => _controller;

  bool get isInitialized => _controller?.value.isInitialized ?? false;

  Future<void> initialize([ResolutionPreset preset = ResolutionPreset.max]) async {
    final cameras = await availableCameras();
    if (cameras.isEmpty) return;
    final cam = cameras.firstWhere(
      (c) => c.lensDirection == CameraLensDirection.back,
      orElse: () => cameras.first,
    );
    _controller = CameraController(cam, preset, enableAudio: false);
    await _controller!.initialize();
  }

  Future<XFile> capture() async {
    if (_controller == null || !_controller!.value.isInitialized) {
      throw StateError('Camera not initialized');
    }
    return _controller!.takePicture();
  }

  void toggleTorch() {
    if (_controller == null || !_controller!.value.isInitialized) return;
    final current = _controller!.value.flashMode;
    _controller!.setFlashMode(
      current == FlashMode.torch ? FlashMode.off : FlashMode.torch,
    );
  }

  void dispose() {
    _controller?.dispose();
    _controller = null;
  }
}
