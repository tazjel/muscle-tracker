import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import '../config.dart';

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
        if (lres.statusCode == 200) { jwtToken = ld['token']; customerId = ld['customer_id']?.toString() ?? '1'; customerName = ld['name'] ?? _name.text; Navigator.pushNamedAndRemoveUntil(context, '/home', (r) => false); }
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
