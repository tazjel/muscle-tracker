import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'dart:async';
import 'dart:convert';
import 'dart:math';
import 'package:audioplayers/audioplayers.dart';
import 'package:http/http.dart' as http;
import 'package:webview_flutter/webview_flutter.dart';
import '../config.dart';

// Full 360° Body Scan Tab
class BodyScanTab extends StatefulWidget {
  final CameraController controller;
  final double pitch;
  final double roll;
  final Map<String, dynamic> latestSensor;

  const BodyScanTab({
    super.key,
    required this.controller,
    required this.pitch,
    required this.roll,
    required this.latestSensor,
  });

  @override
  State<BodyScanTab> createState() => _BodyScanTabState();
}

class _BodyScanTabState extends State<BodyScanTab> {
  bool fullScanRunning = false;
  int fullScanPass = 0;
  int fullScanFrameCount = 0;
  final int fullScanTotalFrames = 30;
  List<Map<String, dynamic>> fullScanFrames = [];
  String fullScanInstruction = '';
  AudioPlayer? scanAudioPlayer;

  @override
  void dispose() {
    scanAudioPlayer?.dispose();
    super.dispose();
  }

  Future<void> startFullBodyScan() async {
    if (fullScanRunning) return;
    fullScanFrames.clear();
    scanAudioPlayer ??= AudioPlayer();
    setState(() {
      fullScanRunning = true;
      fullScanPass = 0;
      fullScanFrameCount = 0;
      fullScanInstruction = 'PREPARING FULL BODY SCAN...';
    });

    final passes = [
      {'pass': 1, 'distance': 2.5, 'label': '2.5m — FULL BODY'},
      {'pass': 2, 'distance': 1.0, 'label': '1.0m — DETAIL'},
      {'pass': 3, 'distance': 0.5, 'label': '0.5m — SKIN TEXTURE'},
    ];

    for (final passConfig in passes) {
      if (!mounted || !fullScanRunning) return;
      final passNum = passConfig['pass'] as int;
      final distance = passConfig['distance'] as double;
      final label = passConfig['label'] as String;
      setState(() {
        fullScanPass = passNum;
        fullScanInstruction = 'PASS $passNum/3 — $label\nBEGIN ROTATING SLOWLY';
      });

      try { await scanAudioPlayer!.play(AssetSource('audio/pass${passNum}_start.mp3')); } catch (_) {}

      for (int i = 0; i < 10; i++) {
        if (!mounted || !fullScanRunning) return;
        try {
          if (!widget.controller.value.isInitialized) continue;
          if (widget.controller.value.isTakingPicture) {
            await Future.delayed(const Duration(milliseconds: 200));
          }
          final img = await widget.controller.takePicture();

          double compassDeg = 0;
          if (widget.latestSensor.containsKey('mag_x') && widget.latestSensor.containsKey('mag_y')) {
            final mx = (widget.latestSensor['mag_x'] as num?)?.toDouble() ?? 0;
            final my = (widget.latestSensor['mag_y'] as num?)?.toDouble() ?? 0;
            compassDeg = (atan2(my, mx) * 180 / pi) % 360;
          }

          fullScanFrames.add({
            'path': img.path,
            'pass': passNum,
            'distance_m': distance,
            'compass_deg': compassDeg,
            'pitch_deg': widget.pitch,
            'roll_deg': widget.roll,
            'timestamp_ms': DateTime.now().millisecondsSinceEpoch,
          });

          if (!mounted || !fullScanRunning) return;
          setState(() {
            fullScanFrameCount = fullScanFrames.length;
            fullScanInstruction = 'PASS $passNum/3 — $label\nFrame ${i + 1}/10 — KEEP ROTATING';
          });

          if (i % 2 == 1) { try { await scanAudioPlayer!.play(AssetSource('audio/rotate_cue.mp3')); } catch (_) {} }
        } catch (e) {
          debugPrint('Full scan frame capture error: $e');
        }
        await Future.delayed(const Duration(milliseconds: 1500));
      }

      try { await scanAudioPlayer!.play(AssetSource('audio/pass_complete.mp3')); } catch (_) {}

      if (passNum < 3) {
        for (int countdown = 3; countdown >= 1; countdown--) {
          if (!mounted || !fullScanRunning) return;
          final nextLabel = passes[passNum]['label'];
          setState(() { fullScanInstruction = 'MOVE TO $nextLabel\n$countdown seconds...'; });
          await Future.delayed(const Duration(seconds: 1));
        }
      }
    }

    try { await scanAudioPlayer!.play(AssetSource('audio/scan_complete.mp3')); } catch (_) {}
    if (!mounted) return;
    setState(() { fullScanInstruction = 'SCAN COMPLETE — UPLOADING...'; });
    await _uploadFullBodyScan();
  }

  Future<void> _uploadFullBodyScan() async {
    if (fullScanFrames.isEmpty) return;
    try {
      final uri = Uri.parse('${AppConfig.serverBaseUrl}/api/customer/$customerId/body_scan');
      final request = http.MultipartRequest('POST', uri);
      if (jwtToken != null) request.headers['Authorization'] = 'Bearer $jwtToken';

      for (int i = 0; i < fullScanFrames.length; i++) {
        final framePath = fullScanFrames[i]['path'] as String;
        request.files.add(await http.MultipartFile.fromPath(
          'frame_${i.toString().padLeft(3, '0')}',
          framePath,
          filename: 'frame_${i.toString().padLeft(3, '0')}.jpg',
        ));
      }

      final sensorLog = fullScanFrames.map((f) => {
        'pass': f['pass'], 'distance_m': f['distance_m'],
        'compass_deg': f['compass_deg'], 'pitch_deg': f['pitch_deg'],
        'roll_deg': f['roll_deg'], 'timestamp_ms': f['timestamp_ms'],
      }).toList();
      request.fields['sensor_log'] = jsonEncode(sensorLog);

      final passConfig = [
        {'pass': 1, 'distance_m': 2.5, 'frame_indices': List.generate(10, (i) => i)},
        {'pass': 2, 'distance_m': 1.0, 'frame_indices': List.generate(10, (i) => i + 10)},
        {'pass': 3, 'distance_m': 0.5, 'frame_indices': List.generate(10, (i) => i + 20)},
      ];
      request.fields['pass_config'] = jsonEncode(passConfig);

      setState(() { fullScanInstruction = 'UPLOADING ${fullScanFrames.length} FRAMES...'; });

      final response = await request.send();
      final body = await response.stream.bytesToString();

      if (response.statusCode == 200) {
        final result = jsonDecode(body);
        if (!mounted) return;
        setState(() { fullScanRunning = false; fullScanInstruction = 'UPLOAD COMPLETE'; });
        if (result['session_id'] != null) {
          Navigator.of(context).push(MaterialPageRoute(
            builder: (_) => _BodyScanViewerScreen(
              sessionId: result['session_id'],
              viewerUrl: result['viewer_url'],
            ),
          ));
        }
      } else {
        if (!mounted) return;
        setState(() { fullScanInstruction = 'UPLOAD FAILED: $body'; });
      }
    } catch (e) {
      if (mounted) setState(() { fullScanInstruction = 'UPLOAD ERROR: $e'; });
    }
  }

  void cancelFullScan() {
    scanAudioPlayer?.stop();
    setState(() {
      fullScanRunning = false;
      fullScanPass = 0;
      fullScanFrameCount = 0;
      fullScanInstruction = '';
      fullScanFrames.clear();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        child: fullScanRunning ? _buildScanOverlay() : _buildStartUI(),
      ),
    );
  }

  Widget _buildStartUI() {
    return Center(
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        const Icon(Icons.accessibility_new, size: 64, color: AppTheme.primaryTeal),
        const SizedBox(height: 16),
        const Text('FULL BODY SCAN', style: TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.bold, letterSpacing: 2)),
        const SizedBox(height: 8),
        const Text('3-pass 360° scan: 2.5m → 1.0m → 0.5m\n10 frames per pass = 30 frames total',
          textAlign: TextAlign.center, style: TextStyle(color: Colors.white54, fontSize: 13)),
        const SizedBox(height: 32),
        ElevatedButton.icon(
          onPressed: customerId != null ? startFullBodyScan : null,
          icon: const Icon(Icons.view_in_ar, size: 28),
          label: const Text('START FULL BODY SCAN', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
          style: ElevatedButton.styleFrom(
            backgroundColor: Colors.deepPurple,
            foregroundColor: Colors.white,
            padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
          ),
        ),
      ]),
    );
  }

  Widget _buildScanOverlay() {
    return Container(
      padding: const EdgeInsets.all(24),
      color: Colors.black87,
      child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
        Text(fullScanInstruction,
          textAlign: TextAlign.center,
          style: const TextStyle(color: Colors.white, fontSize: 24, fontWeight: FontWeight.bold)),
        const SizedBox(height: 16),
        LinearProgressIndicator(
          value: fullScanTotalFrames > 0 ? fullScanFrameCount / fullScanTotalFrames : 0,
          backgroundColor: Colors.white24,
          valueColor: const AlwaysStoppedAnimation(Colors.deepPurple),
        ),
        const SizedBox(height: 8),
        Text('$fullScanFrameCount / $fullScanTotalFrames frames',
          style: const TextStyle(color: Colors.white70, fontSize: 16)),
        const SizedBox(height: 16),
        TextButton(
          onPressed: cancelFullScan,
          child: const Text('CANCEL', style: TextStyle(color: Colors.redAccent, fontSize: 18)),
        ),
      ]),
    );
  }
}

class _BodyScanViewerScreen extends StatelessWidget {
  final String sessionId;
  final String? viewerUrl;
  const _BodyScanViewerScreen({required this.sessionId, this.viewerUrl});
  @override
  Widget build(BuildContext context) {
    final url = viewerUrl != null
        ? 'http://192.168.100.7:8000$viewerUrl'
        : 'http://192.168.100.7:8000${AppConfig.serverBaseUrl}/api/body_scan/$sessionId/viewer';
    return Scaffold(
      appBar: AppBar(title: const Text('3D Body Viewer'), backgroundColor: Colors.deepPurple),
      body: WebViewWidget(
        controller: WebViewController()
          ..setJavaScriptMode(JavaScriptMode.unrestricted)
          ..loadRequest(Uri.parse(url)),
      ),
    );
  }
}
