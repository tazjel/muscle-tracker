import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import '../config.dart';

class ApiService {
  static final ApiService _instance = ApiService._();
  factory ApiService() => _instance;
  ApiService._();

  static ApiService get instance => _instance;

  Map<String, String> get _authHeaders => {
    'Content-Type': 'application/json',
    if (jwtToken != null) 'Authorization': 'Bearer $jwtToken',
  };

  Map<String, String> get _authOnlyHeaders => {
    if (jwtToken != null) 'Authorization': 'Bearer $jwtToken',
  };

  Future<Map<String, dynamic>> get(String path) async {
    final res = await http.get(
      Uri.parse('${AppConfig.serverBaseUrl}$path'),
      headers: _authOnlyHeaders,
    );
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> post(String path, {Map<String, dynamic>? body}) async {
    final res = await http.post(
      Uri.parse('${AppConfig.serverBaseUrl}$path'),
      headers: _authHeaders,
      body: body != null ? jsonEncode(body) : null,
    );
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> uploadImage(String path, File image) async {
    final request = http.MultipartRequest('POST', Uri.parse('${AppConfig.serverBaseUrl}$path'));
    if (jwtToken != null) request.headers['Authorization'] = 'Bearer $jwtToken';
    request.files.add(await http.MultipartFile.fromPath('image', image.path));
    final streamedResponse = await request.send();
    final response = await http.Response.fromStream(streamedResponse);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> uploadMultipart(String path, {
    required Map<String, String> fields,
    required List<MapEntry<String, String>> filePaths,
  }) async {
    final request = http.MultipartRequest('POST', Uri.parse('${AppConfig.serverBaseUrl}$path'));
    if (jwtToken != null) request.headers['Authorization'] = 'Bearer $jwtToken';
    request.fields.addAll(fields);
    for (final entry in filePaths) {
      request.files.add(await http.MultipartFile.fromPath(entry.key, entry.value));
    }
    final streamedResponse = await request.send();
    final response = await http.Response.fromStream(streamedResponse);
    return jsonDecode(response.body) as Map<String, dynamic>;
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
