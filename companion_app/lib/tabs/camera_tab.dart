import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'package:path_provider/path_provider.dart';
import 'dart:async';
import 'dart:io';
import 'dart:convert';
import 'dart:ui' as ui;
import 'package:http/http.dart' as http;
import '../config.dart';
import '../services/secure_delete.dart';
import '../widgets/level_painter.dart';

// Photo + Video Capture Tab
class CameraTab extends StatefulWidget {
  final CameraController controller;
  final double pitch;
  final double roll;
  final Map<String, dynamic> latestSensor;

  const CameraTab({
    super.key,
    required this.controller,
    required this.pitch,
    required this.roll,
    required this.latestSensor,
  });

  @override
  State<CameraTab> createState() => CameraTabState();
}

class CameraTabState extends State<CameraTab> {
  int capturePhase = 0;
  final List<String> phaseLabels = ['FRONT VIEW', 'SIDE VIEW'];
  final List<IconData> phaseIcons = [Icons.person, Icons.person_outline];
  String selectedMuscleGroup = 'quadricep';
  double cameraDistanceCm = 75.0;
  final Map<String, IconData> muscleIcons = {
    'bicep': Icons.fitness_center, 'tricep': Icons.fitness_center,
    'quadricep': Icons.accessibility_new, 'hamstring': Icons.accessibility_new,
    'calf': Icons.accessibility_new, 'glute': Icons.sports_gymnastics,
    'deltoid': Icons.sports_gymnastics, 'lat': Icons.sports_gymnastics,
  };
  String? frontPath, sidePath;
  bool isCapturing = false, isUploading = false, isRecordingMode = false, isRecording = false, showGhost = false;
  int recordingCountdown = 5;
  Timer? countdownTimer;
  String? statusMessage;
  ui.Image? ghostImage;
  bool torchOn = false;
  bool isAutoMode = true;
  bool autoRunning = false;
  int autoCountdown = 0;
  String autoInstruction = '';
  Timer? autoTimer;

  bool get isLevel => widget.pitch.abs() < 0.5 && widget.roll.abs() < 0.5;

  @override
  void dispose() {
    countdownTimer?.cancel();
    autoTimer?.cancel();
    // Privacy: delete any unsent captures
    if (frontPath != null) SecureDelete.path(frontPath!);
    if (sidePath != null) SecureDelete.path(sidePath!);
    // Zero out in-memory image data
    ghostImage?.dispose();
    ghostImage = null;
    super.dispose();
  }

  Future<void> captureImage() async {
    if (!widget.controller.value.isInitialized || isCapturing) return;
    setState(() { isCapturing = true; statusMessage = 'Analyzing pose...'; });
    try {
      final XFile image = await widget.controller.takePicture();
      var request = http.MultipartRequest('POST', Uri.parse('${AppConfig.serverBaseUrl}/api/pose_check'));
      request.headers['Authorization'] = 'Bearer ${jwtToken ?? ''}';
      request.files.add(await http.MultipartFile.fromPath('image', image.path));
      request.fields['muscle_group'] = selectedMuscleGroup;
      var streamedResponse = await request.send().timeout(const Duration(seconds: 5));
      var response = await http.Response.fromStream(streamedResponse);

      if (response.statusCode == 200) {
        final result = jsonDecode(response.body);
        if (result['status'] == 'corrections_needed' && result['corrections'] != null) {
          if (!mounted) return;
          String instructions = (result['corrections'] as List).map((c) => "• ${c['instruction']}").join("\n");
          final proceed = await showDialog<bool>(context: context, builder: (c) => AlertDialog(title: const Text('Pose Check'), content: Text(instructions), actions: [TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('RETAKE')), TextButton(onPressed: () => Navigator.pop(c, true), child: const Text('CONTINUE'))]));
          if (proceed != true) { setState(() { isCapturing = false; statusMessage = 'Adjust pose and retry'; }); return; }
        }
      }

      if (capturePhase == 0) {
        frontPath = image.path;
        setState(() { capturePhase = 1; isCapturing = false; statusMessage = null; });
      } else {
        sidePath = image.path;
        await widget.controller.pausePreview();
        if (!mounted) return;
        final confirmed = await Navigator.push(context, MaterialPageRoute(builder: (_) => _ReviewScreen(frontPath: frontPath!, sidePath: sidePath!)));
        if (confirmed == true) await _uploadScan();
        else { resetCapture(); await widget.controller.resumePreview(); }
      }
    } catch (e) { setState(() { statusMessage = 'Error: $e'; isCapturing = false; }); }
  }

  Future<void> _uploadScan() async {
    setState(() { isUploading = true; statusMessage = 'Uploading...'; });
    try {
      var request = http.MultipartRequest('POST', Uri.parse('${AppConfig.serverBaseUrl}/api/upload_scan/$customerId'));
      request.headers['Authorization'] = 'Bearer ${jwtToken ?? ''}';
      request.files.add(await http.MultipartFile.fromPath('front', frontPath!));
      request.files.add(await http.MultipartFile.fromPath('side', sidePath!));
      request.fields['muscle_group'] = selectedMuscleGroup;
      request.fields['camera_distance_cm'] = cameraDistanceCm.round().toString();
      var streamedResponse = await request.send().timeout(const Duration(seconds: 30));
      var response = await http.Response.fromStream(streamedResponse);
      if (!mounted) return;
      if (response.statusCode == 401) {
        jwtToken = null;
        return;
      }
      final result = jsonDecode(response.body);
      if (response.statusCode == 200 && result['status'] == 'success') {
        // Privacy: securely delete local captures after successful upload
        if (frontPath != null) await SecureDelete.path(frontPath!);
        if (sidePath != null) await SecureDelete.path(sidePath!);
        frontPath = null;
        sidePath = null;
        setState(() => isUploading = false);
        resetCapture();
        Navigator.push(context, MaterialPageRoute(builder: (_) => _ResultsScreenPlaceholder(result: result, muscleGroup: selectedMuscleGroup)));
      } else { setState(() { statusMessage = 'Failed: ${result["message"]}'; isUploading = false; }); }
    } catch (e) { setState(() { statusMessage = 'Error: $e'; isUploading = false; }); }
  }

  Future<void> toggleRecording() async {
    if (isRecording) { await _stopVideoRecording(); return; }
    if (!widget.controller.value.isInitialized || widget.controller.value.isRecordingVideo) return;
    try {
      await widget.controller.startVideoRecording();
      setState(() { isRecording = true; recordingCountdown = 5; statusMessage = 'Keep steady...'; });
      countdownTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
        setState(() { if (recordingCountdown > 0) recordingCountdown--; else _stopVideoRecording(); });
      });
    } catch (e) { setState(() => statusMessage = 'Error: $e'); }
  }

  Future<void> _stopVideoRecording() async {
    if (!isRecording) return;
    countdownTimer?.cancel();
    try {
      XFile file = await widget.controller.stopVideoRecording();
      setState(() { isRecording = false; isUploading = true; statusMessage = 'Processing video...'; });
      var request = http.MultipartRequest('POST', Uri.parse('${AppConfig.serverBaseUrl}/api/upload_video/$customerId'));
      request.headers['Authorization'] = 'Bearer ${jwtToken ?? ''}';
      request.files.add(await http.MultipartFile.fromPath('video', file.path));
      request.fields['muscle_group'] = selectedMuscleGroup;
      request.fields['camera_distance_cm'] = cameraDistanceCm.round().toString();
      var streamedResponse = await request.send().timeout(const Duration(seconds: 30));
      var response = await http.Response.fromStream(streamedResponse);
      final result = jsonDecode(response.body);
      if (response.statusCode == 200 && result['status'] == 'success') {
        setState(() => isUploading = false);
        if (mounted) Navigator.push(context, MaterialPageRoute(builder: (_) => _ResultsScreenPlaceholder(result: result, muscleGroup: selectedMuscleGroup)));
      } else { setState(() { statusMessage = 'Error: ${result['message']}'; isUploading = false; }); }
    } catch (e) { setState(() { statusMessage = 'Error: $e'; isUploading = false; }); }
  }

  Future<void> toggleTorch() async {
    try {
      torchOn = !torchOn;
      await widget.controller.setFlashMode(torchOn ? FlashMode.torch : FlashMode.off);
      setState(() {});
    } catch (e) { setState(() => statusMessage = 'Error: $e'); }
  }

  Future<void> startAutoCapture() async {
    if (autoRunning || isCapturing) return;
    resetCapture();
    setState(() { autoRunning = true; isAutoMode = true; });
    setState(() { autoInstruction = 'FRONT — CAPTURING...'; autoCountdown = 0; });
    final frontBest = await burstCaptureBest(8);
    if (!mounted || !autoRunning || frontBest == null) return;
    frontPath = frontBest;
    setState(() { capturePhase = 1; });
    for (int i = 5; i >= 1; i--) {
      setState(() { autoInstruction = 'ROTATE 90° — $i s'; });
      await Future.delayed(const Duration(seconds: 1));
      if (!mounted || !autoRunning) return;
    }
    setState(() { autoInstruction = 'SIDE — CAPTURING...'; });
    final sideBest = await burstCaptureBest(8);
    if (!mounted || !autoRunning || sideBest == null) return;
    sidePath = sideBest;
    setState(() { autoInstruction = 'Uploading...'; });
    await _uploadScan();
    if (mounted) setState(() { autoRunning = false; autoInstruction = ''; });
  }

  Future<String?> burstCaptureBest(int count) async {
    if (!widget.controller.value.isInitialized) return null;
    final frames = <String>[];
    for (int i = 0; i < count; i++) {
      try {
        if (widget.controller.value.isTakingPicture) { await Future.delayed(const Duration(milliseconds: 100)); continue; }
        final XFile img = await widget.controller.takePicture();
        frames.add(img.path);
        setState(() { autoInstruction = 'BURST ${frames.length}/$count'; });
      } catch (e) {
        if (kDebugMode) print('Burst capture error: $e');
        await Future.delayed(const Duration(milliseconds: 200));
      }
    }
    if (frames.isEmpty) return null;
    String best = frames.first;
    int bestSize = 0;
    for (final path in frames) {
      final size = await File(path).length();
      if (size > bestSize) { bestSize = size; best = path; }
    }
    // Privacy: delete all non-best burst frames
    for (final path in frames) {
      if (path != best) await SecureDelete.path(path);
    }
    return best;
  }

  Future<void> autoShowStep(String label, int seconds) async {
    setState(() { autoInstruction = label; autoCountdown = seconds; });
    if (seconds <= 0) return;
    final completer = Completer<void>();
    autoTimer?.cancel();
    autoTimer = Timer.periodic(const Duration(seconds: 1), (t) {
      if (!mounted) { t.cancel(); completer.complete(); return; }
      if (autoCountdown <= 1) { t.cancel(); setState(() => autoCountdown = 0); completer.complete(); }
      else { setState(() => autoCountdown--); }
    });
    return completer.future;
  }

  void cancelAuto() {
    autoTimer?.cancel();
    setState(() { autoRunning = false; autoInstruction = ''; autoCountdown = 0; });
    resetCapture();
  }

  Future<void> toggleGhost() async {
    if (showGhost) { setState(() { showGhost = false; ghostImage = null; }); return; }
    setState(() => statusMessage = 'Loading overlay...');
    try {
      final dir = await getApplicationDocumentsDirectory();
      final file = File('${dir.path}/scans/latest_${selectedMuscleGroup}_${capturePhase == 0 ? "front" : "side"}.jpg');
      if (await file.exists()) {
        final codec = await ui.instantiateImageCodec(await file.readAsBytes());
        final frame = await codec.getNextFrame();
        setState(() { ghostImage = frame.image; showGhost = true; statusMessage = null; });
      } else {
        setState(() { showGhost = false; statusMessage = 'No previous scan'; });
        Timer(const Duration(seconds: 2), () { if (mounted) setState(() => statusMessage = null); });
      }
    } catch (e) { setState(() => statusMessage = 'Ghost failed: $e'); }
  }

  void resetCapture() {
    setState(() { capturePhase = 0; frontPath = null; sidePath = null; showGhost = false; ghostImage = null; statusMessage = null; });
  }

  void showDistancePicker() {
    double tempDist = cameraDistanceCm;
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.grey[900],
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(16))),
      builder: (ctx) => StatefulBuilder(builder: (ctx, setSheetState) => Padding(
        padding: const EdgeInsets.all(24),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Text('Camera Distance', style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          Text('${tempDist.round()} cm', style: TextStyle(color: AppTheme.primaryTeal, fontSize: 32, fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          Row(children: [
            const Text('30', style: TextStyle(color: Colors.white54, fontSize: 12)),
            Expanded(child: Slider(
              value: tempDist, min: 30, max: 300, divisions: 27,
              activeColor: AppTheme.primaryTeal,
              label: '${tempDist.round()} cm',
              onChanged: (v) => setSheetState(() => tempDist = v),
            )),
            const Text('300', style: TextStyle(color: Colors.white54, fontSize: 12)),
          ]),
          const SizedBox(height: 4),
          const Text('Set to the distance between phone and body', style: TextStyle(color: Colors.white54, fontSize: 12)),
          const SizedBox(height: 16),
          Row(children: [
            for (final preset in [60, 100, 150, 200])
              Expanded(child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 4),
                child: OutlinedButton(
                  style: OutlinedButton.styleFrom(
                    side: BorderSide(color: tempDist == preset.toDouble() ? AppTheme.primaryTeal : Colors.white24),
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 8),
                  ),
                  onPressed: () => setSheetState(() => tempDist = preset.toDouble()),
                  child: Text('${preset}cm', style: const TextStyle(fontSize: 12)),
                ),
              )),
          ]),
          const SizedBox(height: 16),
          SizedBox(width: double.infinity, child: ElevatedButton(
            style: ElevatedButton.styleFrom(backgroundColor: AppTheme.primaryTeal, padding: const EdgeInsets.symmetric(vertical: 14)),
            onPressed: () { setState(() => cameraDistanceCm = tempDist); Navigator.pop(ctx); },
            child: const Text('SET DISTANCE', style: TextStyle(fontWeight: FontWeight.bold)),
          )),
        ]),
      )),
    );
  }

  Widget _phaseDot(int p) {
    return Container(
      width: 8, height: 8,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: capturePhase == p ? AppTheme.primaryTeal
            : ((p == 0 ? frontPath != null : sidePath != null) ? AppTheme.accentGreen : Colors.white24),
      ),
    );
  }

  Widget _modeBtn(String l, bool a) {
    return GestureDetector(
      onTap: () => setState(() {
        isRecordingMode = l == 'VIDEO';
        isAutoMode = l == 'AUTO';
        statusMessage = null;
        if (!isAutoMode) { autoRunning = false; autoTimer?.cancel(); }
      }),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
        decoration: BoxDecoration(
          color: a ? AppTheme.primaryTeal : Colors.transparent,
          borderRadius: BorderRadius.circular(20),
        ),
        child: Text(l, style: TextStyle(color: a ? Colors.black : Colors.white70, fontWeight: FontWeight.bold, fontSize: 11)),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.controller.value.isInitialized) {
      return const Scaffold(body: Center(child: CircularProgressIndicator(color: AppTheme.primaryTeal)));
    }
    return Scaffold(
      body: Stack(fit: StackFit.expand, children: [
        CameraPreview(widget.controller),
        if (showGhost && ghostImage != null)
          CustomPaint(painter: GhostOverlayPainter(image: ghostImage)),
        CustomPaint(painter: LevelPainter(pitch: widget.pitch, roll: widget.roll, color: isLevel ? AppTheme.accentGreen : AppTheme.accentRed)),
        CustomPaint(painter: BodyGuidePainter(phase: capturePhase, muscleGroup: selectedMuscleGroup)),
        _buildTopBar(),
        _buildCaptureUI(),
        if (autoRunning) Positioned.fill(child: AbsorbPointer(absorbing: true, child: _buildAutoOverlay())),
        if (isUploading && !autoRunning) _buildUploadOverlay(),
      ]),
    );
  }

  Widget _buildTopBar() {
    return Positioned(
      top: 0, left: 0, right: 0,
      child: Container(
        padding: EdgeInsets.only(top: MediaQuery.of(context).padding.top + 8, left: 16, right: 16, bottom: 8),
        decoration: const BoxDecoration(gradient: LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: [Colors.black87, Colors.transparent])),
        child: Row(children: [
          Flexible(child: DropdownButtonHideUnderline(child: DropdownButton<String>(
            value: selectedMuscleGroup,
            dropdownColor: Colors.black87,
            icon: const Icon(Icons.arrow_drop_down, color: AppTheme.primaryTeal, size: 18),
            style: const TextStyle(color: AppTheme.primaryTeal, fontWeight: FontWeight.bold, fontSize: 13),
            isDense: true,
            onChanged: frontPath != null ? null : (v) => setState(() => selectedMuscleGroup = v!),
            items: muscleIcons.keys.map((m) => DropdownMenuItem(
              value: m,
              child: Row(children: [Icon(muscleIcons[m], size: 14, color: AppTheme.primaryTeal), const SizedBox(width: 6), Text(m.toUpperCase())]),
            )).toList(),
          ))),
          GestureDetector(
            onTap: showDistancePicker,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(color: Colors.white12, borderRadius: BorderRadius.circular(12)),
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                const Icon(Icons.straighten, color: Colors.white70, size: 14),
                const SizedBox(width: 4),
                Text('${cameraDistanceCm.round()}cm', style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w600)),
              ]),
            ),
          ),
          const Spacer(),
          IconButton(
            icon: Icon(torchOn ? Icons.flashlight_on : Icons.flashlight_off, color: torchOn ? Colors.yellow : Colors.white70),
            padding: EdgeInsets.zero, constraints: const BoxConstraints(minWidth: 36, minHeight: 36),
            onPressed: toggleTorch,
          ),
          IconButton(
            icon: Icon(showGhost ? Icons.visibility : Icons.visibility_off, color: showGhost ? AppTheme.primaryTeal : Colors.white70),
            padding: EdgeInsets.zero, constraints: const BoxConstraints(minWidth: 36, minHeight: 36),
            onPressed: toggleGhost,
          ),
        ]),
      ),
    );
  }

  Widget _buildCaptureUI() {
    final bottomPad = MediaQuery.of(context).padding.bottom + 24;
    return Positioned(
      bottom: 0, left: 0, right: 0,
      child: Container(
        padding: EdgeInsets.fromLTRB(24, 16, 24, bottomPad),
        decoration: const BoxDecoration(gradient: LinearGradient(begin: Alignment.bottomCenter, end: Alignment.topCenter, colors: [Colors.black87, Colors.transparent])),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          // Mode selector
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Container(
              margin: const EdgeInsets.only(bottom: 16),
              decoration: BoxDecoration(color: Colors.white10, borderRadius: BorderRadius.circular(20)),
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                _modeBtn('PHOTO', !isRecordingMode && !isAutoMode),
                _modeBtn('VIDEO', isRecordingMode && !isAutoMode),
                _modeBtn('AUTO', isAutoMode),
              ]),
            ),
          ),
          // Phase indicator
          AnimatedSwitcher(
            duration: const Duration(milliseconds: 300),
            child: isRecording
                ? Text('00:0$recordingCountdown', key: const ValueKey('timer'), style: const TextStyle(color: AppTheme.accentRed, fontSize: 32, fontWeight: FontWeight.bold))
                : Row(mainAxisSize: MainAxisSize.min, children: [
                    _phaseDot(0),
                    const SizedBox(width: 6),
                    Text(phaseLabels[capturePhase], key: ValueKey(capturePhase), style: const TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.bold, letterSpacing: 2)),
                    const SizedBox(width: 6),
                    _phaseDot(1),
                  ]),
          ),
          const SizedBox(height: 12),
          if (statusMessage != null)
            Text(statusMessage!, style: const TextStyle(color: AppTheme.primaryTeal, fontSize: 13, fontWeight: FontWeight.w500)),
          const SizedBox(height: 24),
          Row(mainAxisAlignment: MainAxisAlignment.center, children: [
            if (frontPath != null) IconButton(onPressed: resetCapture, icon: const Icon(Icons.refresh, color: Colors.white54)),
            const SizedBox(width: 24),
            GestureDetector(
              onTap: (isCapturing) ? null : (isAutoMode ? startAutoCapture : (isRecordingMode ? toggleRecording : captureImage)),
              child: Container(
                width: 76, height: 76,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: isRecording ? AppTheme.accentRed : AppTheme.primaryTeal,
                  border: Border.all(color: Colors.white, width: 4),
                ),
                child: isCapturing || (isUploading && isRecordingMode)
                    ? const Padding(padding: EdgeInsets.all(20), child: CircularProgressIndicator(color: Colors.black, strokeWidth: 3))
                    : Icon(
                        isAutoMode ? Icons.play_arrow : (isRecordingMode ? (isRecording ? Icons.stop : Icons.videocam) : phaseIcons[capturePhase]),
                        color: Colors.black, size: 36,
                      ),
              ),
            ),
            const SizedBox(width: 72),
          ]),
        ]),
      ),
    );
  }

  Widget _buildAutoOverlay() {
    return Container(
      color: Colors.black.withOpacity(0.75),
      child: Center(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Text(autoInstruction, style: const TextStyle(color: Colors.white, fontSize: 28, fontWeight: FontWeight.bold, letterSpacing: 3)),
          const SizedBox(height: 24),
          if (autoCountdown > 0)
            Text('$autoCountdown', style: const TextStyle(color: AppTheme.primaryTeal, fontSize: 96, fontWeight: FontWeight.bold)),
          if (autoCountdown == 0 && isCapturing)
            const Padding(padding: EdgeInsets.all(20), child: CircularProgressIndicator(color: AppTheme.primaryTeal, strokeWidth: 4)),
        ]),
      ),
    );
  }

  Widget _buildUploadOverlay() {
    return Container(
      color: Colors.black.withOpacity(0.87),
      child: const Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
        CircularProgressIndicator(color: AppTheme.primaryTeal),
        SizedBox(height: 20),
        Text('Vision Engine Analysis...', style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold)),
        Text('Quantifying muscle metrics', style: TextStyle(color: Colors.white54, fontSize: 12)),
      ])),
    );
  }
}

// Minimal local review screen used by CameraTab
class _ReviewScreen extends StatelessWidget {
  final String frontPath, sidePath;
  const _ReviewScreen({required this.frontPath, required this.sidePath});
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Review Captures')),
      body: Column(children: [
        Expanded(child: Row(children: [
          Expanded(child: Column(children: [const Padding(padding: EdgeInsets.all(12), child: Text('FRONTAL', style: TextStyle(fontWeight: FontWeight.bold, color: AppTheme.primaryTeal))), Expanded(child: Image.file(File(frontPath), fit: BoxFit.contain))])),
          const VerticalDivider(width: 1, color: Colors.white10),
          Expanded(child: Column(children: [const Padding(padding: EdgeInsets.all(12), child: Text('LATERAL', style: TextStyle(fontWeight: FontWeight.bold, color: AppTheme.primaryTeal))), Expanded(child: Image.file(File(sidePath), fit: BoxFit.contain))])),
        ])),
        Padding(padding: const EdgeInsets.all(32), child: Row(children: [
          Expanded(child: OutlinedButton.icon(onPressed: () => Navigator.pop(context, false), icon: const Icon(Icons.refresh), label: const Text('RETAKE'), style: OutlinedButton.styleFrom(foregroundColor: Colors.white70, side: const BorderSide(color: Colors.white24)))),
          const SizedBox(width: 16),
          Expanded(child: FilledButton.icon(onPressed: () => Navigator.pop(context, true), icon: const Icon(Icons.check_circle), label: const Text('ANALYZE'))),
        ])),
      ]),
    );
  }
}

// Minimal placeholder that just shows result JSON — the real ResultsScreen is in main.dart
class _ResultsScreenPlaceholder extends StatelessWidget {
  final Map<String, dynamic> result;
  final String muscleGroup;
  const _ResultsScreenPlaceholder({required this.result, required this.muscleGroup});
  @override
  Widget build(BuildContext context) {
    final vol = result['volume_cm3']?.toDouble() ?? 0.0;
    return Scaffold(
      appBar: AppBar(title: const Text('Scan Analysis')),
      body: Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
        Text(muscleGroup.toUpperCase(), style: const TextStyle(color: AppTheme.primaryTeal, fontWeight: FontWeight.w900, letterSpacing: 3)),
        const SizedBox(height: 16),
        Text('${vol.toStringAsFixed(1)} cm³', style: const TextStyle(fontSize: 52, fontWeight: FontWeight.bold, color: Colors.white)),
        const SizedBox(height: 24),
        FilledButton(onPressed: () => Navigator.pop(context), child: const Text('BACK')),
      ])),
    );
  }
}
