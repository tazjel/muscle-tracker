import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:share_plus/share_plus.dart';
import 'package:path_provider/path_provider.dart';
import '../config.dart';
import '../services/secure_delete.dart';
import '../widgets/level_painter.dart';

class LivePreviewScreen extends StatefulWidget {
  const LivePreviewScreen({super.key});
  @override
  State<LivePreviewScreen> createState() => _LivePreviewScreenState();
}

class _LivePreviewScreenState extends State<LivePreviewScreen> {
  CameraController? _controller;
  Timer? _analysisTimer;
  bool _analyzing = false;
  bool _locked = false;
  Map<String, dynamic>? _lastResult;
  List<List<double>>? _contourPoints;
  String _selectedMuscleGroup = 'bicep';

  Uint8List? _lockedFrameBytes;
  List<List<double>>? _lockedContour;
  Map<String, dynamic>? _lockedMetrics;

  @override
  void initState() { super.initState(); _initCamera(); }

  Future<void> _initCamera() async {
    final cameras = await availableCameras();
    if (cameras.isEmpty) return;
    final cam = cameras.firstWhere(
      (c) => c.lensDirection == CameraLensDirection.back,
      orElse: () => cameras.first,
    );
    _controller = CameraController(cam, ResolutionPreset.max, enableAudio: false);
    try {
      await _controller!.initialize();
      if (mounted) { setState(() {}); _startAnalysis(); }
    } catch (_) {}
  }

  void _startAnalysis() {
    _analysisTimer?.cancel();
    _analysisTimer = Timer.periodic(const Duration(milliseconds: 500), (_) => _analyzeFrame());
  }

  Future<void> _analyzeFrame() async {
    if (_analyzing || _locked || _controller == null || !_controller!.value.isInitialized) return;
    _analyzing = true;
    try {
      final XFile img = await _controller!.takePicture();
      final bytes = await img.readAsBytes();
      final b64 = base64Encode(bytes);
      final res = await http.post(
        Uri.parse('${AppConfig.serverBaseUrl}/api/live_analyze'),
        headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ${jwtToken ?? ''}'},
        body: jsonEncode({'image_b64': b64, 'muscle_group': _selectedMuscleGroup}),
      ).timeout(const Duration(seconds: 3));
      if (!mounted) return;
      if (res.statusCode == 200) {
        final data = jsonDecode(res.body) as Map<String, dynamic>;
        final rawPts = data['contour_points'] as List<dynamic>?;
        setState(() {
          _lastResult = data;
          _contourPoints = rawPts?.map<List<double>>((p) => [
            (p[0] as num).toDouble(), (p[1] as num).toDouble(),
          ]).toList();
        });
      }
    } catch (_) {
      // timeout / network — skip frame silently
    } finally {
      _analyzing = false;
    }
  }

  Future<void> _lockFrame() async {
    if (_controller == null || !_controller!.value.isInitialized) return;
    try {
      final XFile img = await _controller!.takePicture();
      final bytes = await img.readAsBytes();
      setState(() {
        _locked = true;
        _lockedFrameBytes = bytes;
        _lockedContour = _contourPoints;
        _lockedMetrics = _lastResult;
      });
    } catch (_) {}
  }

  void _unlock() {
    setState(() { _locked = false; _lockedFrameBytes = null; _lockedContour = null; _lockedMetrics = null; });
    _startAnalysis();
  }

  Future<void> _saveLockedFrame() async {
    if (_lockedFrameBytes == null) return;
    try {
      final dir = await getTemporaryDirectory();
      final file = File('${dir.path}/live_${DateTime.now().millisecondsSinceEpoch}.jpg');
      await file.writeAsBytes(_lockedFrameBytes!);
      await Share.shareXFiles([XFile(file.path)], text: 'Muscle Tracker Live Measure');
      // Privacy: delete temp file after sharing
      await SecureDelete.path(file.path);
      // Clear in-memory bytes
      if (mounted) setState(() => _lockedFrameBytes = null);
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Share failed: $e')));
    }
  }

  @override
  void dispose() { _analysisTimer?.cancel(); _controller?.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: Stack(fit: StackFit.expand, children: [
        // Camera preview or locked frame
        if (_locked && _lockedFrameBytes != null)
          Image.memory(_lockedFrameBytes!, fit: BoxFit.cover)
        else if (_controller != null && _controller!.value.isInitialized)
          CameraPreview(_controller!)
        else
          const Center(child: CircularProgressIndicator(color: AppTheme.primaryTeal)),

        // Contour overlay (live)
        if (!_locked && _contourPoints != null && _contourPoints!.isNotEmpty)
          CustomPaint(painter: ContourOverlayPainter(points: _contourPoints!)),
        // Contour overlay (locked — green)
        if (_locked && _lockedContour != null && _lockedContour!.isNotEmpty)
          CustomPaint(painter: ContourOverlayPainter(points: _lockedContour!, color: AppTheme.accentGreen)),

        // Top bar
        Positioned(
          top: 0, left: 0, right: 0,
          child: Container(
            padding: EdgeInsets.only(top: MediaQuery.of(context).padding.top + 8, left: 4, right: 16, bottom: 12),
            decoration: const BoxDecoration(gradient: LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: [Colors.black87, Colors.transparent])),
            child: Row(children: [
              IconButton(icon: const Icon(Icons.arrow_back, color: Colors.white), onPressed: () => Navigator.pop(context)),
              const Text('LIVE MEASURE', style: TextStyle(color: AppTheme.primaryTeal, fontWeight: FontWeight.bold, letterSpacing: 2, fontSize: 13)),
              const Spacer(),
              // Scan pulse indicator
              Container(width: 8, height: 8, margin: const EdgeInsets.only(right: 8),
                decoration: BoxDecoration(shape: BoxShape.circle, color: _analyzing ? AppTheme.primaryTeal : Colors.white24)),
              DropdownButtonHideUnderline(child: DropdownButton<String>(
                value: _selectedMuscleGroup,
                dropdownColor: Colors.black87,
                icon: const Icon(Icons.arrow_drop_down, color: AppTheme.primaryTeal),
                style: const TextStyle(color: AppTheme.primaryTeal, fontWeight: FontWeight.bold, fontSize: 13),
                onChanged: _locked ? null : (v) => setState(() => _selectedMuscleGroup = v!),
                items: ['bicep', 'tricep', 'quad', 'calf', 'delt', 'lat'].map((m) =>
                  DropdownMenuItem(value: m, child: Text(m.toUpperCase())),
                ).toList(),
              )),
            ]),
          ),
        ),

        // Metric badges
        if (!_locked && _lastResult != null) _buildMetricBadges(_lastResult!),
        if (_locked && _lockedMetrics != null) _buildMetricBadges(_lockedMetrics!),
        // No-server hint when no results yet
        if (_lastResult == null && !_analyzing && !_locked)
          Positioned(left: 16, bottom: 120, child: _badge('⚡ Connect server for live analysis', Colors.white38)),

        // Bottom controls
        Positioned(
          bottom: 0, left: 0, right: 0,
          child: Container(
            padding: EdgeInsets.fromLTRB(24, 16, 24, MediaQuery.of(context).padding.bottom + 24),
            decoration: const BoxDecoration(gradient: LinearGradient(begin: Alignment.bottomCenter, end: Alignment.topCenter, colors: [Colors.black87, Colors.transparent])),
            child: _locked ? _buildLockedControls() : _buildLiveControls(),
          ),
        ),
      ]),
    );
  }

  Widget _buildMetricBadges(Map<String, dynamic> data) {
    final circ = data['circumference_cm']?.toDouble();
    final width = data['width_mm']?.toDouble();
    final area  = data['area_cm2']?.toDouble();
    return Positioned(
      left: 16, bottom: 120,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        if (circ != null)  _badge('⊙ ${circ.toStringAsFixed(1)} cm', AppTheme.primaryTeal),
        if (width != null) _badge('↔ ${width.toStringAsFixed(1)} mm', Colors.white70),
        if (area != null)  _badge('□ ${area.toStringAsFixed(1)} cm²', Colors.white54),
      ]),
    );
  }

  Widget _badge(String text, Color color) => Container(
    margin: const EdgeInsets.only(bottom: 6),
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
    decoration: BoxDecoration(
      color: Colors.black54,
      borderRadius: BorderRadius.circular(8),
      border: Border.all(color: color.withOpacity(0.5)),
    ),
    child: Text(text, style: TextStyle(color: color, fontWeight: FontWeight.bold, fontSize: 13)),
  );

  Widget _buildLiveControls() => Row(mainAxisAlignment: MainAxisAlignment.center, children: [
    GestureDetector(
      onTap: _lockFrame,
      child: Container(
        width: 72, height: 72,
        decoration: BoxDecoration(shape: BoxShape.circle, color: AppTheme.primaryTeal, border: Border.all(color: Colors.white, width: 3)),
        child: const Icon(Icons.lock, color: Colors.black, size: 32),
      ),
    ),
    const SizedBox(width: 16),
    const Text('LOCK & SAVE', style: TextStyle(color: Colors.white70, fontSize: 11, fontWeight: FontWeight.bold, letterSpacing: 1.5)),
  ]);

  Widget _buildLockedControls() => Row(children: [
    Expanded(child: OutlinedButton.icon(
      onPressed: _unlock,
      icon: const Icon(Icons.refresh),
      label: const Text('CONTINUE'),
      style: OutlinedButton.styleFrom(foregroundColor: Colors.white70, side: const BorderSide(color: Colors.white24)),
    )),
    const SizedBox(width: 12),
    Expanded(child: FilledButton.icon(
      onPressed: _saveLockedFrame,
      icon: const Icon(Icons.share),
      label: const Text('SHARE'),
    )),
  ]);
}
