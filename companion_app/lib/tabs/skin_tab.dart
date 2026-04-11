import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'dart:convert';
import 'package:http/http.dart' as http;
import '../config.dart';
import '../services/secure_delete.dart';
import '../widgets/skin_guide_overlay.dart';

// 8-Region Skin Capture Tab
class SkinTab extends StatefulWidget {
  final CameraController controller;

  const SkinTab({
    super.key,
    required this.controller,
  });

  @override
  State<SkinTab> createState() => _SkinTabState();
}

class _SkinTabState extends State<SkinTab> {
  bool isCapturing = false;
  String selectedSkinRegion = 'forearm';
  final Map<String, bool> skinRegionsUploaded = {};
  String? statusMessage;

  static const List<String> skinRegions = [
    'forearm', 'chest', 'abdomen', 'thigh', 'calf', 'upper_arm', 'shoulders', 'back',
  ];
  static const Map<String, String> skinRegionLabels = {
    'forearm': 'Forearm', 'chest': 'Chest', 'abdomen': 'Abdomen',
    'thigh': 'Thigh', 'calf': 'Calf', 'upper_arm': 'Upper Arm',
    'shoulders': 'Shoulders', 'back': 'Back',
  };
  static const Map<String, String> skinRegionGuides = {
    'forearm': 'Hold camera 10-15cm from inner forearm',
    'chest': 'Hold camera 10-15cm from center chest',
    'abdomen': 'Hold camera 10-15cm from stomach area',
    'thigh': 'Hold camera 10-15cm from front thigh',
    'calf': 'Hold camera 10-15cm from calf muscle',
    'upper_arm': 'Hold camera 10-15cm from upper arm',
    'shoulders': 'Hold camera 10-15cm from shoulder',
    'back': 'Hold camera 10-15cm from lower back',
  };

  Future<void> captureSkinRegion() async {
    if (!widget.controller.value.isInitialized || isCapturing) return;
    setState(() { isCapturing = true; statusMessage = 'Capturing skin...'; });
    try {
      final img = await widget.controller.takePicture();
      setState(() => statusMessage = 'Uploading $selectedSkinRegion...');
      var request = http.MultipartRequest(
        'POST',
        Uri.parse('${AppConfig.serverBaseUrl}/api/customer/$customerId/skin_region/$selectedSkinRegion'),
      );
      request.headers['Authorization'] = 'Bearer ${jwtToken ?? ''}';
      request.files.add(await http.MultipartFile.fromPath('image', img.path));
      var streamedResponse = await request.send().timeout(const Duration(seconds: 30));
      var response = await http.Response.fromStream(streamedResponse);
      if (!mounted) return;
      final result = jsonDecode(response.body);
      if (response.statusCode == 200 && result['status'] == 'success') {
        // Privacy: delete local capture after successful upload
        await SecureDelete.path(img.path);
        setState(() {
          skinRegionsUploaded[selectedSkinRegion] = true;
          final uploaded = skinRegionsUploaded.values.where((v) => v).length;
          statusMessage = '$uploaded/${skinRegions.length} regions captured';
          isCapturing = false;
          final next = skinRegions.firstWhere(
            (r) => skinRegionsUploaded[r] != true,
            orElse: () => selectedSkinRegion,
          );
          selectedSkinRegion = next;
        });
      } else {
        await SecureDelete.path(img.path);
        setState(() { statusMessage = 'Failed: ${result["message"] ?? "error"}'; isCapturing = false; });
      }
    } catch (e) {
      setState(() { statusMessage = 'Error: $e'; isCapturing = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.controller.value.isInitialized) {
      return const Scaffold(body: Center(child: CircularProgressIndicator(color: AppTheme.primaryTeal)));
    }
    return Scaffold(
      body: Stack(fit: StackFit.expand, children: [
        CameraPreview(widget.controller),
        _buildSkinGuideOverlay(),
        _buildSkinRegionSelector(),
        _buildCaptureButton(),
      ]),
    );
  }

  Widget _buildSkinGuideOverlay() {
    return Positioned.fill(
      child: IgnorePointer(
        child: CustomPaint(painter: SkinGuideOverlayPainter()),
      ),
    );
  }

  Widget _buildSkinRegionSelector() {
    final uploaded = skinRegionsUploaded.values.where((v) => v).length;
    return Positioned(
      top: MediaQuery.of(context).padding.top + 8,
      left: 8, right: 8,
      child: Column(children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          decoration: BoxDecoration(color: Colors.black54, borderRadius: BorderRadius.circular(12)),
          child: Column(children: [
            Text('SKIN CAPTURE  $uploaded/${skinRegions.length}',
              style: const TextStyle(color: AppTheme.primaryTeal, fontWeight: FontWeight.bold, fontSize: 12)),
            const SizedBox(height: 4),
            Text(skinRegionGuides[selectedSkinRegion] ?? '',
              style: const TextStyle(color: Colors.white70, fontSize: 11)),
            if (statusMessage != null) ...[
              const SizedBox(height: 4),
              Text(statusMessage!, style: const TextStyle(color: AppTheme.primaryTeal, fontSize: 11)),
            ],
          ]),
        ),
        const SizedBox(height: 8),
        Wrap(
          spacing: 4, runSpacing: 4, alignment: WrapAlignment.center,
          children: skinRegions.map((r) {
            final done = skinRegionsUploaded[r] == true;
            final selected = r == selectedSkinRegion;
            return GestureDetector(
              onTap: () => setState(() => selectedSkinRegion = r),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                decoration: BoxDecoration(
                  color: done ? AppTheme.accentGreen.withAlpha(80) : (selected ? AppTheme.primaryTeal.withAlpha(80) : Colors.white10),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: selected ? AppTheme.primaryTeal : (done ? AppTheme.accentGreen : Colors.white24)),
                ),
                child: Text(
                  skinRegionLabels[r] ?? r,
                  style: TextStyle(
                    color: done ? AppTheme.accentGreen : (selected ? AppTheme.primaryTeal : Colors.white70),
                    fontSize: 11,
                    fontWeight: selected ? FontWeight.bold : FontWeight.normal,
                  ),
                ),
              ),
            );
          }).toList(),
        ),
      ]),
    );
  }

  Widget _buildCaptureButton() {
    final bottomPad = MediaQuery.of(context).padding.bottom + 32;
    return Positioned(
      bottom: bottomPad, left: 0, right: 0,
      child: Center(
        child: GestureDetector(
          onTap: isCapturing ? null : captureSkinRegion,
          child: Container(
            width: 76, height: 76,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: AppTheme.primaryTeal,
              border: Border.all(color: Colors.white, width: 4),
            ),
            child: isCapturing
                ? const Padding(padding: EdgeInsets.all(20), child: CircularProgressIndicator(color: Colors.black, strokeWidth: 3))
                : const Icon(Icons.camera_alt, color: Colors.black, size: 36),
          ),
        ),
      ),
    );
  }
}
