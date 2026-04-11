import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'dart:convert';
import 'package:http/http.dart' as http;
import '../config.dart';

/// Centralized auth state using ValueNotifier for reactive UI updates.
/// Credentials stored in Android Keystore via flutter_secure_storage (encrypted).
class AuthService {
  static final AuthService _instance = AuthService._();
  factory AuthService() => _instance;
  AuthService._();

  static AuthService get instance => _instance;

  final token = ValueNotifier<String?>(null);
  final customerId = ValueNotifier<String?>(null);
  final customerName = ValueNotifier<String?>(null);

  static const _storage = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
  );

  bool get isLoggedIn => token.value != null;

  /// Load saved credentials from encrypted secure storage.
  Future<void> loadFromPrefs() async {
    final savedToken = await _storage.read(key: 'jwt_token');
    final savedId = await _storage.read(key: 'customer_id');
    final savedName = await _storage.read(key: 'customer_name');

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
        await _persist();
        return true;
      }
    } catch (e) {
      if (kDebugMode) print('AuthService login failed: $e');
    }
    return false;
  }

  /// Clear auth state and delete encrypted credentials.
  Future<void> logout() async {
    token.value = null;
    customerId.value = null;
    customerName.value = null;
    await _storage.delete(key: 'jwt_token');
    await _storage.delete(key: 'customer_id');
    await _storage.delete(key: 'customer_name');
  }

  /// Persist current auth state to encrypted secure storage.
  Future<void> _persist() async {
    if (token.value != null) {
      await _storage.write(key: 'jwt_token', value: token.value!);
    }
    if (customerId.value != null) {
      await _storage.write(key: 'customer_id', value: customerId.value!);
    }
    if (customerName.value != null) {
      await _storage.write(key: 'customer_name', value: customerName.value!);
    }
  }
}
