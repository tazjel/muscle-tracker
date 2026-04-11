import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:convert';
import 'package:http/http.dart' as http;
import '../config.dart';

/// Centralized auth state using ValueNotifier for reactive UI updates.
/// Replaces the global jwtToken/customerId/customerName variables.
class AuthService {
  static final AuthService _instance = AuthService._();
  factory AuthService() => _instance;
  AuthService._();

  static AuthService get instance => _instance;

  final token = ValueNotifier<String?>(null);
  final customerId = ValueNotifier<String?>(null);
  final customerName = ValueNotifier<String?>(null);

  SharedPreferences? _prefs;

  bool get isLoggedIn => token.value != null;

  /// Load saved credentials from SharedPreferences.
  Future<void> loadFromPrefs() async {
    _prefs = await SharedPreferences.getInstance();
    final savedToken = _prefs?.getString('jwt_token');
    final savedId = _prefs?.getString('customer_id');
    final savedName = _prefs?.getString('customer_name');

    if (savedToken != null) {
      token.value = savedToken;
      customerId.value = savedId ?? '1';
      customerName.value = savedName ?? 'User';
    }
  }

  /// Validate current token against the server.
  Future<bool> validateToken() async {
    if (token.value == null) return false;
    try {
      final res = await http.get(
        Uri.parse('${AppConfig.serverBaseUrl}/api/health'),
      ).timeout(const Duration(seconds: 4));
      return res.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  /// Login with email (and optional password).
  Future<bool> login({required String email, String? password}) async {
    try {
      final body = <String, dynamic>{'email': email};
      if (password != null) body['password'] = password;

      final res = await http.post(
        Uri.parse('${AppConfig.serverBaseUrl}/api/auth/token'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(body),
      ).timeout(const Duration(seconds: 4));

      final data = jsonDecode(res.body);
      if (res.statusCode == 200 && data['status'] == 'success') {
        token.value = data['token'];
        customerId.value = data['customer_id']?.toString() ?? '1';
        customerName.value = data['name'] ?? 'User';
        _persist();
        return true;
      }
    } catch (e) {
      print('AuthService login failed: $e');
    }
    return false;
  }

  /// Clear auth state and persisted credentials.
  void logout() {
    token.value = null;
    customerId.value = null;
    customerName.value = null;
    _prefs?.remove('jwt_token');
    _prefs?.remove('customer_id');
    _prefs?.remove('customer_name');
  }

  /// Persist current auth state to SharedPreferences.
  void _persist() {
    if (token.value != null) {
      _prefs?.setString('jwt_token', token.value!);
    }
    if (customerId.value != null) {
      _prefs?.setString('customer_id', customerId.value!);
    }
    if (customerName.value != null) {
      _prefs?.setString('customer_name', customerName.value!);
    }
  }
}
