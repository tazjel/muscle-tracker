import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'package:sensors_plus/sensors_plus.dart';
import 'package:path_provider/path_provider.dart';
import 'dart:async';
import 'dart:io';
import 'dart:convert';
import 'package:http/http.dart' as http;

late List<CameraDescription> _cameras;

// Server configuration — change for production
const String serverBaseUrl = 'http://10.0.2.2:8000'; // Android emulator → host
String? _jwtToken;

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  _cameras = await availableCameras();
  runApp(const MuscleCompanionApp());
}

class MuscleCompanionApp extends StatelessWidget {
  const MuscleCompanionApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Muscle Tracker',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: Colors.teal,
          brightness: Brightness.dark,
        ),
        useMaterial3: true,
      ),
      home: const LoginScreen(),
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

    setState(() {
      _isLoading = true;
      _error = null;
    });

    try {
      final response = await http.post(
        Uri.parse('$serverBaseUrl/api/auth/token'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'email': email}),
      );
      
      final data = jsonDecode(response.body);

      if (response.statusCode == 200 && data['status'] == 'success') {
        _jwtToken = data['token'];
        if (!mounted) return;
        Navigator.pushReplacement(
          context,
          MaterialPageRoute(builder: (_) => const CameraLevelScreen()),
        );
      } else {
        setState(() => _error = data['message'] ?? 'Login failed');
      }
    } catch (e) {
      setState(() => _error = 'Network error: $e');
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: const Text('Connect to Clinic'),
        backgroundColor: Colors.black,
        foregroundColor: Colors.teal,
      ),
      body: Padding(
        padding: const EdgeInsets.all(24.0),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.fitness_center, size: 64, color: Colors.teal),
            const SizedBox(height: 32),
            TextField(
              controller: _emailController,
              decoration: InputDecoration(
                labelText: 'Email Address',
                labelStyle: const TextStyle(color: Colors.teal),
                errorText: _error,
                enabledBorder: const OutlineInputBorder(
                  borderSide: BorderSide(color: Colors.white30),
                ),
                focusedBorder: const OutlineInputBorder(
                  borderSide: BorderSide(color: Colors.teal),
                ),
              ),
              style: const TextStyle(color: Colors.white),
              keyboardType: TextInputType.emailAddress,
            ),
            const SizedBox(height: 24),
            _isLoading
                ? const CircularProgressIndicator(color: Colors.teal)
                : SizedBox(
                    width: double.infinity,
                    child: FilledButton(
                      onPressed: _login,
                      style: FilledButton.styleFrom(
                        backgroundColor: Colors.teal,
                        padding: const EdgeInsets.symmetric(vertical: 16),
                      ),
                      child: const Text('CONNECT', style: TextStyle(letterSpacing: 1.5)),
                    ),
                  ),
          ],
        ),
      ),
    );
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
  double _pitch = 0.0;
  double _roll = 0.0;
  final double _levelTolerance = 0.5;

  // Capture workflow: 0 = Front, 1 = Side
  int _capturePhase = 0;
  final List<String> _phaseLabels = ['FRONT VIEW', 'SIDE VIEW'];
  final List<IconData> _phaseIcons = [Icons.person, Icons.person_outline];

  // Captured image paths
  String? _frontPath;
  String? _sidePath;

  // State flags
  bool _isCapturing = false;
  bool _isUploading = false;
  String? _statusMessage;

  // Low-pass filter for sensor smoothing
  double _filteredPitch = 0.0;
  double _filteredRoll = 0.0;
  static const double _smoothingFactor = 0.15;

  @override
  void initState() {
    super.initState();
    _initCamera();
    _initSensors();
  }

  Future<void> _initCamera() async {
    if (_cameras.isEmpty) {
      setState(() => _statusMessage = 'No cameras available');
      return;
    }
    _controller = CameraController(_cameras[0], ResolutionPreset.high);
    try {
      await _controller!.initialize();
      if (!mounted) return;
      setState(() {});
    } catch (e) {
      setState(() => _statusMessage = 'Camera init failed: $e');
    }
  }

  void _initSensors() {
    _sensorSubscription = accelerometerEventStream().listen((event) {
      if (!mounted) return;
      // Low-pass filter for stable readings
      _filteredPitch += (event.y - _filteredPitch) * _smoothingFactor;
      _filteredRoll += (event.x - _filteredRoll) * _smoothingFactor;
      setState(() {
        _pitch = _filteredPitch;
        _roll = _filteredRoll;
      });
    });
  }

  @override
  void dispose() {
    _controller?.dispose();
    _sensorSubscription?.cancel();
    super.dispose();
  }

  bool get isLevel =>
      _pitch.abs() < _levelTolerance && _roll.abs() < _levelTolerance;

  Future<void> _captureImage() async {
    if (_isCapturing || _controller == null || !_controller!.value.isInitialized) {
      return;
    }

    setState(() => _isCapturing = true);

    try {
      final XFile photo = await _controller!.takePicture();

      // Save to app directory with structured naming
      final dir = await getApplicationDocumentsDirectory();
      final scanDir = Directory('${dir.path}/scans');
      if (!await scanDir.exists()) {
        await scanDir.create(recursive: true);
      }

      final timestamp = DateTime.now().millisecondsSinceEpoch;
      final phase = _capturePhase == 0 ? 'front' : 'side';
      final savePath = '${scanDir.path}/${phase}_$timestamp.jpg';

      await File(photo.path).copy(savePath);

      setState(() {
        if (_capturePhase == 0) {
          _frontPath = savePath;
          _capturePhase = 1;
          _statusMessage = 'Front captured! Now rotate for SIDE VIEW.';
        } else {
          _sidePath = savePath;
          _statusMessage = 'Both views captured!';
        }
        _isCapturing = false;
      });

      // If both captured, show review
      if (_frontPath != null && _sidePath != null) {
        if (!mounted) return;
        final shouldUpload = await Navigator.push<bool>(
          context,
          MaterialPageRoute(
            builder: (_) => ReviewScreen(
              frontPath: _frontPath!,
              sidePath: _sidePath!,
            ),
          ),
        );

        if (shouldUpload == true) {
          _uploadScan();
        } else {
          _resetCapture();
        }
      }
    } catch (e) {
      setState(() {
        _isCapturing = false;
        _statusMessage = 'Capture failed: $e';
      });
    }
  }

  Future<void> _uploadScan() async {
    if (_frontPath == null || _sidePath == null) return;

    setState(() {
      _isUploading = true;
      _statusMessage = 'Uploading scan...';
    });

    try {
      // NOTE: Uploading to customer ID 1 for now (to match existing logic)
      final uri = Uri.parse('$serverBaseUrl/api/upload_scan/1');
      var request = http.MultipartRequest('POST', uri);
      
      // Add authentication token from memory
      request.headers['Authorization'] = 'Bearer ${_jwtToken ?? ''}';

      request.files.add(await http.MultipartFile.fromPath('front', _frontPath!));
      request.files.add(await http.MultipartFile.fromPath('side', _sidePath!));

      var streamedResponse = await request.send();
      var response = await http.Response.fromStream(streamedResponse);
      
      if (!mounted) return;

      if (response.statusCode == 401) {
        // Token expired or invalid
        _jwtToken = null;
        Navigator.pushReplacement(
          context,
          MaterialPageRoute(builder: (_) => const LoginScreen()),
        );
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Session expired. Please login again.')),
        );
        return;
      }

      final result = jsonDecode(response.body);

      if (response.statusCode == 200 && result['status'] == 'success') {
        setState(() {
          _statusMessage = 'Scan uploaded! Volume: ${result["volume_cm3"]} cm³';
          _isUploading = false;
        });

        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Volume: ${result["volume_cm3"]} cm³'),
            backgroundColor: Colors.teal,
            duration: const Duration(seconds: 5),
          ),
        );
      } else {
        setState(() {
          _statusMessage = 'Upload failed: ${result["message"] ?? response.reasonPhrase}';
          _isUploading = false;
        });
      }
    } catch (e) {
      setState(() {
        _statusMessage = 'Upload error: $e';
        _isUploading = false;
      });
    }

    _resetCapture();
  }

  void _resetCapture() {
    setState(() {
      _capturePhase = 0;
      _frontPath = null;
      _sidePath = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_controller == null || !_controller!.value.isInitialized) {
      return Scaffold(
        backgroundColor: Colors.black,
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const CircularProgressIndicator(color: Colors.teal),
              if (_statusMessage != null) ...[
                const SizedBox(height: 16),
                Text(_statusMessage!, style: const TextStyle(color: Colors.white)),
              ],
            ],
          ),
        ),
      );
    }

    return Scaffold(
      backgroundColor: Colors.black,
      body: Stack(
        fit: StackFit.expand,
        children: [
          // Camera preview
          CameraPreview(_controller!),

          // Level indicator overlay
          CustomPaint(
            painter: LevelPainter(
              pitch: _pitch,
              roll: _roll,
              color: isLevel ? Colors.greenAccent : Colors.redAccent,
            ),
          ),

          // Guide overlay (body outline)
          CustomPaint(painter: BodyGuidePainter(phase: _capturePhase)),

          // Top status bar
          _buildTopBar(),

          // Bottom capture UI
          _buildCaptureUI(),

          // Upload overlay
          if (_isUploading) _buildUploadOverlay(),
        ],
      ),
    );
  }

  Widget _buildTopBar() {
    return Positioned(
      top: 0,
      left: 0,
      right: 0,
      child: Container(
        padding: EdgeInsets.only(
          top: MediaQuery.of(context).padding.top + 8,
          left: 16,
          right: 16,
          bottom: 8,
        ),
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [Colors.black87, Colors.transparent],
          ),
        ),
        child: Row(
          children: [
            const Icon(Icons.fitness_center, color: Colors.teal, size: 20),
            const SizedBox(width: 8),
            const Text('MUSCLE TRACKER',
                style: TextStyle(
                    color: Colors.teal,
                    fontWeight: FontWeight.bold,
                    fontSize: 14)),
            const Spacer(),
            // Phase indicator dots
            Row(
              children: [
                _phaseDot(0),
                const SizedBox(width: 8),
                _phaseDot(1),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _phaseDot(int phase) {
    final isActive = _capturePhase == phase;
    final isDone = (phase == 0 && _frontPath != null) ||
        (phase == 1 && _sidePath != null);
    return Container(
      width: 10,
      height: 10,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: isDone
            ? Colors.greenAccent
            : isActive
                ? Colors.teal
                : Colors.grey.shade700,
        border: Border.all(color: Colors.white30, width: 1),
      ),
    );
  }

  Widget _buildCaptureUI() {
    return Positioned(
      bottom: 0,
      left: 0,
      right: 0,
      child: Container(
        padding: const EdgeInsets.fromLTRB(24, 16, 24, 40),
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.bottomCenter,
            end: Alignment.topCenter,
            colors: [Colors.black87, Colors.transparent],
          ),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Status message
            if (_statusMessage != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Text(
                  _statusMessage!,
                  style: const TextStyle(color: Colors.white70, fontSize: 13),
                  textAlign: TextAlign.center,
                ),
              ),

            // Phase label
            Text(
              _phaseLabels[_capturePhase],
              style: const TextStyle(
                color: Colors.white,
                fontSize: 22,
                fontWeight: FontWeight.bold,
                letterSpacing: 2,
              ),
            ),
            const SizedBox(height: 8),

            // Alignment indicator
            Container(
              padding:
                  const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
              decoration: BoxDecoration(
                color: Colors.black54,
                borderRadius: BorderRadius.circular(20),
                border: Border.all(
                  color: isLevel ? Colors.greenAccent : Colors.redAccent,
                  width: 1,
                ),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    isLevel ? Icons.check_circle : Icons.warning,
                    color: isLevel ? Colors.greenAccent : Colors.redAccent,
                    size: 16,
                  ),
                  const SizedBox(width: 8),
                  Text(
                    isLevel ? 'ALIGNED — READY' : 'TILT TO ALIGN',
                    style: TextStyle(
                      color: isLevel ? Colors.greenAccent : Colors.redAccent,
                      fontWeight: FontWeight.bold,
                      fontSize: 13,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 20),

            // Capture button
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                // Reset button
                if (_frontPath != null)
                  IconButton(
                    onPressed: _resetCapture,
                    icon:
                        const Icon(Icons.refresh, color: Colors.white54, size: 28),
                  ),

                const SizedBox(width: 20),

                // Main capture button
                GestureDetector(
                  onTap: isLevel && !_isCapturing ? _captureImage : null,
                  child: Container(
                    width: 72,
                    height: 72,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color:
                          isLevel ? Colors.teal : Colors.grey.shade800,
                      border: Border.all(
                        color: isLevel ? Colors.white : Colors.grey,
                        width: 4,
                      ),
                    ),
                    child: _isCapturing
                        ? const Padding(
                            padding: EdgeInsets.all(18),
                            child: CircularProgressIndicator(
                              color: Colors.white,
                              strokeWidth: 3,
                            ),
                          )
                        : Icon(
                            _phaseIcons[_capturePhase],
                            color: Colors.white,
                            size: 32,
                          ),
                  ),
                ),

                const SizedBox(width: 48),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildUploadOverlay() {
    return Container(
      color: Colors.black87,
      child: const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircularProgressIndicator(color: Colors.teal),
            SizedBox(height: 20),
            Text('Analyzing scan...',
                style: TextStyle(color: Colors.white, fontSize: 18)),
            SizedBox(height: 8),
            Text('This may take a moment',
                style: TextStyle(color: Colors.white54, fontSize: 14)),
          ],
        ),
      ),
    );
  }
}

// --- BODY GUIDE OVERLAY ---

class BodyGuidePainter extends CustomPainter {
  final int phase;
  BodyGuidePainter({required this.phase});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = Colors.white.withOpacity(0.15)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5;

    final cx = size.width / 2;
    final cy = size.height / 2;

    if (phase == 0) {
      // Front view: shoulders-to-hips outline
      final path = Path()
        ..moveTo(cx - 60, cy - 120)  // left shoulder
        ..lineTo(cx - 80, cy - 80)   // left arm
        ..lineTo(cx - 50, cy + 80)   // left hip
        ..lineTo(cx + 50, cy + 80)   // right hip
        ..lineTo(cx + 80, cy - 80)   // right arm
        ..lineTo(cx + 60, cy - 120)  // right shoulder
        ..close();
      canvas.drawPath(path, paint);
      // Head
      canvas.drawCircle(Offset(cx, cy - 150), 30, paint);
    } else {
      // Side view: profile outline
      final path = Path()
        ..moveTo(cx - 20, cy - 120)
        ..lineTo(cx - 30, cy - 80)
        ..lineTo(cx - 25, cy + 80)
        ..lineTo(cx + 25, cy + 80)
        ..lineTo(cx + 40, cy - 80)
        ..lineTo(cx + 20, cy - 120)
        ..close();
      canvas.drawPath(path, paint);
      canvas.drawCircle(Offset(cx + 5, cy - 150), 28, paint);
    }
  }

  @override
  bool shouldRepaint(covariant BodyGuidePainter old) => old.phase != phase;
}

// --- LEVEL INDICATOR ---

class LevelPainter extends CustomPainter {
  final double pitch, roll;
  final Color color;
  LevelPainter({required this.pitch, required this.roll, required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, 120);

    // Outer ring
    final outerPaint = Paint()
      ..color = Colors.white.withOpacity(0.3)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.0;
    canvas.drawCircle(center, 35, outerPaint);

    // Cross-hairs
    final crossPaint = Paint()
      ..color = Colors.white.withOpacity(0.15)
      ..strokeWidth = 1.0;
    canvas.drawLine(
        Offset(center.dx - 35, center.dy), Offset(center.dx + 35, center.dy), crossPaint);
    canvas.drawLine(
        Offset(center.dx, center.dy - 35), Offset(center.dx, center.dy + 35), crossPaint);

    // Level bubble
    final bubbleOffset = Offset(
      center.dx - roll.clamp(-3.0, 3.0) * 10,
      center.dy - pitch.clamp(-3.0, 3.0) * 10,
    );
    final bubblePaint = Paint()
      ..color = color
      ..style = PaintingStyle.fill;
    canvas.drawCircle(bubbleOffset, 12, bubblePaint);

    // Glow effect when level
    if (color == Colors.greenAccent) {
      final glowPaint = Paint()
        ..color = color.withOpacity(0.2)
        ..style = PaintingStyle.fill;
      canvas.drawCircle(bubbleOffset, 20, glowPaint);
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => true;
}

// --- REVIEW SCREEN ---

class ReviewScreen extends StatelessWidget {
  final String frontPath;
  final String sidePath;

  const ReviewScreen({
    super.key,
    required this.frontPath,
    required this.sidePath,
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: const Text('Review Captures'),
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
      ),
      body: Column(
        children: [
          Expanded(
            child: Row(
              children: [
                // Front preview
                Expanded(
                  child: Column(
                    children: [
                      const Padding(
                        padding: EdgeInsets.all(8),
                        child: Text('FRONT',
                            style: TextStyle(
                                color: Colors.teal,
                                fontWeight: FontWeight.bold)),
                      ),
                      Expanded(
                        child: Image.file(File(frontPath), fit: BoxFit.contain),
                      ),
                    ],
                  ),
                ),
                const VerticalDivider(color: Colors.grey, width: 1),
                // Side preview
                Expanded(
                  child: Column(
                    children: [
                      const Padding(
                        padding: EdgeInsets.all(8),
                        child: Text('SIDE',
                            style: TextStyle(
                                color: Colors.teal,
                                fontWeight: FontWeight.bold)),
                      ),
                      Expanded(
                        child: Image.file(File(sidePath), fit: BoxFit.contain),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          // Action buttons
          Padding(
            padding: const EdgeInsets.all(24),
            child: Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: () => Navigator.pop(context, false),
                    icon: const Icon(Icons.refresh),
                    label: const Text('RETAKE'),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: Colors.white70,
                      side: const BorderSide(color: Colors.white30),
                      padding: const EdgeInsets.symmetric(vertical: 16),
                    ),
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: FilledButton.icon(
                    onPressed: () => Navigator.pop(context, true),
                    icon: const Icon(Icons.cloud_upload),
                    label: const Text('ANALYZE'),
                    style: FilledButton.styleFrom(
                      backgroundColor: Colors.teal,
                      padding: const EdgeInsets.symmetric(vertical: 16),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
