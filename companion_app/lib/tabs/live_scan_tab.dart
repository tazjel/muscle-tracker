import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'dart:async';
import 'dart:convert';
import 'dart:math';
import 'package:http/http.dart' as http;
import 'package:webview_flutter/webview_flutter.dart';
import '../config.dart';
import '../services/secure_delete.dart';

// Coverage-Guided Live Scan Tab
class LiveScanTab extends StatefulWidget {
  final CameraController controller;
  final double pitch;
  final double roll;
  final Map<String, dynamic> latestSensor;

  const LiveScanTab({
    super.key,
    required this.controller,
    required this.pitch,
    required this.roll,
    required this.latestSensor,
  });

  @override
  State<LiveScanTab> createState() => _LiveScanTabState();
}

class _LiveScanTabState extends State<LiveScanTab> {
  bool liveScanRunning = false;
  bool liveScanStarting = false;
  String liveScanSessionId = '';
  int liveScanFrameCount = 0;
  double liveScanCoveragePct = 0.0;
  Map<String, dynamic> liveScanCoverage = {};
  List<Map<String, dynamic>> liveScanGuidance = [];
  bool liveScanReadyToFinalize = false;
  String liveScanInstruction = '';
  Timer? liveScanPollTimer;
  Timer? liveScanCaptureTimer;
  double liveScanDistanceMin = 0.1;
  double liveScanDistanceMax = 2.5;
  double liveScanCurrentDistance = 2.5;

  @override
  void dispose() {
    liveScanCaptureTimer?.cancel();
    liveScanPollTimer?.cancel();
    super.dispose();
  }

  Future<void> showLiveScanDialog() async {
    double minDist = liveScanDistanceMin;
    double maxDist = liveScanDistanceMax;
    await showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(builder: (ctx, setDlg) => AlertDialog(
        backgroundColor: const Color(0xFF1A1A2E),
        title: const Text('Live Scan Setup', style: TextStyle(color: Colors.white)),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          const Text('Set distance range (meters):', style: TextStyle(color: Colors.white70)),
          const SizedBox(height: 16),
          Row(children: [
            const Text('Min:', style: TextStyle(color: Colors.white70, fontSize: 12)),
            Expanded(child: Slider(
              value: minDist, min: 0.1, max: 1.0, divisions: 9,
              label: '${minDist.toStringAsFixed(1)}m',
              onChanged: (v) => setDlg(() => minDist = v),
            )),
            Text('${minDist.toStringAsFixed(1)}m', style: const TextStyle(color: Colors.white)),
          ]),
          Row(children: [
            const Text('Max:', style: TextStyle(color: Colors.white70, fontSize: 12)),
            Expanded(child: Slider(
              value: maxDist, min: 1.0, max: 3.0, divisions: 20,
              label: '${maxDist.toStringAsFixed(1)}m',
              onChanged: (v) => setDlg(() => maxDist = v),
            )),
            Text('${maxDist.toStringAsFixed(1)}m', style: const TextStyle(color: Colors.white)),
          ]),
          const SizedBox(height: 8),
          const Text('Start far (full body), then move closer for detail.\nRotate 360° slowly.',
            textAlign: TextAlign.center, style: TextStyle(color: Colors.white54, fontSize: 12)),
        ]),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('CANCEL')),
          ElevatedButton(
            style: ElevatedButton.styleFrom(backgroundColor: Colors.tealAccent.shade700),
            onPressed: () {
              Navigator.pop(ctx);
              liveScanDistanceMin = minDist;
              liveScanDistanceMax = maxDist;
              liveScanCurrentDistance = maxDist;
              startLiveScan();
            },
            child: const Text('START SCAN'),
          ),
        ],
      )),
    );
  }

  Future<void> startLiveScan() async {
    if (liveScanRunning || liveScanStarting) return;
    liveScanStarting = true;

    final uri = Uri.parse('${AppConfig.serverBaseUrl}/api/customer/$customerId/live_scan/start');
    try {
      final resp = await http.post(uri,
        headers: {'Content-Type': 'application/json', if (jwtToken != null) 'Authorization': 'Bearer $jwtToken'},
        body: jsonEncode({'distance_min_m': liveScanDistanceMin, 'distance_max_m': liveScanDistanceMax}),
      );
      final result = jsonDecode(resp.body);
      if (result['status'] != 'ok') {
        liveScanStarting = false;
        return;
      }

      setState(() {
        liveScanRunning = true;
        liveScanStarting = false;
        liveScanSessionId = result['session_id'];
        liveScanFrameCount = 0;
        liveScanCoveragePct = 0;
        liveScanReadyToFinalize = false;
        liveScanGuidance = [];
        liveScanInstruction = 'ROTATE SLOWLY — CAPTURING...';
      });

      liveScanCaptureTimer = Timer.periodic(const Duration(seconds: 2), (_) => _captureLiveFrame());
      liveScanPollTimer = Timer.periodic(const Duration(seconds: 3), (_) => _pollLiveScanStatus());
    } catch (e) {
      liveScanStarting = false;
    }
  }

  Future<void> _captureLiveFrame() async {
    if (!liveScanRunning || !mounted) return;
    if (widget.controller.value.isInitialized != true) return;
    if (widget.controller.value.isTakingPicture) return;

    try {
      final img = await widget.controller.takePicture();

      double compassDeg = 0;
      if (widget.latestSensor.containsKey('mag_x') && widget.latestSensor.containsKey('mag_y')) {
        final mx = (widget.latestSensor['mag_x'] as num?)?.toDouble() ?? 0;
        final my = (widget.latestSensor['mag_y'] as num?)?.toDouble() ?? 0;
        compassDeg = (atan2(my, mx) * 180 / pi) % 360;
      }

      final uri = Uri.parse('${AppConfig.serverBaseUrl}/api/customer/$customerId/live_scan/$liveScanSessionId/frame');
      final request = http.MultipartRequest('POST', uri);
      if (jwtToken != null) request.headers['Authorization'] = 'Bearer $jwtToken';
      request.files.add(await http.MultipartFile.fromPath('frame', img.path));
      request.fields['metadata'] = jsonEncode({
        'compass_deg': compassDeg,
        'pitch_deg': widget.pitch,
        'roll_deg': widget.roll,
        'distance_m': liveScanCurrentDistance,
        'timestamp_ms': DateTime.now().millisecondsSinceEpoch,
      });

      final resp = await request.send();
      if (resp.statusCode == 200) setState(() => liveScanFrameCount++);
      // Privacy: delete frame immediately after upload attempt
      await SecureDelete.path(img.path);
    } catch (e) { print('Live scan frame upload error: $e'); }
  }

  Future<void> _pollLiveScanStatus() async {
    if (!liveScanRunning || !mounted) return;
    try {
      final uri = Uri.parse('${AppConfig.serverBaseUrl}/api/customer/$customerId/live_scan/$liveScanSessionId/status');
      final resp = await http.get(uri, headers: {if (jwtToken != null) 'Authorization': 'Bearer $jwtToken'});
      final data = jsonDecode(resp.body);
      final pct = (data['coverage_pct'] as num?)?.toDouble() ?? 0;
      final ready = data['ready_to_finalize'] == true;
      setState(() {
        liveScanCoveragePct = pct;
        liveScanCoverage = (data['coverage_report'] as Map<String, dynamic>?) ?? {};
        liveScanGuidance = List<Map<String, dynamic>>.from(data['guidance'] ?? []);
        liveScanReadyToFinalize = ready;

        if (liveScanReadyToFinalize) {
          liveScanInstruction = 'ALL REGIONS COVERED — AUTO-FINALIZING...';
          liveScanCaptureTimer?.cancel();
          liveScanPollTimer?.cancel();
          Future.microtask(() => finalizeLiveScan());
        } else if (liveScanGuidance.isNotEmpty) {
          liveScanInstruction = liveScanGuidance.first['message'] ?? 'KEEP ROTATING';
        }
      });
    } catch (e) { print('Live scan poll error: $e'); }
  }

  Future<void> finalizeLiveScan() async {
    setState(() => liveScanInstruction = 'BUILDING 3D MODEL...');
    liveScanPollTimer?.cancel();
    liveScanCaptureTimer?.cancel();

    try {
      final uri = Uri.parse('${AppConfig.serverBaseUrl}/api/customer/$customerId/live_scan/$liveScanSessionId/finalize');
      final client = http.Client();
      final request = http.Request('POST', uri);
      request.headers['Content-Type'] = 'application/json';
      if (jwtToken != null) request.headers['Authorization'] = 'Bearer $jwtToken';
      final streamed = await client.send(request).timeout(const Duration(minutes: 5));
      final resp = await http.Response.fromStream(streamed);
      final data = jsonDecode(resp.body);

      setState(() { liveScanRunning = false; liveScanInstruction = ''; });

      if (data['viewer_url'] != null && mounted) {
        final viewerUrl = 'http://192.168.100.7:8000${data['viewer_url']}';
        Navigator.push(context, MaterialPageRoute(
          builder: (_) => Scaffold(
            appBar: AppBar(title: const Text('3D Body Viewer'), backgroundColor: Colors.deepPurple),
            body: WebViewWidget(
              controller: WebViewController()
                ..setJavaScriptMode(JavaScriptMode.unrestricted)
                ..loadRequest(Uri.parse(viewerUrl)),
            ),
          ),
        ));
      }
    } catch (e) {
      debugPrint('Live scan finalize error: $e');
      if (mounted) setState(() { liveScanRunning = false; liveScanInstruction = ''; });
    }
  }

  void cancelLiveScan() {
    liveScanCaptureTimer?.cancel();
    liveScanPollTimer?.cancel();
    setState(() {
      liveScanRunning = false;
      liveScanStarting = false;
      liveScanSessionId = '';
      liveScanInstruction = '';
      liveScanFrameCount = 0;
      liveScanCoveragePct = 0;
      liveScanReadyToFinalize = false;
      liveScanGuidance = [];
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        child: liveScanRunning ? _buildLiveScanOverlay() : _buildStartUI(),
      ),
    );
  }

  Widget _buildStartUI() {
    return Center(
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        const Icon(Icons.radar, size: 64, color: AppTheme.primaryTeal),
        const SizedBox(height: 16),
        const Text('LIVE SCAN', style: TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.bold, letterSpacing: 2)),
        const SizedBox(height: 8),
        const Text('Coverage-guided real-time scan.\nRotate 360° — server tracks coverage automatically.',
          textAlign: TextAlign.center, style: TextStyle(color: Colors.white54, fontSize: 13)),
        const SizedBox(height: 32),
        ElevatedButton.icon(
          onPressed: customerId != null ? showLiveScanDialog : null,
          icon: const Icon(Icons.stream, size: 28),
          label: const Text('START LIVE SCAN', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
          style: ElevatedButton.styleFrom(
            backgroundColor: Colors.teal,
            foregroundColor: Colors.white,
            padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
          ),
        ),
      ]),
    );
  }

  Widget _buildLiveScanOverlay() {
    final regionColors = <String, Color>{};
    final regions = (liveScanCoverage['regions'] as Map<String, dynamic>?) ?? {};
    for (final rn in ['front_torso', 'back_torso', 'right_arm', 'left_arm', 'right_leg', 'left_leg', 'head']) {
      final info = regions[rn] as Map<String, dynamic>?;
      final grade = info?['grade'] ?? 'missing';
      regionColors[rn] = grade == 'excellent' ? Colors.green
          : grade == 'good' ? Colors.lightGreen
          : grade == 'fair' ? Colors.orange
          : Colors.red;
    }

    return Container(
      color: Colors.black.withOpacity(0.7),
      child: Column(children: [
        // Top bar
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
          color: Colors.black54,
          child: Row(children: [
            Container(width: 10, height: 10, decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: liveScanReadyToFinalize ? Colors.green : Colors.tealAccent,
            )),
            const SizedBox(width: 8),
            Text('LIVE SCAN — $liveScanFrameCount frames',
              style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 13, letterSpacing: 1)),
            const Spacer(),
            Text('${liveScanCoveragePct.toStringAsFixed(0)}%',
              style: TextStyle(
                color: liveScanReadyToFinalize ? Colors.green : Colors.tealAccent,
                fontWeight: FontWeight.bold, fontSize: 22,
              )),
          ]),
        ),
        const SizedBox(height: 12),
        // Progress bar
        Padding(padding: const EdgeInsets.symmetric(horizontal: 24), child: ClipRRect(
          borderRadius: BorderRadius.circular(8),
          child: LinearProgressIndicator(
            value: liveScanCoveragePct / 100,
            minHeight: 10,
            backgroundColor: Colors.white12,
            valueColor: AlwaysStoppedAnimation(liveScanCoveragePct >= 100 ? Colors.green : Colors.tealAccent),
          ),
        )),
        const SizedBox(height: 16),
        // 7-region grid
        Padding(padding: const EdgeInsets.symmetric(horizontal: 16), child: Wrap(
          spacing: 8, runSpacing: 6, alignment: WrapAlignment.center,
          children: regionColors.entries.map((e) => Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            decoration: BoxDecoration(
              color: e.value.withOpacity(0.2),
              borderRadius: BorderRadius.circular(6),
              border: Border.all(color: e.value, width: 1.5),
            ),
            child: Text(e.key.replaceAll('_', ' ').toUpperCase(),
              style: TextStyle(color: e.value, fontSize: 10, fontWeight: FontWeight.bold)),
          )).toList(),
        )),
        const SizedBox(height: 16),
        // Guidance instruction
        Padding(padding: const EdgeInsets.symmetric(horizontal: 24), child: Text(
          liveScanInstruction,
          textAlign: TextAlign.center,
          style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold),
        )),
        const Spacer(),
        // Distance slider
        Padding(padding: const EdgeInsets.symmetric(horizontal: 24), child: Row(children: [
          const Text('DISTANCE', style: TextStyle(color: Colors.white54, fontSize: 11)),
          Expanded(child: Slider(
            value: liveScanCurrentDistance,
            min: liveScanDistanceMin,
            max: liveScanDistanceMax,
            divisions: (((liveScanDistanceMax - liveScanDistanceMin) * 10).round()).clamp(1, 100),
            label: '${liveScanCurrentDistance.toStringAsFixed(1)}m',
            activeColor: Colors.tealAccent,
            onChanged: (v) => setState(() => liveScanCurrentDistance = v),
          )),
          Text('${liveScanCurrentDistance.toStringAsFixed(1)}m',
            style: const TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.bold)),
        ])),
        // Cancel button
        Padding(padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16), child: Row(children: [
          Expanded(child: TextButton(
            onPressed: cancelLiveScan,
            child: const Text('CANCEL', style: TextStyle(color: Colors.redAccent, fontSize: 16)),
          )),
        ])),
      ]),
    );
  }
}
