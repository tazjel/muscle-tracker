"""
Unified scan pipeline — one function that runs every analysis step.
Both the API and CLI share this so logic is never duplicated.
"""
import os
import logging
import cv2

logger = logging.getLogger(__name__)


def full_scan_pipeline(
    image_front_path,
    image_side_path=None,
    image_before_path=None,
    user_weight_kg=None,
    user_height_cm=None,
    gender='male',
    muscle_group=None,
    marker_size_mm=20.0,
    volume_model='elliptical_cylinder',
    shape_template=None,
    output_dir=None,
):
    """
    Run the complete analysis pipeline on one or two images.

    Parameters
    ----------
    image_front_path  : str  — required, front-view image
    image_side_path   : str  — optional, side-view image (enables 3D)
    image_before_path : str  — optional, previous scan for growth comparison
    user_weight_kg    : float
    user_height_cm    : float
    gender            : 'male' | 'female'
    muscle_group      : str
    marker_size_mm    : float — ArUco marker size for calibration
    volume_model      : str
    shape_template    : str  — if provided, scores shape vs. template
    output_dir        : str  — if provided, saves annotated image here

    Returns
    -------
    dict with keys:
        calibrated, ratio_mm_per_px, metrics,
        area_mm2, width_mm, height_mm,
        volume_cm3, advanced_volume,
        circumference_cm, circumference_inches,
        shape_score, shape_grade,
        definition_score, definition_grade,
        growth_pct, growth_analysis,
        body_composition,
        mesh_data,       (vertices/faces/volume_cm3 if side view available)
        annotated_img,   (path to annotated image if output_dir given)
        errors           (list of non-fatal messages)
    """
    from core.vision_medical import analyze_muscle_growth
    from core.volumetrics import estimate_muscle_volume
    from core.volumetrics_advanced import slice_volume_estimate
    from core.circumference import estimate_circumference
    from core.segmentation import score_muscle_shape, AVAILABLE_TEMPLATES

    errors = []
    result = {'errors': errors}

    # ── 1. Front image analysis ──────────────────────────────────────────────
    res_f = analyze_muscle_growth(
        image_front_path, image_front_path,
        marker_size_mm, align=False,
        muscle_group=muscle_group,
        user_height_cm=user_height_cm,
    )
    if 'error' in res_f:
        return {'error': res_f['error'], 'errors': [res_f['error']]}

    ratio_mm_per_px = res_f.get('ratio', 1.0)
    pixels_per_cm   = 10.0 / ratio_mm_per_px if ratio_mm_per_px > 0 else 1.0
    pixels_per_mm   = 1.0  / ratio_mm_per_px if ratio_mm_per_px > 0 else 1.0
    unit    = 'mm' if res_f.get('calibrated') else 'px'
    metrics = res_f.get('metrics', {})

    result['calibrated']      = res_f.get('calibrated', False)
    result['ratio_mm_per_px'] = ratio_mm_per_px
    result['metrics']         = metrics

    area   = metrics.get(f'area_a_{unit}2', 0.0)
    width  = metrics.get(f'width_a_{unit}',  0.0)
    height = metrics.get(f'height_a_{unit}', 0.0)
    result['area_mm2']  = area
    result['width_mm']  = width
    result['height_mm'] = height

    contour_front = res_f.get('raw_data', {}).get('contour_a')
    result['contour_front'] = contour_front

    # ── 2. Side image (optional) ─────────────────────────────────────────────
    area_side = width_side = 0.0
    contour_side = None
    pixels_per_mm_side = pixels_per_mm

    if image_side_path and os.path.exists(image_side_path):
        res_s = analyze_muscle_growth(
            image_side_path, image_side_path,
            marker_size_mm, align=False,
            muscle_group=muscle_group,
        )
        if 'error' not in res_s:
            unit_s    = 'mm' if res_s.get('calibrated') else 'px'
            area_side  = res_s['metrics'].get(f'area_a_{unit_s}2', 0.0)
            width_side = res_s['metrics'].get(f'width_a_{unit_s}', 0.0)
            contour_side = res_s.get('raw_data', {}).get('contour_a')
            ratio_s      = res_s.get('ratio', 1.0)
            pixels_per_mm_side = 1.0 / ratio_s if ratio_s > 0 else 1.0
        else:
            errors.append(f'Side view: {res_s["error"]}')
    result['contour_side'] = contour_side

    # ── 3. Volume ────────────────────────────────────────────────────────────
    vol_result = estimate_muscle_volume(area, area_side, width, width_side, volume_model)
    result['volume_cm3'] = vol_result.get('volume_cm3', 0.0)

    if res_f.get('calibrated') and contour_front is not None:
        try:
            result['advanced_volume'] = slice_volume_estimate(contour_front, pixels_per_cm)
        except Exception as e:
            errors.append(f'Advanced volume: {e}')

    # ── 4. 3D Mesh (requires side view) ─────────────────────────────────────
    if contour_front is not None and contour_side is not None:
        try:
            from core.mesh_reconstruction import reconstruct_mesh_from_silhouettes
            mesh_data = reconstruct_mesh_from_silhouettes(
                contour_front, contour_side,
                pixels_per_mm, pixels_per_mm_side,
            )
            result['mesh_data'] = mesh_data
            if mesh_data.get('volume_cm3'):
                result['volume_cm3'] = mesh_data['volume_cm3']
        except Exception as e:
            errors.append(f'3D mesh: {e}')

    # ── 5. Circumference ─────────────────────────────────────────────────────
    if contour_front is not None:
        try:
            circ = estimate_circumference(contour_front, pixels_per_mm)
            circ_cm = circ.get('circumference_cm')
            result['circumference_cm']     = circ_cm
            result['circumference_inches'] = round(circ_cm / 2.54, 2) if circ_cm else None
        except Exception as e:
            errors.append(f'Circumference: {e}')

    # ── 6. Shape scoring ─────────────────────────────────────────────────────
    if shape_template and shape_template in AVAILABLE_TEMPLATES and contour_front is not None:
        try:
            shape_result = score_muscle_shape(contour_front, shape_template)
            result['shape_score'] = shape_result.get('score')
            result['shape_grade'] = shape_result.get('grade')
        except Exception as e:
            errors.append(f'Shape score: {e}')

    # ── 7. Definition scoring ────────────────────────────────────────────────
    if contour_front is not None:
        try:
            from core.definition_scorer import score_muscle_definition
            front_img = cv2.imread(image_front_path)
            if front_img is not None:
                def_result = score_muscle_definition(
                    front_img, contour_front, muscle_group or 'bicep'
                )
                result['definition_score'] = def_result.get('overall_definition')
                result['definition_grade'] = def_result.get('grade')
        except Exception as e:
            errors.append(f'Definition: {e}')

    # ── 8. Growth comparison ─────────────────────────────────────────────────
    if image_before_path and os.path.exists(image_before_path):
        try:
            growth = analyze_muscle_growth(
                image_before_path, image_front_path, marker_size_mm
            )
            if 'error' not in growth:
                result['growth_pct']      = growth['metrics'].get('growth_pct')
                result['growth_analysis'] = {
                    k: v for k, v in growth.items() if k != 'raw_data'
                }
        except Exception as e:
            errors.append(f'Growth: {e}')

    # ── 9. Body composition ──────────────────────────────────────────────────
    try:
        from core.body_composition import estimate_body_composition, estimate_lean_mass
        landmarks = {}
        try:
            from core.body_segmentation import segment_body
            img = cv2.imread(image_front_path)
            if img is not None:
                seg = segment_body(img)
                if seg and 'landmarks' in seg:
                    landmarks = seg['landmarks']
        except Exception:
            pass
        body_comp = estimate_body_composition(
            landmarks=landmarks,
            user_weight_kg=user_weight_kg,
            user_height_cm=user_height_cm,
            gender=gender,
        )
        if user_weight_kg and body_comp.get('estimated_body_fat_pct') is not None:
            lean = estimate_lean_mass(user_weight_kg, body_comp['estimated_body_fat_pct'])
            body_comp.update(lean)
        result['body_composition'] = body_comp
    except Exception as e:
        errors.append(f'Body composition: {e}')

    # ── 10. Measurement overlay ──────────────────────────────────────────────
    if contour_front is not None and output_dir:
        try:
            from core.measurement_overlay import draw_measurement_overlay
            front_img = cv2.imread(image_front_path)
            if front_img is not None:
                annotated = draw_measurement_overlay(
                    front_img, contour_front, metrics,
                    calibrated=res_f.get('calibrated', False),
                )
                base     = os.path.splitext(os.path.basename(image_front_path))[0]
                ann_path = os.path.join(output_dir, f'{base}_annotated.png')
                cv2.imwrite(ann_path, annotated)
                result['annotated_img'] = ann_path
        except Exception as e:
            errors.append(f'Overlay: {e}')

    return result
