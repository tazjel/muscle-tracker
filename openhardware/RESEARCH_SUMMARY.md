# RESEARCH: Skin Appearance & 3D Scanning Metrics

This document summarizes the calibrated metrics and algorithms developed for human skin verification in the `gtd3d` project.

---

## 1. Fitzpatrick Skin Type Calibration (Task 1)
Calibrated for neutral white (D65) lighting. Values are for **OpenCV HSV** (H: 0-180, S/V: 0-255).

| Type | Hue Range | Saturation | Value (Brightness) | ITA° Range |
| :--- | :--- | :--- | :--- | :--- |
| **I** | 5 – 24 | 20 – 100 | 180 – 255 | > 55° |
| **II** | 4 – 15 | 70 – 115 | 170 – 210 | 41° to 55° |
| **III** | 5 – 12 | 85 – 135 | 150 – 200 | 28° to 41° |
| **IV** | 5 – 12 | 100 – 155 | 135 – 180 | 10° to 28° |
| **V** | 4 – 15 | 105 – 165 | 110 – 150 | -30° to 10° |
| **VI** | 0 – 15 | 100 – 255 | 25 – 120 | < -30° |

**ITA Formula:** `arctan((L* - 50) / b*) * (180 / pi)`

---

## 2. Subsurface Scattering (SSS) / "Plastic Skin" (Task 2)
Human skin exhibits "Edge Warmth" (Red Bleed) at shadow terminators due to light scattering through tissue.
- **Metric:** Edge Warmth Ratio = (Red-channel gradient / Luminance gradient).
- **Skin Threshold:** > 1.2 at boundaries.
- **Plastic Threshold:** ~1.0 (neutral transition).

---

## 3. Specular Highlight Patterns (Task 3)
Human skin has soft, diffuse highlights. 
- **Max Surface Area:** 7.0% (Total body area).
- **Max Highlight Size:** 20px (At typical resolution).
- **Min Blur Sigma:** 2.0 (Sharp edges indicate plastic).

---

## 4. Hardware Techniques for Improvement
- **Slit-Scanning:** Using a line laser (Arduino) + Mobile Camera (OpenCV) to extract depth.
- **Visual Hull:** Front + Side silhouettes integrated into 3D space via `Open3D`.
- **Cross-Polarization:** Using CPL filters on cameras and polarizing film on lights to remove glints.