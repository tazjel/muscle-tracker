import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import '../config.dart';

class ApiService {
  static final ApiService _instance = ApiService._();
  factory ApiService() => _instance;
  ApiService._();

  static ApiService get instance => _instance;

  final List<Map<String, dynamic>> _offlineQueue = [];

  int get queueLength => _offlineQueue.length;

  Map<String, String> get _authHeaders => {
    'Content-Type': 'application/json',
    if (jwtToken != null) 'Authorization': 'Bearer $jwtToken',
  };

  Map<String, String> get _authOnlyHeaders => {
    if (jwtToken != null) 'Authorization': 'Bearer $jwtToken',
  };

  // Exponential backoff retry: 1s, 2s, 4s
  Future<T> _retryWithBackoff<T>(Future<T> Function() fn, {int maxRetries = 3}) async {
    int attempt = 0;
    while (true) {
      try {
        return await fn();
      } on SocketException {
        rethrow;
      } on TimeoutException {
        rethrow;
      } catch (e) {
        if (attempt >= maxRetries - 1) rethrow;
        await Future.delayed(Duration(seconds: 1 << attempt));
        attempt++;
      }
    }
  }

  Future<Map<String, dynamic>> get(String path) async {
    try {
      return await _retryWithBackoff(() async {
        final res = await http
            .get(Uri.parse('${AppConfig.serverBaseUrl}$path'), headers: _authOnlyHeaders)
            .timeout(const Duration(seconds: 10));
        return jsonDecode(res.body) as Map<String, dynamic>;
      });
    } on SocketException {
      _offlineQueue.add({'method': 'GET', 'path': path, 'body': null, 'timestamp': DateTime.now().toIso8601String()});
      return {'status': 'queued', 'message': 'Request queued for retry'};
    } on TimeoutException {
      _offlineQueue.add({'method': 'GET', 'path': path, 'body': null, 'timestamp': DateTime.now().toIso8601String()});
      return {'status': 'queued', 'message': 'Request queued for retry'};
    }
  }

  Future<Map<String, dynamic>> post(String path, {Map<String, dynamic>? body}) async {
    try {
      return await _retryWithBackoff(() async {
        final res = await http
            .post(
              Uri.parse('${AppConfig.serverBaseUrl}$path'),
              headers: _authHeaders,
              body: body != null ? jsonEncode(body) : null,
            )
            .timeout(const Duration(seconds: 10));
        return jsonDecode(res.body) as Map<String, dynamic>;
      });
    } on SocketException {
      _offlineQueue.add({'method': 'POST', 'path': path, 'body': body, 'timestamp': DateTime.now().toIso8601String()});
      return {'status': 'queued', 'message': 'Request queued for retry'};
    } on TimeoutException {
      _offlineQueue.add({'method': 'POST', 'path': path, 'body': body, 'timestamp': DateTime.now().toIso8601String()});
      return {'status': 'queued', 'message': 'Request queued for retry'};
    }
  }

  Future<Map<String, dynamic>> uploadImage(String path, File image) async {
    try {
      return await _retryWithBackoff(() async {
        final request = http.MultipartRequest('POST', Uri.parse('${AppConfig.serverBaseUrl}$path'));
        if (jwtToken != null) request.headers['Authorization'] = 'Bearer $jwtToken';
        request.files.add(await http.MultipartFile.fromPath('image', image.path));
        final streamedResponse = await request.send().timeout(const Duration(seconds: 30));
        final response = await http.Response.fromStream(streamedResponse);
        return jsonDecode(response.body) as Map<String, dynamic>;
      });
    } on SocketException {
      _offlineQueue.add({'method': 'UPLOAD_IMAGE', 'path': path, 'body': {'imagePath': image.path}, 'timestamp': DateTime.now().toIso8601String()});
      return {'status': 'queued', 'message': 'Request queued for retry'};
    } on TimeoutException {
      _offlineQueue.add({'method': 'UPLOAD_IMAGE', 'path': path, 'body': {'imagePath': image.path}, 'timestamp': DateTime.now().toIso8601String()});
      return {'status': 'queued', 'message': 'Request queued for retry'};
    }
  }

  Future<Map<String, dynamic>> uploadMultipart(String path, {
    required Map<String, String> fields,
    required List<MapEntry<String, String>> filePaths,
  }) async {
    try {
      return await _retryWithBackoff(() async {
        final request = http.MultipartRequest('POST', Uri.parse('${AppConfig.serverBaseUrl}$path'));
        if (jwtToken != null) request.headers['Authorization'] = 'Bearer $jwtToken';
        request.fields.addAll(fields);
        for (final entry in filePaths) {
          request.files.add(await http.MultipartFile.fromPath(entry.key, entry.value));
        }
        final streamedResponse = await request.send().timeout(const Duration(seconds: 30));
        final response = await http.Response.fromStream(streamedResponse);
        return jsonDecode(response.body) as Map<String, dynamic>;
      });
    } on SocketException {
      _offlineQueue.add({'method': 'UPLOAD_MULTIPART', 'path': path, 'body': {'fields': fields}, 'timestamp': DateTime.now().toIso8601String()});
      return {'status': 'queued', 'message': 'Request queued for retry'};
    } on TimeoutException {
      _offlineQueue.add({'method': 'UPLOAD_MULTIPART', 'path': path, 'body': {'fields': fields}, 'timestamp': DateTime.now().toIso8601String()});
      return {'status': 'queued', 'message': 'Request queued for retry'};
    }
  }

  /// Replay all queued requests in order. Removes entries that succeed.
  Future<void> flushQueue() async {
    if (_offlineQueue.isEmpty) return;
    final toRetry = List<Map<String, dynamic>>.from(_offlineQueue);
    for (final entry in toRetry) {
      try {
        final method = entry['method'] as String;
        final path = entry['path'] as String;
        final body = entry['body'] as Map<String, dynamic>?;
        bool success = false;
        if (method == 'GET') {
          final res = await http
              .get(Uri.parse('${AppConfig.serverBaseUrl}$path'), headers: _authOnlyHeaders)
              .timeout(const Duration(seconds: 10));
          success = res.statusCode < 500;
        } else if (method == 'POST') {
          final res = await http
              .post(
                Uri.parse('${AppConfig.serverBaseUrl}$path'),
                headers: _authHeaders,
                body: body != null ? jsonEncode(body) : null,
              )
              .timeout(const Duration(seconds: 10));
          success = res.statusCode < 500;
        } else if (method == 'UPLOAD_IMAGE') {
          final imagePath = body?['imagePath'] as String?;
          if (imagePath != null && await File(imagePath).exists()) {
            final request = http.MultipartRequest('POST', Uri.parse('${AppConfig.serverBaseUrl}$path'));
            if (jwtToken != null) request.headers['Authorization'] = 'Bearer $jwtToken';
            request.files.add(await http.MultipartFile.fromPath('image', imagePath));
            final streamed = await request.send().timeout(const Duration(seconds: 30));
            success = streamed.statusCode < 500;
          } else {
            // File no longer available — drop the entry
            success = true;
          }
        } else if (method == 'UPLOAD_MULTIPART') {
          // Re-queuing multipart without original file paths is not possible; drop it
          success = true;
        }
        if (success) _offlineQueue.remove(entry);
      } catch (_) {
        // Still offline — stop flushing
        break;
      }
    }
  }

  Future<http.Response> getRaw(String path) async {
    return http.get(
      Uri.parse('${AppConfig.serverBaseUrl}$path'),
      headers: _authOnlyHeaders,
    );
  }

  Future<http.Response> postRaw(String path, {Map<String, dynamic>? body}) async {
    return http.post(
      Uri.parse('${AppConfig.serverBaseUrl}$path'),
      headers: _authHeaders,
      body: body != null ? jsonEncode(body) : null,
    );
  }
}
