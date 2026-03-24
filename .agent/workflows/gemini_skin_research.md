# Gemini Research Tasks: Skin Appearance Verification

These tasks support the `skin-check` tool in `scripts/agent_browser.py` which analyzes rendered 3D body screenshots for human skin appearance. The tool currently uses basic HSV heuristics — Gemini research should provide calibrated values and new metrics.

---

## Task 1: Fitzpatrick Skin Type Ranges in HSV and LAB Color Spaces

**Goal:** Provide exact numeric ranges for all 6 Fitzpatrick skin types in both HSV (OpenCV scale: H 0-180, S 0-255, V 0-255) and CIELAB color spaces.

**What we need:**
- For each Fitzpatrick type (I through VI), provide:
  - HSV hue range (min-max)
  - HSV saturation range (min-max)
  - HSV value/brightness range (min-max)
  - LAB `a*` channel range (indicates redness/warmth)
  - LAB `b*` channel range (indicates yellowness)
- Source these from dermatology or computer vision literature (cite papers)
- Include ranges measured under **neutral white illumination** (our viewer uses white directional + ambient light)

**Current heuristic (to improve):**
- Skin hue: H ∈ [0, 25] or [165, 180] (OpenCV scale)
- Skin tone plausibility: S ∈ [20, 180], V ∈ [50, 255]
- Color warmth: LAB a* > 125

**Deliverable:** A Python dict/lookup table we can drop into `core/glb_inspector.py:analyze_skin_tone()`.

**Example output format:**
```python
FITZPATRICK_RANGES = {
    "I":  {"h_min": 0, "h_max": 20, "s_min": 25, "s_max": 80, "v_min": 180, "v_max": 255, "lab_a_min": 130, "lab_a_max": 145, "lab_b_min": 135, "lab_b_max": 155},
    "II": { ... },
    ...
}
```

---

## Task 2: Subsurface Scattering Visual Signatures in Screenshots

**Goal:** Determine if we can detect the absence of subsurface scattering (SSS) — i.e., "plastic skin" — from a flat 2D screenshot of a rendered 3D body.

**Context:**
- Our Three.js viewer uses `MeshPhysicalMaterial` with sheen (0.35) and clearcoat (0.06) to approximate SSS
- Real SSS causes warm color bleeding at contour edges (light passes through thin skin at silhouette)
- Without SSS, skin looks like painted plastic — sharp shadow/light transitions, no edge warmth

**Research questions:**
1. What visual signatures distinguish SSS-rendered skin from non-SSS in a screenshot?
2. Can we measure "edge warmth" — are pixels near the body silhouette warmer (higher LAB `a*`) than center pixels?
3. What is a computable metric? E.g., `edge_warmth_ratio = mean_a_star_edge / mean_a_star_center` — what threshold separates real-looking from plastic?
4. Does Three.js `sheen` actually produce measurable edge warmth, or is it too subtle?

**Deliverable:** A proposed function signature + algorithm:
```python
def detect_plastic_skin(screenshot_path) -> dict:
    """Returns {'plastic_score': 0-100, 'edge_warmth': float, 'issues': [...]}"""
```

---

## Task 3: Specular Highlight Patterns — Human Skin vs Plastic

**Goal:** Provide metrics to distinguish correct skin specularity from "wet/plastic" specularity in rendered screenshots.

**Context:**
- Our material: roughness 0.6, clearcoat 0.06, specular intensity 0.4
- Real human skin has small, diffuse specular highlights (due to micro-roughness + sebum)
- Incorrect settings produce large, sharp, "wet ball" highlights

**Research questions:**
1. What is the expected size distribution of specular highlights on human skin at typical viewing distances?
2. How to measure highlight "sharpness" — gradient magnitude at highlight edges?
3. What ratio of specular area to total body area is normal for human skin? (We currently flag > 8%)
4. Should specular detection vary by body region (face oilier than forearms)?

**Deliverable:** Refined thresholds for `analyze_skin_tone()`:
```python
# Current: specular_pct > 8% → TOO_SHINY
# Proposed: ???
SPECULAR_THRESHOLDS = {
    "max_pct": ???,
    "max_highlight_size_px": ???,
    "min_highlight_blur_sigma": ???,
}
```

---

## How to Use These Results

After Gemini delivers results, integrate into:
- `core/glb_inspector.py` → `analyze_skin_tone()` function (line ~340)
- Add Fitzpatrick lookup table as a module-level constant
- Add `detect_plastic_skin()` as a new function if Task 2 yields a viable metric
- Update specular thresholds based on Task 3 findings

Test with: `$PY scripts/agent_browser.py skin-check meshes/skin_densepose.glb`
