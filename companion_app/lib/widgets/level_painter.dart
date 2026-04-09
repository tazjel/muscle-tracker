import 'package:flutter/material.dart';
import 'dart:ui' as ui;
import '../config.dart';

class BodyGuidePainter extends CustomPainter {
  final int phase;
  final String muscleGroup;
  BodyGuidePainter({required this.phase, this.muscleGroup = 'bicep'});

  static const _guidanceText = {
    'bicep':     'Flex arm, elbow ~90°, raise to shoulder',
    'tricep':    'Extend arm back, elbow straight',
    'quadricep': 'Stand straight, legs together, facing camera',
    'hamstring': 'Stand straight, back to camera',
    'calf':      'Stand straight, heels on ground',
    'glute':     'Stand straight, back to camera',
    'deltoid':   'Arms at sides, slight abduction',
    'lat':       'Arms wide, lat spread pose',
  };

  @override
  void paint(Canvas canvas, Size size) {
    final outline = Paint()..color = Colors.white.withOpacity(0.1)..style = PaintingStyle.stroke..strokeWidth = 1.0;
    final jointPrimary   = Paint()..color = AppTheme.primaryTeal.withOpacity(0.7)..style = PaintingStyle.fill;
    final jointSecondary = Paint()..color = AppTheme.accentGreen.withOpacity(0.6)..style = PaintingStyle.fill;
    final cx = size.width / 2, cy = size.height / 2;

    if (phase == 0) {
      canvas.drawPath(Path()..moveTo(cx - 50, cy - 100)..lineTo(cx - 70, cy - 60)..lineTo(cx - 40, cy + 100)..lineTo(cx + 40, cy + 100)..lineTo(cx + 70, cy - 60)..lineTo(cx + 50, cy - 100)..close(), outline);
      canvas.drawCircle(Offset(cx, cy - 130), 25, outline);
      canvas.drawCircle(Offset(cx - 52, cy - 62), 6, jointPrimary);
      canvas.drawCircle(Offset(cx + 52, cy - 62), 6, jointPrimary);
      canvas.drawCircle(Offset(cx - 68, cy - 10), 5, jointSecondary);
      canvas.drawCircle(Offset(cx + 68, cy - 10), 5, jointSecondary);
      canvas.drawCircle(Offset(cx - 38, cy + 2),  5, jointSecondary);
      canvas.drawCircle(Offset(cx + 38, cy + 2),  5, jointSecondary);
      canvas.drawCircle(Offset(cx - 38, cy + 56), 5, jointSecondary);
      canvas.drawCircle(Offset(cx + 38, cy + 56), 5, jointSecondary);
    } else {
      canvas.drawPath(Path()..moveTo(cx - 15, cy - 100)..lineTo(cx - 25, cy - 60)..lineTo(cx - 20, cy + 100)..lineTo(cx + 20, cy + 100)..lineTo(cx + 35, cy - 60)..lineTo(cx + 15, cy - 100)..close(), outline);
      canvas.drawCircle(Offset(cx + 5, cy - 130), 24, outline);
      canvas.drawCircle(Offset(cx + 20, cy - 62), 6, jointPrimary);
      canvas.drawCircle(Offset(cx + 32, cy - 8),  5, jointSecondary);
      canvas.drawCircle(Offset(cx + 10, cy + 2),  5, jointSecondary);
      canvas.drawCircle(Offset(cx + 12, cy + 56), 5, jointSecondary);
    }

    final guidance = _guidanceText[muscleGroup] ?? '';
    if (guidance.isNotEmpty) {
      final tp = TextPainter(
        text: TextSpan(text: guidance, style: const TextStyle(color: Color(0xFFB2EBF2), fontSize: 11, fontWeight: FontWeight.w500)),
        textDirection: TextDirection.ltr,
      )..layout(maxWidth: size.width - 32);
      tp.paint(canvas, Offset(16, size.height * 0.62));
    }
  }

  @override
  bool shouldRepaint(covariant BodyGuidePainter old) => old.phase != phase || old.muscleGroup != muscleGroup;
}

class LevelPainter extends CustomPainter {
  final double pitch, roll; final Color color; LevelPainter({required this.pitch, required this.roll, required this.color});
  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, 120);
    canvas.drawCircle(center, 35, Paint()..color = Colors.white24..style = PaintingStyle.stroke..strokeWidth = 1.0);
    canvas.drawLine(Offset(center.dx - 35, center.dy), Offset(center.dx + 35, center.dy), Paint()..color = Colors.white10);
    canvas.drawLine(Offset(center.dx, center.dy - 35), Offset(center.dx, center.dy + 35), Paint()..color = Colors.white10);
    final b = Offset(center.dx - roll.clamp(-3.0, 3.0) * 10, center.dy - pitch.clamp(-3.0, 3.0) * 10);
    canvas.drawCircle(b, 10, Paint()..color = color);
    if (color == AppTheme.accentGreen) canvas.drawCircle(b, 18, Paint()..color = color.withOpacity(0.1));
  }
  @override
  bool shouldRepaint(covariant CustomPainter old) => true;
}

class GhostOverlayPainter extends CustomPainter {
  final ui.Image? image; GhostOverlayPainter({this.image});
  @override
  void paint(Canvas canvas, Size size) {
    if (image == null) return;
    double sw = image!.width.toDouble(), sh = image!.height.toDouble(), dw = size.width, dh = size.height;
    double scale = (dw / sw > dh / sh) ? dh / sh : dw / sw;
    double fw = sw * scale, fh = sh * scale, dx = (dw - fw) / 2, dy = (dh - fh) / 2;
    canvas.drawImageRect(image!, Rect.fromLTWH(0, 0, sw, sh), Rect.fromLTWH(dx, dy, fw, fh), Paint()..color = Colors.white.withOpacity(0.2));
  }
  @override
  bool shouldRepaint(covariant GhostOverlayPainter old) => old.image != image;
}

class ContourOverlayPainter extends CustomPainter {
  final List<List<double>> points;
  final Color color;
  const ContourOverlayPainter({required this.points, this.color = const Color(0xFF00E5FF)});

  @override
  void paint(Canvas canvas, Size size) {
    if (points.isEmpty) return;
    final stroke = Paint()..color = color.withOpacity(0.85)..style = PaintingStyle.stroke..strokeWidth = 2.0;
    final fill   = Paint()..color = color.withOpacity(0.07)..style  = PaintingStyle.fill;
    final path = Path()..moveTo(points[0][0], points[0][1]);
    for (int i = 1; i < points.length; i++) { path.lineTo(points[i][0], points[i][1]); }
    path.close();
    canvas.drawPath(path, fill);
    canvas.drawPath(path, stroke);
    final dot = Paint()..color = color..style = PaintingStyle.fill;
    for (final p in points) { canvas.drawCircle(Offset(p[0], p[1]), 3.0, dot); }
  }

  @override
  bool shouldRepaint(covariant ContourOverlayPainter old) => old.points != points || old.color != color;
}
