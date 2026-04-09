import 'package:flutter/material.dart';
import '../config.dart';

class DevPanel extends StatelessWidget {
  final String customerId;
  final String? jwtToken;
  final double cameraDistanceCm;
  final bool profileCompleted;
  final VoidCallback? onEditProfile;
  final VoidCallback? onForceScan;

  const DevPanel({
    super.key,
    required this.customerId,
    this.jwtToken,
    this.cameraDistanceCm = 75,
    this.profileCompleted = false,
    this.onEditProfile,
    this.onForceScan,
  });

  @override
  Widget build(BuildContext context) {
    if (!AppConfig.devMode) return const SizedBox.shrink();
    return Positioned(
      top: 40, right: 8,
      child: Container(
        padding: const EdgeInsets.all(8),
        decoration: BoxDecoration(
          color: Colors.black.withOpacity(0.85),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: Colors.amber.withOpacity(0.6)),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('⚙ DEV', style: TextStyle(color: Colors.amber, fontWeight: FontWeight.bold, fontSize: 11)),
          const SizedBox(height: 4),
          Text('ID: $customerId', style: const TextStyle(color: Colors.white70, fontSize: 10)),
          Text('Dist: ${cameraDistanceCm.round()}cm', style: const TextStyle(color: Colors.white70, fontSize: 10)),
          Text(
            'Profile: ${profileCompleted ? "✓" : "✗"}',
            style: TextStyle(color: profileCompleted ? Colors.greenAccent : Colors.redAccent, fontSize: 10),
          ),
          if (jwtToken != null)
            Text('JWT: ${jwtToken!.length > 8 ? jwtToken!.substring(0, 8) : jwtToken!}…',
                style: const TextStyle(color: Colors.white38, fontSize: 9)),
          const SizedBox(height: 6),
          if (onEditProfile != null)
            _devBtn('Edit Profile', Colors.teal, onEditProfile!),
          if (onForceScan != null)
            _devBtn('Force Scan', Colors.orange, onForceScan!),
        ]),
      ),
    );
  }

  Widget _devBtn(String label, Color color, VoidCallback onTap) => GestureDetector(
    onTap: onTap,
    child: Container(
      margin: const EdgeInsets.only(top: 4),
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(color: color.withOpacity(0.2),
          borderRadius: BorderRadius.circular(4),
          border: Border.all(color: color.withOpacity(0.5))),
      child: Text(label, style: TextStyle(color: color, fontSize: 10, fontWeight: FontWeight.bold)),
    ),
  );
}
