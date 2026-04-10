import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import '../config.dart';

class ProgressScreen extends StatefulWidget {
  final String? muscleGroup; const ProgressScreen({super.key, this.muscleGroup});
  @override
  State<ProgressScreen> createState() => _ProgressScreenState();
}

class _ProgressScreenState extends State<ProgressScreen> {
  bool _l = true; String? _e; Map<String, dynamic>? _d;
  @override
  void initState() { super.initState(); _f(); }
  Future<void> _f() async {
    setState(() { _l = true; _e = null; });
    try {
      final res = await http.get(Uri.parse('${AppConfig.serverBaseUrl}/api/customer/$customerId/progress${widget.muscleGroup != null ? "?muscle_group=${widget.muscleGroup}" : ""}'), headers: {'Authorization': 'Bearer ${jwtToken ?? ''}'});
      final data = jsonDecode(res.body);
      if (res.statusCode == 200 && data['status'] == 'success') setState(() { _d = data; _l = false; });
      else setState(() { _e = data['message'] ?? 'Load failed'; _l = false; });
    } catch (err) { setState(() { _e = 'Error: $err'; _l = false; }); }
  }
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Progress Analytics')),
      body: _l ? const Center(child: CircularProgressIndicator()) : (_e != null ? Center(child: Text(_e!)) : _buildBody()),
    );
  }
  Widget _buildBody() {
    final tr = _d?['trend'] ?? {}; if (tr['status'] == 'Insufficient Data' || tr.isEmpty) return const Center(child: Text('Add more scans to unlock analytics'));
    final sm = _d?['volume_summary'] ?? {}, st = _d?['growth_streak'] ?? {}, dir = tr['direction'] ?? 'unknown', col = dir == 'gaining' ? AppTheme.accentGreen : (dir == 'losing' ? AppTheme.accentRed : Colors.orangeAccent);
    return SingleChildScrollView(padding: const EdgeInsets.all(24), child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      const Text('OVERALL CLINICAL TREND', style: TextStyle(color: AppTheme.primaryTeal, fontWeight: FontWeight.bold, letterSpacing: 2, fontSize: 12)),
      Text(dir.toUpperCase(), style: TextStyle(fontSize: 40, fontWeight: FontWeight.w900, color: col)),
      const SizedBox(height: 32),
      _stat('Total Change', '${sm['total_change_cm3']?.toStringAsFixed(1) ?? "0"} cm³ (${sm['total_change_pct']?.toStringAsFixed(1) ?? "0"}%)'),
      _stat('Weekly Growth', '${tr['weekly_rate_cm3']?.toStringAsFixed(2) ?? "0"} cm³/wk'),
      _stat('Consistency (R²)', '${tr['consistency_r2']?.toStringAsFixed(2) ?? "0"}'),
      _stat('30-Day Forecast', '${tr['projected_30d_cm3']?.toStringAsFixed(1) ?? "0"} cm³'),
      _stat('Growth Streak', '${st['consecutive_gains'] ?? 0} cycles'),
      const SizedBox(height: 32),
      if (_d?['correlation'] != null) ...[
        const Text('HEALTH CORRELATIONS', style: TextStyle(color: AppTheme.primaryTeal, fontWeight: FontWeight.bold, letterSpacing: 2, fontSize: 12)),
        const SizedBox(height: 16),
        ...(_d!['correlation'] as Map<String, dynamic>).entries.map((e) {
          final v = e.value as double, c = v > 0 ? AppTheme.accentGreen : AppTheme.accentRed, str = v.abs() > 0.7 ? 'Strong' : (v.abs() > 0.4 ? 'Moderate' : 'Weak');
          return _stat(e.key.replaceAll('_', ' ').toUpperCase(), '$str ${v > 0 ? "Positive" : "Negative"} (${v.toStringAsFixed(2)})', valCol: c);
        }),
      ],
    ]));
  }
  Widget _stat(String l, String v, {Color? valCol}) { return Card(margin: const EdgeInsets.only(bottom: 12), child: Padding(padding: const EdgeInsets.all(16), child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [Expanded(child: Text(l, style: const TextStyle(color: Colors.white54, fontSize: 14))), Text(v, style: TextStyle(color: valCol ?? Colors.white, fontSize: 15, fontWeight: FontWeight.bold))]))); }
}
