import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';
import '../config.dart';
import '../services/secure_delete.dart';
import 'history_screen.dart';
import 'live_preview_screen.dart';
import 'model_viewer_screen.dart';
import 'report_viewer_screen.dart';

class ResultsScreen extends StatefulWidget {
  final Map<String, dynamic> result;
  final String muscleGroup;
  const ResultsScreen({super.key, required this.result, required this.muscleGroup});
  @override
  State<ResultsScreen> createState() => _ResultsScreenState();
}

class _ResultsScreenState extends State<ResultsScreen> {
  bool _downloadingReport = false;

  Future<void> _downloadSessionReport(int scanId) async {
    setState(() => _downloadingReport = true);
    try {
      final res = await http.post(
        Uri.parse('${AppConfig.serverBaseUrl}/api/customer/$customerId/session_report'),
        headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ${jwtToken ?? ''}'},
        body: jsonEncode({'scan_id': scanId}),
      ).timeout(const Duration(seconds: 30));
      if (!mounted) return;
      if (res.statusCode == 200) {
        final dir  = await getTemporaryDirectory();
        final file = File('${dir.path}/session_report_$scanId.pdf');
        await file.writeAsBytes(res.bodyBytes);
        await Share.shareXFiles([XFile(file.path)], text: 'Muscle Tracker Session Report');
        // Privacy: delete temp PDF after sharing
        await SecureDelete.path(file.path);
      } else {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Report generation failed')));
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error: $e')));
    } finally {
      if (mounted) setState(() => _downloadingReport = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final r          = widget.result;
    final muscleGroup = widget.muscleGroup;
    final vol        = r['volume_cm3']?.toDouble()        ?? 0.0;
    final growth     = r['growth_pct']?.toDouble();
    final delta      = r['volume_delta_cm3']?.toDouble();
    final score      = r['shape_score']?.toDouble();
    final grade      = r['shape_grade'];
    final calibrated = r['calibrated']  ?? false;
    final scanId     = r['scan_id'];
    final meshId     = r['mesh_id'];
    final circCm     = r['circumference_cm']?.toDouble();
    final defScore   = r['definition_score']?.toDouble();
    final defGrade   = r['definition_grade'] as String?;
    final annUrl     = r['annotated_img_url'] as String?;

    return Scaffold(
      appBar: AppBar(title: const Text('Scan Analysis')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [

          // ── Volume hero card ──────────────────────────────────────────
          Card(child: Padding(padding: const EdgeInsets.all(32), child: Column(children: [
            Text(muscleGroup.toUpperCase(),
                style: const TextStyle(color: AppTheme.primaryTeal, fontWeight: FontWeight.w900, letterSpacing: 3)),
            const SizedBox(height: 16),
            Text('${vol.toStringAsFixed(1)} cm³',
                style: const TextStyle(fontSize: 52, fontWeight: FontWeight.bold, color: Colors.white)),
            const Text('QUANTIFIED VOLUME', style: TextStyle(color: Colors.white38, letterSpacing: 1.5)),
            const SizedBox(height: 20),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
              decoration: BoxDecoration(
                color: calibrated ? Colors.green.withOpacity(0.1) : Colors.orange.withOpacity(0.1),
                borderRadius: BorderRadius.circular(20),
                border: Border.all(color: calibrated ? AppTheme.accentGreen : Colors.orange, width: 0.5),
              ),
              child: Text(
                calibrated ? 'OPTICAL CALIBRATION ACTIVE' : 'ESTIMATED SCALE',
                style: TextStyle(color: calibrated ? AppTheme.accentGreen : Colors.orange, fontSize: 10, fontWeight: FontWeight.bold),
              ),
            ),
          ]))),
          const SizedBox(height: 12),

          // ── Annotated image preview ───────────────────────────────────
          if (annUrl != null)
            Card(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Padding(padding: EdgeInsets.fromLTRB(16, 14, 0, 8),
                  child: Text('ANNOTATED IMAGE', style: TextStyle(color: AppTheme.primaryTeal, fontWeight: FontWeight.bold, fontSize: 11, letterSpacing: 1.2))),
              ClipRRect(
                borderRadius: const BorderRadius.only(bottomLeft: Radius.circular(12), bottomRight: Radius.circular(12)),
                child: Image.network(
                  '${AppConfig.serverBaseUrl}$annUrl',
                  headers: {'Authorization': 'Bearer ${jwtToken ?? ''}'},
                  fit: BoxFit.contain,
                  errorBuilder: (_, __, ___) => const SizedBox.shrink(),
                ),
              ),
            ])),
          if (annUrl != null) const SizedBox(height: 12),

          // ── Metrics row (growth + circumference + definition) ─────────
          Row(children: [
            if (growth != null) Expanded(child: Card(child: Padding(padding: const EdgeInsets.all(16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text('Growth', style: TextStyle(color: Colors.white54, fontSize: 11)),
              const SizedBox(height: 6),
              Text('${growth > 0 ? "+" : ""}${growth.toStringAsFixed(1)}%',
                  style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold,
                      color: growth >= 0 ? AppTheme.accentGreen : AppTheme.accentRed)),
              if (delta != null) Text('${delta > 0 ? "+" : ""}${delta.toStringAsFixed(1)} cm³',
                  style: const TextStyle(color: Colors.white38, fontSize: 11)),
            ])))),
            if (circCm != null) ...[
              const SizedBox(width: 10),
              Expanded(child: Card(child: Padding(padding: const EdgeInsets.all(16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Text('Circumference', style: TextStyle(color: Colors.white54, fontSize: 11)),
                const SizedBox(height: 6),
                Text('${circCm.toStringAsFixed(1)} cm',
                    style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: Colors.white)),
                Text('${(circCm / 2.54).toStringAsFixed(1)} in',
                    style: const TextStyle(color: Colors.white38, fontSize: 11)),
              ])))),
            ],
          ]),
          const SizedBox(height: 10),

          // ── Shape + Definition ────────────────────────────────────────
          Row(children: [
            if (score != null) Expanded(child: Card(child: Padding(padding: const EdgeInsets.all(16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text('Shape', style: TextStyle(color: Colors.white54, fontSize: 11)),
              const SizedBox(height: 6),
              Row(children: [
                Text('${score.toStringAsFixed(0)}/100',
                    style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: Colors.white70)),
                const SizedBox(width: 10),
                Container(padding: const EdgeInsets.all(8), decoration: const BoxDecoration(shape: BoxShape.circle, color: AppTheme.primaryTeal),
                    child: Text(grade ?? '-', style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.black, fontSize: 13))),
              ]),
            ])))),
            if (defScore != null) ...[
              const SizedBox(width: 10),
              Expanded(child: Card(child: Padding(padding: const EdgeInsets.all(16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Text('Definition', style: TextStyle(color: Colors.white54, fontSize: 11)),
                const SizedBox(height: 6),
                Row(children: [
                  Text('${defScore.toStringAsFixed(0)}/100',
                      style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: Colors.white70)),
                  if (defGrade != null) ...[
                    const SizedBox(width: 10),
                    Container(padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                        decoration: BoxDecoration(color: Colors.orange.withOpacity(0.2), borderRadius: BorderRadius.circular(8)),
                        child: Text(defGrade, style: const TextStyle(color: Colors.orange, fontWeight: FontWeight.bold, fontSize: 12))),
                  ],
                ]),
              ])))),
            ],
          ]),
          const SizedBox(height: 36),

          // ── Action buttons ────────────────────────────────────────────
          if (scanId != null) ...[
            _downloadingReport
                ? const Center(child: Padding(padding: EdgeInsets.all(8), child: CircularProgressIndicator(color: AppTheme.primaryTeal)))
                : FilledButton.icon(
                    onPressed: () => _downloadSessionReport(scanId),
                    icon: const Icon(Icons.picture_as_pdf),
                    label: const Text('DOWNLOAD SESSION REPORT'),
                    style: FilledButton.styleFrom(backgroundColor: const Color(0xFF1A3A4A), foregroundColor: Colors.white),
                  ),
            const SizedBox(height: 10),
            FilledButton.icon(
              onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => ReportViewerScreen(scanId: scanId))),
              icon: const Icon(Icons.summarize),
              label: const Text('VIEW CLINICAL REPORT'),
              style: FilledButton.styleFrom(backgroundColor: Colors.white10, foregroundColor: Colors.white),
            ),
            const SizedBox(height: 10),
            if (meshId != null)
              FilledButton.icon(
                onPressed: () => Navigator.push(context, MaterialPageRoute(
                  builder: (_) => ModelViewerScreen(meshId: int.parse(meshId.toString())),
                )),
                icon: const Icon(Icons.view_in_ar, size: 18),
                label: const Text('VIEW 3D'),
                style: FilledButton.styleFrom(
                  backgroundColor: const Color(0xFF1B5E20),
                  foregroundColor: Colors.white,
                ),
              ),
            const SizedBox(height: 10),
          ],
          FilledButton.icon(
            onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const LivePreviewScreen())),
            icon: const Icon(Icons.videocam),
            label: const Text('LIVE MEASURE'),
            style: FilledButton.styleFrom(backgroundColor: const Color(0xFF0D3B2A), foregroundColor: AppTheme.accentGreen),
          ),
          const SizedBox(height: 10),
          FilledButton.icon(
            onPressed: () => Navigator.pop(context),
            icon: const Icon(Icons.add_a_photo),
            label: const Text('NEW SCAN'),
          ),
          TextButton(
            onPressed: () => Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => HistoryScreen(muscleGroup: muscleGroup))),
            child: const Text('VIEW FULL HISTORY', style: TextStyle(color: AppTheme.primaryTeal)),
          ),
        ]),
      ),
    );
  }
}
