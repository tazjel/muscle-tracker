// GTD3D API Service — will receive HTTP calls from main.dart
class ApiService {
  static final ApiService _instance = ApiService._();
  factory ApiService() => _instance;
  ApiService._();
}
