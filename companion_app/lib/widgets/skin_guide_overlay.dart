import 'package:flutter/material.dart';

class SkinGuideOverlayPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final cx = size.width / 2, cy = size.height / 2;
    final rw = size.width * 0.6, rh = size.height * 0.35;
    final rect = Rect.fromCenter(center: Offset(cx, cy), width: rw, height: rh);
    final paint = Paint()
      ..color = const Color(0x5500BCD4)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.5;
    canvas.drawRRect(RRect.fromRectAndRadius(rect, const Radius.circular(16)), paint);
    final cornerLen = 20.0;
    final cp = Paint()..color = const Color(0xFF00BCD4)..strokeWidth = 3..style = PaintingStyle.stroke;
    canvas.drawLine(Offset(rect.left, rect.top + cornerLen), rect.topLeft, cp);
    canvas.drawLine(rect.topLeft, Offset(rect.left + cornerLen, rect.top), cp);
    canvas.drawLine(Offset(rect.right - cornerLen, rect.top), rect.topRight, cp);
    canvas.drawLine(rect.topRight, Offset(rect.right, rect.top + cornerLen), cp);
    canvas.drawLine(Offset(rect.left, rect.bottom - cornerLen), rect.bottomLeft, cp);
    canvas.drawLine(rect.bottomLeft, Offset(rect.left + cornerLen, rect.bottom), cp);
    canvas.drawLine(Offset(rect.right - cornerLen, rect.bottom), rect.bottomRight, cp);
    canvas.drawLine(rect.bottomRight, Offset(rect.right, rect.bottom - cornerLen), cp);
  }
  @override
  bool shouldRepaint(covariant CustomPainter old) => false;
}
