import 'dart:io';
import 'package:flutter/material.dart';
import '../config.dart';

class ReviewScreen extends StatelessWidget {
  final String frontPath, sidePath; const ReviewScreen({super.key, required this.frontPath, required this.sidePath});
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Review Captures')),
      body: Column(children: [
        Expanded(child: Row(children: [
          Expanded(child: Column(children: [const Padding(padding: EdgeInsets.all(12), child: Text('FRONTAL', style: TextStyle(fontWeight: FontWeight.bold, color: AppTheme.primaryTeal))), Expanded(child: Image.file(File(frontPath), fit: BoxFit.contain))])),
          const VerticalDivider(width: 1, color: Colors.white10),
          Expanded(child: Column(children: [const Padding(padding: EdgeInsets.all(12), child: Text('LATERAL', style: TextStyle(fontWeight: FontWeight.bold, color: AppTheme.primaryTeal))), Expanded(child: Image.file(File(sidePath), fit: BoxFit.contain))])),
        ])),
        Padding(padding: const EdgeInsets.all(32), child: Row(children: [
          Expanded(child: OutlinedButton.icon(onPressed: () => Navigator.pop(context, false), icon: const Icon(Icons.refresh), label: const Text('RETAKE'), style: OutlinedButton.styleFrom(foregroundColor: Colors.white70, side: const BorderSide(color: Colors.white24)))),
          const SizedBox(width: 16),
          Expanded(child: FilledButton.icon(onPressed: () => Navigator.pop(context, true), icon: const Icon(Icons.check_circle), label: const Text('ANALYZE'))),
        ])),
      ]),
    );
  }
}
