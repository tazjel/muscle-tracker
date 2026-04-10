import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import '../config.dart';
import 'register_screen.dart';

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
        Navigator.pushReplacementNamed(context, '/home');
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
            Navigator.pushReplacementNamed(context, '/home');
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
