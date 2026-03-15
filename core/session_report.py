"""
Comprehensive single-session PDF report — the "wow document" that shows
every analysis the engine can do in one professional PDF.
"""
import os
import logging
import tempfile
import numpy as np
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import cm

logger = logging.getLogger(__name__)

ACCENT_TEAL = colors.Color(0, 0.7, 0.8)
ACCENT_GOLD = colors.Color(1, 0.8, 0)
TEXT_DIM = colors.Color(0.4, 0.4, 0.4)
SUCCESS_GREEN = colors.Color(0, 0.78, 0.4)
WARN_ORANGE = colors.Color(1.0, 0.55, 0.0)
ERROR_RED = colors.Color(0.9, 0.2, 0.2)
BG_DARK = colors.Color(0.96, 0.96, 0.96)


def generate_session_report(scan_results, output_path='session_report.pdf'):
    """
    Generate a comprehensive PDF report for a single scan session.

    scan_results keys (all optional except patient_name, scan_date, muscle_group):
        patient_name, scan_date, muscle_group, image_bgr,
        metrics, contour, growth_analysis, volume_cm3,
        circumference_cm, shape_score, shape_grade,
        definition (dict), body_composition (dict),
        symmetry (dict), mesh_preview_path, trend_data
    """
    if output_path.endswith('.png'):
        output_path = output_path.replace('.png', '.pdf')

    c = canvas.Canvas(output_path, pagesize=A4)
    width, height = A4

    y = _draw_cover_header(c, width, height, scan_results)

    # --- Photo & Measurements ---
    image_bgr = scan_results.get('image_bgr')
    if image_bgr is not None:
        y = _draw_image_section(c, image_bgr, scan_results.get('metrics', {}), y, width)

    # --- Growth Analysis ---
    growth = scan_results.get('growth_analysis')
    if growth:
        y = _check_page(c, y, height, width)
        y = _draw_section_header(c, 'GROWTH ANALYSIS', y, width)
        growth_pct = growth.get('growth_pct', 0)
        delta = growth.get('area_change_mm2', 0)
        color = SUCCESS_GREEN if growth_pct > 0 else ERROR_RED if growth_pct < 0 else colors.black
        c.setFont('Helvetica-Bold', 12)
        c.setFillColor(color)
        c.drawString(2 * cm, y, f"Growth: {growth_pct:+.1f}%  |  Area change: {delta:+.0f} mm²")
        y -= 1.2 * cm

    # --- Volume ---
    volume = scan_results.get('volume_cm3')
    if volume:
        y = _check_page(c, y, height, width)
        y = _draw_section_header(c, 'VOLUMETRIC ANALYSIS', y, width)
        c.setFont('Helvetica-Bold', 14)
        c.setFillColor(colors.black)
        c.drawString(2 * cm, y, f"Estimated Volume: {volume:.2f} cm³")
        y -= 1.2 * cm

    # --- Circumference ---
    circ = scan_results.get('circumference_cm')
    if circ:
        y = _check_page(c, y, height, width)
        y = _draw_section_header(c, 'CIRCUMFERENCE', y, width)
        inches = circ / 2.54
        c.setFont('Helvetica-Bold', 13)
        c.setFillColor(colors.black)
        c.drawString(2 * cm, y, f"{circ:.1f} cm  /  {inches:.1f} in")
        y -= 1.2 * cm

    # --- Shape Score ---
    shape_score = scan_results.get('shape_score')
    shape_grade = scan_results.get('shape_grade', 'N/A')
    if shape_score is not None:
        y = _check_page(c, y, height, width)
        y = _draw_section_header(c, 'SHAPE QUALITY', y, width)
        g_color = SUCCESS_GREEN if shape_grade in ('S', 'A') else WARN_ORANGE if shape_grade == 'B' else ERROR_RED
        c.setFont('Helvetica-Bold', 20)
        c.setFillColor(g_color)
        c.drawString(2 * cm, y, shape_grade)
        c.setFont('Helvetica-Bold', 12)
        c.setFillColor(colors.black)
        c.drawString(3.5 * cm, y + 0.2 * cm, f"Score: {shape_score:.1f}/100")
        _draw_bar(c, 7 * cm, y + 0.2 * cm, 6 * cm, 0.4 * cm, shape_score / 100.0)
        y -= 1.4 * cm

    # --- Definition ---
    definition = scan_results.get('definition')
    if definition:
        y = _check_page(c, y, height, width)
        y = _draw_section_header(c, 'MUSCLE DEFINITION', y, width)
        grade = definition.get('grade', 'N/A')
        score = definition.get('overall_definition', 0)
        c.setFont('Helvetica-Bold', 12)
        c.setFillColor(SUCCESS_GREEN if score >= 65 else WARN_ORANGE if score >= 40 else ERROR_RED)
        c.drawString(2 * cm, y, f"{grade}  ({score:.0f}/100)")
        _draw_bar(c, 7 * cm, y, 5 * cm, 0.4 * cm, score / 100.0)
        y -= 1.2 * cm

    # --- Body Composition ---
    body_comp = scan_results.get('body_composition')
    if body_comp:
        y = _check_page(c, y, height, width)
        y = _draw_section_header(c, 'BODY COMPOSITION', y, width)
        items = [
            ('BMI', body_comp.get('bmi')),
            ('Body Fat', f"{body_comp.get('estimated_body_fat_pct', 'N/A')}%"),
            ('Classification', body_comp.get('classification', 'N/A')),
            ('W/H Ratio', body_comp.get('waist_to_hip_ratio')),
        ]
        col = 0
        for label, val in items:
            if val is not None:
                c.setFont('Helvetica', 10)
                c.setFillColor(colors.black)
                c.drawString(2 * cm + (col % 2) * 8 * cm, y, f"{label}: {val}")
                if col % 2 == 1:
                    y -= 0.5 * cm
                col += 1
        if col % 2 != 0:
            y -= 0.5 * cm
        y -= 0.7 * cm

    # --- Symmetry ---
    symmetry = scan_results.get('symmetry')
    if symmetry:
        y = _check_page(c, y, height, width)
        y = _draw_section_header(c, 'SYMMETRY AUDIT', y, width)
        imbalance = symmetry.get('composite_imbalance_pct', 0)
        verdict = symmetry.get('verdict', 'N/A')
        s_color = SUCCESS_GREEN if imbalance < 5 else WARN_ORANGE if imbalance < 10 else ERROR_RED
        c.setFont('Helvetica-Bold', 11)
        c.setFillColor(s_color)
        c.drawString(2 * cm, y, f"Imbalance: {imbalance:.1f}%  —  {verdict}")
        y -= 1.2 * cm

    # --- Footer ---
    _draw_footer(c, width)

    c.showPage()
    c.save()
    logger.info("Session report saved: %s", output_path)
    return output_path


# ── Helpers ─────────────────────────────────────────────────────────────────

def _draw_cover_header(c, width, height, scan_results):
    y = height - 1.5 * cm
    c.setStrokeColor(ACCENT_TEAL)
    c.setLineWidth(3)
    c.line(1 * cm, height - 0.8 * cm, width - 1 * cm, height - 0.8 * cm)

    c.setFont('Helvetica-Bold', 22)
    c.setFillColor(ACCENT_TEAL)
    c.drawString(1.5 * cm, y, 'MUSCLE TRACKER')

    c.setFont('Helvetica', 10)
    c.setFillColor(TEXT_DIM)
    c.drawString(1.5 * cm, y - 0.7 * cm, 'Personal Vision Session Report')

    patient = scan_results.get('patient_name', 'Patient')
    date = scan_results.get('scan_date', datetime.now().strftime('%Y-%m-%d'))
    muscle = scan_results.get('muscle_group', 'N/A').title()

    c.setFont('Helvetica-Bold', 10)
    c.setFillColor(colors.black)
    c.drawRightString(width - 1.5 * cm, y, f"Patient: {patient}")
    c.setFont('Helvetica', 10)
    c.drawRightString(width - 1.5 * cm, y - 0.5 * cm, f"Date: {date}  |  Muscle: {muscle}")

    return y - 2.2 * cm


def _draw_image_section(c, image_bgr, metrics, y, width):
    """Embed the scan image as a JPEG in the PDF."""
    try:
        import cv2
        from reportlab.lib.utils import ImageReader
        import io
        _, buf = cv2.imencode('.jpg', image_bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
        img_io = io.BytesIO(buf.tobytes())
        img_reader = ImageReader(img_io)

        img_w = 7 * cm
        img_h = 8 * cm
        c.drawImage(img_reader, 1.5 * cm, y - img_h, width=img_w, height=img_h,
                    preserveAspectRatio=True)

        # Metrics beside image
        mx = 10 * cm
        my = y - 0.5 * cm
        c.setFont('Helvetica-Bold', 10)
        c.setFillColor(ACCENT_TEAL)
        c.drawString(mx, my, 'MEASUREMENTS')
        my -= 0.6 * cm
        c.setFont('Helvetica', 10)
        c.setFillColor(colors.black)
        for k, v in metrics.items():
            label = k.replace('_', ' ').title()
            val_str = f"{v:.1f}" if isinstance(v, float) else str(v)
            c.drawString(mx, my, f"{label}: {val_str}")
            my -= 0.5 * cm
            if my < y - img_h:
                break

        return y - img_h - 0.8 * cm
    except Exception:
        logger.debug("Image embed failed, skipping", exc_info=True)
        return y


def _draw_section_header(c, title, y, width):
    c.setFillColor(BG_DARK)
    c.rect(1.5 * cm, y - 0.15 * cm, width - 3 * cm, 0.65 * cm, fill=1, stroke=0)
    c.setStrokeColor(ACCENT_TEAL)
    c.setLineWidth(2)
    c.line(1.5 * cm, y - 0.15 * cm, 1.5 * cm, y + 0.5 * cm)
    c.setFont('Helvetica-Bold', 10)
    c.setFillColor(ACCENT_TEAL)
    c.drawString(1.9 * cm, y, title)
    return y - 0.9 * cm


def _draw_bar(c, x, y, w, h, value):
    value = max(0.0, min(1.0, value))
    c.setStrokeColor(colors.lightgrey)
    c.setLineWidth(0.5)
    c.rect(x, y, w, h, fill=0)
    bar_color = SUCCESS_GREEN if value > 0.7 else WARN_ORANGE if value > 0.4 else ERROR_RED
    c.setFillColor(bar_color)
    c.rect(x, y, w * value, h, fill=1, stroke=0)


def _draw_footer(c, width):
    c.setStrokeColor(colors.lightgrey)
    c.setLineWidth(0.5)
    c.line(1 * cm, 1.5 * cm, width - 1 * cm, 1.5 * cm)
    c.setFont('Helvetica', 8)
    c.setFillColor(TEXT_DIM)
    c.drawString(1.5 * cm, 1.1 * cm,
                 'Generated by Muscle Tracker Engine v5.0 | Personal Vision Edition')
    c.drawRightString(width - 1.5 * cm, 1.1 * cm,
                      datetime.now().strftime('%Y-%m-%d %H:%M'))


def _check_page(c, y, height, width):
    """Start a new page if not enough space remaining."""
    if y < 5 * cm:
        _draw_footer(c, width)
        c.showPage()
        return height - 2 * cm
    return y
