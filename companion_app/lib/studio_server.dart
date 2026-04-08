import 'dart:async';
import 'dart:typed_data';
import 'dart:io';
import 'dart:convert';
import 'package:shelf/shelf.dart';
import 'package:shelf/shelf_io.dart' as io;
import 'package:shelf_router/shelf_router.dart';
typedef CameraFrameCallback = Future<Uint8List?> Function();
typedef SensorDataCallback = Map<String, dynamic> Function();
typedef ControlCallback = Future<void> Function(String action, dynamic value);

class StudioWebServer {
  final CameraFrameCallback onFrameRequest;
  final SensorDataCallback onSensorRequest;
  final ControlCallback onControl;
  HttpServer? _server;

  StudioWebServer({
    required this.onFrameRequest, 
    required this.onSensorRequest,
    required this.onControl
  });

  Future<void> start(int port) async {
    final router = Router();

    // MJPEG Stream endpoint
    router.get('/video', (Request request) async {
      // ... same logic ...

      final controller = StreamController<List<int>>();
      
      Timer.periodic(const Duration(milliseconds: 100), (timer) async {
        if (controller.isClosed) {
          timer.cancel();
          return;
        }
        final frame = await onFrameRequest();
        if (frame != null) {
          controller.add('--boundary\r\n'.codeUnits);
          controller.add('Content-Type: image/jpeg\r\n'.codeUnits);
          controller.add('Content-Length: ${frame.length}\r\n\r\n'.codeUnits);
          controller.add(frame);
          controller.add('\r\n'.codeUnits);
        }
      });

      return Response.ok(
        controller.stream,
        headers: {
          'Content-Type': 'multipart/x-mixed-replace; boundary=boundary',
          'Cache-Control': 'no-cache',
          'Connection': 'close',
          'Pragma': 'no-cache',
        },
      );
    });

    // Control endpoint
    router.post('/control', (Request request) async {
      final payload = await request.readAsString();
      onControl('action', payload); 
      return Response.ok('OK');
    });

    // Single high-res capture endpoint (full camera resolution)
    router.get('/capture', (Request request) async {
      final frame = await onFrameRequest();
      if (frame == null) {
        return Response.internalServerError(body: 'Camera not ready');
      }
      return Response.ok(
        frame,
        headers: {
          'Content-Type': 'image/jpeg',
          'Content-Length': '${frame.length}',
          'Cache-Control': 'no-cache',
        },
      );
    });

    // Sensors endpoint
    router.get('/sensors', (Request request) async {
      final data = onSensorRequest();
      return Response.ok(
        jsonEncode(data),
        headers: {'Content-Type': 'application/json'},
      );
    });

    _server = await io.serve(router, '0.0.0.0', port);
    print('Studio Server running on port ${_server!.port}');
  }

  Future<void> stop() async {
    await _server?.close();
  }
}
