import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'package:path_provider/path_provider.dart';
import 'package:sensors_plus/sensors_plus.dart';
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import '../config.dart';

// Dual/Multi Device Capture Tab
class MultiCaptureTab extends StatefulWidget {
  final CameraController controller;
  final double pitch;
  final double roll;
  final Map<String, dynamic> latestSensor;
  final List<Map<String, dynamic>> sensorLog;
  final String selectedMuscleGroup;
  final double cameraDistanceCm;

  const MultiCaptureTab({
    super.key,
    required this.controller,
    required this.pitch,
    required this.roll,
    required this.latestSensor,
    required this.sensorLog,
    required this.selectedMuscleGroup,
    required this.cameraDistanceCm,
  });

  @override
  State<MultiCaptureTab> createState() => _MultiCaptureTabState();
}

class _MultiCaptureTabState extends State<MultiCaptureTab> {
  bool isDualMode = false;
  String dualRole = 'front';
  String dualStatus = 'READY';
  int dualCaptureCount = 0;
  Timer? triggerPollTimer;
  bool isCapturing = false;
  String? statusMessage;

  // Profile Builder
  bool isProfileMode = false;
  bool profileRunning = false;
  bool profileLocked = false;
  bool isTakingProfileFrame = false;
  int profileSecondsLeft = 20;
  int profileFrameCount = 0;
  Timer? profileTimer;

  StreamSubscription? gyroSub;
  StreamSubscription? magSub;
  final List<Map<String, dynamic>> localSensorLog = [];

  @override
  void initState() {
    super.initState();
    _loadDualRole();
    _initSensorSubs();
  }

  @override
  void dispose() {
    triggerPollTimer?.cancel();
    profileTimer?.cancel();
    gyroSub?.cancel();
    magSub?.cancel();
    super.dispose();
  }

  void _initSensorSubs() {
    try {
      gyroSub = gyroscopeEventStream().listen((event) {
        widget.latestSensor['gyro_x'] = event.x;
        widget.latestSensor['gyro_y'] = event.y;
        widget.latestSensor['gyro_z'] = event.z;
      });
    } catch (e) { print('Gyro sensor unavailable: $e'); }
    try {
      magSub = magnetometerEventStream().listen((event) {
        widget.latestSensor['mag_x'] = event.x;
        widget.latestSensor['mag_y'] = event.y;
        widget.latestSensor['mag_z'] = event.z;
      });
    } catch (e) { print('Magnetometer unavailable: $e'); }
  }

  Future<void> _loadDualRole() async {
    final paths = [
      '/data/local/tmp/muscle_tracker_role.json',
      '/sdcard/muscle_tracker_role.json',
    ];
    try {
      final docsDir = await getApplicationDocumentsDirectory();
      paths.insert(0, '${docsDir.path}/muscle_tracker_role.json');
    } catch (e) { print('Failed to get docs dir: $e'); }
    for (final path in paths) {
      try {
        final file = File(path);
        if (await file.exists()) {
          final data = jsonDecode(await file.readAsString());
          if (!mounted) return;
          setState(() {
            dualRole = data['role'] ?? 'front';
            isDualMode = true;
          });
          _startTriggerPolling();
          return;
        }
      } catch (e) { print('Role file read error: $e'); }
    }
  }

  void _startTriggerPolling() {
    triggerPollTimer?.cancel();
    triggerPollTimer = Timer.periodic(const Duration(milliseconds: 500), (_) async {
      final paths = [
        '/data/local/tmp/muscle_tracker_trigger',
        '/sdcard/muscle_tracker_trigger',
      ];
      for (final path in paths) {
        try {
          final trigger = File(path);
          if (await trigger.exists()) {
            await trigger.delete();
            _dualCapture();
            return;
          }
        } catch (e) { print('Trigger poll error: $e'); }
      }
    });
  }

  Future<void> _dualCapture() async {
    if (isCapturing || !widget.controller.value.isInitialized) return;
    setState(() { dualStatus = 'CAPTURING'; isCapturing = true; });
    try {
      final tmpDir = await getTemporaryDirectory();
      final dualDir = Directory('${tmpDir.path}/muscle_dual');
      if (!await dualDir.exists()) await dualDir.create(recursive: true);
      final timestamp = DateTime.now().millisecondsSinceEpoch;
      dualCaptureCount++;
      final frames = <String>[];
      for (int i = 0; i < 4; i++) {
        try {
          if (widget.controller.value.isTakingPicture) { await Future.delayed(const Duration(milliseconds: 100)); continue; }
          final img = await widget.controller.takePicture();
          frames.add(img.path);
        } catch (e) { print('Dual capture frame error: $e'); await Future.delayed(const Duration(milliseconds: 200)); }
      }
      if (frames.isNotEmpty) {
        String best = frames.first;
        int bestSize = 0;
        for (final path in frames) {
          final size = await File(path).length();
          if (size > bestSize) { bestSize = size; best = path; }
        }
        final dest = '${dualDir.path}/${dualRole}_${dualCaptureCount}_$timestamp.jpg';
        await File(best).copy(dest);
      }
      if (!mounted) return;
      setState(() { dualStatus = 'DONE'; isCapturing = false; });
      await Future.delayed(const Duration(seconds: 2));
      if (mounted) setState(() => dualStatus = 'READY');
    } catch (e) {
      if (!mounted) return;
      setState(() { dualStatus = 'ERROR'; isCapturing = false; });
      await Future.delayed(const Duration(seconds: 2));
      if (mounted) setState(() => dualStatus = 'READY');
    }
  }

  Future<void> startProfileCapture() async {
    if (profileRunning) return;
    localSensorLog.clear();
    final framePaths = <String>[];
    final dir = await getTemporaryDirectory();
    final sessionDir = Directory('${dir.path}/profile_session_${DateTime.now().millisecondsSinceEpoch}');
    await sessionDir.create(recursive: true);
    if (!mounted) return;
    setState(() { profileRunning = true; profileLocked = true; profileSecondsLeft = 20; profileFrameCount = 0; });
    int tick = 0;
    profileTimer = Timer.periodic(const Duration(seconds: 1), (timer) async {
      if (!mounted || !profileRunning) { timer.cancel(); return; }
      setState(() => profileSecondsLeft = 20 - tick);
      if (tick >= 20) {
        timer.cancel();
        await _finishProfileCapture(framePaths, sessionDir);
        return;
      }
      if (isTakingProfileFrame) { tick++; return; }
      try {
        if (widget.controller.value.isInitialized && !widget.controller.value.isTakingPicture) {
          isTakingProfileFrame = true;
          final img = await widget.controller.takePicture();
          final fname = 'frame_${tick.toString().padLeft(3, '0')}.jpg';
          final dest = File('${sessionDir.path}/$fname');
          await File(img.path).copy(dest.path);
          framePaths.add(dest.path);
          localSensorLog.add({
            'filename': fname,
            'timestamp': DateTime.now().millisecondsSinceEpoch / 1000.0,
            ...widget.latestSensor,
          });
          if (mounted) setState(() => profileFrameCount = framePaths.length);
          isTakingProfileFrame = false;
        }
      } catch (e) { print('Profile frame capture error: $e'); isTakingProfileFrame = false; }
      tick++;
    });
  }

  Future<void> _finishProfileCapture(List<String> framePaths, Directory sessionDir) async {
    if (!mounted) return;
    setState(() { profileRunning = false; profileLocked = false; isTakingProfileFrame = false; profileSecondsLeft = 0; statusMessage = 'Uploading session...'; });
    try {
      var request = http.MultipartRequest(
        'POST', Uri.parse('${AppConfig.serverBaseUrl}/api/customer/$customerId/upload_session'));
      request.headers['Authorization'] = 'Bearer ${jwtToken ?? ''}';
      request.fields['muscle_group'] = widget.selectedMuscleGroup;
      request.fields['camera_distance_cm'] = widget.cameraDistanceCm.round().toString();
      request.fields['sensor_log'] = jsonEncode(localSensorLog);
      for (final path in framePaths) {
        final fname = path.split('/').last;
        request.files.add(await http.MultipartFile.fromPath(fname, path));
      }
      final streamed = await request.send().timeout(const Duration(seconds: 60));
      final res = await http.Response.fromStream(streamed);
      if (!mounted) return;
      setState(() => statusMessage = null);
      if (res.statusCode == 200) {
        // Navigate to progress screen
        final data = jsonDecode(res.body);
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Session uploaded: ${data['progress_pct'] ?? 0}% complete')),
          );
        }
      } else {
        setState(() => statusMessage = 'Upload failed');
      }
    } catch (e) {
      if (mounted) setState(() { statusMessage = 'Error: $e'; profileLocked = false; });
    } finally {
      try { await sessionDir.delete(recursive: true); } catch (e) { print('Cleanup error: $e'); }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.controller.value.isInitialized) {
      return const Scaffold(body: Center(child: CircularProgressIndicator(color: AppTheme.primaryTeal)));
    }
    return Scaffold(
      body: Stack(fit: StackFit.expand, children: [
        CameraPreview(widget.controller),
        if (isDualMode) _buildDualOverlay() else _buildProfileUI(),
        if (profileLocked) _buildProfileLockScreen(),
      ]),
    );
  }

  Widget _buildProfileUI() {
    final bottomPad = MediaQuery.of(context).padding.bottom + 24;
    return Positioned(
      bottom: 0, left: 0, right: 0,
      child: Container(
        padding: EdgeInsets.fromLTRB(24, 16, 24, bottomPad),
        decoration: const BoxDecoration(gradient: LinearGradient(
          begin: Alignment.bottomCenter, end: Alignment.topCenter,
          colors: [Colors.black87, Colors.transparent],
        )),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Text('PROFILE BUILDER', style: TextStyle(color: AppTheme.primaryTeal, fontWeight: FontWeight.bold, letterSpacing: 2, fontSize: 13)),
          const SizedBox(height: 8),
          const Text('20-second capture — rotate slowly 360°',
            style: TextStyle(color: Colors.white54, fontSize: 12), textAlign: TextAlign.center),
          if (statusMessage != null) ...[
            const SizedBox(height: 6),
            Text(statusMessage!, style: const TextStyle(color: AppTheme.primaryTeal, fontSize: 12)),
          ],
          const SizedBox(height: 16),
          GestureDetector(
            onTap: profileRunning ? null : startProfileCapture,
            child: Container(
              width: 76, height: 76,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: profileRunning ? AppTheme.accentRed : AppTheme.primaryTeal,
                border: Border.all(color: Colors.white, width: 4),
              ),
              child: isCapturing
                  ? const Padding(padding: EdgeInsets.all(20), child: CircularProgressIndicator(color: Colors.black, strokeWidth: 3))
                  : Icon(profileRunning ? Icons.stop : Icons.person_search, color: Colors.black, size: 36),
            ),
          ),
        ]),
      ),
    );
  }

  Widget _buildDualOverlay() {
    final statusColor = dualStatus == 'READY' ? Colors.blue
        : dualStatus == 'CAPTURING' ? Colors.amber
        : dualStatus == 'DONE' ? AppTheme.accentGreen
        : AppTheme.accentRed;
    final roleLabel = dualRole == 'front' ? 'FRONT CAMERA' : 'BACK CAMERA';
    return Positioned.fill(child: Stack(children: [
      Positioned(
        top: MediaQuery.of(context).padding.top + 16, left: 0, right: 0,
        child: Center(child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
          decoration: BoxDecoration(color: Colors.black87, borderRadius: BorderRadius.circular(8)),
          child: Text(roleLabel, style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold, letterSpacing: 2)),
        )),
      ),
      Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
        if (dualStatus == 'DONE') const Icon(Icons.check_circle, color: AppTheme.accentGreen, size: 72)
        else if (dualStatus == 'CAPTURING') const SizedBox(width: 60, height: 60, child: CircularProgressIndicator(color: Colors.amber, strokeWidth: 5))
        else Container(width: 72, height: 72, decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: Colors.blue, width: 3)),
            child: const Icon(Icons.radio_button_unchecked, color: Colors.blue, size: 36)),
        const SizedBox(height: 16),
        Text(dualStatus, style: TextStyle(color: statusColor, fontSize: 24, fontWeight: FontWeight.bold, letterSpacing: 3)),
        const SizedBox(height: 8),
        Text('Captures: $dualCaptureCount', style: const TextStyle(color: Colors.white54, fontSize: 13)),
      ])),
      Positioned(
        top: MediaQuery.of(context).size.height / 2 - 50,
        left: MediaQuery.of(context).size.width / 2 - 50,
        child: GestureDetector(
          onTap: _dualCapture,
          child: Container(width: 100, height: 100, color: Colors.transparent),
        ),
      ),
      Positioned(
        bottom: MediaQuery.of(context).padding.bottom + 20, left: 0, right: 0,
        child: Center(child: Text('Controlled by desktop script',
          style: TextStyle(color: Colors.white.withOpacity(0.3), fontSize: 11))),
      ),
    ]));
  }

  Widget _buildProfileLockScreen() {
    return Positioned.fill(child: AbsorbPointer(
      absorbing: true,
      child: Container(
        color: Colors.black.withOpacity(0.45),
        child: SafeArea(child: Column(children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
            color: Colors.black.withOpacity(0.6),
            child: Row(children: [
              Container(width: 10, height: 10, decoration: const BoxDecoration(shape: BoxShape.circle, color: AppTheme.accentRed)),
              const SizedBox(width: 10),
              const Text('RECORDING — SCREEN LOCKED', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 12, letterSpacing: 1.5)),
              const Spacer(),
              Text('${profileSecondsLeft}s', style: const TextStyle(color: AppTheme.accentRed, fontWeight: FontWeight.bold, fontSize: 20)),
            ]),
          ),
          const Spacer(),
          Container(
            padding: const EdgeInsets.all(16),
            margin: const EdgeInsets.all(20),
            decoration: BoxDecoration(color: Colors.black.withOpacity(0.7), borderRadius: BorderRadius.circular(12)),
            child: Column(children: [
              Text('$profileFrameCount / 20 frames captured', style: const TextStyle(color: AppTheme.primaryTeal, fontWeight: FontWeight.bold, fontSize: 16)),
              const SizedBox(height: 6),
              const Text('Keep phone steady • Good lighting helps\nScreen locked to prevent accidents',
                textAlign: TextAlign.center, style: TextStyle(color: Colors.white54, fontSize: 12)),
            ]),
          ),
          const SizedBox(height: 20),
        ])),
      ),
    ));
  }
}
