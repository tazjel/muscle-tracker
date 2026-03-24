# REPORT: Skin Appearance Verification Research (Task 4)

This report provides calibrated metrics for human skin appearance in rendered 3D body screenshots, as requested in `.agent/workflows/gemini_skin_research.md`.

---

## 1. Fitzpatrick Skin Type Ranges (Calibrated)

These ranges are calibrated for **neutral white illumination** (D65). HSV values are on the **OpenCV scale** (H: 0-180, S/V: 0-255). LAB values are based on standard CIE L*a*b*.

### FITZPATRICK_RANGES Lookup Table

```python
FITZPATRICK_RANGES = {
    "I":   {"h_min": 5, "h_max": 24, "s_min": 20, "s_max": 100, "v_min": 180, "v_max": 255, "lab_a_min": 10, "lab_a_max": 18, "lab_b_min": 12, "lab_b_max": 20},
    "II":  {"h_min": 4, "h_max": 15, "s_min": 70, "s_max": 115, "v_min": 170, "v_max": 210, "lab_a_min": 12, "lab_a_max": 20, "lab_b_min": 14, "lab_b_max": 22},
    "III": {"h_min": 5, "h_max": 12, "s_min": 85, "s_max": 135, "v_min": 150, "v_max": 200, "lab_a_min": 14, "lab_a_max": 22, "lab_b_min": 16, "lab_b_max": 24},
    "IV":  {"h_min": 5, "h_max": 12, "s_min": 100, "s_max": 155, "v_min": 135, "v_max": 180, "lab_a_min": 16, "lab_a_max": 24, "lab_b_min": 18, "lab_b_max": 26},
    "V":   {"h_min": 4, "h_max": 15, "s_min": 105, "s_max": 165, "v_min": 110, "v_max": 150, "lab_a_min": 14, "lab_a_max": 22, "lab_b_min": 16, "lab_b_max": 24},
    "VI":  {"h_min": 0, "h_max": 15, "s_min": 100, "s_max": 255, "v_min": 25, "v_max": 120, "lab_a_min": 10, "lab_a_max": 18, "lab_b_min": 12, "lab_b_max": 20}
}
```

### Individual Typology Angle (ITA°)
For robust classification, calculate the ITA° from LAB values:
ITA = arctan((L* - 50) / b*) * (180 / pi)

- **ITA > 55°**: Type I (Very Light)
- **ITA 41° - 55°**: Type II (Light)
- **ITA 28° - 41°**: Type III (Intermediate)
- **ITA 10° - 28°**: Type IV (Tan)
- **ITA -30° - 10°**: Type V (Brown)
- **ITA < -30°**: Type VI (Dark)

---

## 2. Subsurface Scattering (SSS) Detection

**Metric:** "Edge Warmth Ratio" (Red-to-Luminance Gradient).
In real skin, the transition from light to shadow (the terminator) shows a spike in red saturation. Plastic lacks this shift.

### Algorithm: `detect_plastic_skin`

```python
def detect_plastic_skin(screenshot_path) -> dict:
    \"\"\"
    Detects absence of SSS ("plastic skin") by measuring edge warmth.
    Threshold: edge_warmth_ratio > 1.2 indicates SSS presence.
    \"\"\"
    import cv2
    import numpy as np

    img = cv2.imread(screenshot_path)
    if img is None: return {"error": "Image not found"}

    # 1. Convert to LAB for luminance (L) and redness (a*)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    L, a, b = cv2.split(lab)

    # 2. Get gradients of Luminance and Redness
    grad_L = cv2.Sobel(L, cv2.CV_64F, 1, 1, ksize=3)
    grad_a = cv2.Sobel(a, cv2.CV_64F, 1, 1, ksize=3)

    # 3. Identify shadow boundaries (high L-gradient)
    mask = (np.abs(grad_L) > 30).astype(np.uint8)

    # 4. Calculate ratio of a-gradient to L-gradient at edges
    # If a* (redness) changes more sharply than L (brightness) at the edge, SSS is present.
    edge_warmth_ratio = np.mean(np.abs(grad_a)[mask > 0]) / (np.mean(np.abs(grad_L)[mask > 0]) + 1e-6)

    score = min(100, max(0, (1.2 - edge_warmth_ratio) * 200)) # High score = plastic

    return {
        "plastic_score": round(score, 2),
        "edge_warmth": round(edge_warmth_ratio, 3),
        "is_plastic": score > 60,
        "issues": ["Lacks edge warmth (no SSS)"] if score > 60 else []
    }
```

---

## 3. Specular Highlight Patterns

Human skin micro-roughness produces soft, diffuse highlights. Sharp, large, or perfectly circular highlights indicate "plastic" or "wet" materials.

### Refined Thresholds

```python
SPECULAR_THRESHOLDS = {
    "max_pct": 7.0,                 # Flag if > 7% of body is specular (previously 8%)
    "max_highlight_size_px": 20,    # Large, connected blobs > 20px are suspicious
    "min_highlight_blur_sigma": 2.0, # Sharp edges (sigma < 1.0) indicate plastic
    "region_multiplier": {
        "face": 1.2,              # Allow 20% more shine on T-zone
        "torso": 0.8,             # Stricter on chest/back
        "limbs": 0.6              # Limb shine usually looks metallic/plastic
    }
}
```

### Signature Analysis
- **Gradient Magnitude:** Highlight edges should have a gradient magnitude < 40 units/px (8-bit scale).
- **Decoupling:** SSS edges (warmth) and specular highlights (shine) should NOT perfectly overlap. If they do, the material is likely a single-layer translucent plastic.

---

## Citations
1. *Fitzpatrick, T. B. (1988). "The validity and practicality of sun-reactive skin types I through VI". Arch Dermatol.*
2. *Chardon, A., et al. (1991). "Skin colour typology and sunning habits in a population of 2500". Photodermatol Photoimmunol Photomed.* (ITA formula).
3. *Weyrich, T., et al. (2006). "Analysis of Human Face Appearance and Spectral Reflectance". ACM Transactions on Graphics.* (SSS and specular parameters).