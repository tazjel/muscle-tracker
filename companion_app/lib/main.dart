import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'package:sensors_plus/sensors_plus.dart';
import 'package:path_provider/path_provider.dart';
import 'dart:async';
import 'dart:io';
import 'dart:convert';
import 'dart:ui' as ui;
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:share_plus/share_plus.dart';

late List<CameraDescription> _cameras;

// --- CONFIG & THEME ---

class AppConfig {
  static const String serverBaseUrl = 'http://192.168.100.16:8000/web_app';
  static const String appVersion = '3.0.0';
}

class AppTheme {
  static const Color primaryTeal = ui.Color(0xFF009688);
  static const Color darkBg = ui.Color(0xFF000000);
  static const Color cardBg = ui.Color(0xFF121212);
  static const Color accentGreen = ui.Color(0xFF69F0AE);
  static const Color accentRed = ui.Color(0xFFFF5252);

  static ThemeData get darkTheme => ThemeData(
    brightness: Brightness.dark,
    scaffoldBackgroundColor: darkBg,
    colorScheme: ColorScheme.fromSeed(seedColor: primaryTeal, brightness: Brightness.dark, primary: primaryTeal),
    cardTheme: CardThemeData(color: cardBg, elevation: 2, shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12))),
    appBarTheme: const AppBarTheme(backgroundColor: darkBg, foregroundColor: Colors.white, centerTitle: true, elevation: 0),
    filledButtonTheme: FilledButtonThemeData(style: FilledButton.styleFrom(
      backgroundColor: primaryTeal,
      foregroundColor: Colors.black,
      padding: const EdgeInsets.symmetric(vertical: 16),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
      textStyle: const TextStyle(fontWeight: FontWeight.bold, letterSpacing: 1.2),
    )),
    useMaterial3: true,
  );
}

String? _jwtToken;
String? _customerId;
String? _customerName;

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  _cameras = await availableCameras();
  // Auto-login with demo account; fall back to local demo if server unreachable
  try {
    final res = await http.post(
      Uri.parse('${AppConfig.serverBaseUrl}/api/auth/token'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'email': 'demo@muscle.com'}),
    ).timeout(const Duration(seconds: 4));
    final data = jsonDecode(res.body);
    if (res.statusCode == 200 && data['status'] == 'success') {
      _jwtToken = data['token'];
      _customerId = data['customer_id']?.toString() ?? '1';
      _customerName = data['name'] ?? 'Demo User';
    }
  } catch (_) {}
  _jwtToken ??= 'demo';
  _customerId ??= '1';
  _customerName ??= 'Demo User';
  runApp(const MuscleCompanionApp());
}

class MuscleCompanionApp extends StatelessWidget {
  const MuscleCompanionApp({super.key});
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Muscle Tracker v3',
      theme: AppTheme.darkTheme,
      home: const CameraLevelScreen(),
      debugShowCheckedModeBanner: false,
    );
  }
}

// --- LOGIN SCREEN ---

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});
  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _emailController = TextEditingController();
  bool _isLoading = false;
  String? _error;

  Future<void> _login() async {
    final email = _emailController.text.trim();
    if (email.isEmpty) return;
    setState(() { _isLoading = true; _error = null; });
    try {
      final response = await http.post(
        Uri.parse('${AppConfig.serverBaseUrl}/api/auth/token'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'email': email}),
      );
      final data = jsonDecode(response.body);
      if (response.statusCode == 200 && data['status'] == 'success') {
        _jwtToken = data['token'];
        _customerId = data['customer_id']?.toString() ?? '1';
        _customerName = data['name'] ?? 'User';
        if (!mounted) return;
        Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => const CameraLevelScreen()));
      } else { setState(() => _error = data['message'] ?? 'Login failed'); }
    } catch (e) { setState(() => _error = 'Network error: $e'); }
    finally { if (mounted) setState(() => _isLoading = false); }
  }

  @override
  Widget build(BuildContext context) {
    final mq = MediaQuery.of(context);
    final isTablet = mq.size.shortestSide >= 600;
    final isLandscape = mq.size.width > mq.size.height;
    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(gradient: LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: [Color(0xFF004D40), Color(0xFF001A14)])),
        child: isTablet && isLandscape ? _buildTabletLandscape(context) : _buildPhoneLayout(context),
      ),
    );
  }

  Widget _buildPhoneLayout(BuildContext context) {
    return SingleChildScrollView(
      child: ConstrainedBox(
        constraints: BoxConstraints(minHeight: MediaQuery.of(context).size.height),
        child: Padding(
          padding: EdgeInsets.only(left: 32, right: 32, top: MediaQuery.of(context).padding.top + 16, bottom: 40),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.center,
            children: _loginFormWidgets(context),
          ),
        ),
      ),
    );
  }

  Widget _buildTabletLandscape(BuildContext context) {
    return SafeArea(
      child: Row(children: [
        Expanded(child: Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Icon(Icons.fitness_center, size: 96, color: AppTheme.primaryTeal),
          const SizedBox(height: 28),
          const Text('MUSCLE TRACKER', style: TextStyle(fontSize: 32, fontWeight: FontWeight.w900, letterSpacing: 3, color: Colors.white)),
          const SizedBox(height: 10),
          const Text('Clinical Vision Engine v3.0', style: TextStyle(fontSize: 14, color: Colors.white54, letterSpacing: 1.5)),
        ]))),
        Expanded(child: Center(child: SizedBox(width: 440, child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 40, vertical: 32),
          child: Column(mainAxisSize: MainAxisSize.min, children: _loginFormWidgets(context, hideHeader: true)),
        )))),
      ]),
    );
  }

  List<Widget> _loginFormWidgets(BuildContext context, {bool hideHeader = false}) {
    return [
      if (!hideHeader) ...[
        const Hero(tag: 'logo', child: Icon(Icons.fitness_center, size: 56, color: AppTheme.primaryTeal)),
        const SizedBox(height: 12),
        const Text('MUSCLE TRACKER', textAlign: TextAlign.center, style: TextStyle(fontSize: 22, fontWeight: FontWeight.w900, letterSpacing: 2, color: Colors.white)),
        const Text('Clinical Vision Engine v3.0', textAlign: TextAlign.center, style: TextStyle(fontSize: 11, color: Colors.white54, letterSpacing: 1.5)),
        const SizedBox(height: 20),
      ],
      TextField(
        controller: _emailController,
        decoration: InputDecoration(labelText: 'Email Address', errorText: _error, prefixIcon: const Icon(Icons.email, color: AppTheme.primaryTeal)),
        keyboardType: TextInputType.emailAddress,
      ),
      const SizedBox(height: 32),
      _isLoading ? const CircularProgressIndicator(color: AppTheme.primaryTeal) : Column(children: [
        SizedBox(width: double.infinity, child: FilledButton(onPressed: _login, child: const Text('CONNECT'))),
        const SizedBox(height: 12),
        SizedBox(width: double.infinity, child: OutlinedButton(
          onPressed: () {
            _customerId = '1'; _customerName = 'Demo User'; _jwtToken = 'demo';
            Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => const CameraLevelScreen()));
          },
          style: OutlinedButton.styleFrom(foregroundColor: Colors.white54, side: const BorderSide(color: Colors.white24)),
          child: const Text('DEMO MODE'),
        )),
        const SizedBox(height: 12),
        TextButton(onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const RegisterScreen())), child: const Text('CREATE CLINICAL ACCOUNT', style: TextStyle(color: AppTheme.primaryTeal, fontSize: 13))),
      ]),
    ];
  }
}

// --- MAIN CAPTURE SCREEN ---

class CameraLevelScreen extends StatefulWidget {
  const CameraLevelScreen({super.key});
  @override
  State<CameraLevelScreen> createState() => _CameraLevelScreenState();
}

class _CameraLevelScreenState extends State<CameraLevelScreen> {
  CameraController? _controller;
  StreamSubscription<AccelerometerEvent>? _sensorSubscription;
  double _pitch = 0.0, _roll = 0.0;
  final double _levelTolerance = 0.5;
  int _capturePhase = 0;
  final List<String> _phaseLabels = ['FRONT VIEW', 'SIDE VIEW'];
  final List<IconData> _phaseIcons = [Icons.person, Icons.person_outline];
  String _selectedMuscleGroup = 'bicep';
  final Map<String, IconData> _muscleIcons = {
    'bicep': Icons.fitness_center, 'tricep': Icons.fitness_center,
    'quad': Icons.accessibility_new, 'calf': Icons.accessibility_new,
    'delt': Icons.sports_gymnastics, 'lat': Icons.sports_gymnastics,
  };
  String? _frontPath, _sidePath;
  bool _isCapturing = false, _isUploading = false, _isRecordingMode = false, _isRecording = false, _showGhost = false;
  int _recordingCountdown = 5;
  Timer? _countdownTimer;
  String? _statusMessage;
  ui.Image? _ghostImage;
  double _filteredPitch = 0.0, _filteredRoll = 0.0;
  static const double _smoothingFactor = 0.15;

  @override
  void initState() { super.initState(); _initCamera(); _initSensors(); }
  
  Future<void> _initCamera() async {
    if (_cameras.isEmpty) { setState(() => _statusMessage = 'No cameras'); return; }
    final cam = _cameras.firstWhere(
      (c) => c.lensDirection == CameraLensDirection.back,
      orElse: () => _cameras.first,
    );
    _controller = CameraController(cam, ResolutionPreset.medium, enableAudio: false);
    try { await _controller!.initialize(); if (mounted) setState(() {}); }
    catch (e) { setState(() => _statusMessage = 'Camera error: $e'); }
  }

  void _initSensors() {
    _sensorSubscription = accelerometerEventStream().listen((event) {
      if (!mounted) return;
      _filteredPitch += (event.y - _filteredPitch) * _smoothingFactor;
      _filteredRoll += (event.x - _filteredRoll) * _smoothingFactor;
      setState(() { _pitch = _filteredPitch; _roll = _filteredRoll; });
    });
  }

  @override
  void dispose() { _controller?.dispose(); _sensorSubscription?.cancel(); _countdownTimer?.cancel(); super.dispose(); }

  bool get isLevel => _pitch.abs() < _levelTolerance && _roll.abs() < _levelTolerance;

  Future<void> _captureImage() async {
    if (_controller == null || !_controller!.value.isInitialized || _isCapturing) return;
    setState(() { _isCapturing = true; _statusMessage = 'Analyzing pose...'; });
    try {
      final XFile image = await _controller!.takePicture();
      var request = http.MultipartRequest('POST', Uri.parse('${AppConfig.serverBaseUrl}/api/pose_check'));
      request.headers['Authorization'] = 'Bearer ${_jwtToken ?? ''}';
      request.files.add(await http.MultipartFile.fromPath('image', image.path));
      request.fields['muscle_group'] = _selectedMuscleGroup;
      var streamedResponse = await request.send().timeout(const Duration(seconds: 5));
      var response = await http.Response.fromStream(streamedResponse);
      
      if (response.statusCode == 200) {
        final result = jsonDecode(response.body);
        if (result['status'] == 'corrections_needed' && result['corrections'] != null) {
          if (!mounted) return;
          String instructions = (result['corrections'] as List).map((c) => "• ${c['instruction']}").join("\n");
          final proceed = await showDialog<bool>(context: context, builder: (c) => AlertDialog(title: const Text('Pose Check'), content: Text(instructions), actions: [TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('RETAKE')), TextButton(onPressed: () => Navigator.pop(c, true), child: const Text('CONTINUE'))]));
          if (proceed != true) { setState(() { _isCapturing = false; _statusMessage = 'Adjust pose and retry'; }); return; }
        }
      }

      if (_capturePhase == 0) {
        _frontPath = image.path;
        await _saveLatestScan(image.path, 'front');
        setState(() { _capturePhase = 1; _isCapturing = false; _statusMessage = null; });
      } else {
        _sidePath = image.path;
        await _saveLatestScan(image.path, 'side');
        await _controller!.pausePreview();
        if (!mounted) return;
        final confirmed = await Navigator.push(context, MaterialPageRoute(builder: (_) => ReviewScreen(frontPath: _frontPath!, sidePath: _sidePath!)));
        if (confirmed == true) await _uploadScan();
        else { _resetCapture(); await _controller!.resumePreview(); }
      }
    } catch (e) { setState(() { _statusMessage = 'Error: $e'; _isCapturing = false; }); }
  }

  Future<void> _uploadScan() async {
    setState(() { _isUploading = true; _statusMessage = 'Uploading...'; });
    try {
      var request = http.MultipartRequest('POST', Uri.parse('${AppConfig.serverBaseUrl}/api/upload_scan/$_customerId'));
      request.headers['Authorization'] = 'Bearer ${_jwtToken ?? ''}';
      request.files.add(await http.MultipartFile.fromPath('front', _frontPath!));
      request.files.add(await http.MultipartFile.fromPath('side', _sidePath!));
      request.fields['muscle_group'] = _selectedMuscleGroup;
      var streamedResponse = await request.send().timeout(const Duration(seconds: 30));
      var response = await http.Response.fromStream(streamedResponse);
      if (!mounted) return;
      if (response.statusCode == 401) { _jwtToken = null; Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => const LoginScreen())); return; }
      final result = jsonDecode(response.body);
      if (response.statusCode == 200 && result['status'] == 'success') {
        setState(() => _isUploading = false);
        _resetCapture();
        Navigator.push(context, MaterialPageRoute(builder: (_) => ResultsScreen(result: result, muscleGroup: _selectedMuscleGroup)));
      } else { setState(() { _statusMessage = 'Failed: ${result["message"]}'; _isUploading = false; }); }
    } catch (e) { setState(() { _statusMessage = 'Error: $e'; _isUploading = false; }); }
  }

  Future<void> _toggleRecording() async {
    if (_isRecording) { await _stopVideoRecording(); return; }
    if (_controller == null || !_controller!.value.isInitialized || _controller!.value.isRecordingVideo) return;
    try {
      await _controller!.startVideoRecording();
      setState(() { _isRecording = true; _recordingCountdown = 5; _statusMessage = 'Keep steady...'; });
      _countdownTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
        setState(() { if (_recordingCountdown > 0) _recordingCountdown--; else _stopVideoRecording(); });
      });
    } catch (e) { setState(() => _statusMessage = 'Error: $e'); }
  }

  Future<void> _stopVideoRecording() async {
    if (!_isRecording) return;
    _countdownTimer?.cancel();
    try {
      XFile file = await _controller!.stopVideoRecording();
      setState(() { _isRecording = false; _isUploading = true; _statusMessage = 'Processing video...'; });
      var request = http.MultipartRequest('POST', Uri.parse('${AppConfig.serverBaseUrl}/api/upload_video/$_customerId'));
      request.headers['Authorization'] = 'Bearer ${_jwtToken ?? ''}';
      request.files.add(await http.MultipartFile.fromPath('video', file.path));
      request.fields['muscle_group'] = _selectedMuscleGroup;
      var streamedResponse = await request.send().timeout(const Duration(seconds: 30));
      var response = await http.Response.fromStream(streamedResponse);
      final result = jsonDecode(response.body);
      if (response.statusCode == 200 && result['status'] == 'success') {
        setState(() => _isUploading = false);
        if (mounted) Navigator.push(context, MaterialPageRoute(builder: (_) => ResultsScreen(result: result, muscleGroup: _selectedMuscleGroup)));
      } else { setState(() { _statusMessage = 'Error: ${result['message']}'; _isUploading = false; }); }
    } catch (e) { setState(() { _statusMessage = 'Error: $e'; _isUploading = false; }); }
  }

  Future<void> _toggleGhost() async {
    if (_showGhost) { setState(() { _showGhost = false; _ghostImage = null; }); return; }
    setState(() => _statusMessage = 'Loading overlay...');
    try {
      final dir = await getApplicationDocumentsDirectory();
      final file = File('${dir.path}/scans/latest_${_selectedMuscleGroup}_${_capturePhase == 0 ? "front" : "side"}.jpg');
      if (await file.exists()) {
        final codec = await ui.instantiateImageCodec(await file.readAsBytes());
        final frame = await codec.getNextFrame();
        setState(() { _ghostImage = frame.image; _showGhost = true; _statusMessage = null; });
      } else { setState(() { _showGhost = false; _statusMessage = 'No previous scan'; }); Timer(const Duration(seconds: 2), () => setState(() => _statusMessage = null)); }
    } catch (e) { setState(() => _statusMessage = 'Ghost failed: $e'); }
  }

  Future<void> _saveLatestScan(String path, String phase) async {
    try {
      final dir = await getApplicationDocumentsDirectory();
      final scansDir = Directory('${dir.path}/scans');
      if (!await scansDir.exists()) await scansDir.create(recursive: true);
      await File(path).copy('${scansDir.path}/latest_${_selectedMuscleGroup}_$phase.jpg');
    } catch (e) { print(e); }
  }

  void _resetCapture() { setState(() { _capturePhase = 0; _frontPath = null; _sidePath = null; _showGhost = false; _ghostImage = null; _statusMessage = null; }); }

  @override
  Widget build(BuildContext context) {
    if (_controller == null || !_controller!.value.isInitialized) return const Scaffold(body: Center(child: CircularProgressIndicator(color: AppTheme.primaryTeal)));
    return Scaffold(
      body: Stack(fit: StackFit.expand, children: [
        CameraPreview(_controller!),
        if (_showGhost && _ghostImage != null) CustomPaint(painter: GhostOverlayPainter(image: _ghostImage)),
        CustomPaint(painter: LevelPainter(pitch: _pitch, roll: _roll, color: isLevel ? AppTheme.accentGreen : AppTheme.accentRed)),
        CustomPaint(painter: BodyGuidePainter(phase: _capturePhase, muscleGroup: _selectedMuscleGroup)),
        _buildTopBar(),
        _buildCaptureUI(),
        if (_isUploading) _buildUploadOverlay(),
      ]),
    );
  }

  Widget _buildTopBar() {
    return Positioned(top: 0, left: 0, right: 0, child: Container(padding: EdgeInsets.only(top: MediaQuery.of(context).padding.top + 8, left: 16, right: 16, bottom: 8), decoration: const BoxDecoration(gradient: LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: [Colors.black87, Colors.transparent])), child: Row(children: [
      GestureDetector(onTap: () => _showProfile(), child: Container(padding: const EdgeInsets.all(4), decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: AppTheme.primaryTeal, width: 1.5)), child: const Icon(Icons.person, color: AppTheme.primaryTeal, size: 20))),
      const SizedBox(width: 12),
      DropdownButtonHideUnderline(child: DropdownButton<String>(value: _selectedMuscleGroup, dropdownColor: Colors.black87, icon: const Icon(Icons.arrow_drop_down, color: AppTheme.primaryTeal), style: const TextStyle(color: AppTheme.primaryTeal, fontWeight: FontWeight.bold, fontSize: 14), onChanged: _frontPath != null ? null : (v) => setState(() => _selectedMuscleGroup = v!), items: _muscleIcons.keys.map((m) => DropdownMenuItem(value: m, child: Row(children: [Icon(_muscleIcons[m], size: 16, color: AppTheme.primaryTeal), const SizedBox(width: 8), Text(m.toUpperCase())]))).toList())),
      const Spacer(),
      IconButton(icon: Icon(_showGhost ? Icons.visibility : Icons.visibility_off, color: _showGhost ? AppTheme.primaryTeal : Colors.white70), padding: EdgeInsets.zero, constraints: const BoxConstraints(minWidth: 36, minHeight: 36), onPressed: _toggleGhost),
      IconButton(icon: const Icon(Icons.history, color: Colors.white), padding: EdgeInsets.zero, constraints: const BoxConstraints(minWidth: 36, minHeight: 36), onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => HistoryScreen(muscleGroup: _selectedMuscleGroup)))),
      // R-6: Live Measure shortcut
      IconButton(
        icon: const Icon(Icons.videocam, color: AppTheme.accentGreen, size: 20),
        padding: EdgeInsets.zero,
        constraints: const BoxConstraints(minWidth: 36, minHeight: 36),
        tooltip: 'Live Measure',
        onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const LivePreviewScreen())),
      ),
    ])));
  }

  Widget _phaseDot(int p) { return Container(width: 8, height: 8, decoration: BoxDecoration(shape: BoxShape.circle, color: _capturePhase == p ? AppTheme.primaryTeal : ((p == 0 ? _frontPath != null : _sidePath != null) ? AppTheme.accentGreen : Colors.white24))); }

  Widget _buildCaptureUI() {
    final bottomPad = MediaQuery.of(context).padding.bottom + 24;
    return Positioned(bottom: 0, left: 0, right: 0, child: Container(padding: EdgeInsets.fromLTRB(24, 16, 24, bottomPad), decoration: const BoxDecoration(gradient: LinearGradient(begin: Alignment.bottomCenter, end: Alignment.topCenter, colors: [Colors.black87, Colors.transparent])), child: Column(mainAxisSize: MainAxisSize.min, children: [
      Container(margin: const EdgeInsets.only(bottom: 16), decoration: BoxDecoration(color: Colors.white10, borderRadius: BorderRadius.circular(20)), child: Row(mainAxisSize: MainAxisSize.min, children: [_modeBtn('PHOTO', !_isRecordingMode), _modeBtn('VIDEO', _isRecordingMode)])),
      AnimatedSwitcher(duration: const Duration(milliseconds: 300), child: _isRecording ? Text('00:0$_recordingCountdown', key: const ValueKey('timer'), style: const TextStyle(color: AppTheme.accentRed, fontSize: 32, fontWeight: FontWeight.bold)) : Row(mainAxisSize: MainAxisSize.min, children: [_phaseDot(0), const SizedBox(width: 6), Text(_phaseLabels[_capturePhase], key: ValueKey(_capturePhase), style: const TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.bold, letterSpacing: 2)), const SizedBox(width: 6), _phaseDot(1)])),
      const SizedBox(height: 12),
      if (_statusMessage != null) Text(_statusMessage!, style: const TextStyle(color: AppTheme.primaryTeal, fontSize: 13, fontWeight: FontWeight.w500)),
      const SizedBox(height: 24),
      Row(mainAxisAlignment: MainAxisAlignment.center, children: [
        if (_frontPath != null) IconButton(onPressed: _resetCapture, icon: const Icon(Icons.refresh, color: Colors.white54)),
        const SizedBox(width: 24),
        GestureDetector(onTap: isLevel && !_isCapturing ? (_isRecordingMode ? _toggleRecording : _captureImage) : null, child: Container(width: 76, height: 76, decoration: BoxDecoration(shape: BoxShape.circle, color: _isRecording ? AppTheme.accentRed : (isLevel ? AppTheme.primaryTeal : Colors.grey.shade800), border: Border.all(color: Colors.white, width: 4)), child: _isCapturing || (_isUploading && _isRecordingMode) ? const Padding(padding: EdgeInsets.all(20), child: CircularProgressIndicator(color: Colors.black, strokeWidth: 3)) : Icon(_isRecordingMode ? (_isRecording ? Icons.stop : Icons.videocam) : _phaseIcons[_capturePhase], color: Colors.black, size: 36))),
        const SizedBox(width: 72),
      ]),
    ])));
  }

  Widget _modeBtn(String l, bool a) { return GestureDetector(onTap: () => setState(() { _isRecordingMode = l == 'VIDEO'; _statusMessage = null; }), child: Container(padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6), decoration: BoxDecoration(color: a ? AppTheme.primaryTeal : Colors.transparent, borderRadius: BorderRadius.circular(20)), child: Text(l, style: TextStyle(color: a ? Colors.black : Colors.white70, fontWeight: FontWeight.bold, fontSize: 11)))); }

  void _showProfile() {
    showDialog(context: context, builder: (c) => AlertDialog(backgroundColor: AppTheme.cardBg, title: Row(children: [const Icon(Icons.account_circle, color: AppTheme.primaryTeal), const SizedBox(width: 12), Text(_customerName ?? 'Profile')]), content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [Text('ID: $_customerId', style: const TextStyle(color: Colors.white70)), const Text('Role: Clinical Data Contributor', style: TextStyle(color: AppTheme.primaryTeal, fontSize: 11))]), actions: [TextButton(onPressed: () { _jwtToken = null; Navigator.pushAndRemoveUntil(context, MaterialPageRoute(builder: (_) => const LoginScreen()), (r) => false); }, child: const Text('LOGOUT', style: TextStyle(color: AppTheme.accentRed))), TextButton(onPressed: () => Navigator.pop(c), child: const Text('CLOSE'))]));
  }

  Widget _buildUploadOverlay() { return Container(color: Colors.black.withOpacity(0.87), child: const Center(child: Column(mainAxisSize: MainAxisSize.min, children: [CircularProgressIndicator(color: AppTheme.primaryTeal), SizedBox(height: 20), Text('Vision Engine Analysis...', style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold)), Text('Quantifying muscle metrics', style: TextStyle(color: Colors.white54, fontSize: 12))]))); }
}

// --- SUPPORTING UI ---

// R-6: Enhanced BodyGuidePainter with colored joint indicators and guidance text
class BodyGuidePainter extends CustomPainter {
  final int phase;
  final String muscleGroup;
  BodyGuidePainter({required this.phase, this.muscleGroup = 'bicep'});

  static const _guidanceText = {
    'bicep':  'Flex arm, elbow ~90°, raise to shoulder',
    'tricep': 'Extend arm back, elbow straight',
    'quad':   'Stand straight, legs together',
    'calf':   'Stand straight, heels on ground',
    'delt':   'Arms at sides, slight abduction',
    'lat':    'Arms wide, lat spread pose',
  };

  @override
  void paint(Canvas canvas, Size size) {
    final outline = Paint()..color = Colors.white.withOpacity(0.1)..style = PaintingStyle.stroke..strokeWidth = 1.0;
    final jointPrimary   = Paint()..color = AppTheme.primaryTeal.withOpacity(0.7)..style = PaintingStyle.fill;
    final jointSecondary = Paint()..color = AppTheme.accentGreen.withOpacity(0.6)..style = PaintingStyle.fill;
    final cx = size.width / 2, cy = size.height / 2;

    if (phase == 0) {
      // Body outline — front
      canvas.drawPath(Path()..moveTo(cx - 50, cy - 100)..lineTo(cx - 70, cy - 60)..lineTo(cx - 40, cy + 100)..lineTo(cx + 40, cy + 100)..lineTo(cx + 70, cy - 60)..lineTo(cx + 50, cy - 100)..close(), outline);
      canvas.drawCircle(Offset(cx, cy - 130), 25, outline);
      // Joint dots: shoulders (primary), elbows (secondary based on muscle), hips (secondary)
      canvas.drawCircle(Offset(cx - 52, cy - 62), 6, jointPrimary);   // L shoulder
      canvas.drawCircle(Offset(cx + 52, cy - 62), 6, jointPrimary);   // R shoulder
      canvas.drawCircle(Offset(cx - 68, cy - 10), 5, jointSecondary); // L elbow
      canvas.drawCircle(Offset(cx + 68, cy - 10), 5, jointSecondary); // R elbow
      canvas.drawCircle(Offset(cx - 38, cy + 2),  5, jointSecondary); // L hip
      canvas.drawCircle(Offset(cx + 38, cy + 2),  5, jointSecondary); // R hip
      canvas.drawCircle(Offset(cx - 38, cy + 56), 5, jointSecondary); // L knee
      canvas.drawCircle(Offset(cx + 38, cy + 56), 5, jointSecondary); // R knee
    } else {
      // Body outline — side
      canvas.drawPath(Path()..moveTo(cx - 15, cy - 100)..lineTo(cx - 25, cy - 60)..lineTo(cx - 20, cy + 100)..lineTo(cx + 20, cy + 100)..lineTo(cx + 35, cy - 60)..lineTo(cx + 15, cy - 100)..close(), outline);
      canvas.drawCircle(Offset(cx + 5, cy - 130), 24, outline);
      canvas.drawCircle(Offset(cx + 20, cy - 62), 6, jointPrimary);   // shoulder (side)
      canvas.drawCircle(Offset(cx + 32, cy - 8),  5, jointSecondary); // elbow (side)
      canvas.drawCircle(Offset(cx + 10, cy + 2),  5, jointSecondary); // hip (side)
      canvas.drawCircle(Offset(cx + 12, cy + 56), 5, jointSecondary); // knee (side)
    }

    // Guidance text strip at top-left
    final guidance = _guidanceText[muscleGroup] ?? '';
    if (guidance.isNotEmpty) {
      final tp = TextPainter(
        text: TextSpan(text: guidance, style: const TextStyle(color: Color(0xFFB2EBF2), fontSize: 11, fontWeight: FontWeight.w500)),
        textDirection: TextDirection.ltr,
      )..layout(maxWidth: size.width - 32);
      tp.paint(canvas, Offset(16, size.height * 0.62));
    }
  }

  @override
  bool shouldRepaint(covariant BodyGuidePainter old) => old.phase != phase || old.muscleGroup != muscleGroup;
}

class LevelPainter extends CustomPainter {
  final double pitch, roll; final Color color; LevelPainter({required this.pitch, required this.roll, required this.color});
  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, 120);
    canvas.drawCircle(center, 35, Paint()..color = Colors.white24..style = PaintingStyle.stroke..strokeWidth = 1.0);
    canvas.drawLine(Offset(center.dx - 35, center.dy), Offset(center.dx + 35, center.dy), Paint()..color = Colors.white10);
    canvas.drawLine(Offset(center.dx, center.dy - 35), Offset(center.dx, center.dy + 35), Paint()..color = Colors.white10);
    final b = Offset(center.dx - roll.clamp(-3.0, 3.0) * 10, center.dy - pitch.clamp(-3.0, 3.0) * 10);
    canvas.drawCircle(b, 10, Paint()..color = color);
    if (color == AppTheme.accentGreen) canvas.drawCircle(b, 18, Paint()..color = color.withOpacity(0.1));
  }
  @override
  bool shouldRepaint(covariant CustomPainter old) => true;
}

class GhostOverlayPainter extends CustomPainter {
  final ui.Image? image; GhostOverlayPainter({this.image});
  @override
  void paint(Canvas canvas, Size size) {
    if (image == null) return;
    double sw = image!.width.toDouble(), sh = image!.height.toDouble(), dw = size.width, dh = size.height;
    double scale = (dw / sw > dh / sh) ? dh / sh : dw / sw;
    double fw = sw * scale, fh = sh * scale, dx = (dw - fw) / 2, dy = (dh - fh) / 2;
    canvas.drawImageRect(image!, Rect.fromLTWH(0, 0, sw, sh), Rect.fromLTWH(dx, dy, fw, fh), Paint()..color = Colors.white.withOpacity(0.2));
  }
  @override
  bool shouldRepaint(covariant GhostOverlayPainter old) => old.image != image;
}

class ReviewScreen extends StatelessWidget {
  final String frontPath, sidePath; const ReviewScreen({super.key, required this.frontPath, required this.sidePath});
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

class ResultsScreen extends StatefulWidget {
  final Map<String, dynamic> result;
  final String muscleGroup;
  const ResultsScreen({super.key, required this.result, required this.muscleGroup});
  @override
  State<ResultsScreen> createState() => _ResultsScreenState();
}

class _ResultsScreenState extends State<ResultsScreen> {
  bool _downloadingReport = false;

  Future<void> _downloadSessionReport(int scanId) async {
    setState(() => _downloadingReport = true);
    try {
      final res = await http.post(
        Uri.parse('${AppConfig.serverBaseUrl}/api/customer/$_customerId/session_report'),
        headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ${_jwtToken ?? ''}'},
        body: jsonEncode({'scan_id': scanId}),
      ).timeout(const Duration(seconds: 30));
      if (!mounted) return;
      if (res.statusCode == 200) {
        final dir  = await getTemporaryDirectory();
        final file = File('${dir.path}/session_report_$scanId.pdf');
        await file.writeAsBytes(res.bodyBytes);
        await Share.shareXFiles([XFile(file.path)], text: 'Muscle Tracker Session Report');
      } else {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Report generation failed')));
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error: $e')));
    } finally {
      if (mounted) setState(() => _downloadingReport = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final r          = widget.result;
    final muscleGroup = widget.muscleGroup;
    final vol        = r['volume_cm3']?.toDouble()        ?? 0.0;
    final growth     = r['growth_pct']?.toDouble();
    final delta      = r['volume_delta_cm3']?.toDouble();
    final score      = r['shape_score']?.toDouble();
    final grade      = r['shape_grade'];
    final calibrated = r['calibrated']  ?? false;
    final scanId     = r['scan_id'];
    final circCm     = r['circumference_cm']?.toDouble();
    final defScore   = r['definition_score']?.toDouble();
    final defGrade   = r['definition_grade'] as String?;
    final annUrl     = r['annotated_img_url'] as String?;

    return Scaffold(
      appBar: AppBar(title: const Text('Scan Analysis')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [

          // ── Volume hero card ──────────────────────────────────────────
          Card(child: Padding(padding: const EdgeInsets.all(32), child: Column(children: [
            Text(muscleGroup.toUpperCase(),
                style: const TextStyle(color: AppTheme.primaryTeal, fontWeight: FontWeight.w900, letterSpacing: 3)),
            const SizedBox(height: 16),
            Text('${vol.toStringAsFixed(1)} cm³',
                style: const TextStyle(fontSize: 52, fontWeight: FontWeight.bold, color: Colors.white)),
            const Text('QUANTIFIED VOLUME', style: TextStyle(color: Colors.white38, letterSpacing: 1.5)),
            const SizedBox(height: 20),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
              decoration: BoxDecoration(
                color: calibrated ? Colors.green.withOpacity(0.1) : Colors.orange.withOpacity(0.1),
                borderRadius: BorderRadius.circular(20),
                border: Border.all(color: calibrated ? AppTheme.accentGreen : Colors.orange, width: 0.5),
              ),
              child: Text(
                calibrated ? 'OPTICAL CALIBRATION ACTIVE' : 'ESTIMATED SCALE',
                style: TextStyle(color: calibrated ? AppTheme.accentGreen : Colors.orange, fontSize: 10, fontWeight: FontWeight.bold),
              ),
            ),
          ]))),
          const SizedBox(height: 12),

          // ── Annotated image preview ───────────────────────────────────
          if (annUrl != null)
            Card(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Padding(padding: EdgeInsets.fromLTRB(16, 14, 0, 8),
                  child: Text('ANNOTATED IMAGE', style: TextStyle(color: AppTheme.primaryTeal, fontWeight: FontWeight.bold, fontSize: 11, letterSpacing: 1.2))),
              ClipRRect(
                borderRadius: const BorderRadius.only(bottomLeft: Radius.circular(12), bottomRight: Radius.circular(12)),
                child: Image.network(
                  '${AppConfig.serverBaseUrl}$annUrl',
                  headers: {'Authorization': 'Bearer ${_jwtToken ?? ''}'},
                  fit: BoxFit.contain,
                  errorBuilder: (_, __, ___) => const SizedBox.shrink(),
                ),
              ),
            ])),
          if (annUrl != null) const SizedBox(height: 12),

          // ── Metrics row (growth + circumference + definition) ─────────
          Row(children: [
            if (growth != null) Expanded(child: Card(child: Padding(padding: const EdgeInsets.all(16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text('Growth', style: TextStyle(color: Colors.white54, fontSize: 11)),
              const SizedBox(height: 6),
              Text('${growth > 0 ? "+" : ""}${growth.toStringAsFixed(1)}%',
                  style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold,
                      color: growth >= 0 ? AppTheme.accentGreen : AppTheme.accentRed)),
              if (delta != null) Text('${delta > 0 ? "+" : ""}${delta.toStringAsFixed(1)} cm³',
                  style: const TextStyle(color: Colors.white38, fontSize: 11)),
            ])))),
            if (circCm != null) ...[
              const SizedBox(width: 10),
              Expanded(child: Card(child: Padding(padding: const EdgeInsets.all(16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Text('Circumference', style: TextStyle(color: Colors.white54, fontSize: 11)),
                const SizedBox(height: 6),
                Text('${circCm.toStringAsFixed(1)} cm',
                    style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: Colors.white)),
                Text('${(circCm / 2.54).toStringAsFixed(1)} in',
                    style: const TextStyle(color: Colors.white38, fontSize: 11)),
              ])))),
            ],
          ]),
          const SizedBox(height: 10),

          // ── Shape + Definition ────────────────────────────────────────
          Row(children: [
            if (score != null) Expanded(child: Card(child: Padding(padding: const EdgeInsets.all(16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text('Shape', style: TextStyle(color: Colors.white54, fontSize: 11)),
              const SizedBox(height: 6),
              Row(children: [
                Text('${score.toStringAsFixed(0)}/100',
                    style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: Colors.white70)),
                const SizedBox(width: 10),
                Container(padding: const EdgeInsets.all(8), decoration: const BoxDecoration(shape: BoxShape.circle, color: AppTheme.primaryTeal),
                    child: Text(grade ?? '-', style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.black, fontSize: 13))),
              ]),
            ])))),
            if (defScore != null) ...[
              const SizedBox(width: 10),
              Expanded(child: Card(child: Padding(padding: const EdgeInsets.all(16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Text('Definition', style: TextStyle(color: Colors.white54, fontSize: 11)),
                const SizedBox(height: 6),
                Row(children: [
                  Text('${defScore.toStringAsFixed(0)}/100',
                      style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: Colors.white70)),
                  if (defGrade != null) ...[
                    const SizedBox(width: 10),
                    Container(padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                        decoration: BoxDecoration(color: Colors.orange.withOpacity(0.2), borderRadius: BorderRadius.circular(8)),
                        child: Text(defGrade, style: const TextStyle(color: Colors.orange, fontWeight: FontWeight.bold, fontSize: 12))),
                  ],
                ]),
              ])))),
            ],
          ]),
          const SizedBox(height: 36),

          // ── Action buttons ────────────────────────────────────────────
          if (scanId != null) ...[
            _downloadingReport
                ? const Center(child: Padding(padding: EdgeInsets.all(8), child: CircularProgressIndicator(color: AppTheme.primaryTeal)))
                : FilledButton.icon(
                    onPressed: () => _downloadSessionReport(scanId),
                    icon: const Icon(Icons.picture_as_pdf),
                    label: const Text('DOWNLOAD SESSION REPORT'),
                    style: FilledButton.styleFrom(backgroundColor: const Color(0xFF1A3A4A), foregroundColor: Colors.white),
                  ),
            const SizedBox(height: 10),
            FilledButton.icon(
              onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => ReportViewerScreen(scanId: scanId))),
              icon: const Icon(Icons.summarize),
              label: const Text('VIEW CLINICAL REPORT'),
              style: FilledButton.styleFrom(backgroundColor: Colors.white10, foregroundColor: Colors.white),
            ),
            const SizedBox(height: 10),
          ],
          FilledButton.icon(
            onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const LivePreviewScreen())),
            icon: const Icon(Icons.videocam),
            label: const Text('LIVE MEASURE'),
            style: FilledButton.styleFrom(backgroundColor: const Color(0xFF0D3B2A), foregroundColor: AppTheme.accentGreen),
          ),
          const SizedBox(height: 10),
          FilledButton.icon(
            onPressed: () => Navigator.pop(context),
            icon: const Icon(Icons.add_a_photo),
            label: const Text('NEW SCAN'),
          ),
          TextButton(
            onPressed: () => Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => HistoryScreen(muscleGroup: muscleGroup))),
            child: const Text('VIEW FULL HISTORY', style: TextStyle(color: AppTheme.primaryTeal)),
          ),
        ]),
      ),
    );
  }
}

class HistoryScreen extends StatefulWidget {
  final String? muscleGroup; const HistoryScreen({super.key, this.muscleGroup});
  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  bool _l = true; String? _e; List<dynamic> _s = [];
  @override
  void initState() { super.initState(); _f(); }
  Future<void> _f() async {
    setState(() { _l = true; _e = null; });
    try {
      final res = await http.get(Uri.parse('${AppConfig.serverBaseUrl}/api/customer/$_customerId/scans${widget.muscleGroup != null ? "?muscle_group=${widget.muscleGroup}" : ""}'), headers: {'Authorization': 'Bearer ${_jwtToken ?? ''}'});
      final d = jsonDecode(res.body);
      if (res.statusCode == 200 && d['status'] == 'success') setState(() { _s = d['scans']; _l = false; });
      else setState(() { _e = d['message'] ?? 'Load failed'; _l = false; });
    } catch (err) { setState(() { _e = 'Error: $err'; _l = false; }); }
  }
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Clinical History')),
      body: _l ? const Center(child: CircularProgressIndicator()) : (_e != null ? Center(child: Text(_e!)) : Column(children: [
        Padding(padding: const EdgeInsets.all(16), child: Row(children: [
          Expanded(child: FilledButton.icon(onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => ProgressScreen(muscleGroup: widget.muscleGroup))), icon: const Icon(Icons.trending_up), label: const Text('TRENDS'), style: FilledButton.styleFrom(backgroundColor: const Color(0xFF1A237E), foregroundColor: Colors.white))),
          const SizedBox(width: 8),
          Expanded(child: FilledButton.icon(onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const HealthLogScreen())), icon: const Icon(Icons.monitor_heart), label: const Text('HEALTH'), style: FilledButton.styleFrom(backgroundColor: const Color(0xFF37474F), foregroundColor: Colors.white))),
        ])),
        Expanded(child: _s.isEmpty ? const Center(child: Text('No data found')) : ListView.builder(itemCount: _s.length, itemBuilder: (c, i) {
          final sc = _s[i], vol = sc['volume_cm3']?.toDouble() ?? 0.0, gr = sc['growth_pct']?.toDouble(), id = sc['id'];
          return Card(margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6), child: ListTile(
            title: Text('${sc['scan_date'].split('T')[0]} - ${sc['muscle_group'].toUpperCase()}', style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
            subtitle: Text('Volume: ${vol.toStringAsFixed(1)} cm³ | Grade: ${sc['shape_grade'] ?? "-"}', style: const TextStyle(fontSize: 12)),
            trailing: Row(mainAxisSize: MainAxisSize.min, children: [
              if (gr != null) Text('${gr > 0 ? "+" : ""}${gr.toStringAsFixed(1)}%', style: TextStyle(fontWeight: FontWeight.bold, color: gr >= 0 ? AppTheme.accentGreen : AppTheme.accentRed)),
              const SizedBox(width: 8),
              IconButton(icon: const Icon(Icons.summarize, color: AppTheme.primaryTeal, size: 20), onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => ReportViewerScreen(scanId: id)))),
            ]),
          ));
        })),
      ])),
    );
  }
}

class ProgressScreen extends StatefulWidget {
  final String? muscleGroup; const ProgressScreen({super.key, this.muscleGroup});
  @override
  State<ProgressScreen> createState() => _ProgressScreenState();
}

class _ProgressScreenState extends State<ProgressScreen> {
  bool _l = true; String? _e; Map<String, dynamic>? _d;
  @override
  void initState() { super.initState(); _f(); }
  Future<void> _f() async {
    setState(() { _l = true; _e = null; });
    try {
      final res = await http.get(Uri.parse('${AppConfig.serverBaseUrl}/api/customer/$_customerId/progress${widget.muscleGroup != null ? "?muscle_group=${widget.muscleGroup}" : ""}'), headers: {'Authorization': 'Bearer ${_jwtToken ?? ''}'});
      final data = jsonDecode(res.body);
      if (res.statusCode == 200 && data['status'] == 'success') setState(() { _d = data; _l = false; });
      else setState(() { _e = data['message'] ?? 'Load failed'; _l = false; });
    } catch (err) { setState(() { _e = 'Error: $err'; _l = false; }); }
  }
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Progress Analytics')),
      body: _l ? const Center(child: CircularProgressIndicator()) : (_e != null ? Center(child: Text(_e!)) : _buildBody()),
    );
  }
  Widget _buildBody() {
    final tr = _d?['trend'] ?? {}; if (tr['status'] == 'Insufficient Data' || tr.isEmpty) return const Center(child: Text('Add more scans to unlock analytics'));
    final sm = _d?['volume_summary'] ?? {}, st = _d?['growth_streak'] ?? {}, dir = tr['direction'] ?? 'unknown', col = dir == 'gaining' ? AppTheme.accentGreen : (dir == 'losing' ? AppTheme.accentRed : Colors.orangeAccent);
    return SingleChildScrollView(padding: const EdgeInsets.all(24), child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      const Text('OVERALL CLINICAL TREND', style: TextStyle(color: AppTheme.primaryTeal, fontWeight: FontWeight.bold, letterSpacing: 2, fontSize: 12)),
      Text(dir.toUpperCase(), style: TextStyle(fontSize: 40, fontWeight: FontWeight.w900, color: col)),
      const SizedBox(height: 32),
      _stat('Total Change', '${sm['total_change_cm3']?.toStringAsFixed(1) ?? "0"} cm³ (${sm['total_change_pct']?.toStringAsFixed(1) ?? "0"}%)'),
      _stat('Weekly Growth', '${tr['weekly_rate_cm3']?.toStringAsFixed(2) ?? "0"} cm³/wk'),
      _stat('Consistency (R²)', '${tr['consistency_r2']?.toStringAsFixed(2) ?? "0"}'),
      _stat('30-Day Forecast', '${tr['projected_30d_cm3']?.toStringAsFixed(1) ?? "0"} cm³'),
      _stat('Growth Streak', '${st['consecutive_gains'] ?? 0} cycles'),
      const SizedBox(height: 32),
      if (_d?['correlation'] != null) ...[
        const Text('HEALTH CORRELATIONS', style: TextStyle(color: AppTheme.primaryTeal, fontWeight: FontWeight.bold, letterSpacing: 2, fontSize: 12)),
        const SizedBox(height: 16),
        ...(_d!['correlation'] as Map<String, dynamic>).entries.map((e) {
          final v = e.value as double, c = v > 0 ? AppTheme.accentGreen : AppTheme.accentRed, str = v.abs() > 0.7 ? 'Strong' : (v.abs() > 0.4 ? 'Moderate' : 'Weak');
          return _stat(e.key.replaceAll('_', ' ').toUpperCase(), '$str ${v > 0 ? "Positive" : "Negative"} (${v.toStringAsFixed(2)})', valCol: c);
        }),
      ],
    ]));
  }
  Widget _stat(String l, String v, {Color? valCol}) { return Card(margin: const EdgeInsets.only(bottom: 12), child: Padding(padding: const EdgeInsets.all(16), child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [Expanded(child: Text(l, style: const TextStyle(color: Colors.white54, fontSize: 14))), Text(v, style: TextStyle(color: valCol ?? Colors.white, fontSize: 15, fontWeight: FontWeight.bold))]))); }
}

class HealthLogScreen extends StatefulWidget {
  const HealthLogScreen({super.key});
  @override
  State<HealthLogScreen> createState() => _HealthLogScreenState();
}

class _HealthLogScreenState extends State<HealthLogScreen> {
  final _fk = GlobalKey<FormState>(), _cals = TextEditingController(), _pro = TextEditingController(), _carb = TextEditingController(), _fat = TextEditingController(), _wat = TextEditingController(), _at = TextEditingController(), _ad = TextEditingController(), _slp = TextEditingController(), _wt = TextEditingController(), _nts = TextEditingController();
  bool _sub = false;
  Future<void> _s() async {
    if (!_fk.currentState!.validate()) return;
    setState(() => _sub = true);
    try {
      final res = await http.post(Uri.parse('${AppConfig.serverBaseUrl}/api/customer/$_customerId/health_log'), headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ${_jwtToken ?? ''}'}, body: jsonEncode({'calories_in': int.tryParse(_cals.text) ?? 0, 'protein_g': int.tryParse(_pro.text) ?? 0, 'carbs_g': int.tryParse(_carb.text) ?? 0, 'fat_g': int.tryParse(_fat.text) ?? 0, 'water_ml': int.tryParse(_wat.text) ?? 0, 'activity_type': _at.text, 'activity_duration_min': int.tryParse(_ad.text) ?? 0, 'sleep_hours': double.tryParse(_slp.text) ?? 0.0, 'body_weight_kg': double.tryParse(_wt.text) ?? 0.0, 'notes': _nts.text}));
      if (res.statusCode == 200 || res.statusCode == 201) { ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Log saved'))); Navigator.pop(context); }
      else { ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error: ${jsonDecode(res.body)['message']}'))); }
    } catch (e) { ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Network error: $e'))); }
    finally { if (mounted) setState(() => _sub = false); }
  }
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Log Health Data')),
      body: SingleChildScrollView(padding: const EdgeInsets.all(24), child: Form(key: _fk, child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        _title('NUTRITION'),
        Row(children: [Expanded(child: _tf(_cals, 'Calories', Icons.local_fire_department, num: true)), const SizedBox(width: 16), Expanded(child: _tf(_pro, 'Protein (g)', Icons.egg, num: true))]),
        const SizedBox(height: 12),
        Row(children: [Expanded(child: _tf(_carb, 'Carbs (g)', Icons.bakery_dining, num: true)), const SizedBox(width: 16), Expanded(child: _tf(_fat, 'Fat (g)', Icons.opacity, num: true))]),
        const SizedBox(height: 12),
        _tf(_wat, 'Water (ml)', Icons.water_drop, num: true),
        const SizedBox(height: 32),
        _title('ACTIVITY & RECOVERY'),
        _tf(_at, 'Activity Type', Icons.directions_run),
        const SizedBox(height: 12),
        Row(children: [Expanded(child: _tf(_ad, 'Duration (m)', Icons.timer, num: true)), const SizedBox(width: 16), Expanded(child: _tf(_slp, 'Sleep (h)', Icons.bedtime, num: true))]),
        const SizedBox(height: 32),
        _title('VITALS'),
        _tf(_wt, 'Weight (kg)', Icons.monitor_weight, num: true),
        const SizedBox(height: 12),
        _tf(_nts, 'Notes', Icons.notes, lines: 2),
        const SizedBox(height: 40),
        _sub ? const Center(child: CircularProgressIndicator()) : FilledButton.icon(onPressed: _s, icon: const Icon(Icons.save), label: const Text('SAVE LOG')),
        TextButton(onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const HealthLogListScreen())), child: const Text('VIEW HISTORY', style: TextStyle(color: AppTheme.primaryTeal))),
      ]))),
    );
  }
  Widget _title(String t) => Padding(padding: const EdgeInsets.only(bottom: 16), child: Text(t, style: const TextStyle(color: AppTheme.primaryTeal, fontWeight: FontWeight.bold, letterSpacing: 1.2, fontSize: 12)));
  Widget _tf(TextEditingController c, String l, IconData i, {bool num = false, int lines = 1}) => TextFormField(controller: c, decoration: InputDecoration(labelText: l, prefixIcon: Icon(i, size: 18), labelStyle: const TextStyle(fontSize: 13)), keyboardType: num ? TextInputType.number : null, maxLines: lines);
}

class HealthLogListScreen extends StatefulWidget {
  const HealthLogListScreen({super.key});
  @override
  State<HealthLogListScreen> createState() => _HealthLogListScreenState();
}

class _HealthLogListScreenState extends State<HealthLogListScreen> {
  bool _l = true; List<dynamic> _logs = [];
  @override
  void initState() { super.initState(); _f(); }
  Future<void> _f() async {
    try {
      final res = await http.get(Uri.parse('${AppConfig.serverBaseUrl}/api/customer/$_customerId/health_logs'), headers: {'Authorization': 'Bearer ${_jwtToken ?? ''}'});
      final d = jsonDecode(res.body);
      if (res.statusCode == 200 && d['status'] == 'success') setState(() { _logs = d['logs']; _l = false; });
      else setState(() { _l = false; });
    } catch (e) { setState(() { _l = false; }); }
  }
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Health History')),
      body: _l ? const Center(child: CircularProgressIndicator()) : (_logs.isEmpty ? const Center(child: Text('No logs found')) : ListView.builder(itemCount: _logs.length, itemBuilder: (c, i) {
        final log = _logs[i]; return Card(margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6), child: Padding(padding: const EdgeInsets.all(16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [Text(log['log_date'], style: const TextStyle(fontWeight: FontWeight.bold, color: AppTheme.primaryTeal)), Text('${log['body_weight_kg'] ?? "-"} kg', style: const TextStyle(color: Colors.white54, fontSize: 12))]),
          const Divider(height: 24, color: Colors.white10),
          Row(mainAxisAlignment: MainAxisAlignment.spaceAround, children: [
            _stat(Icons.local_fire_department, '${log['calories_in'] ?? 0}', 'kcal'),
            _stat(Icons.egg, '${log['protein_g'] ?? 0}', 'g'),
            _stat(Icons.bedtime, '${log['sleep_hours'] ?? 0}', 'h'),
          ]),
          if (log['activity_type'] != null) Padding(padding: const EdgeInsets.only(top: 12), child: Text('Activity: ${log['activity_type']} (${log['activity_duration_min']}m)', style: const TextStyle(color: Colors.white38, fontSize: 11))),
        ])));
      })),
    );
  }
  Widget _stat(IconData i, String v, String u) => Column(children: [Icon(i, color: AppTheme.primaryTeal, size: 16), const SizedBox(height: 4), Text(v, style: const TextStyle(fontWeight: FontWeight.bold)), Text(u, style: const TextStyle(color: Colors.white38, fontSize: 10))]);
}

class RegisterScreen extends StatefulWidget {
  const RegisterScreen({super.key});
  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  final _fk = GlobalKey<FormState>(), _name = TextEditingController(), _em = TextEditingController(), _h = TextEditingController(), _w = TextEditingController();
  String _g = 'Male'; bool _l = false;
  Future<void> _reg() async {
    if (!_fk.currentState!.validate()) return;
    setState(() => _l = true);
    try {
      final res = await http.post(Uri.parse('${AppConfig.serverBaseUrl}/api/customers'), headers: {'Content-Type': 'application/json'}, body: jsonEncode({'name': _name.text.trim(), 'email': _em.text.trim(), 'height_cm': double.tryParse(_h.text) ?? 0.0, 'weight_kg': double.tryParse(_w.text) ?? 0.0, 'gender': _g}));
      if (res.statusCode == 200 || res.statusCode == 201) {
        final lres = await http.post(Uri.parse('${AppConfig.serverBaseUrl}/api/auth/token'), headers: {'Content-Type': 'application/json'}, body: jsonEncode({'email': _em.text.trim()}));
        final ld = jsonDecode(lres.body);
        if (lres.statusCode == 200) { _jwtToken = ld['token']; _customerId = ld['customer_id']?.toString() ?? '1'; _customerName = ld['name'] ?? _name.text; Navigator.pushAndRemoveUntil(context, MaterialPageRoute(builder: (_) => const CameraLevelScreen()), (r) => false); }
      } else { ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(jsonDecode(res.body)['message'] ?? 'Failed'))); }
    } catch (e) { ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error: $e'))); }
    finally { if (mounted) setState(() => _l = false); }
  }
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Create Account')),
      body: SingleChildScrollView(padding: const EdgeInsets.all(32), child: Form(key: _fk, child: Column(children: [
        _f(_name, 'Full Name', Icons.person), const SizedBox(height: 16),
        _f(_em, 'Email', Icons.email, type: TextInputType.emailAddress), const SizedBox(height: 16),
        Row(children: [Expanded(child: _f(_h, 'Height (cm)', Icons.height, num: true)), const SizedBox(width: 16), Expanded(child: _f(_w, 'Weight (kg)', Icons.monitor_weight, num: true))]),
        const SizedBox(height: 16),
        DropdownButtonFormField<String>(value: _g, dropdownColor: AppTheme.cardBg, decoration: const InputDecoration(labelText: 'Gender', prefixIcon: Icon(Icons.people, size: 18)), items: ['Male', 'Female', 'Other'].map((g) => DropdownMenuItem(value: g, child: Text(g))).toList(), onChanged: (v) => setState(() => _g = v!)),
        const SizedBox(height: 48),
        _l ? const CircularProgressIndicator() : SizedBox(width: double.infinity, child: FilledButton(onPressed: _reg, child: const Text('REGISTER & CONTINUE'))),
      ]))),
    );
  }
  Widget _f(TextEditingController c, String l, IconData i, {bool num = false, TextInputType? type}) => TextFormField(controller: c, decoration: InputDecoration(labelText: l, prefixIcon: Icon(i, size: 18)), keyboardType: num ? TextInputType.number : type, validator: (v) => v == null || v.isEmpty ? 'Required' : null);
}

class ReportViewerScreen extends StatelessWidget {
  final int scanId; const ReportViewerScreen({super.key, required this.scanId});
  Future<Uint8List> _f() async { final r = await http.get(Uri.parse('${AppConfig.serverBaseUrl}/api/customer/$_customerId/report/$scanId'), headers: {'Authorization': 'Bearer ${_jwtToken ?? ''}'}); if (r.statusCode == 200) return r.bodyBytes; throw Exception('Error ${r.statusCode}'); }
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Clinical Report')),
      body: FutureBuilder<Uint8List>(future: _f(), builder: (context, sn) {
        if (sn.connectionState == ConnectionState.waiting) return const Center(child: CircularProgressIndicator());
        if (sn.hasError) return Center(child: Text('Error: ${sn.error}'));
        final b = sn.data!;
        return Column(children: [
          Expanded(child: InteractiveViewer(child: Center(child: Image.memory(b)))),
          Padding(padding: const EdgeInsets.all(24), child: Row(children: [
            Expanded(child: OutlinedButton.icon(onPressed: () async { final d = await getApplicationDocumentsDirectory(); await File('${d.path}/report_$scanId.png').writeAsBytes(b); ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Saved to documents'))); }, icon: const Icon(Icons.save), label: const Text('SAVE'))),
            const SizedBox(width: 16),
            Expanded(child: FilledButton.icon(onPressed: () async { final d = await getTemporaryDirectory(); final f = File('${d.path}/r_$scanId.png'); await f.writeAsBytes(b); await Share.shareXFiles([XFile(f.path)], text: 'Muscle Tracker Report'); }, icon: const Icon(Icons.share), label: const Text('SHARE'))),
          ])),
        ]);
      }),
    );
  }
}

// --- R-5: LIVE PREVIEW SCREEN ---

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
    if (_cameras.isEmpty) return;
    final cam = _cameras.firstWhere(
      (c) => c.lensDirection == CameraLensDirection.back,
      orElse: () => _cameras.first,
    );
    _controller = CameraController(cam, ResolutionPreset.medium, enableAudio: false);
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
        headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ${_jwtToken ?? ''}'},
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

// --- R-5: CONTOUR OVERLAY PAINTER ---

class ContourOverlayPainter extends CustomPainter {
  final List<List<double>> points;
  final Color color;
  const ContourOverlayPainter({required this.points, this.color = const Color(0xFF00E5FF)});

  @override
  void paint(Canvas canvas, Size size) {
    if (points.isEmpty) return;
    final stroke = Paint()..color = color.withOpacity(0.85)..style = PaintingStyle.stroke..strokeWidth = 2.0;
    final fill   = Paint()..color = color.withOpacity(0.07)..style  = PaintingStyle.fill;
    final path = Path()..moveTo(points[0][0], points[0][1]);
    for (int i = 1; i < points.length; i++) { path.lineTo(points[i][0], points[i][1]); }
    path.close();
    canvas.drawPath(path, fill);
    canvas.drawPath(path, stroke);
    // Corner dots
    final dot = Paint()..color = color..style = PaintingStyle.fill;
    for (final p in points) { canvas.drawCircle(Offset(p[0], p[1]), 3.0, dot); }
  }

  @override
  bool shouldRepaint(covariant ContourOverlayPainter old) => old.points != points || old.color != color;
}
