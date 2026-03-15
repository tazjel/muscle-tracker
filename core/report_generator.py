import cv2
import numpy as np
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Report layout constants
REPORT_WIDTH = 1200
MARGIN = 30
HEADER_H = 120
SECTION_GAP = 20
FONT = cv2.FONT_HERSHEY_SIMPLEX
FONT_SMALL = cv2.FONT_HERSHEY_PLAIN

# Colors (BGR)
BG_DARK = (25, 25, 30)
BG_SECTION = (40, 40, 45)
ACCENT_TEAL = (200, 180, 0)
ACCENT_GOLD = (50, 200, 255)
TEXT_WHITE = (240, 240, 240)
TEXT_DIM = (160, 160, 160)
GREEN = (0, 200, 100)
RED = (80, 80, 220)


def generate_clinical_report(scan_result, volume_result=None,
                              symmetry_result=None, shape_result=None,
                              trend_result=None, output_path="report.png",
                              patient_name="Patient", scan_date=None):
    """
    Generates a comprehensive clinical report image.

    Combines all analysis results into a single professional-grade
    report suitable for clinics and athlete consultations.
    """
    scan_date = scan_date or datetime.now().strftime("%Y-%m-%d")
    sections = []

    # Header
    sections.append(_render_header(patient_name, scan_date))

    # Growth analysis section
    if scan_result and scan_result.get("status") == "Success":
        sections.append(_render_growth_section(scan_result))

    # Volume section
    if volume_result and volume_result.get("volume_cm3", 0) > 0:
        sections.append(_render_volume_section(volume_result))

    # Shape score section
    if shape_result and "score" in shape_result:
        sections.append(_render_shape_section(shape_result))

    # Symmetry section
    if symmetry_result and symmetry_result.get("status") == "Success":
        sections.append(_render_symmetry_section(symmetry_result))

    # Trend section
    if trend_result and trend_result.get("status") == "Success":
        sections.append(_render_trend_section(trend_result))

    # Footer
    sections.append(_render_footer())

    # Stack all sections vertically
    total_h = sum(s.shape[0] for s in sections)
    report = np.full((total_h, REPORT_WIDTH, 3), BG_DARK, dtype=np.uint8)

    y = 0
    for section in sections:
        h = section.shape[0]
        report[y:y + h, :] = section
        y += h

    cv2.imwrite(output_path, report)
    logger.info("Clinical report saved: %s (%dx%d)", output_path, REPORT_WIDTH, total_h)
    return output_path


def _render_header(patient_name, scan_date):
    """Render the report header with branding."""
    header = np.full((HEADER_H, REPORT_WIDTH, 3), BG_DARK, dtype=np.uint8)

    # Title bar
    cv2.rectangle(header, (0, 0), (REPORT_WIDTH, 4), ACCENT_TEAL, -1)

    cv2.putText(header, "MUSCLE TRACKER", (MARGIN, 45),
                FONT, 1.2, ACCENT_TEAL, 2)
    cv2.putText(header, "Clinical Muscle Analysis Report",
                (MARGIN, 75), FONT, 0.6, TEXT_DIM, 1)

    # Patient info (right side)
    cv2.putText(header, f"Patient: {patient_name}",
                (REPORT_WIDTH - 350, 45), FONT, 0.6, TEXT_WHITE, 1)
    cv2.putText(header, f"Date: {scan_date}",
                (REPORT_WIDTH - 350, 75), FONT, 0.6, TEXT_DIM, 1)

    # Separator
    cv2.line(header, (MARGIN, HEADER_H - 5),
             (REPORT_WIDTH - MARGIN, HEADER_H - 5), (60, 60, 65), 1)

    return header


def _render_growth_section(result):
    """Render the muscle growth analysis section."""
    section_h = 160
    section = np.full((section_h, REPORT_WIDTH, 3), BG_DARK, dtype=np.uint8)

    _section_title(section, "GROWTH ANALYSIS", 0)

    metrics = result.get("metrics", {})
    verdict = result.get("verdict", "N/A")
    confidence = result.get("confidence", {})

    y = 55
    col1 = MARGIN + 20
    col2 = 400
    col3 = 750

    # Verdict with color
    verdict_color = GREEN if "Increase" in verdict else RED if "Decrease" in verdict else TEXT_DIM
    cv2.putText(section, f"Verdict: {verdict}", (col1, y), FONT, 0.7, verdict_color, 2)

    # Key metrics
    y += 35
    for key, val in metrics.items():
        if "delta" in key or "growth" in key:
            label = key.replace("_", " ").title()
            val_str = f"{val:+.2f}" if isinstance(val, float) else str(val)
            color = GREEN if isinstance(val, (int, float)) and val > 0 else RED if isinstance(val, (int, float)) and val < 0 else TEXT_WHITE
            cv2.putText(section, f"{label}: {val_str}", (col1, y), FONT, 0.5, color, 1)
            col1 = col2 if col1 < col2 else col3
            if col1 > col3:
                col1 = MARGIN + 20
                y += 28

    # Confidence bar
    y = section_h - 25
    det_conf = confidence.get("detection", 0)
    _draw_progress_bar(section, REPORT_WIDTH - 300, y - 10, 250, 15,
                       det_conf / 100.0, f"Detection: {det_conf:.0f}%")

    return section


def _render_volume_section(result):
    """Render the volumetric analysis section."""
    section_h = 130
    section = np.full((section_h, REPORT_WIDTH, 3), BG_DARK, dtype=np.uint8)

    _section_title(section, "VOLUMETRIC ANALYSIS", 0)

    vol = result.get("volume_cm3", 0.0)
    model = result.get("model", "unknown")

    y = 55
    cv2.putText(section, f"Estimated Volume: {vol:.2f} cm3",
                (MARGIN + 20, y), FONT, 0.8, ACCENT_GOLD, 2)

    y += 35
    details = [
        f"Model: {model.replace('_', ' ').title()}",
        f"Height: {result.get('height_mm', 0):.1f} mm",
        f"Semi-axes: {result.get('semi_axis_a_mm', 0):.1f} x {result.get('semi_axis_b_mm', 0):.1f} mm",
    ]
    x = MARGIN + 20
    for detail in details:
        cv2.putText(section, detail, (x, y), FONT, 0.45, TEXT_DIM, 1)
        x += 320

    return section


def _render_shape_section(result):
    """Render the shape scoring section."""
    section_h = 120
    section = np.full((section_h, REPORT_WIDTH, 3), BG_DARK, dtype=np.uint8)

    _section_title(section, "SHAPE ANALYSIS", 0)

    score = result.get("score", 0.0)
    grade = result.get("grade", "N/A")
    template = result.get("template", "N/A")

    y = 55
    # Grade badge
    grade_color = GREEN if grade in ("S", "A") else ACCENT_GOLD if grade == "B" else RED
    cv2.putText(section, grade, (MARGIN + 20, y + 10), FONT, 1.5, grade_color, 3)
    cv2.putText(section, f"Score: {score:.1f}/100", (MARGIN + 80, y),
                FONT, 0.7, TEXT_WHITE, 1)
    cv2.putText(section, f"Template: {template.replace('_', ' ').title()}",
                (MARGIN + 80, y + 30), FONT, 0.5, TEXT_DIM, 1)

    # Score bar
    _draw_progress_bar(section, 500, y - 5, 350, 20, score / 100.0)

    # Recommendations
    recs = result.get("recommendations", {})
    if recs.get("assessment"):
        cv2.putText(section, recs["assessment"], (MARGIN + 20, section_h - 15),
                    FONT, 0.45, TEXT_DIM, 1)

    return section


def _render_symmetry_section(result):
    """Render the symmetry analysis section."""
    section_h = 120
    section = np.full((section_h, REPORT_WIDTH, 3), BG_DARK, dtype=np.uint8)

    _section_title(section, "SYMMETRY AUDIT", 0)

    si = result.get("symmetry_indices", {})
    composite = si.get("composite_pct", 0.0)
    dominant = result.get("dominant_side", "Equal")
    risk = result.get("risk_level", "unknown")

    y = 55
    risk_color = GREEN if risk == "low" else ACCENT_GOLD if risk == "moderate" else RED
    cv2.putText(section, f"Imbalance: {composite:.1f}%", (MARGIN + 20, y),
                FONT, 0.7, risk_color, 2)
    cv2.putText(section, f"Dominant: {dominant}  |  Risk: {risk.upper()}",
                (MARGIN + 300, y), FONT, 0.5, TEXT_DIM, 1)

    # Symmetry bar (centered at 50% = perfect)
    bar_val = max(0, min(1, 1 - composite / 50.0))
    _draw_progress_bar(section, 500, y + 20, 350, 15, bar_val, "Symmetry")

    cv2.putText(section, result.get("verdict", ""),
                (MARGIN + 20, section_h - 15), FONT, 0.4, TEXT_DIM, 1)

    return section


def _render_trend_section(result):
    """Render the progress trend section with mini chart."""
    section_h = 180
    section = np.full((section_h, REPORT_WIDTH, 3), BG_DARK, dtype=np.uint8)

    _section_title(section, "PROGRESS TREND", 0)

    trend = result.get("trend", {})
    vol_summary = result.get("volume_summary", {})

    y = 55
    direction = trend.get("direction", "N/A")
    dir_color = GREEN if direction == "gaining" else RED if direction == "losing" else TEXT_DIM
    cv2.putText(section, f"Trend: {direction.upper()}", (MARGIN + 20, y),
                FONT, 0.7, dir_color, 2)

    y += 30
    stats = [
        f"Weekly rate: {trend.get('weekly_rate_cm3', 0):+.3f} cm3/wk",
        f"Consistency (R2): {trend.get('consistency_r2', 0):.2f}",
        f"30-day projection: {trend.get('projected_30d_cm3', 0):.2f} cm3",
    ]
    x = MARGIN + 20
    for s in stats:
        cv2.putText(section, s, (x, y), FONT, 0.45, TEXT_DIM, 1)
        x += 380

    # Mini sparkline chart
    periods = result.get("periods", [])
    if periods:
        chart_x = MARGIN + 20
        chart_y = y + 25
        chart_w = REPORT_WIDTH - 2 * MARGIN - 40
        chart_h = 60

        cv2.rectangle(section, (chart_x, chart_y),
                      (chart_x + chart_w, chart_y + chart_h), (50, 50, 55), 1)

        changes = [p["volume_change_cm3"] for p in periods]
        if changes:
            max_abs = max(abs(c) for c in changes) or 1
            n = len(changes)
            bar_w = max(4, chart_w // (n * 2))
            for i, c in enumerate(changes):
                bx = chart_x + int(chart_w * i / n) + bar_w
                mid_y = chart_y + chart_h // 2
                bar_h = int((c / max_abs) * (chart_h // 2 - 5))
                color = GREEN if c >= 0 else RED
                cv2.rectangle(section, (bx, mid_y - bar_h),
                              (bx + bar_w, mid_y), color, -1)
            # Zero line
            cv2.line(section, (chart_x, chart_y + chart_h // 2),
                     (chart_x + chart_w, chart_y + chart_h // 2), TEXT_DIM, 1)

    return section


def _render_footer():
    """Render the report footer."""
    footer_h = 50
    footer = np.full((footer_h, REPORT_WIDTH, 3), BG_DARK, dtype=np.uint8)
    cv2.line(footer, (MARGIN, 5), (REPORT_WIDTH - MARGIN, 5), (60, 60, 65), 1)
    cv2.putText(footer, "Generated by Muscle Tracker v2.3 | Clinical Metrology Engine",
                (MARGIN, 30), FONT, 0.4, TEXT_DIM, 1)
    cv2.putText(footer, datetime.now().strftime("%Y-%m-%d %H:%M"),
                (REPORT_WIDTH - 200, 30), FONT, 0.4, TEXT_DIM, 1)
    return footer


def _section_title(img, title, y_offset):
    """Draw a section title bar."""
    y = y_offset + 5
    cv2.rectangle(img, (MARGIN, y), (REPORT_WIDTH - MARGIN, y + 30), BG_SECTION, -1)
    cv2.line(img, (MARGIN, y), (MARGIN + 4, y + 30), ACCENT_TEAL, 3)
    cv2.putText(img, title, (MARGIN + 15, y + 22), FONT, 0.55, ACCENT_TEAL, 1)


def _draw_progress_bar(img, x, y, w, h, value, label=None):
    """Draw a progress bar with optional label."""
    value = max(0.0, min(1.0, value))
    # Background
    cv2.rectangle(img, (x, y), (x + w, y + h), (60, 60, 65), -1)
    # Fill
    fill_w = int(w * value)
    if value > 0.7:
        color = GREEN
    elif value > 0.4:
        color = ACCENT_GOLD
    else:
        color = RED
    cv2.rectangle(img, (x, y), (x + fill_w, y + h), color, -1)
    # Border
    cv2.rectangle(img, (x, y), (x + w, y + h), (80, 80, 85), 1)
    if label:
        cv2.putText(img, label, (x, y - 5), FONT_SMALL, 1.0, TEXT_DIM, 1)
