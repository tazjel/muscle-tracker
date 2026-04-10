import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import '../config.dart';
import 'health_log_screen.dart';
import 'progress_screen.dart';
import 'report_viewer_screen.dart';

class HistoryScreen extends StatefulWidget {
  final String? muscleGroup; const HistoryScreen({super.key, this.muscleGroup});
  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  bool _l = true; String? _e; List<dynamic> _s = [];
  @override
  void initState() { super.initState(); _f(); }
  Future<void> _f() async {
    setState(() { _l = true; _e = null; });
    try {
      final res = await http.get(Uri.parse('${AppConfig.serverBaseUrl}/api/customer/$customerId/scans${widget.muscleGroup != null ? "?muscle_group=${widget.muscleGroup}" : ""}'), headers: {'Authorization': 'Bearer ${jwtToken ?? ''}'});
      final d = jsonDecode(res.body);
      if (res.statusCode == 200 && d['status'] == 'success') setState(() { _s = d['scans']; _l = false; });
      else setState(() { _e = d['message'] ?? 'Load failed'; _l = false; });
    } catch (err) { setState(() { _e = 'Error: $err'; _l = false; }); }
  }
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Clinical History')),
      body: _l ? const Center(child: CircularProgressIndicator()) : (_e != null ? Center(child: Text(_e!)) : Column(children: [
        Padding(padding: const EdgeInsets.all(16), child: Row(children: [
          Expanded(child: FilledButton.icon(onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => ProgressScreen(muscleGroup: widget.muscleGroup))), icon: const Icon(Icons.trending_up), label: const Text('TRENDS'), style: FilledButton.styleFrom(backgroundColor: const Color(0xFF1A237E), foregroundColor: Colors.white))),
          const SizedBox(width: 8),
          Expanded(child: FilledButton.icon(onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const HealthLogScreen())), icon: const Icon(Icons.monitor_heart), label: const Text('HEALTH'), style: FilledButton.styleFrom(backgroundColor: const Color(0xFF37474F), foregroundColor: Colors.white))),
        ])),
        Expanded(child: _s.isEmpty ? const Center(child: Text('No data found')) : ListView.builder(itemCount: _s.length, itemBuilder: (c, i) {
          final sc = _s[i], vol = sc['volume_cm3']?.toDouble() ?? 0.0, gr = sc['growth_pct']?.toDouble(), id = sc['id'];
          return Card(margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6), child: ListTile(
            title: Text('${sc['scan_date'].split('T')[0]} - ${sc['muscle_group'].toUpperCase()}', style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
            subtitle: Text('Volume: ${vol.toStringAsFixed(1)} cm³ | Grade: ${sc['shape_grade'] ?? "-"}', style: const TextStyle(fontSize: 12)),
            trailing: Row(mainAxisSize: MainAxisSize.min, children: [
              if (gr != null) Text('${gr > 0 ? "+" : ""}${gr.toStringAsFixed(1)}%', style: TextStyle(fontWeight: FontWeight.bold, color: gr >= 0 ? AppTheme.accentGreen : AppTheme.accentRed)),
              const SizedBox(width: 8),
              IconButton(icon: const Icon(Icons.summarize, color: AppTheme.primaryTeal, size: 20), onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => ReportViewerScreen(scanId: id)))),
            ]),
          ));
        })),
      ])),
    );
  }
}
