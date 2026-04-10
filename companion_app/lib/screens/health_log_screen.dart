import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import '../config.dart';

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
