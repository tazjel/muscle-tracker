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
                              patient_name="Patient", scan_date=None,
                              # v5 extras (all optional)
                              circumference_cm=None,
                              definition_result=None,
                              body_composition=None,
                              annotated_image_bgr=None,
                              mesh_preview_path=None):
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

    # --- Annotated Photo ---
    if annotated_image_bgr is not None:
        y = _check_page(c, y, height, width)
        y = _draw_section_header(c, "ANNOTATED SCAN IMAGE", y, width)
        try:
            import cv2
            import io
            from reportlab.lib.utils import ImageReader
            _, buf = cv2.imencode('.jpg', annotated_image_bgr,
                                  [cv2.IMWRITE_JPEG_QUALITY, 85])
            img_io  = io.BytesIO(buf.tobytes())
            img_rdr = ImageReader(img_io)
            img_w, img_h = 7 * cm, 8 * cm
            c.drawImage(img_rdr, 1.5 * cm, y - img_h,
                        width=img_w, height=img_h, preserveAspectRatio=True)
            y -= img_h + 0.5 * cm
        except Exception:
            logger.debug("Annotated image embed failed", exc_info=True)

    # --- Circumference ---
    if circumference_cm is not None:
        y = _check_page(c, y, height, width)
        y = _draw_section_header(c, "CIRCUMFERENCE ESTIMATE", y, width)
        inches = circumference_cm / 2.54
        c.setFont("Helvetica-Bold", 14)
        c.setFillColor(colors.black)
        c.drawString(2 * cm, y, f"{circumference_cm:.1f} cm  /  {inches:.1f} in")
        y -= 1.2 * cm

    # --- Definition Score ---
    if definition_result:
        y = _check_page(c, y, height, width)
        y = _draw_section_header(c, "MUSCLE DEFINITION", y, width)
        score = definition_result.get('overall_definition', 0) or 0
        grade = definition_result.get('grade', 'N/A')
        d_color = SUCCESS_GREEN if score >= 65 else colors.orange if score >= 40 else ERROR_RED
        c.setFont("Helvetica-Bold", 20)
        c.setFillColor(d_color)
        c.drawString(2 * cm, y, grade)
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(colors.black)
        c.drawString(3.5 * cm, y + 0.2 * cm, f"Score: {score:.0f}/100")
        _draw_mini_bar(c, 7 * cm, y + 0.2 * cm, 6 * cm, 0.45 * cm, score / 100.0)
        y -= 1.4 * cm

    # --- Body Composition ---
    if body_composition:
        y = _check_page(c, y, height, width)
        y = _draw_section_header(c, "BODY COMPOSITION", y, width)
        items = [
            ('BMI',            body_composition.get('bmi')),
            ('Body Fat %',     body_composition.get('estimated_body_fat_pct')),
            ('Lean Mass',      f"{body_composition.get('lean_mass_kg', '–')} kg"
                               if body_composition.get('lean_mass_kg') else None),
            ('Classification', body_composition.get('classification')),
            ('W/H Ratio',      body_composition.get('waist_to_hip_ratio')),
            ('Confidence',     body_composition.get('confidence')),
        ]
        col = 0
        for label, val in items:
            if val is None:
                continue
            val_str = f"{val:.1f}" if isinstance(val, float) else str(val)
            if label == 'Body Fat %' and isinstance(val, float):
                val_str = f"{val:.1f}%"
            c.setFont("Helvetica", 10)
            c.setFillColor(colors.black)
            c.drawString(2 * cm + (col % 2) * 8 * cm, y, f"{label}: {val_str}")
            if col % 2 == 1:
                y -= 0.5 * cm
            col += 1
        if col % 2 != 0:
            y -= 0.5 * cm
        y -= 0.7 * cm

    # --- 3D Mesh Preview ---
    if mesh_preview_path and os.path.exists(mesh_preview_path):
        y = _check_page(c, y, height, width)
        y = _draw_section_header(c, "3D MESH PREVIEW", y, width)
        try:
            from reportlab.lib.utils import ImageReader
            img_w, img_h = 8 * cm, 7 * cm
            c.drawImage(ImageReader(mesh_preview_path),
                        width / 2 - img_w / 2, y - img_h,
                        width=img_w, height=img_h, preserveAspectRatio=True)
            y -= img_h + 0.5 * cm
        except Exception:
            logger.debug("Mesh preview embed failed", exc_info=True)

    # --- Footer ---
    c.setStrokeColor(colors.lightgrey)
    c.setLineWidth(0.5)
    c.line(1 * cm, 1.5 * cm, width - 1 * cm, 1.5 * cm)

    c.setFont("Helvetica", 8)
    c.setFillColor(TEXT_DIM)
    c.drawString(1.5 * cm, 1.1 * cm, "Generated by Muscle Tracker Engine v5.0 | Clinical Grade Metrology")
    c.drawRightString(width - 1.5 * cm, 1.1 * cm, datetime.now().strftime("%Y-%m-%d %H:%M"))

    c.showPage()
    c.save()
    
    logger.info(f"Clinical PDF report saved: {output_path}")
    return output_path


def _check_page(c, y, height, width):
    """Start a new page if less than 5 cm remaining."""
    if y < 5 * cm:
        _draw_footer_line(c, width)
        c.showPage()
        return height - 2 * cm
    return y


def _draw_footer_line(c, width):
    c.setStrokeColor(colors.lightgrey)
    c.setLineWidth(0.5)
    c.line(1 * cm, 1.5 * cm, width - 1 * cm, 1.5 * cm)


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
