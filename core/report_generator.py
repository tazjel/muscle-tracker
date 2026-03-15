"""
Clinical report generation in PDF format using reportlab.
Replaces the old PNG-based generator for better accessibility and printing.
"""
import os
import logging
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import cm

logger = logging.getLogger(__name__)

# Colors
ACCENT_TEAL = colors.Color(0, 0.7, 0.8)
ACCENT_GOLD = colors.Color(1, 0.8, 0)
TEXT_DIM = colors.Color(0.4, 0.4, 0.4)
SUCCESS_GREEN = colors.Color(0, 0.8, 0.4)
ERROR_RED = colors.Color(0.9, 0.2, 0.2)


def generate_clinical_report(scan_result, volume_result=None,
                              symmetry_result=None, shape_result=None,
                              trend_result=None, output_path="report.pdf",
                              patient_name="Patient", scan_date=None):
    """
    Generates a professional clinical report in PDF format.
    """
    if output_path.endswith('.png'):
        output_path = output_path.replace('.png', '.pdf')

    scan_date = scan_date or datetime.now().strftime("%Y-%m-%d")
    
    c = canvas.Canvas(output_path, pagesize=A4)
    width, height = A4
    y = height - 2 * cm

    # --- Header ---
    c.setStrokeColor(ACCENT_TEAL)
    c.setLineWidth(3)
    c.line(1 * cm, height - 1 * cm, width - 1 * cm, height - 1 * cm)
    
    c.setFont("Helvetica-Bold", 24)
    c.setFillColor(ACCENT_TEAL)
    c.drawString(1.5 * cm, y, "MUSCLE TRACKER")
    
    c.setFont("Helvetica", 10)
    c.setFillColor(TEXT_DIM)
    c.drawString(1.5 * cm, y - 0.8 * cm, "Clinical Muscle Analysis Report")
    
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.black)
    c.drawRightString(width - 1.5 * cm, y, f"Patient: {patient_name}")
    c.setFont("Helvetica", 10)
    c.drawRightString(width - 1.5 * cm, y - 0.5 * cm, f"Date: {scan_date}")
    
    y -= 2 * cm

    # --- Growth Analysis ---
    if scan_result and scan_result.get("status") == "Success":
        y = _draw_section_header(c, "GROWTH ANALYSIS", y, width)
        metrics = scan_result.get("metrics", {})
        verdict = scan_result.get("verdict", "Stable")
        
        c.setFont("Helvetica-Bold", 12)
        v_color = SUCCESS_GREEN if "Increase" in verdict else ERROR_RED if "Decrease" in verdict else colors.black
        c.setFillColor(v_color)
        c.drawString(2 * cm, y, f"Verdict: {verdict}")
        
        y -= 0.8 * cm
        c.setFont("Helvetica", 10)
        c.setFillColor(colors.black)
        
        col = 0
        for key, val in metrics.items():
            if "delta" in key or "growth" in key:
                label = key.replace("_", " ").title()
                val_str = f"{val:+.2f}" if isinstance(val, (int, float)) else str(val)
                c.drawString(2 * cm + (col % 2) * 8 * cm, y, f"{label}: {val_str}")
                if col % 2 == 1:
                    y -= 0.5 * cm
                col += 1
        if col % 2 != 0:
            y -= 0.5 * cm
        
        # Confidence
        det_conf = scan_result.get("confidence", {}).get("detection", 0)
        _draw_mini_bar(c, width - 6 * cm, y + 0.5 * cm, 4 * cm, 0.3 * cm, det_conf / 100.0, f"Detection: {det_conf}%")
        y -= 1 * cm

    # --- Volumetric Analysis ---
    if volume_result and volume_result.get("volume_cm3", 0) > 0:
        y = _draw_section_header(c, "VOLUMETRIC ANALYSIS", y, width)
        vol = volume_result.get("volume_cm3")
        model = volume_result.get("model", "unknown").replace("_", " ").title()
        
        c.setFont("Helvetica-Bold", 14)
        c.setFillColor(colors.black)
        c.drawString(2 * cm, y, f"Estimated Volume: {vol:.2f} cm³")
        
        y -= 0.6 * cm
        c.setFont("Helvetica", 10)
        c.setFillColor(TEXT_DIM)
        c.drawString(2 * cm, y, f"Model: {model} | Height: {volume_result.get('height_mm', 0):.1f} mm")
        y -= 1.2 * cm

    # --- Shape Analysis ---
    if shape_result and "score" in shape_result:
        y = _draw_section_header(c, "SHAPE QUALITY AUDIT", y, width)
        score = shape_result.get("score", 0)
        grade = shape_result.get("grade", "N/A")
        
        c.setFont("Helvetica-Bold", 20)
        g_color = SUCCESS_GREEN if grade in ("S", "A") else colors.orange if grade == "B" else ERROR_RED
        c.setFillColor(g_color)
        c.drawString(2 * cm, y, grade)
        
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(colors.black)
        c.drawString(3.5 * cm, y + 0.2 * cm, f"Score: {score:.1f}/100")
        
        _draw_mini_bar(c, 7 * cm, y + 0.2 * cm, 6 * cm, 0.5 * cm, score / 100.0)
        y -= 1.2 * cm

    # --- Symmetry ---
    if symmetry_result and symmetry_result.get("status") == "Success":
        y = _draw_section_header(c, "SYMMETRY AUDIT", y, width)
        si = symmetry_result.get("symmetry_indices", {})
        composite = si.get("composite_pct", 0.0)
        risk = symmetry_result.get("risk_level", "unknown")
        
        c.setFont("Helvetica-Bold", 12)
        r_color = SUCCESS_GREEN if risk == "low" else colors.orange if risk == "moderate" else ERROR_RED
        c.setFillColor(r_color)
        c.drawString(2 * cm, y, f"Imbalance Index: {composite:.1f}% ({risk.upper()} RISK)")
        
        y -= 0.6 * cm
        c.setFont("Helvetica", 10)
        c.setFillColor(TEXT_DIM)
        c.drawString(2 * cm, y, symmetry_result.get("verdict", ""))
        y -= 1.2 * cm

    # --- Footer ---
    c.setStrokeColor(colors.lightgrey)
    c.setLineWidth(0.5)
    c.line(1 * cm, 1.5 * cm, width - 1 * cm, 1.5 * cm)
    
    c.setFont("Helvetica", 8)
    c.setFillColor(TEXT_DIM)
    c.drawString(1.5 * cm, 1.1 * cm, "Generated by Muscle Tracker Engine v4.0 | Clinical Grade Metrology")
    c.drawRightString(width - 1.5 * cm, 1.1 * cm, datetime.now().strftime("%Y-%m-%d %H:%M"))

    c.showPage()
    c.save()
    
    logger.info(f"Clinical PDF report saved: {output_path}")
    return output_path


def _draw_section_header(c, title, y, width):
    c.setFillColor(colors.whitesmoke)
    c.rect(1.5 * cm, y - 0.2 * cm, width - 3 * cm, 0.7 * cm, fill=1, stroke=0)
    c.setStrokeColor(ACCENT_TEAL)
    c.setLineWidth(2)
    c.line(1.5 * cm, y - 0.2 * cm, 1.5 * cm, y + 0.5 * cm)
    
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(ACCENT_TEAL)
    c.drawString(1.8 * cm, y, title)
    return y - 1 * cm


def _draw_mini_bar(c, x, y, w, h, value, label=None):
    value = max(0, min(1, value))
    c.setStrokeColor(colors.lightgrey)
    c.setLineWidth(0.5)
    c.rect(x, y, w, h, fill=0)
    
    bar_color = SUCCESS_GREEN if value > 0.7 else colors.orange if value > 0.4 else ERROR_RED
    c.setFillColor(bar_color)
    c.rect(x, y, w * value, h, fill=1, stroke=0)
    
    if label:
        c.setFont("Helvetica", 7)
        c.setFillColor(TEXT_DIM)
        c.drawString(x, y + h + 2, label)
