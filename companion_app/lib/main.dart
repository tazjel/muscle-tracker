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
String? _customerId;
String? _customerName;

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
        _customerId = data['customer_id']?.toString() ?? '1';
        _customerName = data['name'] ?? 'User';
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
                    child: Column(
                      children: [
                        FilledButton(
                          onPressed: _login,
                          style: FilledButton.styleFrom(
                            backgroundColor: Colors.teal,
                            padding: const EdgeInsets.symmetric(vertical: 16),
                            minimumSize: const Size(double.infinity, 50),
                          ),
                          child: const Text('CONNECT', style: TextStyle(letterSpacing: 1.5)),
                        ),
                        const SizedBox(height: 16),
                        TextButton(
                          onPressed: () {
                            Navigator.push(context, MaterialPageRoute(builder: (_) => const RegisterScreen()));
                          },
                          child: const Text('CREATE ACCOUNT', style: TextStyle(color: Colors.teal)),
                        ),
                      ],
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

  // Selected muscle group
  String _selectedMuscleGroup = 'bicep';
  final List<String> _muscleGroups = ['bicep', 'tricep', 'quad', 'calf', 'delt', 'lat'];

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

  Future<bool> _runPoseCheck(String imagePath) async {
    setState(() => _statusMessage = 'Checking pose...');
    try {
      var request = http.MultipartRequest('POST', Uri.parse('$serverBaseUrl/api/pose_check'));
      request.headers['Authorization'] = 'Bearer ${_jwtToken ?? ''}';
      request.files.add(await http.MultipartFile.fromPath('image', imagePath));
      request.fields['muscle_group'] = _selectedMuscleGroup;

      var streamedResponse = await request.send().timeout(const Duration(seconds: 5));
      var response = await http.Response.fromStream(streamedResponse);
      
      if (response.statusCode == 200) {
        final result = jsonDecode(response.body);
        if (result['status'] == 'corrections_needed' && result['corrections'] != null) {
          if (!mounted) return true;
          
          List<dynamic> corrections = result['corrections'];
          String instructions = corrections.map((c) => "• ${c['instruction']}").join("\n");
          
          final shouldContinue = await showDialog<bool>(
            context: context,
            barrierDismissible: false,
            builder: (BuildContext context) {
              return AlertDialog(
                title: const Text('Pose Correction'),
                content: Text('Please adjust your pose:\n\n$instructions'),
                actions: [
                  TextButton(
                    onPressed: () => Navigator.pop(context, false), // Retake
                    child: const Text('Retake'),
                  ),
                  TextButton(
                    onPressed: () => Navigator.pop(context, true), // Continue anyway
                    child: const Text('Continue Anyway'),
                  ),
                ],
              );
            },
          );
          return shouldContinue ?? false;
        }
      }
    } catch (e) {
      // If pose check fails (timeout/network), don't block the user
      debugPrint('Pose check failed: $e');
    }
    return true; // OK or failed check -> proceed
  }

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

      if (_capturePhase == 0) {
        // Run pose check on front view
        bool proceed = await _runPoseCheck(savePath);
        if (!proceed) {
          // User chose to retake
          File(savePath).deleteSync();
          setState(() {
            _statusMessage = 'Retake Front View';
            _isCapturing = false;
          });
          return;
        }
      }

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
      final uri = Uri.parse('$serverBaseUrl/api/upload_scan/');
      var request = http.MultipartRequest('POST', uri);
      
      // Add authentication token from memory
      request.headers['Authorization'] = 'Bearer ${_jwtToken ?? ''}';

      request.files.add(await http.MultipartFile.fromPath('front', _frontPath!));
      request.files.add(await http.MultipartFile.fromPath('side', _sidePath!));
      request.fields['muscle_group'] = _selectedMuscleGroup;

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
          _isUploading = false;
        });

        _resetCapture();
        if (!mounted) return;
        
        Navigator.push(
          context,
          MaterialPageRoute(
            builder: (_) => ResultsScreen(
              result: result,
              muscleGroup: _selectedMuscleGroup,
            ),
          ),
        );
        return;
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

  void _showProfileDialog(BuildContext context) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: Colors.grey.shade900,
        title: Row(
          children: [
            const Icon(Icons.account_circle, color: Colors.teal),
            const SizedBox(width: 8),
            Text(_customerName ?? 'Profile', style: const TextStyle(color: Colors.white)),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Customer ID: ', style: const TextStyle(color: Colors.white70)),
            const SizedBox(height: 8),
            const Text('Role: Clinical User', style: TextStyle(color: Colors.teal, fontSize: 12)),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () {
              _jwtToken = null;
              _customerId = null;
              _customerName = null;
              Navigator.pushAndRemoveUntil(
                context,
                MaterialPageRoute(builder: (_) => const LoginScreen()),
                (route) => false,
              );
            },
            child: const Text('LOGOUT', style: TextStyle(color: Colors.redAccent)),
          ),
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('CLOSE')),
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
            GestureDetector(
              onTap: () => _showProfileDialog(context),
              child: Container(
                padding: const EdgeInsets.all(4),
                decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: Colors.teal, width: 1.5)),
                child: const Icon(Icons.person, color: Colors.teal, size: 20),
              ),
            ),
            const SizedBox(width: 8),
            // Muscle Group Selector
            DropdownButtonHideUnderline(
              child: DropdownButton<String>(
                value: _selectedMuscleGroup,
                dropdownColor: Colors.black87,
                icon: const Icon(Icons.arrow_drop_down, color: Colors.teal),
                style: const TextStyle(
                  color: Colors.teal,
                  fontWeight: FontWeight.bold,
                  fontSize: 14,
                ),
                onChanged: _frontPath != null ? null : (String? newValue) {
                  if (newValue != null) {
                    setState(() {
                      _selectedMuscleGroup = newValue;
                    });
                  }
                },
                items: _muscleGroups.map<DropdownMenuItem<String>>((String value) {
                  return DropdownMenuItem<String>(
                    value: value,
                    child: Text(value.toUpperCase()),
                  );
                }).toList(),
              ),
            ),
            const Spacer(),
            IconButton(
              icon: const Icon(Icons.history, color: Colors.white),
              onPressed: () {
                Navigator.push(context, MaterialPageRoute(builder: (_) => HistoryScreen(muscleGroup: _selectedMuscleGroup)));
              },
            ),
            const SizedBox(width: 8),
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

// --- RESULTS SCREEN ---
class ResultsScreen extends StatelessWidget {
  final Map<String, dynamic> result;
  final String muscleGroup;

  const ResultsScreen({
    super.key,
    required this.result,
    required this.muscleGroup,
  });

  @override
  Widget build(BuildContext context) {
    final double volume = result['volume_cm3']?.toDouble() ?? 0.0;
    final double? growth = result['growth_pct']?.toDouble();
    final double? delta = result['volume_delta_cm3']?.toDouble();
    final double? score = result['shape_score']?.toDouble();
    final String? grade = result['shape_grade'];
    final bool calibrated = result['calibrated'] ?? false;

    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: const Text('Scan Results'),
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Card(
              color: Colors.grey.shade900,
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  children: [
                    Text(muscleGroup.toUpperCase(), style: const TextStyle(color: Colors.teal, fontWeight: FontWeight.bold, letterSpacing: 2)),
                    const SizedBox(height: 16),
                    Text('${volume.toStringAsFixed(2)} cm³', style: const TextStyle(fontSize: 48, fontWeight: FontWeight.bold, color: Colors.white)),
                    const Text('ESTIMATED VOLUME', style: TextStyle(color: Colors.white54)),
                    const SizedBox(height: 16),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                      decoration: BoxDecoration(
                        color: calibrated ? Colors.green.withOpacity(0.2) : Colors.orange.withOpacity(0.2),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: calibrated ? Colors.green : Colors.orange),
                      ),
                      child: Text(calibrated ? 'CALIBRATED' : 'UNCALIBRATED', style: TextStyle(color: calibrated ? Colors.green : Colors.orange, fontSize: 12)),
                    ),
                  ],
                ),
              ),
            ),
            if (growth != null) ...[
              const SizedBox(height: 16),
              Card(
                color: Colors.grey.shade900,
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text('Growth', style: TextStyle(fontSize: 18, color: Colors.white)),
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          Text('${growth > 0 ? '+' : ''}${growth.toStringAsFixed(1)}%', style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold, color: growth >= 0 ? Colors.greenAccent : Colors.redAccent)),
                          Text('${delta! > 0 ? '+' : ''}${delta.toStringAsFixed(1)} cm³', style: const TextStyle(color: Colors.white54)),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
            ],
            if (score != null) ...[
              const SizedBox(height: 16),
              Card(
                color: Colors.grey.shade900,
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text('Shape', style: TextStyle(fontSize: 18, color: Colors.white)),
                      Row(
                        children: [
                          Text('${score.toStringAsFixed(1)}/100', style: const TextStyle(fontSize: 18, color: Colors.white70)),
                          const SizedBox(width: 12),
                          Container(
                            padding: const EdgeInsets.all(8),
                            decoration: const BoxDecoration(shape: BoxShape.circle, color: Colors.teal),
                            child: Text(grade ?? '-', style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.black)),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
            ],
            const SizedBox(height: 40),
            FilledButton.icon(
              onPressed: () => Navigator.pop(context),
              icon: const Icon(Icons.add_a_photo),
              label: const Text('NEW SCAN', style: TextStyle(letterSpacing: 1.2)),
              style: FilledButton.styleFrom(backgroundColor: Colors.teal, padding: const EdgeInsets.symmetric(vertical: 16)),
            ),
            const SizedBox(height: 16),
            OutlinedButton.icon(
              onPressed: () {
                Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => HistoryScreen(muscleGroup: muscleGroup)));
              },
              icon: const Icon(Icons.history),
              label: const Text('VIEW HISTORY', style: TextStyle(letterSpacing: 1.2)),
              style: OutlinedButton.styleFrom(foregroundColor: Colors.white, side: const BorderSide(color: Colors.white30), padding: const EdgeInsets.symmetric(vertical: 16)),
            ),
          ],
        ),
      ),
    );
  }
}

// --- HISTORY SCREEN ---
class HistoryScreen extends StatefulWidget {
  final String? muscleGroup;
  const HistoryScreen({super.key, this.muscleGroup});

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  bool _isLoading = true;
  String? _error;
  List<dynamic> _scans = [];

  @override
  void initState() {
    super.initState();
    _fetchHistory();
  }

  Future<void> _fetchHistory() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });

    try {
      String url = '$serverBaseUrl/api/customer//scans';
      if (widget.muscleGroup != null) {
        url += '?muscle_group=${widget.muscleGroup}';
      }
      
      final response = await http.get(
        Uri.parse(url),
        headers: {'Authorization': 'Bearer ${_jwtToken ?? ''}'},
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        if (data['status'] == 'success') {
          setState(() {
            _scans = data['scans'];
            _isLoading = false;
          });
        } else {
          setState(() {
            _error = data['message'] ?? 'Failed to load history';
            _isLoading = false;
          });
        }
      } else {
        setState(() {
          _error = 'Server error: ${response.statusCode}';
          _isLoading = false;
        });
      }
    } catch (e) {
      setState(() {
        _error = 'Network error: $e';
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: const Text('History'),
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator(color: Colors.teal));
    }
    if (_error != null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(_error!, style: const TextStyle(color: Colors.redAccent)),
            const SizedBox(height: 16),
            ElevatedButton(onPressed: _fetchHistory, child: const Text('Retry')),
          ],
        ),
      );
    }

    if (_scans.isEmpty) {
      return const Center(
        child: Text('No scans yet.', style: TextStyle(color: Colors.white54, fontSize: 18)),
      );
    }

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(16.0),
          child: SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: () {
                Navigator.push(context, MaterialPageRoute(builder: (_) => ProgressScreen(muscleGroup: widget.muscleGroup)));
              },
              icon: const Icon(Icons.trending_up),
              label: const Text('VIEW TRENDS'),
              style: FilledButton.styleFrom(backgroundColor: Colors.teal.shade700),
            ),
          ),
        ),
        Expanded(
          child: ListView.builder(
            itemCount: _scans.length,
            itemBuilder: (context, index) {
              final scan = _scans[index];
              final dateStr = scan['scan_date']?.toString().split('T')[0] ?? 'Unknown';
              final volume = scan['volume_cm3']?.toDouble() ?? 0.0;
              final growth = scan['growth_pct']?.toDouble();
              final grade = scan['shape_grade'];
              
              return Card(
                color: Colors.grey.shade900,
                margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                child: ListTile(
                  title: Text('$dateStr - ${(scan['muscle_group'] as String).toUpperCase()}', style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                  subtitle: Text('Volume: ${volume.toStringAsFixed(1)} cm³${grade != null ? ' | Grade: $grade' : ''}', style: const TextStyle(color: Colors.white70)),
                  trailing: growth != null 
                    ? Text('${growth > 0 ? '+' : ''}${growth.toStringAsFixed(1)}%', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16, color: growth >= 0 ? Colors.greenAccent : Colors.redAccent))
                    : const Text('-', style: TextStyle(color: Colors.white54)),
                ),
              );
            },
          ),
        ),
      ],
    );
  }
}

// --- PROGRESS SCREEN ---
class ProgressScreen extends StatefulWidget {
  final String? muscleGroup;
  const ProgressScreen({super.key, this.muscleGroup});

  @override
  State<ProgressScreen> createState() => _ProgressScreenState();
}

class _ProgressScreenState extends State<ProgressScreen> {
  bool _isLoading = true;
  String? _error;
  Map<String, dynamic>? _trendData;

  @override
  void initState() {
    super.initState();
    _fetchProgress();
  }

  Future<void> _fetchProgress() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });

    try {
      String url = '$serverBaseUrl/api/customer//progress';
      if (widget.muscleGroup != null) {
        url += '?muscle_group=${widget.muscleGroup}';
      }
      
      final response = await http.get(
        Uri.parse(url),
        headers: {'Authorization': 'Bearer ${_jwtToken ?? ''}'},
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        if (data['status'] == 'success') {
          setState(() {
            _trendData = data;
            _isLoading = false;
          });
        } else {
          setState(() {
            _error = data['message'] ?? 'Failed to load progress';
            _isLoading = false;
          });
        }
      } else {
        setState(() {
          _error = 'Server error: ${response.statusCode}';
          _isLoading = false;
        });
      }
    } catch (e) {
      setState(() {
        _error = 'Network error: $e';
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: const Text('Progress & Trends'),
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator(color: Colors.teal));
    }
    if (_error != null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(_error!, style: const TextStyle(color: Colors.redAccent)),
            const SizedBox(height: 16),
            ElevatedButton(onPressed: _fetchProgress, child: const Text('Retry')),
          ],
        ),
      );
    }

    final trendObj = _trendData?['trend'] ?? {};
    if (trendObj['status'] == 'Insufficient Data' || trendObj.isEmpty) {
      return const Center(
        child: Text('Insufficient data to analyze trends.\nPlease complete at least 2 scans.', textAlign: TextAlign.center, style: TextStyle(color: Colors.white54, fontSize: 16)),
      );
    }

    final summary = _trendData?['volume_summary'] ?? {};
    final streak = _trendData?['growth_streak'] ?? {};
    final bestPeriod = _trendData?['best_period'] ?? {};

    final direction = trendObj['direction'] ?? 'UNKNOWN';
    final color = direction == 'gaining' ? Colors.greenAccent : (direction == 'losing' ? Colors.redAccent : Colors.orangeAccent);

    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('OVERALL TREND', style: TextStyle(color: Colors.teal.shade200, fontWeight: FontWeight.bold, letterSpacing: 1.5)),
          const SizedBox(height: 8),
          Text(direction.toUpperCase(), style: TextStyle(fontSize: 36, fontWeight: FontWeight.bold, color: color)),
          const SizedBox(height: 24),

          _buildStatCard('Total Change', '${summary['total_change_cm3']?.toStringAsFixed(1) ?? '0'} cm³ (${summary['total_change_pct']?.toStringAsFixed(1) ?? '0'}%)'),
          _buildStatCard('Weekly Rate', '${trendObj['weekly_rate_cm3']?.toStringAsFixed(2) ?? '0'} cm³/wk'),
          _buildStatCard('Consistency (R²)', '${trendObj['consistency_r2']?.toStringAsFixed(2) ?? '0'}'),
          _buildStatCard('30-Day Projection', '${trendObj['projected_30d_cm3']?.toStringAsFixed(1) ?? '0'} cm³'),
          _buildStatCard('Growth Streak', '${streak['consecutive_gains'] ?? 0} periods'),
          if (bestPeriod['volume_change_cm3'] != null)
            _buildStatCard('Best Period Gain', '+${bestPeriod['volume_change_cm3']?.toStringAsFixed(1) ?? '0'} cm³'),
        ],
      ),
    );
  }

  Widget _buildStatCard(String label, String value, {Color? valueColor}) {
    return Card(
      color: Colors.grey.shade900,
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Expanded(child: Text(label, style: const TextStyle(color: Colors.white70, fontSize: 16))),
            Text(value, style: TextStyle(color: valueColor ?? Colors.white, fontSize: 16, fontWeight: FontWeight.bold)),
          ],
        ),
      ),
    );
  }
}


// --- HEALTH LOG SCREEN ---
class HealthLogScreen extends StatefulWidget {
  const HealthLogScreen({super.key});

  @override
  State<HealthLogScreen> createState() => _HealthLogScreenState();
}

class _HealthLogScreenState extends State<HealthLogScreen> {
  final _formKey = GlobalKey<FormState>();
  final _caloriesController = TextEditingController();
  final _proteinController = TextEditingController();
  final _carbsController = TextEditingController();
  final _fatController = TextEditingController();
  final _waterController = TextEditingController();
  final _activityTypeController = TextEditingController();
  final _activityDurationController = TextEditingController();
  final _sleepController = TextEditingController();
  final _weightController = TextEditingController();
  final _notesController = TextEditingController();
  bool _isSubmitting = false;

  Future<void> _submitLog() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() => _isSubmitting = true);

    try {
      final response = await http.post(
        Uri.parse('/api/customer//health_log'),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ',
        },
        body: jsonEncode({
          'calories': double.tryParse(_caloriesController.text) ?? 0.0,
          'protein_g': double.tryParse(_proteinController.text) ?? 0.0,
          'carbs_g': double.tryParse(_carbsController.text) ?? 0.0,
          'fat_g': double.tryParse(_fatController.text) ?? 0.0,
          'water_ml': double.tryParse(_waterController.text) ?? 0.0,
          'activity_type': _activityTypeController.text,
          'activity_duration_min': double.tryParse(_activityDurationController.text) ?? 0.0,
          'sleep_hours': double.tryParse(_sleepController.text) ?? 0.0,
          'body_weight_kg': double.tryParse(_weightController.text) ?? 0.0,
          'notes': _notesController.text,
        }),
      );

      if (!mounted) return;

      if (response.statusCode == 200 || response.statusCode == 201) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Health log saved successfully!')),
        );
        Navigator.pop(context);
      } else {
        final error = jsonDecode(response.body)['message'] ?? 'Failed to save log';
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error: ')),
        );
      }
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Network error: ')),
      );
    } finally {
      if (mounted) setState(() => _isSubmitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: const Text('Log Health Data'),
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _buildSectionTitle('NUTRITION'),
              Row(
                children: [
                  Expanded(child: _buildTextField(_caloriesController, 'Calories', Icons.local_fire_department, keyboardType: TextInputType.number)),
                  const SizedBox(width: 16),
                  Expanded(child: _buildTextField(_proteinController, 'Protein (g)', Icons.egg, keyboardType: TextInputType.number)),
                ],
              ),
              const SizedBox(height: 16),
              Row(
                children: [
                  Expanded(child: _buildTextField(_carbsController, 'Carbs (g)', Icons.bakery_dining, keyboardType: TextInputType.number)),
                  const SizedBox(width: 16),
                  Expanded(child: _buildTextField(_fatController, 'Fat (g)', Icons.opacity, keyboardType: TextInputType.number)),
                ],
              ),
              const SizedBox(height: 16),
              _buildTextField(_waterController, 'Water (ml)', Icons.water_drop, keyboardType: TextInputType.number),
              
              const SizedBox(height: 32),
              _buildSectionTitle('ACTIVITY & SLEEP'),
              _buildTextField(_activityTypeController, 'Activity Type', Icons.directions_run),
              const SizedBox(height: 16),
              Row(
                children: [
                  Expanded(child: _buildTextField(_activityDurationController, 'Duration (min)', Icons.timer, keyboardType: TextInputType.number)),
                  const SizedBox(width: 16),
                  Expanded(child: _buildTextField(_sleepController, 'Sleep (hrs)', Icons.bedtime, keyboardType: TextInputType.number)),
                ],
              ),
              
              const SizedBox(height: 32),
              _buildSectionTitle('BODY'),
              _buildTextField(_weightController, 'Body Weight (kg)', Icons.monitor_weight, keyboardType: TextInputType.number),
              const SizedBox(height: 16),
              _buildTextField(_notesController, 'Notes', Icons.notes, maxLines: 3),
              
              const SizedBox(height: 40),
              _isSubmitting
                  ? const Center(child: CircularProgressIndicator(color: Colors.teal))
                  : FilledButton.icon(
                      onPressed: _submitLog,
                      icon: const Icon(Icons.save),
                      label: const Text('SAVE LOG', style: TextStyle(letterSpacing: 1.5)),
                      style: FilledButton.styleFrom(
                        backgroundColor: Colors.teal,
                        padding: const EdgeInsets.symmetric(vertical: 16),
                      ),
                    ),
              const SizedBox(height: 16),
              TextButton(
                onPressed: () {
                  Navigator.push(context, MaterialPageRoute(builder: (_) => const HealthLogListScreen()));
                },
                child: const Text('VIEW LOG HISTORY', style: TextStyle(color: Colors.teal)),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildSectionTitle(String title) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Text(title, style: TextStyle(color: Colors.teal.shade200, fontWeight: FontWeight.bold, letterSpacing: 1.2)),
    );
  }

  Widget _buildTextField(TextEditingController controller, String label, IconData icon, {TextInputType? keyboardType, int maxLines = 1}) {
    return TextFormField(
      controller: controller,
      decoration: InputDecoration(
        labelText: label,
        prefixIcon: Icon(icon, color: Colors.teal, size: 20),
        labelStyle: const TextStyle(color: Colors.white70),
        enabledBorder: const OutlineInputBorder(borderSide: BorderSide(color: Colors.white24)),
        focusedBorder: const OutlineInputBorder(borderSide: BorderSide(color: Colors.teal)),
      ),
      style: const TextStyle(color: Colors.white),
      keyboardType: keyboardType,
      maxLines: maxLines,
    );
  }
}

// --- HEALTH LOG LIST SCREEN ---
class HealthLogListScreen extends StatefulWidget {
  const HealthLogListScreen({super.key});

  @override
  State<HealthLogListScreen> createState() => _HealthLogListScreenState();
}

class _HealthLogListScreenState extends State<HealthLogListScreen> {
  bool _isLoading = true;
  String? _error;
  List<dynamic> _logs = [];

  @override
  void initState() {
    super.initState();
    _fetchLogs();
  }

  Future<void> _fetchLogs() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });

    try {
      final response = await http.get(
        Uri.parse('/api/customer//health_logs'),
        headers: {'Authorization': 'Bearer '},
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        if (data['status'] == 'success') {
          setState(() {
            _logs = data['health_logs'];
            _isLoading = false;
          });
        } else {
          setState(() {
            _error = data['message'] ?? 'Failed to load logs';
            _isLoading = false;
          });
        }
      } else {
        setState(() {
          _error = 'Server error: ';
          _isLoading = false;
        });
      }
    } catch (e) {
      setState(() {
        _error = 'Network error: ';
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: const Text('Health History'),
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_isLoading) return const Center(child: CircularProgressIndicator(color: Colors.teal));
    if (_error != null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(_error!, style: const TextStyle(color: Colors.redAccent)),
            const SizedBox(height: 16),
            ElevatedButton(onPressed: _fetchLogs, child: const Text('Retry')),
          ],
        ),
      );
    }
    if (_logs.isEmpty) return const Center(child: Text('No health logs yet.', style: TextStyle(color: Colors.white54, fontSize: 18)));

    return ListView.builder(
      itemCount: _logs.length,
      itemBuilder: (context, index) {
        final log = _logs[index];
        final dateStr = log['log_date']?.toString().split('T')[0] ?? 'Unknown';
        return Card(
          color: Colors.grey.shade900,
          margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(dateStr, style: const TextStyle(color: Colors.teal, fontWeight: FontWeight.bold, fontSize: 16)),
                    if (log['body_weight_kg'] != null)
                      Text(' kg', style: const TextStyle(color: Colors.white70)),
                  ],
                ),
                const Divider(color: Colors.white10, height: 20),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceAround,
                  children: [
                    _buildMiniStat(Icons.local_fire_department, '', 'kcal'),
                    _buildMiniStat(Icons.egg, '', 'g'),
                    _buildMiniStat(Icons.bedtime, '', 'hrs'),
                  ],
                ),
                if (log['activity_type'] != null && log['activity_type'].toString().isNotEmpty) ...[
                  const SizedBox(height: 12),
                  Text('Activity:  ( min)', style: const TextStyle(color: Colors.white60, fontSize: 13)),
                ],
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildMiniStat(IconData icon, String value, String unit) {
    return Column(
      children: [
        Icon(icon, color: Colors.teal.shade200, size: 18),
        const SizedBox(height: 4),
        Text(value, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
        Text(unit, style: const TextStyle(color: Colors.white54, fontSize: 10)),
      ],
    );
  }
}

// --- REGISTER SCREEN ---
class RegisterScreen extends StatefulWidget {
  const RegisterScreen({super.key});

  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  final _emailController = TextEditingController();
  final _heightController = TextEditingController();
  final _weightController = TextEditingController();
  String _gender = 'Male';
  bool _isLoading = false;

  Future<void> _register() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() => _isLoading = true);

    try {
      final response = await http.post(
        Uri.parse('/api/customers'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'name': _nameController.text.trim(),
          'email': _emailController.text.trim(),
          'height_cm': double.tryParse(_heightController.text) ?? 0.0,
          'weight_kg': double.tryParse(_weightController.text) ?? 0.0,
          'gender': _gender,
        }),
      );

      final data = jsonDecode(response.body);

      if (response.statusCode == 200 || response.statusCode == 201) {
        // Auto-login after registration
        final loginResponse = await http.post(
          Uri.parse('/api/auth/token'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({'email': _emailController.text.trim()}),
        );
        final loginData = jsonDecode(loginResponse.body);
        if (loginResponse.statusCode == 200) {
          _jwtToken = loginData['token'];
          _customerId = loginData['customer_id']?.toString() ?? '1';
          _customerName = loginData['name'] ?? _nameController.text;
          if (!mounted) return;
          Navigator.pushAndRemoveUntil(
            context,
            MaterialPageRoute(builder: (_) => const CameraLevelScreen()),
            (route) => false,
          );
        }
      } else {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(data['message'] ?? 'Registration failed')),
        );
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Network error: ')),
      );
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: const Text('Create Account'),
        backgroundColor: Colors.black,
        foregroundColor: Colors.teal,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24.0),
        child: Form(
          key: _formKey,
          child: Column(
            children: [
              _buildField(_nameController, 'Full Name', Icons.person),
              const SizedBox(height: 16),
              _buildField(_emailController, 'Email Address', Icons.email, keyboardType: TextInputType.emailAddress),
              const SizedBox(height: 16),
              Row(
                children: [
                  Expanded(child: _buildField(_heightController, 'Height (cm)', Icons.height, keyboardType: TextInputType.number)),
                  const SizedBox(width: 16),
                  Expanded(child: _buildField(_weightController, 'Weight (kg)', Icons.monitor_weight, keyboardType: TextInputType.number)),
                ],
              ),
              const SizedBox(height: 16),
              DropdownButtonFormField<String>(
                value: _gender,
                dropdownColor: Colors.grey.shade900,
                decoration: const InputDecoration(
                  labelText: 'Gender',
                  prefixIcon: Icon(Icons.people, color: Colors.teal),
                  enabledBorder: OutlineInputBorder(borderSide: BorderSide(color: Colors.white24)),
                  focusedBorder: OutlineInputBorder(borderSide: BorderSide(color: Colors.teal)),
                ),
                style: const TextStyle(color: Colors.white),
                items: ['Male', 'Female', 'Other'].map((g) => DropdownMenuItem(value: g, child: Text(g))).toList(),
                onChanged: (val) => setState(() => _gender = val!),
              ),
              const SizedBox(height: 32),
              _isLoading
                ? const CircularProgressIndicator(color: Colors.teal)
                : SizedBox(
                    width: double.infinity,
                    child: FilledButton(
                      onPressed: _register,
                      style: FilledButton.styleFrom(backgroundColor: Colors.teal, padding: const EdgeInsets.symmetric(vertical: 16)),
                      child: const Text('REGISTER & START'),
                    ),
                  ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildField(TextEditingController controller, String label, IconData icon, {TextInputType? keyboardType}) {
    return TextFormField(
      controller: controller,
      decoration: InputDecoration(
        labelText: label,
        prefixIcon: Icon(icon, color: Colors.teal),
        enabledBorder: const OutlineInputBorder(borderSide: BorderSide(color: Colors.white24)),
        focusedBorder: const OutlineInputBorder(borderSide: BorderSide(color: Colors.teal)),
      ),
      style: const TextStyle(color: Colors.white),
      keyboardType: keyboardType,
      validator: (val) => val == null || val.isEmpty ? 'Required' : null,
    );
  }
}
