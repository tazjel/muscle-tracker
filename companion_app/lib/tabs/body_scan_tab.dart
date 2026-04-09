import 'package:flutter/material.dart';
// Body scan tab
class BodyScanTab extends StatefulWidget {
  const BodyScanTab({super.key});
  @override
  State<BodyScanTab> createState() => _BodyScanTabState();
}
class _BodyScanTabState extends State<BodyScanTab> {
  @override
  Widget build(BuildContext context) {
    return const Center(child: Text('Body Scan Tab', style: TextStyle(color: Colors.white)));
  }
}
