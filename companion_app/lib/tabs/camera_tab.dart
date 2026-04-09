import 'package:flutter/material.dart';
// Photo + Video capture tab
class CameraTab extends StatefulWidget {
  const CameraTab({super.key});
  @override
  State<CameraTab> createState() => _CameraTabState();
}
class _CameraTabState extends State<CameraTab> {
  @override
  Widget build(BuildContext context) {
    return const Center(child: Text('Camera Tab', style: TextStyle(color: Colors.white)));
  }
}
