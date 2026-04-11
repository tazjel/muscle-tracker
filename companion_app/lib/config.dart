// GTD3D App Config, Theme, and global state
import 'package:flutter/material.dart';
import 'dart:ui' as ui;
import 'services/auth_service.dart';

// --- CONFIG ---

class AppConfig {
  static const String serverBaseUrl = 'http://192.168.100.7:8000/web_app';
  static const String appVersion = '3.0.0';

  // ── DEV MODE ─────────────────────────────────────────────────────────────
  // Set to false when releasing to production.
  static const bool devMode = true;

  static bool profileCompleted = false;

  // Hardcoded test profile — submitted automatically on first run in dev mode.
  // Edit these values to match the current test subject.
  static const Map<String, dynamic> devProfile = {
    'height_cm':                  168,
    'weight_kg':                  63,
    'shoulder_width_cm':          37,
    'neck_to_shoulder_cm':        15,
    'shoulder_to_head_cm':        25,
    'arm_length_cm':              80,
    'upper_arm_length_cm':        35,
    'forearm_length_cm':          45,
    'torso_length_cm':            50,
    'floor_to_knee_cm':           52,
    'knee_to_belly_cm':           40,
    'back_buttock_to_knee_cm':    61.6,
    'head_circumference_cm':      56,
    'neck_circumference_cm':      35,
    'chest_circumference_cm':     97,
    'bicep_circumference_cm':     32,
    'forearm_circumference_cm':   29,
    'hand_circumference_cm':      21,
    'waist_circumference_cm':     90,
    'hip_circumference_cm':       92,
    'thigh_circumference_cm':     53,
    'quadricep_circumference_cm': 52,
    'calf_circumference_cm':      34,
    'skin_tone_hex':              'C4956A',
  };
}

// --- THEME ---

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

// --- GLOBAL STATE ---
// Delegated to AuthService for centralized reactive state.
// These getters/setters maintain backward compatibility during migration.

String? get jwtToken => AuthService.instance.token.value;
set jwtToken(String? v) => AuthService.instance.token.value = v;

String? get customerId => AuthService.instance.customerId.value;
set customerId(String? v) => AuthService.instance.customerId.value = v;

String? get customerName => AuthService.instance.customerName.value;
set customerName(String? v) => AuthService.instance.customerName.value = v;

void showSnackError(BuildContext context, String message) {
  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(
      content: Text(message),
      backgroundColor: AppTheme.accentRed,
      duration: const Duration(seconds: 3),
    ),
  );
}
