"""
glb_inspector.py — Pure Python GLB texture extraction + quality scoring.

No browser, no server needed. Reverse of export_glb() in mesh_reconstruction.py.

Usage:
    from core.glb_inspector import score_glb
    result = score_glb("meshes/skin_densepose.glb")
    print(result['verdict'])  # PASS / WARN / FAIL
"""
import math
import numpy as np
import cv2


# Fitzpatrick skin type ranges — HSV on OpenCV scale (H:0-180, S/V:0-255),
# LAB a*/b* on standard CIELAB scale (add 128 for OpenCV's 0-255 encoding).
# Source: Chardon et al. 1991 (ITA formula), Fitzpatrick 1988.
FITZPATRICK_RANGES = {
    "I":   {"h_min": 5, "h_max": 24, "s_min": 20, "s_max": 100, "v_min": 180, "v_max": 255,
            "lab_a_min": 138, "lab_a_max": 146, "lab_b_min": 140, "lab_b_max": 148},
    "II":  {"h_min": 4, "h_max": 15, "s_min": 70, "s_max": 115, "v_min": 170, "v_max": 210,
            "lab_a_min": 140, "lab_a_max": 148, "lab_b_min": 142, "lab_b_max": 150},
    "III": {"h_min": 5, "h_max": 12, "s_min": 85, "s_max": 135, "v_min": 150, "v_max": 200,
            "lab_a_min": 142, "lab_a_max": 150, "lab_b_min": 144, "lab_b_max": 152},
    "IV":  {"h_min": 5, "h_max": 12, "s_min": 100, "s_max": 155, "v_min": 135, "v_max": 180,
            "lab_a_min": 144, "lab_a_max": 152, "lab_b_min": 146, "lab_b_max": 154},
    "V":   {"h_min": 4, "h_max": 15, "s_min": 105, "s_max": 165, "v_min": 110, "v_max": 150,
            "lab_a_min": 142, "lab_a_max": 150, "lab_b_min": 144, "lab_b_max": 152},
    "VI":  {"h_min": 0, "h_max": 15, "s_min": 100, "s_max": 255, "v_min": 25, "v_max": 120,
            "lab_a_min": 138, "lab_a_max": 146, "lab_b_min": 140, "lab_b_max": 148},
}

# Specular thresholds — refined from Gemini research (Weyrich et al. 2006)
SPECULAR_THRESHOLDS = {
    "max_pct": 7.0,
    "max_highlight_size_px": 20,
    "min_highlight_blur_sigma": 2.0,
}


def classify_fitzpatrick_ita(L_star, b_star):
    """Classify skin type via Individual Typology Angle (ITA°).
    L_star and b_star in standard CIELAB scale (L*: 0-100, b*: approx -128 to 127).
    For OpenCV LAB: L_star = L_opencv * 100/255, b_star = b_opencv - 128.
    """
    if abs(b_star) < 0.01:
        b_star = 0.01
    ita = math.atan2(L_star - 50, b_star) * (180 / math.pi)
    if ita > 55:
        return "I"
    elif ita > 41:
        return "II"
    elif ita > 28:
        return "III"
    elif ita > 10:
        return "IV"
    elif ita > -30:
        return "V"
    else:
        return "VI"


def detect_plastic_skin(screenshot_path):
    """
    Detect absence of subsurface scattering ("plastic skin") via edge warmth ratio.
    At shadow boundaries, real skin shows a spike in redness (LAB a*) relative to
    luminance change. Plastic materials lack this.

    Returns dict with plastic_score (0-100, high = plastic), edge_warmth ratio, issues.
    """
    img = cv2.imread(screenshot_path)
    if img is None:
        return {"error": "unreadable", "path": screenshot_path}

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    body_mask = gray > 30

    if body_mask.mean() < 0.015:
        return {"plastic_score": 0, "edge_warmth": 0, "issues": []}

    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    L_ch = lab[:, :, 0].astype(np.float64)
    a_ch = lab[:, :, 1].astype(np.float64)

    # Gradients of luminance and redness
    grad_L = cv2.Sobel(L_ch, cv2.CV_64F, 1, 1, ksize=3)
    grad_a = cv2.Sobel(a_ch, cv2.CV_64F, 1, 1, ksize=3)

    # Shadow boundary mask: high luminance gradient on body
    edge_mask = (np.abs(grad_L) > 30) & body_mask
    edge_count = edge_mask.sum()

    if edge_count < 100:
        return {"plastic_score": 0, "edge_warmth": 0, "issues": ["insufficient edges"]}

    # Ratio: redness change vs brightness change at shadow edges
    mean_grad_a = float(np.abs(grad_a)[edge_mask].mean())
    mean_grad_L = float(np.abs(grad_L)[edge_mask].mean())
    edge_warmth = mean_grad_a / (mean_grad_L + 1e-6)

    # Score: >1.2 = strong SSS (photo), >0.3 = acceptable (WebGL render), <0.15 = plastic
    # Note: headless WebGL renders produce much lower edge warmth than photos because
    # Three.js sheen is a screenspace approximation, not true subsurface scattering.
    # Threshold tuned for WebGL renders: 0.15 instead of 1.0.
    plastic_score = min(100, max(0, (0.15 - edge_warmth) * 500))

    issues = []
    if plastic_score > 60:
        issues.append(f"PLASTIC_SKIN: edge warmth ratio={edge_warmth:.3f} (<0.15) — lacks subsurface scattering")

    return {
        "plastic_score": round(plastic_score, 1),
        "edge_warmth": round(edge_warmth, 3),
        "is_plastic": plastic_score > 60,
        "issues": issues,
    }


def extract_textures(glb_path):
    """
    Extract embedded textures from a GLB file.

    Returns dict with:
        albedo:    ndarray (H,W,3) BGR or None
        normal:    ndarray (H,W,3) BGR or None
        roughness: ndarray (H,W,3) BGR or None
        ao:        ndarray (H,W,3) BGR or None
        mesh:      {"vertices": int, "faces": int}
    """
    import pygltflib

    gltf = pygltflib.GLTF2.load(glb_path)
    blob = gltf.binary_blob()

    result = {"albedo": None, "normal": None, "roughness": None, "ao": None,
              "mesh": {"vertices": 0, "faces": 0}}

    # ── Mesh stats ──
    for accessor in gltf.accessors:
        # Find position accessor (VEC3 FLOAT in ARRAY_BUFFER)
        bv_idx = accessor.bufferView
        if bv_idx is None:
            continue
        bv = gltf.bufferViews[bv_idx]
        if accessor.type == "VEC3" and accessor.componentType == pygltflib.FLOAT:
            if bv.target == pygltflib.ARRAY_BUFFER:
                if result["mesh"]["vertices"] == 0:
                    result["mesh"]["vertices"] = accessor.count
        # Find index accessor (SCALAR UNSIGNED_INT in ELEMENT_ARRAY_BUFFER)
        if accessor.type == "SCALAR" and bv.target == pygltflib.ELEMENT_ARRAY_BUFFER:
            result["mesh"]["faces"] = accessor.count // 3

    # ── Extract texture images ──
    if not gltf.materials:
        return result

    mat = gltf.materials[0]
    pbr = mat.pbrMetallicRoughness

    # Helper: image index → numpy array
    def _decode_image(img_index):
        if img_index is None or img_index >= len(gltf.images):
            return None
        img = gltf.images[img_index]
        if img.bufferView is None:
            return None
        bv = gltf.bufferViews[img.bufferView]
        offset = bv.byteOffset or 0
        length = bv.byteLength
        png_bytes = blob[offset:offset + length]
        arr = np.frombuffer(png_bytes, np.uint8)
        decoded = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return decoded

    # Helper: texture info → image index
    def _tex_to_img(tex_info):
        if tex_info is None:
            return None
        tex_idx = tex_info.index
        if tex_idx is None or tex_idx >= len(gltf.textures):
            return None
        return gltf.textures[tex_idx].source

    # Albedo (baseColorTexture)
    if pbr and pbr.baseColorTexture:
        result["albedo"] = _decode_image(_tex_to_img(pbr.baseColorTexture))

    # Normal map
    if mat.normalTexture:
        result["normal"] = _decode_image(_tex_to_img(mat.normalTexture))

    # Metallic-roughness map
    if pbr and pbr.metallicRoughnessTexture:
        result["roughness"] = _decode_image(_tex_to_img(pbr.metallicRoughnessTexture))

    # Occlusion (AO) map
    if mat.occlusionTexture:
        result["ao"] = _decode_image(_tex_to_img(mat.occlusionTexture))

    return result


def score_texture(texture, name="albedo"):
    """
    Score a single texture map for quality.

    Returns dict with metrics + issues list.
    """
    if texture is None:
        return {"present": False, "issues": [f"NO_{name.upper()}"]}

    h, w = texture.shape[:2]
    tex = texture.astype(np.float64)

    # Color variance: std across all pixels
    color_variance = float(np.std(tex))

    # Spatial variance: 8x8 grid of blocks, std of block means
    # This is the "SO SAD" detector — uniform blobs score <8
    block_h, block_w = h // 8, w // 8
    block_means = []
    for bi in range(8):
        for bj in range(8):
            block = tex[bi * block_h:(bi + 1) * block_h,
                        bj * block_w:(bj + 1) * block_w]
            block_means.append(np.mean(block))
    spatial_variance = float(np.std(block_means))

    # Coverage: % of pixels that are not black
    non_black = np.any(texture > 10, axis=-1)
    coverage_pct = float(non_black.mean() * 100)

    # Unique colors (quantized to 16 bins per channel)
    quantized = (texture // 16).reshape(-1, 3)
    unique_colors = len(np.unique(quantized, axis=0))

    # Dominant color: median of non-black pixels
    non_black_pixels = texture[non_black]
    if len(non_black_pixels) > 0:
        dominant_color_bgr = np.median(non_black_pixels, axis=0).astype(int).tolist()
    else:
        dominant_color_bgr = [0, 0, 0]

    # Dominant color percentage: pixels within deltaE < 15
    if len(non_black_pixels) > 0:
        dom = np.array(dominant_color_bgr, dtype=np.float64)
        diffs = np.sqrt(np.sum((non_black_pixels.astype(np.float64) - dom) ** 2, axis=-1))
        dominant_color_pct = float((diffs < 15).sum() / len(non_black_pixels) * 100)
    else:
        dominant_color_pct = 0.0

    # Skin tone plausibility: HSV check on dominant color
    dom_bgr = np.array([[dominant_color_bgr]], dtype=np.uint8)
    dom_hsv = cv2.cvtColor(dom_bgr, cv2.COLOR_BGR2HSV)[0][0]
    h_val, s_val, v_val = int(dom_hsv[0]), int(dom_hsv[1]), int(dom_hsv[2])
    skin_tone_plausible = (
        (h_val <= 25 or h_val >= 165) and
        20 <= s_val <= 180 and
        50 <= v_val <= 255
    )

    # Blue shift: BGR/RGB swap bug detector
    mean_b = float(np.mean(tex[:, :, 0]))
    mean_r = float(np.mean(tex[:, :, 2]))
    blue_shift = mean_b > mean_r + 20

    # Build issues list
    issues = []
    if spatial_variance < 8:
        issues.append("UNIFORM_BLOB")
    if color_variance < 12:
        issues.append("LOW_VARIANCE")
    if coverage_pct < 50:
        issues.append("LOW_COVERAGE")
    if coverage_pct < 75 and coverage_pct >= 50:
        issues.append("PARTIAL_COVERAGE")
    if dominant_color_pct > 60:
        issues.append("MONO_COLOR")
    if blue_shift:
        issues.append("BLUE_SHIFT")
    if not skin_tone_plausible and name == "albedo":
        issues.append("NON_SKIN_TONE")

    return {
        "present": True,
        "resolution": [w, h],
        "color_variance": round(color_variance, 1),
        "spatial_variance": round(spatial_variance, 1),
        "coverage_pct": round(coverage_pct, 1),
        "unique_colors": unique_colors,
        "dominant_color_bgr": dominant_color_bgr,
        "dominant_color_pct": round(dominant_color_pct, 1),
        "skin_tone_plausible": skin_tone_plausible,
        "blue_shift": blue_shift,
        "issues": issues,
    }


def detect_seams(texture):
    """
    Detect visible seams in a texture by finding high-gradient vertical/horizontal lines.

    Returns dict with seam metrics. This catches the front/back and left/right
    boundary artifacts that score_texture() misses.
    """
    if texture is None:
        return {"has_seam": False}

    gray = cv2.cvtColor(texture, cv2.COLOR_BGR2GRAY).astype(np.float64)
    h, w = gray.shape

    # Vertical seam detection: compute column-wise brightness means
    col_means = gray.mean(axis=0)  # (W,) — average brightness per column
    # Gradient between adjacent columns
    col_grad = np.abs(np.diff(col_means))
    # A seam shows as a spike in the column gradient
    col_grad_std = float(col_grad.std())
    max_col_grad = float(col_grad.max())
    # Seam columns: gradient > 3x std
    seam_cols = np.where(col_grad > max(col_grad.mean() + 3 * col_grad_std, 5))[0]

    # Horizontal seam detection
    row_means = gray.mean(axis=1)
    row_grad = np.abs(np.diff(row_means))
    row_grad_std = float(row_grad.std())
    max_row_grad = float(row_grad.max())
    seam_rows = np.where(row_grad > max(row_grad.mean() + 3 * row_grad_std, 5))[0]

    has_seam = len(seam_cols) > 0 or len(seam_rows) > 0

    return {
        "has_seam": has_seam,
        "vertical_seam_cols": len(seam_cols),
        "horizontal_seam_rows": len(seam_rows),
        "max_col_gradient": round(max_col_grad, 1),
        "max_row_gradient": round(max_row_grad, 1),
    }


def check_symmetry(texture):
    """
    Check left-right symmetry of the texture.

    Human bodies are roughly symmetric — a large left-right brightness difference
    indicates uneven photo lighting or a view-stitching seam.
    """
    if texture is None:
        return {"symmetric": True}

    h, w = texture.shape[:2]
    lab = cv2.cvtColor(texture, cv2.COLOR_BGR2LAB)
    l_channel = lab[:, :, 0].astype(np.float64)

    # Only check non-black pixels (texture coverage area)
    non_black = np.any(texture > 10, axis=-1)

    left_mask = non_black[:, :w // 2]
    right_mask = non_black[:, w // 2:]

    if left_mask.sum() < 100 or right_mask.sum() < 100:
        return {"symmetric": True, "note": "not enough coverage to check"}

    left_brightness = float(l_channel[:, :w // 2][left_mask].mean())
    right_brightness = float(l_channel[:, w // 2:][right_mask].mean())
    lr_diff = abs(left_brightness - right_brightness)

    # Also check color (a/b channels in LAB)
    a_channel = lab[:, :, 1].astype(np.float64)
    left_a = float(a_channel[:, :w // 2][left_mask].mean())
    right_a = float(a_channel[:, w // 2:][right_mask].mean())
    color_diff = abs(left_a - right_a)

    asymmetric = lr_diff > 8 or color_diff > 5

    return {
        "symmetric": not asymmetric,
        "lr_brightness_diff": round(lr_diff, 1),
        "lr_color_diff": round(color_diff, 1),
        "left_brightness": round(left_brightness, 1),
        "right_brightness": round(right_brightness, 1),
    }


def analyze_render_screenshot(screenshot_path):
    """
    Analyze a browser render screenshot for visible issues.

    Checks:
    - Body visible (not blank/failed render)
    - Left-right color asymmetry on the rendered body
    - Overall detail level

    Returns dict with metrics.
    """
    img = cv2.imread(screenshot_path)
    if img is None:
        return {"error": "unreadable", "path": screenshot_path}

    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Body detection: non-background pixels (background is dark ~#0a0a2e)
    body_mask = gray > 30
    body_pct = float(body_mask.mean() * 100)

    result = {
        "path": screenshot_path,
        "body_visible_pct": round(body_pct, 1),
        "issues": [],
    }

    if body_pct < 3:
        result["issues"].append("RENDER_BLANK: no body visible in render")
        return result

    # Extract body-only pixels
    body_pixels = img[body_mask]
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)

    # Left-right asymmetry on the body
    body_left = body_mask[:, :w // 2]
    body_right = body_mask[:, w // 2:]
    if body_left.sum() > 100 and body_right.sum() > 100:
        l_ch = lab[:, :, 0].astype(np.float64)
        left_b = float(l_ch[:, :w // 2][body_left].mean())
        right_b = float(l_ch[:, w // 2:][body_right].mean())
        lr_diff = abs(left_b - right_b)
        result["render_lr_diff"] = round(lr_diff, 1)
        if lr_diff > 10:
            result["issues"].append(f"RENDER_ASYMMETRIC: left-right brightness diff={lr_diff:.1f} > 10 "
                                    f"(visible seam or uneven texture)")

    # Edge density (detail level) on body
    body_gray = gray.copy()
    body_gray[~body_mask] = 0
    edges = cv2.Canny(body_gray, 30, 100)
    edge_density = float(edges[body_mask].mean() / 255)
    result["edge_density"] = round(edge_density, 3)
    if edge_density < 0.01:
        result["issues"].append("RENDER_NO_DETAIL: body surface has no visible texture detail")

    return result


def analyze_skin_tone(screenshot_path):
    """
    Analyze a rendered screenshot for human skin appearance.

    Checks HSV color distribution, LAB color temperature, specular highlights,
    and vertical zone consistency on the body pixels.

    Returns dict with metrics and issue codes.
    """
    img = cv2.imread(screenshot_path)
    if img is None:
        return {"error": "unreadable", "path": screenshot_path}

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Isolate body from dark background (#0a0a2e)
    body_mask = gray > 30
    body_pct = float(body_mask.mean() * 100)

    result = {
        "path": screenshot_path,
        "body_visible_pct": round(body_pct, 1),
        "issues": [],
    }

    if body_pct < 1.5:
        result["issues"].append("RENDER_BLANK: no body visible in render")
        return result

    # HSV analysis on body pixels
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    body_hsv = hsv[body_mask]  # (N, 3)
    h_vals = body_hsv[:, 0].astype(np.float64)  # OpenCV H: 0-180
    s_vals = body_hsv[:, 1].astype(np.float64)
    v_vals = body_hsv[:, 2].astype(np.float64)

    # Skin hue percentage: H in [0-25] or [165-180] (OpenCV scale)
    skin_hue_mask = (h_vals <= 25) | (h_vals >= 165)
    skin_hue_pct = float(skin_hue_mask.mean() * 100)
    result["skin_hue_pct"] = round(skin_hue_pct, 1)

    if skin_hue_pct < 40:
        result["issues"].append(
            f"NON_SKIN_HUE: only {skin_hue_pct:.0f}% of body pixels in skin hue range (<40%)")
    elif skin_hue_pct < 60:
        result["issues"].append(
            f"LOW_SKIN_HUE: {skin_hue_pct:.0f}% of body pixels in skin hue range (marginal)")

    # Saturation distribution
    sat_median = float(np.median(s_vals))
    sat_std = float(np.std(s_vals))
    result["sat_median"] = round(sat_median, 1)
    result["sat_std"] = round(sat_std, 1)

    if sat_median < 15:
        result["issues"].append(
            f"DESATURATED: median saturation={sat_median:.0f} (<15) — body looks gray")
    elif sat_median > 200:
        result["issues"].append(
            f"OVERSATURATED: median saturation={sat_median:.0f} (>200) — unnaturally vivid")
    if sat_std < 5:
        result["issues"].append(
            "FLAT_SATURATION: no natural color variation across body surface")

    # Value (brightness) distribution
    val_median = float(np.median(v_vals))
    val_q25 = float(np.percentile(v_vals, 25))
    val_q75 = float(np.percentile(v_vals, 75))
    val_iqr = val_q75 - val_q25
    result["val_median"] = round(val_median, 1)
    result["val_iqr"] = round(val_iqr, 1)

    if val_median < 40:
        result["issues"].append(
            f"TOO_DARK: median brightness={val_median:.0f} (<40)")
    elif val_median > 240:
        result["issues"].append(
            f"TOO_BRIGHT: median brightness={val_median:.0f} (>240)")

    # LAB color temperature
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    body_lab = lab[body_mask]
    lab_a_mean = float(body_lab[:, 1].mean())
    lab_b_mean = float(body_lab[:, 2].mean())
    result["lab_a_mean"] = round(lab_a_mean, 1)
    result["lab_b_mean"] = round(lab_b_mean, 1)

    if lab_a_mean >= 133:
        result["color_temp"] = "warm"
    elif lab_a_mean >= 125:
        result["color_temp"] = "neutral"
    else:
        result["color_temp"] = "cool"
        result["issues"].append(
            f"COOL_CAST: LAB a*={lab_a_mean:.1f} (<125) — skin has green/blue cast")

    # Fitzpatrick classification via ITA°
    L_star = float(body_lab[:, 0].mean()) * 100.0 / 255.0  # OpenCV L → standard L*
    b_star = float(body_lab[:, 2].mean()) - 128.0           # OpenCV b → standard b*
    fitz_type = classify_fitzpatrick_ita(L_star, b_star)
    result["fitzpatrick_type"] = fitz_type

    # Specular highlight detection: very bright + low saturation
    specular_mask = (v_vals > 240) & (s_vals < 30)
    specular_pct = float(specular_mask.mean() * 100)
    result["specular_pct"] = round(specular_pct, 1)

    if specular_pct > SPECULAR_THRESHOLDS["max_pct"]:
        result["issues"].append(
            f"TOO_SHINY: {specular_pct:.1f}% specular pixels (>{SPECULAR_THRESHOLDS['max_pct']}%) — reduce clearcoat or roughness")

    # Vertical zone consistency: divide body bbox into 3 horizontal thirds
    rows_with_body = np.where(body_mask.any(axis=1))[0]
    if len(rows_with_body) > 30:
        top_row, bot_row = rows_with_body[0], rows_with_body[-1]
        third = (bot_row - top_row) // 3
        zone_hues = []
        for z in range(3):
            r0 = top_row + z * third
            r1 = r0 + third
            zone_mask = body_mask[r0:r1, :]
            if zone_mask.sum() > 50:
                zone_h = hsv[r0:r1, :, 0][zone_mask].astype(np.float64)
                zone_hues.append(float(np.median(zone_h)))
        if len(zone_hues) >= 2:
            # Circular hue distance (OpenCV H: 0-180, wraps around)
            # Skin hues cluster near 0° AND 175° — both valid, must use circular diff
            max_circ_diff = 0.0
            for i in range(len(zone_hues)):
                for j in range(i + 1, len(zone_hues)):
                    diff = abs(zone_hues[i] - zone_hues[j])
                    circ_diff = min(diff, 180 - diff)  # circular distance on 0-180 range
                    max_circ_diff = max(max_circ_diff, circ_diff)
            result["zone_hue_spread"] = round(max_circ_diff, 1)
            if max_circ_diff > 10:
                result["issues"].append(
                    f"ZONE_COLOR_SHIFT: hue varies {max_circ_diff:.0f} units across body zones (>10)")

    return result


def score_glb(glb_path):
    """
    Full quality assessment of a GLB file.

    Returns:
        verdict: "PASS" / "WARN" / "FAIL"
        scores, per-texture metrics, issues list, suggestion
    """
    textures = extract_textures(glb_path)
    albedo_score = score_texture(textures["albedo"], "albedo")
    normal_score = score_texture(textures["normal"], "normal")
    roughness_score = score_texture(textures["roughness"], "roughness")
    ao_score = score_texture(textures["ao"], "ao")

    # Additional checks on albedo
    seam_info = detect_seams(textures["albedo"])
    symmetry_info = check_symmetry(textures["albedo"])

    issues = []
    suggestion_parts = []

    # ── Verdict logic ──
    fail = False
    warn = False

    # Albedo is the primary quality signal
    if not albedo_score["present"]:
        fail = True
        issues.append("NO_ALBEDO: GLB has no base color texture")
        suggestion_parts.append("No albedo texture found — check export_glb() received a texture_image.")
    else:
        sv = albedo_score["spatial_variance"]
        cv_val = albedo_score["color_variance"]
        cov = albedo_score["coverage_pct"]
        dom_pct = albedo_score["dominant_color_pct"]

        if sv < 8:
            fail = True
            issues.append(f"ALBEDO_UNIFORM_BLOB: spatial_variance={sv} < 8")
            suggestion_parts.append("Texture lacks spatial detail — check projection mapping or DensePose IUV coverage.")
        elif sv < 15:
            warn = True
            issues.append(f"ALBEDO_LOW_DETAIL: spatial_variance={sv} < 15")

        if cv_val < 12:
            fail = True
            issues.append(f"ALBEDO_FLAT: color_variance={cv_val} < 12")
            suggestion_parts.append("Colors are nearly uniform — may be a solid fill instead of photo texture.")

        if cov < 50:
            fail = True
            issues.append(f"ALBEDO_LOW_COVERAGE: coverage={cov}% < 50%")
            suggestion_parts.append("Over half the texture is black — DensePose may have missed body regions.")
        elif cov < 75:
            warn = True
            issues.append(f"ALBEDO_PARTIAL_COVERAGE: coverage={cov}% < 75%")

        if albedo_score.get("blue_shift"):
            fail = True
            issues.append("ALBEDO_BLUE_SHIFT: mean_B >> mean_R — likely BGR/RGB swap")
            suggestion_parts.append("Blue color shift detected — check cv2.imencode vs RGB order in texture pipeline.")

        if dom_pct > 60:
            warn = True
            issues.append(f"ALBEDO_MONO: dominant_color={dom_pct}% > 60%")

    # ── Seam detection ──
    if seam_info.get("has_seam") and seam_info.get("max_col_gradient", 0) > 10:
        warn = True
        issues.append(f"TEXTURE_SEAM: {seam_info['vertical_seam_cols']} vertical seam lines detected "
                      f"(max_gradient={seam_info['max_col_gradient']})")
        suggestion_parts.append("Visible seams in texture — check photo lighting evenness or reduce multi-view blending.")

    # ── Symmetry check ──
    if not symmetry_info.get("symmetric", True):
        lr = symmetry_info.get("lr_brightness_diff", 0)
        if lr > 15:
            fail = True
            issues.append(f"ASYMMETRIC_TEXTURE: left-right brightness diff={lr} > 15 — "
                          f"L={symmetry_info['left_brightness']} R={symmetry_info['right_brightness']}")
            suggestion_parts.append("Strong left-right asymmetry — likely uneven photo lighting. "
                                    "Retake photos with symmetric lighting or use only front+back views.")
        else:
            warn = True
            issues.append(f"MILD_ASYMMETRY: left-right brightness diff={lr}")

    # Overall score (0-100, based on albedo + symmetry + seams)
    if albedo_score["present"]:
        sv = albedo_score["spatial_variance"]
        cv_val = albedo_score["color_variance"]
        cov = albedo_score["coverage_pct"]
        # Base score: spatial 35%, variance 25%, coverage 25%
        sv_score = min(100, sv / 30 * 100)
        cv_score = min(100, cv_val / 40 * 100)
        cov_score = cov
        base = sv_score * 0.35 + cv_score * 0.25 + cov_score * 0.25

        # Symmetry bonus/penalty (15%)
        lr_diff = symmetry_info.get("lr_brightness_diff", 0)
        sym_score = max(0, 100 - lr_diff * 5)  # -5 points per unit of asymmetry
        overall = int(base + sym_score * 0.15)
    else:
        overall = 0

    if fail:
        verdict = "FAIL"
    elif warn:
        verdict = "WARN"
    else:
        verdict = "PASS"

    suggestion = " ".join(suggestion_parts) if suggestion_parts else "Texture quality looks good."

    return {
        "verdict": verdict,
        "scores": {
            "texture_quality": overall,
            "overall": overall,
        },
        "mesh": textures["mesh"],
        "albedo": albedo_score,
        "symmetry": symmetry_info,
        "seams": seam_info,
        "normal": {k: v for k, v in normal_score.items() if k in ("present", "resolution", "issues")},
        "roughness": {k: v for k, v in roughness_score.items() if k in ("present", "resolution", "issues")},
        "ao": {k: v for k, v in ao_score.items() if k in ("present", "resolution", "issues")},
        "issues": issues,
        "suggestion": suggestion,
    }
