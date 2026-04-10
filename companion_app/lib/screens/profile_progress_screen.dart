import 'package:flutter/material.dart';
import '../config.dart';
import 'history_screen.dart';

class ProfileProgressScreen extends StatelessWidget {
  final Map<String, dynamic> result;
  final String muscleGroup;
  final VoidCallback onCaptureMore;
  const ProfileProgressScreen({super.key, required this.result, required this.muscleGroup, required this.onCaptureMore});

  @override
  Widget build(BuildContext context) {
    final pct = (result['progress_pct'] as num?)?.toInt() ?? 0;
    final isComplete = result['is_complete'] == true;
    final instructions = result['instructions'] as String? ?? '';
    final detail = result['detail'] as String? ?? '';
    final covered = List<String>.from(result['covered_zones'] ?? []);
    final missingReq = List<String>.from(result['missing_required'] ?? []);
    final stats = result['frame_stats'] as Map<String, dynamic>? ?? {};
    const allRequired = ['front', 'right', 'back', 'left'];
    return Scaffold(
      backgroundColor: AppTheme.darkBg,
      appBar: AppBar(title: const Text('Profile Builder'), backgroundColor: AppTheme.darkBg),
      body: SafeArea(child: SingleChildScrollView(padding: const EdgeInsets.all(24), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        // Progress arc
        Center(child: Stack(alignment: Alignment.center, children: [
          SizedBox(width: 140, height: 140, child: CircularProgressIndicator(
            value: pct / 100.0,
            strokeWidth: 12,
            backgroundColor: Colors.white12,
            valueColor: AlwaysStoppedAnimation<Color>(isComplete ? AppTheme.accentGreen : AppTheme.primaryTeal),
          )),
          Column(mainAxisSize: MainAxisSize.min, children: [
            Text('$pct%', style: TextStyle(fontSize: 32, fontWeight: FontWeight.bold, color: isComplete ? AppTheme.accentGreen : Colors.white)),
            Text(isComplete ? 'COMPLETE' : 'BUILDING', style: TextStyle(fontSize: 11, letterSpacing: 2, color: isComplete ? AppTheme.accentGreen : Colors.white54)),
          ]),
        ])),
        const SizedBox(height: 28),
        // Zone checklist
        Container(padding: const EdgeInsets.all(16), decoration: BoxDecoration(color: AppTheme.cardBg, borderRadius: BorderRadius.circular(12)), child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('COVERAGE', style: TextStyle(color: Colors.white54, fontSize: 11, letterSpacing: 2, fontWeight: FontWeight.bold)),
            const SizedBox(height: 12),
            ...allRequired.map((z) {
              final done = covered.contains(z);
              return Padding(padding: const EdgeInsets.symmetric(vertical: 4), child: Row(children: [
                Icon(done ? Icons.check_circle : Icons.radio_button_unchecked, size: 20, color: done ? AppTheme.accentGreen : Colors.white30),
                const SizedBox(width: 10),
                Text(z.toUpperCase(), style: TextStyle(color: done ? Colors.white : Colors.white54, fontWeight: done ? FontWeight.bold : FontWeight.normal)),
                if (!done && missingReq.first == z) ...[
                  const Spacer(),
                  Container(padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2), decoration: BoxDecoration(color: AppTheme.primaryTeal.withOpacity(0.2), borderRadius: BorderRadius.circular(10)), child: const Text('NEXT', style: TextStyle(color: AppTheme.primaryTeal, fontSize: 10, fontWeight: FontWeight.bold))),
                ],
              ]));
            }),
          ],
        )),
        const SizedBox(height: 16),
        // Frame stats
        Row(children: [
          _statChip('${stats['total'] ?? 0}', 'Captured'),
          const SizedBox(width: 8),
          _statChip('${stats['usable'] ?? 0}', 'Usable'),
          const SizedBox(width: 8),
          _statChip('${stats['mapped'] ?? 0}', 'Mapped'),
        ]),
        const SizedBox(height: 24),
        // Instructions
        if (!isComplete) ...[
          Container(width: double.infinity, padding: const EdgeInsets.all(16), decoration: BoxDecoration(color: AppTheme.primaryTeal.withOpacity(0.1), borderRadius: BorderRadius.circular(12), border: Border.all(color: AppTheme.primaryTeal.withOpacity(0.3))), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Text('NEXT STEP', style: TextStyle(color: AppTheme.primaryTeal, fontSize: 11, letterSpacing: 2, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            Text(instructions, style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600)),
            if (detail.isNotEmpty) ...[const SizedBox(height: 4), Text(detail, style: const TextStyle(color: Colors.white60, fontSize: 13))],
            const SizedBox(height: 4),
            const Text('Stand 1 meter away from the phone', style: TextStyle(color: Colors.white38, fontSize: 12)),
          ])),
          const SizedBox(height: 20),
          SizedBox(width: double.infinity, child: FilledButton.icon(
            onPressed: onCaptureMore,
            icon: const Icon(Icons.person_search),
            label: const Text('CAPTURE MORE — AUTO 2'),
            style: FilledButton.styleFrom(backgroundColor: AppTheme.primaryTeal, foregroundColor: Colors.black, padding: const EdgeInsets.symmetric(vertical: 16)),
          )),
        ] else ...[
          Container(width: double.infinity, padding: const EdgeInsets.all(20), decoration: BoxDecoration(color: AppTheme.accentGreen.withOpacity(0.1), borderRadius: BorderRadius.circular(12), border: Border.all(color: AppTheme.accentGreen.withOpacity(0.4))), child: Column(children: [
            const Icon(Icons.check_circle, color: AppTheme.accentGreen, size: 48),
            const SizedBox(height: 12),
            const Text('PROFILE COMPLETE', style: TextStyle(color: AppTheme.accentGreen, fontSize: 20, fontWeight: FontWeight.bold, letterSpacing: 2)),
            const SizedBox(height: 4),
            Text('${muscleGroup.toUpperCase()} profile built successfully', style: const TextStyle(color: Colors.white60, fontSize: 13)),
          ])),
          const SizedBox(height: 20),
          SizedBox(width: double.infinity, child: FilledButton.icon(
            onPressed: () => Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => HistoryScreen(muscleGroup: muscleGroup))),
            icon: const Icon(Icons.dashboard),
            label: const Text('VIEW DASHBOARD'),
            style: FilledButton.styleFrom(backgroundColor: AppTheme.accentGreen, foregroundColor: Colors.black, padding: const EdgeInsets.symmetric(vertical: 16)),
          )),
          const SizedBox(height: 12),
          SizedBox(width: double.infinity, child: OutlinedButton.icon(
            onPressed: onCaptureMore,
            icon: const Icon(Icons.add_a_photo, color: AppTheme.primaryTeal),
            label: const Text('ADD MORE ANGLES', style: TextStyle(color: AppTheme.primaryTeal)),
            style: OutlinedButton.styleFrom(side: const BorderSide(color: AppTheme.primaryTeal), padding: const EdgeInsets.symmetric(vertical: 14)),
          )),
        ],
      ]))),
    );
  }

  Widget _statChip(String value, String label) {
    return Expanded(child: Container(padding: const EdgeInsets.symmetric(vertical: 10), decoration: BoxDecoration(color: AppTheme.cardBg, borderRadius: BorderRadius.circular(8)), child: Column(children: [
      Text(value, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 18)),
      Text(label, style: const TextStyle(color: Colors.white38, fontSize: 11)),
    ])));
  }
}
