import 'dart:io';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';
import '../config.dart';
import '../services/secure_delete.dart';

class ReportViewerScreen extends StatelessWidget {
  final int scanId; const ReportViewerScreen({super.key, required this.scanId});
  Future<Uint8List> _f() async { final r = await http.get(Uri.parse('${AppConfig.serverBaseUrl}/api/customer/$customerId/report/$scanId'), headers: {'Authorization': 'Bearer ${jwtToken ?? ''}'}); if (r.statusCode == 200) return r.bodyBytes; throw Exception('Error ${r.statusCode}'); }
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Clinical Report')),
      body: FutureBuilder<Uint8List>(future: _f(), builder: (context, sn) {
        if (sn.connectionState == ConnectionState.waiting) return const Center(child: CircularProgressIndicator());
        if (sn.hasError) return Center(child: Text('Error: ${sn.error}'));
        final b = sn.data!;
        return Column(children: [
          Expanded(child: InteractiveViewer(child: Center(child: Image.memory(b)))),
          Padding(padding: const EdgeInsets.all(24), child: Row(children: [
            Expanded(child: OutlinedButton.icon(onPressed: () async { final d = await getApplicationDocumentsDirectory(); await File('${d.path}/report_$scanId.png').writeAsBytes(b); ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Saved to documents'))); }, icon: const Icon(Icons.save), label: const Text('SAVE'))),
            const SizedBox(width: 16),
            Expanded(child: FilledButton.icon(onPressed: () async { final d = await getTemporaryDirectory(); final f = File('${d.path}/r_$scanId.png'); await f.writeAsBytes(b); await Share.shareXFiles([XFile(f.path)], text: 'Muscle Tracker Report'); await SecureDelete.path(f.path); }, icon: const Icon(Icons.share), label: const Text('SHARE'))),
          ])),
        ]);
      }),
    );
  }
}
