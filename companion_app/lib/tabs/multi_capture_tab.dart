import 'package:flutter/material.dart';
// Multi-capture tab
class MultiCaptureTab extends StatefulWidget {
  const MultiCaptureTab({super.key});
  @override
  State<MultiCaptureTab> createState() => _MultiCaptureTabState();
}
class _MultiCaptureTabState extends State<MultiCaptureTab> {
  @override
  Widget build(BuildContext context) {
    return const Center(child: Text('Multi-Capture Tab', style: TextStyle(color: Colors.white)));
  }
}
