import 'package:flutter/material.dart';
// Skin capture tab
class SkinTab extends StatefulWidget {
  const SkinTab({super.key});
  @override
  State<SkinTab> createState() => _SkinTabState();
}
class _SkinTabState extends State<SkinTab> {
  @override
  Widget build(BuildContext context) {
    return const Center(child: Text('Skin Tab', style: TextStyle(color: Colors.white)));
  }
}
