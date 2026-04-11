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
import 'screens/review_screen.dart';
import 'screens/report_viewer_screen.dart';
import 'screens/profile_progress_screen.dart';
import 'screens/register_screen.dart';
import 'screens/health_log_screen.dart';
import 'screens/login_screen.dart';
import 'screens/results_screen.dart';
import 'screens/progress_screen.dart';
import 'screens/history_screen.dart';
import 'screens/profile_setup_screen.dart';
import 'screens/live_preview_screen.dart';
import 'screens/model_viewer_screen.dart';
import 'screens/body_scan_review_screen.dart';
import 'services/api_service.dart';
import 'services/camera_service.dart';
import 'services/sensor_service.dart';
import 'services/connectivity_service.dart';
import 'widgets/connection_banner.dart';

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

  ConnectivityService.instance.start();
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

  // Services own camera + sensor state; HomeScreen reads from them
  final _cameraService = CameraService.instance;
  final _sensorService = SensorService.instance;

  double _pitch = 0.0, _roll = 0.0;
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
    try {
      await _cameraService.initialize();
      if (mounted) setState(() {});
    } catch (_) {}
  }

  void _initSensors() {
    _sensorService.start();
    _sensorService.pitch.addListener(() {
      if (!mounted) return;
      setState(() { _pitch = _sensorService.pitch.value; _roll = _sensorService.roll.value; });
    });
    _sensorService.roll.addListener(() {
      if (!mounted) return;
      setState(() { _pitch = _sensorService.pitch.value; _roll = _sensorService.roll.value; });
    });
  }

  @override
  void dispose() {
    _sensorService.stop();
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
    final controller = _cameraService.controller;
    if (controller == null || !controller.value.isInitialized) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator(color: AppTheme.primaryTeal)),
      );
    }
    final latestSensor = _sensorService.latestValues;
    return Scaffold(
      body: Column(
        children: [
          ConnectionBanner(isOnline: ConnectivityService.instance.isOnline),
          Expanded(child: IndexedStack(
        index: _currentTab,
        children: [
          CameraTab(
            controller: controller,
            pitch: _pitch,
            roll: _roll,
            latestSensor: latestSensor,
            onSaveLatestScan: _saveLatestScan,
          ),
          BodyScanTab(
            controller: controller,
            pitch: _pitch,
            roll: _roll,
            latestSensor: latestSensor,
          ),
          LiveScanTab(
            controller: controller,
            pitch: _pitch,
            roll: _roll,
            latestSensor: latestSensor,
          ),
          SkinTab(
            controller: controller,
          ),
          MultiCaptureTab(
            controller: controller,
            pitch: _pitch,
            roll: _roll,
            latestSensor: latestSensor,
            sensorLog: _sensorLog,
            selectedMuscleGroup: 'quadricep',
            cameraDistanceCm: 75.0,
          ),
        ],
      )),
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
      routes: {
        '/home': (_) => const HomeScreen(),
      },
    );
  }
}
