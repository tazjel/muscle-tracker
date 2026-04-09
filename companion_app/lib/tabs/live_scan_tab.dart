import 'package:flutter/material.dart';
// Live scan tab
class LiveScanTab extends StatefulWidget {
  const LiveScanTab({super.key});
  @override
  State<LiveScanTab> createState() => _LiveScanTabState();
}
class _LiveScanTabState extends State<LiveScanTab> {
  @override
  Widget build(BuildContext context) {
    return const Center(child: Text('Live Scan Tab', style: TextStyle(color: Colors.white)));
  }
}
