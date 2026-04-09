import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'package:sensors_plus/sensors_plus.dart';
import 'package:path_provider/path_provider.dart';
import 'dart:async';
import 'dart:io';
import 'dart:convert';
import 'dart:math';
import 'dart:ui' as ui;
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:share_plus/share_plus.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:audioplayers/audioplayers.dart';
import 'studio_server.dart';
import 'config.dart';
import 'widgets/dev_panel.dart';
import 'widgets/level_painter.dart';
import 'widgets/skin_guide_overlay.dart';
import 'tabs/camera_tab.dart';
import 'tabs/body_scan_tab.dart';
import 'tabs/live_scan_tab.dart';
import 'tabs/skin_tab.dart';
import 'tabs/multi_capture_tab.dart';

late List<CameraDescription> _cameras;

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Kiosk mode — always on (dev panel is inside the app, not system UI)
  SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);

  // Tablet (MatePad) → landscape; phone (A24) → portrait
  // Use addPostFrameCallback: physicalSize can be (0,0) before the first frame.
  WidgetsBinding.instance.addPostFrameCallback((_) {
    final view = WidgetsBinding.instance.platformDispatcher.views.first;
    final shortSideDp = view.physicalSize.shortestSide / view.devicePixelRatio;
    if (shortSideDp > 600) {
      SystemChrome.setPreferredOrientations([
        DeviceOrientation.landscapeLeft,
        DeviceOrientation.landscapeRight,
      ]);
    } else {
      SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
    }
  });
  _cameras = await availableCameras();

  // Auto-login
  try {
    final res = await http.post(
      Uri.parse('${AppConfig.serverBaseUrl}/api/auth/token'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'email': 'demo@muscle.com'}),
    ).timeout(const Duration(seconds: 4));
    final data = jsonDecode(res.body);
    if (res.statusCode == 200 && data['status'] == 'success') {
      jwtToken = data['token'];
      customerId = data['customer_id']?.toString() ?? '1';
      customerName = data['name'] ?? 'Demo User';
    }
  } catch (_) {}
  jwtToken ??= 'demo';
  customerId ??= '1';
  customerName ??= 'Demo User';

  // --- Dev mode: auto-submit hardcoded profile, skip setup screen ---
  if (AppConfig.devMode) {
    try {
      // Check if profile already submitted to avoid hammering server
      final pRes = await http.get(
        Uri.parse('${AppConfig.serverBaseUrl}/api/customer/$customerId/body_profile'),
        headers: {'Authorization': 'Bearer $jwtToken'},
      ).timeout(const Duration(seconds: 4));
      final pData = jsonDecode(pRes.body);
      final alreadyDone = pData['profile']?['profile_completed'] == true;
      if (!alreadyDone) {
        // Submit hardcoded dev profile
        await http.post(
          Uri.parse('${AppConfig.serverBaseUrl}/api/customer/$customerId/body_profile'),
          headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer $jwtToken'},
          body: jsonEncode(AppConfig.devProfile),
        ).timeout(const Duration(seconds: 5));
      }
    } catch (_) {}
    // In dev mode, always mark complete so we go straight to camera
    AppConfig.profileCompleted = true;
  } else {
    // Production: check server for profile completion
    try {
      final pRes = await http.get(
        Uri.parse('${AppConfig.serverBaseUrl}/api/customer/$customerId/body_profile'),
        headers: {'Authorization': 'Bearer $jwtToken'},
      ).timeout(const Duration(seconds: 4));
      final pData = jsonDecode(pRes.body);
      AppConfig.profileCompleted = pData['profile']?['profile_completed'] == true;
    } catch (_) {}
  }

  runApp(const MuscleCompanionApp());
}

// =============================================================================
// HOME SCREEN — Tabbed navigation (Wave 1 refactor)
// =============================================================================

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _currentTab = 0;

  // Shared camera + sensor state owned by HomeScreen, passed to all tabs
  CameraController? _controller;
  StreamSubscription<AccelerometerEvent>? _sensorSubscription;
  double _pitch = 0.0, _roll = 0.0;
  double _filteredPitch = 0.0, _filteredRoll = 0.0;
  static const double _smoothingFactor = 0.15;
  final Map<String, dynamic> _latestSensor = {};
  final List<Map<String, dynamic>> _sensorLog = [];

  static const _tabLabels = ['Camera', 'Body Scan', 'Live Scan', 'Skin', 'Multi-Cap'];
  static const _tabIcons = [
    Icons.camera_alt,
    Icons.accessibility_new,
    Icons.radar,
    Icons.texture,
    Icons.devices,
  ];

  @override
  void initState() {
    super.initState();
    _initCamera();
    _initSensors();
  }

  Future<void> _initCamera() async {
    if (_cameras.isEmpty) return;
    final cam = _cameras.firstWhere(
      (c) => c.lensDirection == CameraLensDirection.back,
      orElse: () => _cameras.first,
    );
    _controller = CameraController(cam, ResolutionPreset.max, enableAudio: false);
    try {
      await _controller!.initialize();
      if (mounted) setState(() {});
    } catch (_) {}
  }

  void _initSensors() {
    _sensorSubscription = accelerometerEventStream().listen((event) {
      if (!mounted) return;
      _filteredPitch += (event.y - _filteredPitch) * _smoothingFactor;
      _filteredRoll += (event.x - _filteredRoll) * _smoothingFactor;
      setState(() { _pitch = _filteredPitch; _roll = _filteredRoll; });
      _latestSensor['accel_x'] = event.x;
      _latestSensor['accel_y'] = event.y;
      _latestSensor['accel_z'] = event.z;
    });
  }

  @override
  void dispose() {
    _controller?.dispose();
    _sensorSubscription?.cancel();
    super.dispose();
  }

  Future<void> _saveLatestScan(String path, String phase) async {
    try {
      final dir = await getApplicationDocumentsDirectory();
      final scansDir = Directory('${dir.path}/scans');
      if (!await scansDir.exists()) await scansDir.create(recursive: true);
      await File(path).copy('${scansDir.path}/latest_scan_$phase.jpg');
    } catch (e) { print(e); }
  }

  @override
  Widget build(BuildContext context) {
    if (_controller == null || !_controller!.value.isInitialized) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator(color: AppTheme.primaryTeal)),
      );
    }
    return Scaffold(
      body: IndexedStack(
        index: _currentTab,
        children: [
          CameraTab(
            controller: _controller!,
            pitch: _pitch,
            roll: _roll,
            latestSensor: _latestSensor,
            onSaveLatestScan: _saveLatestScan,
          ),
          BodyScanTab(
            controller: _controller!,
            pitch: _pitch,
            roll: _roll,
            latestSensor: _latestSensor,
          ),
          LiveScanTab(
            controller: _controller!,
            pitch: _pitch,
            roll: _roll,
            latestSensor: _latestSensor,
          ),
          SkinTab(
            controller: _controller!,
          ),
          MultiCaptureTab(
            controller: _controller!,
            pitch: _pitch,
            roll: _roll,
            latestSensor: _latestSensor,
            sensorLog: _sensorLog,
            selectedMuscleGroup: 'quadricep',
            cameraDistanceCm: 75.0,
          ),
        ],
      ),
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _currentTab,
        onTap: (i) => setState(() => _currentTab = i),
        type: BottomNavigationBarType.fixed,
        backgroundColor: Colors.black,
        selectedItemColor: AppTheme.primaryTeal,
        unselectedItemColor: Colors.white38,
        selectedFontSize: 11,
        unselectedFontSize: 10,
        items: List.generate(_tabLabels.length, (i) => BottomNavigationBarItem(
          icon: Icon(_tabIcons[i]),
          label: _tabLabels[i],
        )),
      ),
    );
  }
}

class MuscleCompanionApp extends StatelessWidget {
  const MuscleCompanionApp({super.key});
  @override
  Widget build(BuildContext context) {
    final Widget home = (AppConfig.devMode || AppConfig.profileCompleted)
        ? const HomeScreen()
        : const ProfileSetupScreen();
    return MaterialApp(
      title: 'GTD3D',
      theme: AppTheme.darkTheme,
      home: home,
      debugShowCheckedModeBanner: false,
    );
  }
}

// =============================================================================
// PROFILE SETUP SCREEN
// =============================================================================

class ProfileSetupScreen extends StatefulWidget {
  const ProfileSetupScreen({super.key});
  @override
  State<ProfileSetupScreen> createState() => _ProfileSetupScreenState();
}

class _ProfileSetupScreenState extends State<ProfileSetupScreen> {
  int _step = 0;
  bool _submitting = false;
  String? _error;
  String _gender = 'Male';

  // Step 0 — essentials
  final _heightCtrl   = TextEditingController();
  final _weightCtrl   = TextEditingController();
  // Step 1 — upper body
  final _shoulderCtrl = TextEditingController();
  final _chestCtrl    = TextEditingController();
  final _bicepCtrl    = TextEditingController();
  final _neckCtrl     = TextEditingController();
  // Step 2 — lower body
  final _waistCtrl    = TextEditingController();
  final _hipCtrl      = TextEditingController();
  final _thighCtrl    = TextEditingController();
  final _calfCtrl     = TextEditingController();
  // Step 3 — body type (phenotype)
  double _muscleFactor = 50.0;   // 0-100, maps to 0.0-1.0
  double _bodyFatFactor = 50.0;  // 0-100, maps to 0.0-1.0
  // Step 4 — device setup
  final _camHeightCtrl  = TextEditingController(text: '65');
  final _camDistCtrl    = TextEditingController(text: '100');

  static const _steps = ['Essentials', 'Upper Body', 'Lower Body', 'Body Type', 'Device Setup'];

  @override
  void dispose() {
    for (final c in [_heightCtrl, _weightCtrl, _shoulderCtrl, _chestCtrl,
                     _bicepCtrl, _neckCtrl, _waistCtrl, _hipCtrl, _thighCtrl,
                     _calfCtrl, _camHeightCtrl, _camDistCtrl]) {
      c.dispose();
    }
    super.dispose();
  }

  double? _parse(TextEditingController c) => double.tryParse(c.text.trim());

  Future<void> _submit() async {
    setState(() { _submitting = true; _error = null; });
    try {
      // Submit body profile
      final profile = <String, dynamic>{};
      void add(String k, double? v) { if (v != null && v > 0) profile[k] = v; }
      add('height_cm',              _parse(_heightCtrl));
      add('weight_kg',              _parse(_weightCtrl));
      add('shoulder_width_cm',      _parse(_shoulderCtrl));
      add('chest_circumference_cm', _parse(_chestCtrl));
      add('bicep_circumference_cm', _parse(_bicepCtrl));
      add('neck_circumference_cm',  _parse(_neckCtrl));
      add('waist_circumference_cm', _parse(_waistCtrl));
      add('hip_circumference_cm',   _parse(_hipCtrl));
      add('thigh_circumference_cm', _parse(_thighCtrl));
      add('calf_circumference_cm',  _parse(_calfCtrl));
      profile['skin_tone_hex'] = 'C4956A'; // default light-brown
      profile['gender'] = _gender;
      profile['muscle_factor'] = _muscleFactor / 100.0;  // 0-100 → 0.0-1.0
      profile['weight_factor'] = _bodyFatFactor / 100.0;
      profile['gender_factor'] = _gender == 'Male' ? 1.0 : (_gender == 'Female' ? 0.0 : 0.5);

      await http.post(
        Uri.parse('${AppConfig.serverBaseUrl}/api/customer/$customerId/body_profile'),
        headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer $jwtToken'},
        body: jsonEncode(profile),
      ).timeout(const Duration(seconds: 8));

      // Submit device profile
      final camH = _parse(_camHeightCtrl) ?? 65.0;
      final camD = _parse(_camDistCtrl)   ?? 100.0;
      await http.post(
        Uri.parse('${AppConfig.serverBaseUrl}/api/customer/$customerId/devices'),
        headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer $jwtToken'},
        body: jsonEncode({
          'device_name': 'Phone',
          'role': 'front',
          'orientation': 'portrait',
          'camera_height_from_ground_cm': camH,
          'distance_to_subject_cm': camD,
        }),
      ).timeout(const Duration(seconds: 8));

      AppConfig.profileCompleted = true;
      if (mounted) {
        Navigator.pushReplacement(context,
            MaterialPageRoute(builder: (_) => const HomeScreen()));
      }
    } catch (e) {
      setState(() { _error = 'Could not save profile. Tap Skip to continue.'; });
    } finally {
      setState(() { _submitting = false; });
    }
  }

  Widget _sliderField(String label, double value, String minLabel, String maxLabel, ValueChanged<double> onChanged) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
        Text(label, style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 14)),
        Text('${value.round()}%', style: const TextStyle(color: Color(0xFF009688), fontSize: 16, fontWeight: FontWeight.bold)),
      ]),
      const SizedBox(height: 4),
      Row(children: [
        Text(minLabel, style: const TextStyle(color: Colors.white38, fontSize: 11)),
        Expanded(child: Slider(
          value: value, min: 0, max: 100, divisions: 20,
          activeColor: const Color(0xFF009688),
          onChanged: onChanged,
        )),
        Text(maxLabel, style: const TextStyle(color: Colors.white38, fontSize: 11)),
      ]),
    ]);
  }

  Widget _field(String label, TextEditingController ctrl, String unit, {String? hint}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(children: [
        Expanded(
          child: TextField(
            controller: ctrl,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            style: const TextStyle(color: Colors.white),
            decoration: InputDecoration(
              labelText: label,
              hintText: hint,
              labelStyle: const TextStyle(color: Color(0xFF94A3B8)),
              hintStyle: const TextStyle(color: Color(0xFF475569), fontSize: 12),
              enabledBorder: const OutlineInputBorder(borderSide: BorderSide(color: Color(0xFF334155))),
              focusedBorder: const OutlineInputBorder(borderSide: BorderSide(color: Color(0xFF009688))),
              filled: true, fillColor: const Color(0xFF121212),
            ),
          ),
        ),
        const SizedBox(width: 8),
        SizedBox(width: 36, child: Text(unit, style: const TextStyle(color: Color(0xFF94A3B8)))),
      ]),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF000000),
      appBar: AppBar(
        title: Text('Setup — ${_steps[_step]}'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pushReplacement(context,
                MaterialPageRoute(builder: (_) => const HomeScreen())),
            child: const Text('Skip', style: TextStyle(color: Color(0xFF94A3B8))),
          ),
        ],
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(children: [
            // Step indicator
            Row(mainAxisAlignment: MainAxisAlignment.center, children: List.generate(
              _steps.length, (i) => Container(
                margin: const EdgeInsets.symmetric(horizontal: 4),
                width: 10, height: 10,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: i <= _step ? const Color(0xFF009688) : const Color(0xFF334155),
                ),
              ),
            )),
            const SizedBox(height: 20),
            Expanded(
              child: SingleChildScrollView(child: Column(children: [
                if (_step == 0) ...[
                  const Text('Enter your basic measurements.\nHeight and weight are required.',
                      textAlign: TextAlign.center, style: TextStyle(color: Color(0xFF94A3B8), fontSize: 13)),
                  const SizedBox(height: 12),
                  _field('Height *', _heightCtrl, 'cm'),
                  _field('Weight *', _weightCtrl, 'kg'),
                  const SizedBox(height: 12),
                  DropdownButtonFormField<String>(
                    value: _gender,
                    dropdownColor: AppTheme.cardBg,
                    decoration: const InputDecoration(
                      labelText: 'Gender',
                      prefixIcon: Icon(Icons.people, size: 18),
                    ),
                    items: ['Male', 'Female', 'Other']
                        .map((g) => DropdownMenuItem(value: g, child: Text(g)))
                        .toList(),
                    onChanged: (v) => setState(() => _gender = v!),
                  ),
                ],
                if (_step == 1) ...[
                  const Text('Upper body — all optional but improves 3D accuracy.',
                      textAlign: TextAlign.center, style: TextStyle(color: Color(0xFF94A3B8), fontSize: 13)),
                  const SizedBox(height: 12),
                  _field('Shoulder width', _shoulderCtrl, 'cm', hint: 'Edge to edge'),
                  _field('Chest circumference', _chestCtrl, 'cm', hint: 'At nipple height'),
                  _field('Bicep circumference', _bicepCtrl, 'cm', hint: 'Widest part, arm at side'),
                  _field('Neck circumference', _neckCtrl, 'cm'),
                ],
                if (_step == 2) ...[
                  const Text('Lower body — all optional.',
                      textAlign: TextAlign.center, style: TextStyle(color: Color(0xFF94A3B8), fontSize: 13)),
                  const SizedBox(height: 12),
                  _field('Waist', _waistCtrl, 'cm', hint: 'Below belly button'),
                  _field('Hip / Buttock', _hipCtrl, 'cm'),
                  _field('Upper thigh', _thighCtrl, 'cm'),
                  _field('Calf', _calfCtrl, 'cm'),
                ],
                if (_step == 3) ...[
                  const Text('Describe your body type.\nThis fine-tunes your 3D model.',
                      textAlign: TextAlign.center, style: TextStyle(color: Color(0xFF94A3B8), fontSize: 13)),
                  const SizedBox(height: 20),
                  _sliderField('Muscle Definition', _muscleFactor, 'Low', 'High',
                      (v) => setState(() => _muscleFactor = v)),
                  const SizedBox(height: 16),
                  _sliderField('Body Fat', _bodyFatFactor, 'Lean', 'Heavy',
                      (v) => setState(() => _bodyFatFactor = v)),
                ],
                if (_step == 4) ...[
                  const Text('Tell us how your devices are set up.\nThis calibrates the camera distance.',
                      textAlign: TextAlign.center, style: TextStyle(color: Color(0xFF94A3B8), fontSize: 13)),
                  const SizedBox(height: 12),
                  _field('Camera height from floor', _camHeightCtrl, 'cm',
                      hint: 'Chair height + device position (e.g. 65)'),
                  _field('Distance to subject', _camDistCtrl, 'cm',
                      hint: '100 = 1 metre, 50 = half metre'),
                ],
                if (_error != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 12),
                    child: Text(_error!, style: const TextStyle(color: Color(0xFFFF5252), fontSize: 12)),
                  ),
              ])),
            ),
            Row(children: [
              if (_step > 0)
                Expanded(child: OutlinedButton(
                  onPressed: () => setState(() => _step--),
                  child: const Text('Back'),
                )),
              if (_step > 0) const SizedBox(width: 12),
              Expanded(child: FilledButton(
                onPressed: _submitting ? null
                    : (_step < _steps.length - 1)
                        ? () => setState(() => _step++)
                        : _submit,
                child: _submitting
                    ? const SizedBox(width: 20, height: 20,
                        child: CircularProgressIndicator(strokeWidth: 2, color: Colors.black))
                    : Text(_step < _steps.length - 1 ? 'Next' : 'Save & Start'),
              )),
            ]),
          ]),
        ),
      ),
    );
  }
}

// =============================================================================
// DEV PANEL — overlaid on CameraLevelScreen in dev mode
// =============================================================================

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
        jwtToken = data['token'];
        customerId = data['customer_id']?.toString() ?? '1';
        customerName = data['name'] ?? 'User';
        if (!mounted) return;
        Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => const HomeScreen()));
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
            customerId = '1'; customerName = 'Demo User'; jwtToken = 'demo';
            Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => const HomeScreen()));
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

// CameraLevelScreen extracted to tabs/ (Wave 2 refactor)


// --- SUPPORTING UI ---

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
        Uri.parse('${AppConfig.serverBaseUrl}/api/customer/$customerId/session_report'),
        headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ${jwtToken ?? ''}'},
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
    final meshId     = r['mesh_id'];
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
                  headers: {'Authorization': 'Bearer ${jwtToken ?? ''}'},
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
            if (meshId != null)
              FilledButton.icon(
                onPressed: () => Navigator.push(context, MaterialPageRoute(
                  builder: (_) => ModelViewerScreen(meshId: int.parse(meshId.toString())),
                )),
                icon: const Icon(Icons.view_in_ar, size: 18),
                label: const Text('VIEW 3D'),
                style: FilledButton.styleFrom(
                  backgroundColor: const Color(0xFF1B5E20),
                  foregroundColor: Colors.white,
                ),
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

// --- PROFILE PROGRESS SCREEN (Auto Mode 2) ---

class ProfileProgressScreen extends StatelessWidget {
  final Map<String, dynamic> result;
  final String muscleGroup;
  final VoidCallback onCaptureMore;
  const ProfileProgressScreen({super.key, required this.result, required this.muscleGroup, required this.onCaptureMore});

  @override
  Widget build(BuildContext context) {
    final pct = (result['progress_pct'] as num?)?.toInt() ?? 0;
    final isComplete = result['is_complete'] == true;
    final instructions = result['instructions'] as String? ?? '';
    final detail = result['detail'] as String? ?? '';
    final covered = List<String>.from(result['covered_zones'] ?? []);
    final missingReq = List<String>.from(result['missing_required'] ?? []);
    final stats = result['frame_stats'] as Map<String, dynamic>? ?? {};
    const allRequired = ['front', 'right', 'back', 'left'];
    return Scaffold(
      backgroundColor: AppTheme.darkBg,
      appBar: AppBar(title: const Text('Profile Builder'), backgroundColor: AppTheme.darkBg),
      body: SafeArea(child: SingleChildScrollView(padding: const EdgeInsets.all(24), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        // Progress arc
        Center(child: Stack(alignment: Alignment.center, children: [
          SizedBox(width: 140, height: 140, child: CircularProgressIndicator(
            value: pct / 100.0,
            strokeWidth: 12,
            backgroundColor: Colors.white12,
            valueColor: AlwaysStoppedAnimation<Color>(isComplete ? AppTheme.accentGreen : AppTheme.primaryTeal),
          )),
          Column(mainAxisSize: MainAxisSize.min, children: [
            Text('$pct%', style: TextStyle(fontSize: 32, fontWeight: FontWeight.bold, color: isComplete ? AppTheme.accentGreen : Colors.white)),
            Text(isComplete ? 'COMPLETE' : 'BUILDING', style: TextStyle(fontSize: 11, letterSpacing: 2, color: isComplete ? AppTheme.accentGreen : Colors.white54)),
          ]),
        ])),
        const SizedBox(height: 28),
        // Zone checklist
        Container(padding: const EdgeInsets.all(16), decoration: BoxDecoration(color: AppTheme.cardBg, borderRadius: BorderRadius.circular(12)), child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('COVERAGE', style: TextStyle(color: Colors.white54, fontSize: 11, letterSpacing: 2, fontWeight: FontWeight.bold)),
            const SizedBox(height: 12),
            ...allRequired.map((z) {
              final done = covered.contains(z);
              return Padding(padding: const EdgeInsets.symmetric(vertical: 4), child: Row(children: [
                Icon(done ? Icons.check_circle : Icons.radio_button_unchecked, size: 20, color: done ? AppTheme.accentGreen : Colors.white30),
                const SizedBox(width: 10),
                Text(z.toUpperCase(), style: TextStyle(color: done ? Colors.white : Colors.white54, fontWeight: done ? FontWeight.bold : FontWeight.normal)),
                if (!done && missingReq.first == z) ...[
                  const Spacer(),
                  Container(padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2), decoration: BoxDecoration(color: AppTheme.primaryTeal.withOpacity(0.2), borderRadius: BorderRadius.circular(10)), child: const Text('NEXT', style: TextStyle(color: AppTheme.primaryTeal, fontSize: 10, fontWeight: FontWeight.bold))),
                ],
              ]));
            }),
          ],
        )),
        const SizedBox(height: 16),
        // Frame stats
        Row(children: [
          _statChip('${stats['total'] ?? 0}', 'Captured'),
          const SizedBox(width: 8),
          _statChip('${stats['usable'] ?? 0}', 'Usable'),
          const SizedBox(width: 8),
          _statChip('${stats['mapped'] ?? 0}', 'Mapped'),
        ]),
        const SizedBox(height: 24),
        // Instructions
        if (!isComplete) ...[
          Container(width: double.infinity, padding: const EdgeInsets.all(16), decoration: BoxDecoration(color: AppTheme.primaryTeal.withOpacity(0.1), borderRadius: BorderRadius.circular(12), border: Border.all(color: AppTheme.primaryTeal.withOpacity(0.3))), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Text('NEXT STEP', style: TextStyle(color: AppTheme.primaryTeal, fontSize: 11, letterSpacing: 2, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            Text(instructions, style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600)),
            if (detail.isNotEmpty) ...[const SizedBox(height: 4), Text(detail, style: const TextStyle(color: Colors.white60, fontSize: 13))],
            const SizedBox(height: 4),
            const Text('Stand 1 meter away from the phone', style: TextStyle(color: Colors.white38, fontSize: 12)),
          ])),
          const SizedBox(height: 20),
          SizedBox(width: double.infinity, child: FilledButton.icon(
            onPressed: onCaptureMore,
            icon: const Icon(Icons.person_search),
            label: const Text('CAPTURE MORE — AUTO 2'),
            style: FilledButton.styleFrom(backgroundColor: AppTheme.primaryTeal, foregroundColor: Colors.black, padding: const EdgeInsets.symmetric(vertical: 16)),
          )),
        ] else ...[
          Container(width: double.infinity, padding: const EdgeInsets.all(20), decoration: BoxDecoration(color: AppTheme.accentGreen.withOpacity(0.1), borderRadius: BorderRadius.circular(12), border: Border.all(color: AppTheme.accentGreen.withOpacity(0.4))), child: Column(children: [
            const Icon(Icons.check_circle, color: AppTheme.accentGreen, size: 48),
            const SizedBox(height: 12),
            const Text('PROFILE COMPLETE', style: TextStyle(color: AppTheme.accentGreen, fontSize: 20, fontWeight: FontWeight.bold, letterSpacing: 2)),
            const SizedBox(height: 4),
            Text('${muscleGroup.toUpperCase()} profile built successfully', style: const TextStyle(color: Colors.white60, fontSize: 13)),
          ])),
          const SizedBox(height: 20),
          SizedBox(width: double.infinity, child: FilledButton.icon(
            onPressed: () => Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => HistoryScreen(muscleGroup: muscleGroup))),
            icon: const Icon(Icons.dashboard),
            label: const Text('VIEW DASHBOARD'),
            style: FilledButton.styleFrom(backgroundColor: AppTheme.accentGreen, foregroundColor: Colors.black, padding: const EdgeInsets.symmetric(vertical: 16)),
          )),
          const SizedBox(height: 12),
          SizedBox(width: double.infinity, child: OutlinedButton.icon(
            onPressed: onCaptureMore,
            icon: const Icon(Icons.add_a_photo, color: AppTheme.primaryTeal),
            label: const Text('ADD MORE ANGLES', style: TextStyle(color: AppTheme.primaryTeal)),
            style: OutlinedButton.styleFrom(side: const BorderSide(color: AppTheme.primaryTeal), padding: const EdgeInsets.symmetric(vertical: 14)),
          )),
        ],
      ]))),
    );
  }

  Widget _statChip(String value, String label) {
    return Expanded(child: Container(padding: const EdgeInsets.symmetric(vertical: 10), decoration: BoxDecoration(color: AppTheme.cardBg, borderRadius: BorderRadius.circular(8)), child: Column(children: [
      Text(value, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 18)),
      Text(label, style: const TextStyle(color: Colors.white38, fontSize: 11)),
    ])));
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
      final res = await http.get(Uri.parse('${AppConfig.serverBaseUrl}/api/customer/$customerId/scans${widget.muscleGroup != null ? "?muscle_group=${widget.muscleGroup}" : ""}'), headers: {'Authorization': 'Bearer ${jwtToken ?? ''}'});
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
      final res = await http.get(Uri.parse('${AppConfig.serverBaseUrl}/api/customer/$customerId/progress${widget.muscleGroup != null ? "?muscle_group=${widget.muscleGroup}" : ""}'), headers: {'Authorization': 'Bearer ${jwtToken ?? ''}'});
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
      final res = await http.post(Uri.parse('${AppConfig.serverBaseUrl}/api/customer/$customerId/health_log'), headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ${jwtToken ?? ''}'}, body: jsonEncode({'calories_in': int.tryParse(_cals.text) ?? 0, 'protein_g': int.tryParse(_pro.text) ?? 0, 'carbs_g': int.tryParse(_carb.text) ?? 0, 'fat_g': int.tryParse(_fat.text) ?? 0, 'water_ml': int.tryParse(_wat.text) ?? 0, 'activity_type': _at.text, 'activity_duration_min': int.tryParse(_ad.text) ?? 0, 'sleep_hours': double.tryParse(_slp.text) ?? 0.0, 'body_weight_kg': double.tryParse(_wt.text) ?? 0.0, 'notes': _nts.text}));
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
      final res = await http.get(Uri.parse('${AppConfig.serverBaseUrl}/api/customer/$customerId/health_logs'), headers: {'Authorization': 'Bearer ${jwtToken ?? ''}'});
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
        if (lres.statusCode == 200) { jwtToken = ld['token']; customerId = ld['customer_id']?.toString() ?? '1'; customerName = ld['name'] ?? _name.text; Navigator.pushAndRemoveUntil(context, MaterialPageRoute(builder: (_) => const HomeScreen()), (r) => false); }
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
  Future<Uint8List> _f() async { final r = await http.get(Uri.parse('${AppConfig.serverBaseUrl}/api/customer/$customerId/report/$scanId'), headers: {'Authorization': 'Bearer ${jwtToken ?? ''}'}); if (r.statusCode == 200) return r.bodyBytes; throw Exception('Error ${r.statusCode}'); }
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

// ── 3D Model Viewer (WebView) ─────────────────────────────────────────────────

class ModelViewerScreen extends StatefulWidget {
  final int meshId;
  final String? title;
  const ModelViewerScreen({super.key, required this.meshId, this.title});

  @override
  State<ModelViewerScreen> createState() => _ModelViewerScreenState();
}

class _ModelViewerScreenState extends State<ModelViewerScreen> {
  late final WebViewController _controller;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setNavigationDelegate(NavigationDelegate(
        onPageFinished: (_) => setState(() => _loading = false),
      ))
      ..loadRequest(Uri.parse(
        '${AppConfig.serverBaseUrl}/static/viewer3d/index.html'
        '?model=/api/mesh/${widget.meshId}.glb'
        '&customer=${customerId ?? "1"}'
      ));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0D1117),
      appBar: AppBar(
        title: Text(widget.title ?? '3D Body Model',
            style: const TextStyle(fontSize: 16)),
        backgroundColor: const Color(0xFF161B22),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: Colors.white),
          onPressed: () => Navigator.pop(context),
        ),
      ),
      body: Stack(
        children: [
          WebViewWidget(controller: _controller),
          if (_loading)
            const Center(child: CircularProgressIndicator(
              color: AppTheme.primaryTeal,
            )),
        ],
      ),
    );
  }
}

// ── Body Scan Review Screen ───────────────────────────────────────────────────

class BodyScanReviewScreen extends StatefulWidget {
  final int customerId;
  final String sessionId;
  final String serverBaseUrl;
  final String? token;

  const BodyScanReviewScreen({
    super.key,
    required this.customerId,
    required this.sessionId,
    required this.serverBaseUrl,
    this.token,
  });

  @override
  State<BodyScanReviewScreen> createState() => _BodyScanReviewScreenState();
}

class _BodyScanReviewScreenState extends State<BodyScanReviewScreen> {
  List<Map<String, dynamic>> _tasks = [];
  bool _loading = true;
  bool _processing = false;
  String? _error;
  String? _viewerUrl;
  String _statusMessage = '';

  // Track per-region confirmation state
  final Map<String, bool?> _confirmations = {};

  @override
  void initState() {
    super.initState();
    _fetchTasks();
  }

  Map<String, String> get _authHeaders {
    final headers = <String, String>{'Content-Type': 'application/json'};
    if (widget.token != null) headers['Authorization'] = 'Bearer ${widget.token}';
    return headers;
  }

  Future<void> _fetchTasks() async {
    setState(() { _loading = true; _error = null; });
    try {
      final uri = Uri.parse(
        '${widget.serverBaseUrl}/api/customer/${widget.customerId}/body_scan/${widget.sessionId}/tasks');
      final resp = await http.get(uri, headers: _authHeaders);
      if (resp.statusCode == 200) {
        final data = jsonDecode(resp.body);
        final taskList = (data['task_list'] as List? ?? [])
            .map((t) => Map<String, dynamic>.from(t))
            .toList();
        setState(() {
          _tasks = taskList;
          _loading = false;
          // Initialize confirmation state
          for (final task in taskList) {
            final region = task['region'] as String? ?? '';
            if (!_confirmations.containsKey(region)) {
              _confirmations[region] = null; // pending
            }
          }
        });
      } else {
        setState(() { _error = 'Server error: ${resp.statusCode}'; _loading = false; });
      }
    } catch (e) {
      setState(() { _error = 'Connection error: $e'; _loading = false; });
    }
  }

  Future<void> _confirmRegion(String region, bool confirmed) async {
    setState(() { _confirmations[region] = confirmed; });

    try {
      final uri = Uri.parse(
        '${widget.serverBaseUrl}/api/customer/${widget.customerId}/body_scan/${widget.sessionId}/confirm');
      final resp = await http.post(uri,
        headers: _authHeaders,
        body: jsonEncode({
          'confirmations': [{'region': region, 'confirmed': confirmed}]
        }),
      );
      if (resp.statusCode == 200) {
        final data = jsonDecode(resp.body);
        if (data['task_list'] != null) {
          setState(() {
            _tasks = (data['task_list'] as List)
                .map((t) => Map<String, dynamic>.from(t))
                .toList();
          });
        }
      }
    } catch (e) {
      debugPrint('Confirm error: $e');
    }
  }

  Future<void> _startRecapture(String region) async {
    final result = await Navigator.of(context).push<bool>(MaterialPageRoute(
      builder: (_) => _RegionRecaptureScreen(
        region: region,
        customerId: widget.customerId,
        sessionId: widget.sessionId,
        serverBaseUrl: widget.serverBaseUrl,
        token: widget.token,
      ),
    ));

    if (result == true) {
      await _fetchTasks();
    }
  }

  Future<void> _finalizeAll() async {
    setState(() { _processing = true; _statusMessage = 'Processing final model...'; });
    try {
      final uri = Uri.parse(
        '${widget.serverBaseUrl}/api/customer/${widget.customerId}/body_scan/${widget.sessionId}/finalize');
      final resp = await http.post(uri, headers: _authHeaders);
      if (resp.statusCode == 200) {
        final data = jsonDecode(resp.body);
        setState(() {
          _processing = false;
          _viewerUrl = data['viewer_url'];
          _statusMessage = 'Model complete!';
        });
      } else {
        setState(() {
          _processing = false;
          _statusMessage = 'Processing failed: ${resp.statusCode}';
        });
      }
    } catch (e) {
      setState(() { _processing = false; _statusMessage = 'Error: $e'; });
    }
  }

  void _openInBrowser() {
    if (_viewerUrl != null) {
      Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => Scaffold(
          appBar: AppBar(
            title: const Text('3D Body Viewer'),
            backgroundColor: Colors.deepPurple,
          ),
          body: WebViewWidget(
            controller: WebViewController()
              ..setJavaScriptMode(JavaScriptMode.unrestricted)
              ..loadRequest(Uri.parse('${widget.serverBaseUrl}$_viewerUrl')),
          ),
        ),
      ));
    }
  }

  Color _gradeColor(String grade) {
    switch (grade) {
      case 'excellent': return Colors.green;
      case 'good': return Colors.lightGreen;
      case 'fair': return Colors.orange;
      default: return Colors.red;
    }
  }

  IconData _gradeIcon(String grade) {
    switch (grade) {
      case 'excellent': return Icons.check_circle;
      case 'good': return Icons.check_circle_outline;
      case 'fair': return Icons.warning_amber;
      default: return Icons.error_outline;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Body Scan Review'),
        backgroundColor: Colors.deepPurple,
        foregroundColor: Colors.white,
      ),
      body: _loading
        ? const Center(child: CircularProgressIndicator())
        : _error != null
          ? Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(_error!, style: const TextStyle(color: Colors.red, fontSize: 16)),
                  const SizedBox(height: 16),
                  ElevatedButton(onPressed: _fetchTasks, child: const Text('RETRY')),
                ],
              ),
            )
          : Column(
              children: [
                // Status bar
                if (_statusMessage.isNotEmpty)
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(12),
                    color: _viewerUrl != null ? Colors.green.shade700 : Colors.deepPurple.shade700,
                    child: Text(_statusMessage,
                      textAlign: TextAlign.center,
                      style: const TextStyle(color: Colors.white, fontSize: 16)),
                  ),

                // Task list
                Expanded(
                  child: ListView.builder(
                    padding: const EdgeInsets.all(16),
                    itemCount: _tasks.length,
                    itemBuilder: (ctx, i) {
                      final task = _tasks[i];
                      final region = task['region'] as String? ?? '';
                      final grade = task['grade'] as String? ?? 'missing';
                      final message = task['message'] as String? ?? '';
                      final action = task['action'] as String? ?? 'confirm';
                      final thumbnailIdx = task['thumbnail_idx'] ?? 0;
                      final confirmed = _confirmations[region];

                      return Card(
                        margin: const EdgeInsets.only(bottom: 12),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                          side: BorderSide(
                            color: confirmed == true ? Colors.green
                                : confirmed == false ? Colors.red
                                : Colors.grey.shade300,
                            width: confirmed != null ? 2 : 1,
                          ),
                        ),
                        child: Padding(
                          padding: const EdgeInsets.all(12),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              // Region header with grade
                              Row(
                                children: [
                                  Icon(_gradeIcon(grade), color: _gradeColor(grade), size: 28),
                                  const SizedBox(width: 8),
                                  Expanded(
                                    child: Text(
                                      region.replaceAll('_', ' ').toUpperCase(),
                                      style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                                    ),
                                  ),
                                  Container(
                                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                                    decoration: BoxDecoration(
                                      color: _gradeColor(grade).withOpacity(0.15),
                                      borderRadius: BorderRadius.circular(12),
                                    ),
                                    child: Text(grade.toUpperCase(),
                                      style: TextStyle(color: _gradeColor(grade), fontWeight: FontWeight.bold)),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 8),

                              // Thumbnail
                              ClipRRect(
                                borderRadius: BorderRadius.circular(8),
                                child: Image.network(
                                  '${widget.serverBaseUrl}/api/customer/${widget.customerId}/body_scan/${widget.sessionId}/thumbnail/$thumbnailIdx',
                                  headers: widget.token != null ? {'Authorization': 'Bearer ${widget.token}'} : null,
                                  height: 120,
                                  width: double.infinity,
                                  fit: BoxFit.cover,
                                  errorBuilder: (_, __, ___) => Container(
                                    height: 120,
                                    color: Colors.grey.shade200,
                                    child: const Center(child: Icon(Icons.image_not_supported, size: 40)),
                                  ),
                                ),
                              ),
                              const SizedBox(height: 8),

                              // Message
                              if (message.isNotEmpty)
                                Text(message, style: TextStyle(color: Colors.grey.shade600)),
                              const SizedBox(height: 12),

                              // Action buttons
                              Row(
                                mainAxisAlignment: MainAxisAlignment.end,
                                children: [
                                  if (action == 're-capture' || grade == 'fair' || grade == 'missing')
                                    OutlinedButton.icon(
                                      onPressed: () => _startRecapture(region),
                                      icon: const Icon(Icons.camera_alt, size: 18),
                                      label: const Text('RE-CAPTURE'),
                                      style: OutlinedButton.styleFrom(foregroundColor: Colors.orange),
                                    ),
                                  const SizedBox(width: 8),
                                  if (confirmed != false)
                                    OutlinedButton.icon(
                                      onPressed: () => _confirmRegion(region, false),
                                      icon: const Icon(Icons.close, size: 18),
                                      label: const Text('REJECT'),
                                      style: OutlinedButton.styleFrom(foregroundColor: Colors.red),
                                    ),
                                  const SizedBox(width: 8),
                                  if (confirmed != true)
                                    ElevatedButton.icon(
                                      onPressed: () => _confirmRegion(region, true),
                                      icon: const Icon(Icons.check, size: 18),
                                      label: const Text('CONFIRM'),
                                      style: ElevatedButton.styleFrom(
                                        backgroundColor: Colors.green,
                                        foregroundColor: Colors.white,
                                      ),
                                    ),
                                ],
                              ),
                            ],
                          ),
                        ),
                      );
                    },
                  ),
                ),
              ],
            ),

      // Bottom bar
      bottomNavigationBar: Padding(
        padding: const EdgeInsets.all(16),
        child: _processing
          ? const Center(child: CircularProgressIndicator())
          : _viewerUrl != null
            ? ElevatedButton.icon(
                onPressed: _openInBrowser,
                icon: const Icon(Icons.view_in_ar, size: 24),
                label: const Text('VIEW IN BROWSER', style: TextStyle(fontSize: 18)),
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.deepPurple,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 16),
                ),
              )
            : ElevatedButton.icon(
                onPressed: _finalizeAll,
                icon: const Icon(Icons.check_circle, size: 24),
                label: const Text('CONFIRM ALL & BUILD', style: TextStyle(fontSize: 18)),
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.deepPurple,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 16),
                ),
              ),
      ),
    );
  }
}

// ── Region Re-capture Screen ──────────────────────────────────────────────────

class _RegionRecaptureScreen extends StatefulWidget {
  final String region;
  final int customerId;
  final String sessionId;
  final String serverBaseUrl;
  final String? token;

  const _RegionRecaptureScreen({
    required this.region,
    required this.customerId,
    required this.sessionId,
    required this.serverBaseUrl,
    this.token,
  });

  @override
  State<_RegionRecaptureScreen> createState() => _RegionRecaptureScreenState();
}

class _RegionRecaptureScreenState extends State<_RegionRecaptureScreen> {
  CameraController? _camera;
  bool _capturing = false;
  int _framesCaptured = 0;
  final int _totalFrames = 10;
  final List<String> _capturedPaths = [];
  String _instruction = '';
  bool _uploading = false;

  @override
  void initState() {
    super.initState();
    _initCamera();
  }

  Future<void> _initCamera() async {
    final cameras = await availableCameras();
    final back = cameras.firstWhere(
      (c) => c.lensDirection == CameraLensDirection.back,
      orElse: () => cameras.first,
    );
    _camera = CameraController(back, ResolutionPreset.max, enableAudio: false);
    await _camera!.initialize();
    if (mounted) setState(() {});
  }

  Future<void> _startCapture() async {
    if (_capturing || _camera == null) return;
    setState(() {
      _capturing = true;
      _framesCaptured = 0;
      _capturedPaths.clear();
      _instruction = 'Point camera at your ${widget.region.replaceAll("_", " ").toUpperCase()}\nROTATE SLOWLY';
    });

    for (int i = 0; i < _totalFrames; i++) {
      if (!mounted || !_capturing) return;
      try {
        final img = await _camera!.takePicture();
        _capturedPaths.add(img.path);
        setState(() {
          _framesCaptured = i + 1;
          _instruction = '${widget.region.replaceAll("_", " ").toUpperCase()}\nFrame ${i + 1}/$_totalFrames';
        });
      } catch (e) {
        debugPrint('Recapture frame error: $e');
      }
      await Future.delayed(const Duration(seconds: 2));
    }

    setState(() { _instruction = 'Uploading...'; _uploading = true; });
    await _uploadRecapture();
  }

  Future<void> _uploadRecapture() async {
    try {
      final uri = Uri.parse(
        '${widget.serverBaseUrl}/api/customer/${widget.customerId}/body_scan/${widget.sessionId}/re_capture');
      final request = http.MultipartRequest('POST', uri);
      if (widget.token != null) {
        request.headers['Authorization'] = 'Bearer ${widget.token}';
      }
      request.fields['region'] = widget.region;

      for (int i = 0; i < _capturedPaths.length; i++) {
        request.files.add(await http.MultipartFile.fromPath(
          'frame_${i.toString().padLeft(3, '0')}',
          _capturedPaths[i],
          filename: 'frame_${i.toString().padLeft(3, '0')}.jpg',
        ));
      }

      final resp = await request.send();
      if (resp.statusCode == 200) {
        if (mounted) Navigator.of(context).pop(true);
      } else {
        setState(() { _instruction = 'Upload failed'; _uploading = false; _capturing = false; });
      }
    } catch (e) {
      setState(() { _instruction = 'Error: $e'; _uploading = false; _capturing = false; });
    }
  }

  @override
  void dispose() {
    _camera?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Re-capture: ${widget.region.replaceAll("_", " ")}'),
        backgroundColor: Colors.orange,
        foregroundColor: Colors.white,
      ),
      body: Stack(
        children: [
          // Camera preview
          if (_camera != null && _camera!.value.isInitialized)
            SizedBox.expand(child: CameraPreview(_camera!))
          else
            const Center(child: CircularProgressIndicator()),

          // Overlay
          if (_capturing)
            Positioned.fill(
              child: Container(
                color: Colors.black45,
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(_instruction,
                      textAlign: TextAlign.center,
                      style: const TextStyle(color: Colors.white, fontSize: 24, fontWeight: FontWeight.bold)),
                    const SizedBox(height: 16),
                    LinearProgressIndicator(
                      value: _framesCaptured / _totalFrames,
                      backgroundColor: Colors.white24,
                      valueColor: const AlwaysStoppedAnimation(Colors.orange),
                    ),
                    const SizedBox(height: 8),
                    Text('$_framesCaptured / $_totalFrames frames',
                      style: const TextStyle(color: Colors.white70, fontSize: 16)),
                  ],
                ),
              ),
            ),

          // Start button
          if (!_capturing && !_uploading)
            Positioned(
              bottom: 32, left: 32, right: 32,
              child: ElevatedButton.icon(
                onPressed: _startCapture,
                icon: const Icon(Icons.camera_alt, size: 28),
                label: Text(
                  'START RE-CAPTURE: ${widget.region.replaceAll("_", " ").toUpperCase()}',
                  style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                ),
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.orange,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 16),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
