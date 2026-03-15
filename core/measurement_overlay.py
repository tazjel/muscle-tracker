import cv2
import numpy as np
import math


def _draw_arrow_line(img, pt1, pt2, color, thickness=2, arrow_len=10, arrow_width=6):
    """Draw a line with filled triangular arrowheads at both ends."""
    cv2.line(img, pt1, pt2, color, thickness)
    for tip, base in [(pt1, pt2), (pt2, pt1)]:
        dx = base[0] - tip[0]
        dy = base[1] - tip[1]
        dist = math.hypot(dx, dy)
        if dist == 0:
            continue
        ux, uy = dx / dist, dy / dist
        bx = tip[0] + int(ux * arrow_len)
        by = tip[1] + int(uy * arrow_len)
        px = int(-uy * arrow_width / 2)
        py = int(ux * arrow_width / 2)
        pts = np.array([[tip[0], tip[1]], [bx + px, by + py], [bx - px, by - py]], np.int32)
        cv2.fillPoly(img, [pts], color)


def draw_measurement_overlay(image_bgr, contour, metrics, calibrated=True):
    if image_bgr is None or contour is None:
        return image_bgr
    annotated = image_bgr.copy()
    unit = 'mm' if calibrated else 'px'
    cv2.drawContours(annotated, [contour], -1, (200, 180, 0), 2)
    x, y, w, h = cv2.boundingRect(contour)
    gap = 10
    for i in range(x, x+w, gap*2):
        cv2.line(annotated, (i, y), (min(i+gap, x+w), y), (255, 255, 255), 1)
        cv2.line(annotated, (i, y+h), (min(i+gap, x+w), y+h), (255, 255, 255), 1)
    for i in range(y, y+h, gap*2):
        cv2.line(annotated, (x, i), (x, min(i+gap, y+h)), (255, 255, 255), 1)
        cv2.line(annotated, (x+w, i), (x+w, min(i+gap, y+h)), (255, 255, 255), 1)
    mid_y = y + h // 2
    _draw_arrow_line(annotated, (x, mid_y), (x + w, mid_y), (0, 255, 255))
    width_val = metrics.get('width_a_' + unit, float(w))
    cv2.putText(annotated, 'Width: {:.1f} {}'.format(width_val, unit), (x + 5, mid_y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
    mid_x = x + w // 2
    _draw_arrow_line(annotated, (mid_x, y), (mid_x, y + h), (0, 255, 255))
    height_val = metrics.get('height_a_' + unit, float(h))
    cv2.putText(annotated, 'Height: {:.1f} {}'.format(height_val, unit), (mid_x + 10, y + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
    area_val = metrics.get('area_a_' + unit + '2', float(cv2.contourArea(contour)))
    M = cv2.moments(contour)
    if M['m00'] != 0:
        cX, cY = int(M['m10'] / M['m00']), int(M['m01'] / M['m00'])
        area_str = '{:,}'.format(int(area_val))
        cv2.putText(annotated, 'Area: {} {}2'.format(area_str, unit), (cX - 60, cY), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    if not calibrated:
        cv2.putText(annotated, '* Uncalibrated (px units)', (10, annotated.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)
    return annotated

def draw_volume_cross_section(image_bgr, slice_data, contour):
    if image_bgr is None or not slice_data or contour is None:
        return image_bgr
    annotated = image_bgr.copy()
    x, y, w, h = cv2.boundingRect(contour)
    mask = np.zeros(image_bgr.shape[:2], dtype=np.uint8)
    cv2.fillPoly(mask, [contour], 255)
    widths = slice_data.get('slice_widths_cm', [])
    if not widths: return annotated
    num_slices = len(widths)
    slice_h_px = h / num_slices
    max_w = max(widths) if widths else 1
    for i, w_cm in enumerate(widths):
        curr_y = int(y + i * slice_h_px + slice_h_px/2)
        if curr_y >= mask.shape[0]: break
        row = mask[curr_y, :]
        cols = np.where(row > 0)[0]
        if len(cols) >= 2:
            ratio = w_cm / max_w
            color = (int(255 * (1-ratio)), 0, int(255 * ratio))
            cv2.line(annotated, (cols[0], curr_y), (cols[-1], curr_y), color, 1)
    return annotated

def draw_pose_skeleton(image_bgr, landmarks, corrections=None):
    if image_bgr is None or not landmarks: return image_bgr
    annotated = image_bgr.copy()
    connections = [('LEFT_SHOULDER', 'RIGHT_SHOULDER'), ('LEFT_SHOULDER', 'LEFT_ELBOW'), ('LEFT_ELBOW', 'LEFT_WRIST'), ('RIGHT_SHOULDER', 'RIGHT_ELBOW'), ('RIGHT_ELBOW', 'RIGHT_WRIST'), ('LEFT_SHOULDER', 'LEFT_HIP'), ('RIGHT_SHOULDER', 'RIGHT_HIP'), ('LEFT_HIP', 'RIGHT_HIP'), ('LEFT_HIP', 'LEFT_KNEE'), ('LEFT_KNEE', 'LEFT_ANKLE'), ('RIGHT_HIP', 'RIGHT_KNEE'), ('RIGHT_KNEE', 'RIGHT_ANKLE')]
    for p1_n, p2_n in connections:
        if p1_n in landmarks and p2_n in landmarks:
            cv2.line(annotated, tuple(map(int, landmarks[p1_n])), tuple(map(int, landmarks[p2_n])), (255, 255, 255), 2)
    corr_axes = [c['axis'].lower() for c in corrections] if corrections else []
    for name, pt in landmarks.items():
        color = (0, 255, 0)
        jl = name.lower().replace('_', ' ')
        for axis in corr_axes:
            if jl in axis:
                color = (0, 0, 255); break
        cv2.circle(annotated, tuple(map(int, pt)), 5, color, -1)
        cv2.circle(annotated, tuple(map(int, pt)), 6, (255, 255, 255), 1)
    return annotated
