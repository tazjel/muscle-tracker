"""
Body Scan Pipeline — orchestrates multi-pass 360° body scanning.
Chains existing core modules for DensePose analysis, coverage grading,
mesh building, texture baking, and GLB export.
"""
import os
import json
import logging
import glob

import numpy as np
import cv2

logger = logging.getLogger(__name__)

BODY_REGIONS = {
    'front_torso': [1],
    'back_torso': [2],
    'right_arm': [3, 16, 18, 20, 22],
    'left_arm': [4, 15, 17, 19, 21],
    'right_leg': [6, 7, 9, 11, 13],
    'left_leg': [5, 8, 10, 12, 14],
    'head': [23, 24],
}

GRADE_THRESHOLDS = {
    'excellent': (5000, 3),
    'good': (2000, 2),
    'fair': (500, 1),
}

# ---------------------------------------------------------------------------
# Optional module imports — each wrapped so a missing dep doesn't break import
# ---------------------------------------------------------------------------
try:
    from core.densepose_infer import predict_iuv
    _HAS_DENSEPOSE = True
except Exception as _e:
    logger.warning("densepose_infer unavailable: %s", _e)
    _HAS_DENSEPOSE = False
    predict_iuv = None

try:
    from core.smpl_fitting import build_body_mesh
    _HAS_SMPL = True
except Exception as _e:
    logger.warning("smpl_fitting unavailable: %s", _e)
    _HAS_SMPL = False
    build_body_mesh = None

try:
    from core.texture_bake import bake_from_photos_nn
    _HAS_TEXTURE_BAKE = True
except Exception as _e:
    logger.warning("texture_bake unavailable: %s", _e)
    _HAS_TEXTURE_BAKE = False
    bake_from_photos_nn = None

try:
    from core.densepose_texture import iuv_to_atlas, photo_to_body_texture
    _HAS_DP_TEXTURE = True
except Exception as _e:
    logger.warning("densepose_texture unavailable: %s", _e)
    _HAS_DP_TEXTURE = False
    iuv_to_atlas = None
    photo_to_body_texture = None

try:
    from core.mesh_reconstruction import export_glb
    _HAS_MESH_RECON = True
except Exception as _e:
    logger.warning("mesh_reconstruction unavailable: %s", _e)
    _HAS_MESH_RECON = False
    export_glb = None


# ---------------------------------------------------------------------------
# 1. compute_sharpness
# ---------------------------------------------------------------------------

def compute_sharpness(image_path: str) -> float:
    """Return variance of Laplacian as a sharpness score (higher = sharper)."""
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        logger.warning("compute_sharpness: could not read %s", image_path)
        return 0.0
    return float(cv2.Laplacian(img, cv2.CV_64F).var())


# ---------------------------------------------------------------------------
# 2. process_body_scan
# ---------------------------------------------------------------------------

def process_body_scan(
    session_dir: str,
    sensor_log,
    pass_config,
    profile: dict,
    output_dir: str,
) -> dict:
    """
    Analyse frames in session_dir and produce a coverage report.

    Args:
        session_dir: folder containing frame_*.jpg images.
        sensor_log:  raw sensor data (reserved for future orientation use).
        pass_config: scan-pass configuration (reserved for future multi-pass use).
        profile:     body-measurement dict forwarded to mesh builders.
        output_dir:  destination folder for any intermediate artefacts.

    Returns:
        {
          'coverage_report': dict from analyze_coverage(),
          'task_list':       list of {region, action, message},
          'frame_assignments': list of per-frame dicts,
        }
    """
    os.makedirs(output_dir, exist_ok=True)

    frame_paths = sorted(
        glob.glob(os.path.join(session_dir, 'frame_*.jpg'))
    )
    if not frame_paths:
        logger.warning("process_body_scan: no frame_*.jpg found in %s", session_dir)

    frame_assignments = []

    for frame_path in frame_paths:
        frame_name = os.path.basename(frame_path)
        sharpness = compute_sharpness(frame_path)
        assignment = {
            'frame_path': frame_path,
            'frame_name': frame_name,
            'sharpness': sharpness,
            'iuv': None,
            'region_pixels': {},
            'status': 'pending',
        }

        if not _HAS_DENSEPOSE:
            assignment['status'] = 'no_densepose'
            frame_assignments.append(assignment)
            continue

        try:
            iuv_result = predict_iuv(frame_path)
            if iuv_result is None:
                assignment['status'] = 'densepose_no_detection'
                frame_assignments.append(assignment)
                continue

            assignment['iuv'] = iuv_result

            # IUV channel 0 is the part-index (I) map
            # predict_iuv returns a dict with 'iuv' key (H,W,3) numpy array
            if isinstance(iuv_result, dict):
                iuv_array = iuv_result.get('iuv')
            else:
                iuv_array = iuv_result

            if iuv_array is None:
                assignment['status'] = 'densepose_empty'
                frame_assignments.append(assignment)
                continue

            part_map = iuv_array[:, :, 0] if iuv_array.ndim == 3 else iuv_array

            region_pixels = {}
            for region_name, part_ids in BODY_REGIONS.items():
                mask = np.isin(part_map, part_ids)
                region_pixels[region_name] = int(mask.sum())

            assignment['region_pixels'] = region_pixels
            assignment['status'] = 'ok'

        except Exception as exc:
            logger.error("process_body_scan: DensePose failed on %s: %s", frame_name, exc)
            assignment['status'] = 'densepose_error'

        frame_assignments.append(assignment)

    coverage_report = analyze_coverage(frame_assignments)

    task_list = [
        {
            'region': region_name,
            'action': info['action'],
            'message': info['message'],
        }
        for region_name, info in coverage_report.get('regions', {}).items()
        if info['action'] != 'none'
    ]

    return {
        'coverage_report': coverage_report,
        'task_list': task_list,
        'frame_assignments': frame_assignments,
    }


# ---------------------------------------------------------------------------
# 3. analyze_coverage
# ---------------------------------------------------------------------------

def analyze_coverage(frame_assignments: list) -> dict:
    """
    Grade per-region coverage based on accumulated frame assignments.

    Args:
        frame_assignments: list of dicts produced by process_body_scan().

    Returns:
        {
          'regions': {
            region_name: {
              'grade': str,         # 'excellent'|'good'|'fair'|'missing'
              'pixel_count': int,
              'frames_seen': int,
              'avg_sharpness': float,
              'action': str,        # 'none'|'rescan'|'confirm'
              'thumbnail_idx': int, # index into frame_assignments for best frame
              'message': str,
            }
          }
        }
    """
    region_stats = {
        name: {
            'total_pixels': 0,
            'frame_count': 0,
            'sharpness_sum': 0.0,
            'best_pixels': 0,
            'best_idx': -1,
        }
        for name in BODY_REGIONS
    }

    for idx, fa in enumerate(frame_assignments):
        if fa.get('status') != 'ok':
            continue
        sharpness = fa.get('sharpness', 0.0)
        region_pixels = fa.get('region_pixels', {})

        for region_name in BODY_REGIONS:
            px = region_pixels.get(region_name, 0)
            if px == 0:
                continue
            stats = region_stats[region_name]
            stats['total_pixels'] += px
            stats['frame_count'] += 1
            stats['sharpness_sum'] += sharpness
            if px > stats['best_pixels']:
                stats['best_pixels'] = px
                stats['best_idx'] = idx

    regions = {}
    for region_name, stats in region_stats.items():
        total_px = stats['total_pixels']
        frame_count = stats['frame_count']
        avg_sharp = (
            stats['sharpness_sum'] / frame_count if frame_count > 0 else 0.0
        )
        thumbnail_idx = stats['best_idx']

        # Determine grade
        grade = 'missing'
        for grade_name, (px_threshold, frame_threshold) in GRADE_THRESHOLDS.items():
            if total_px >= px_threshold and frame_count >= frame_threshold:
                grade = grade_name
                break

        # Determine action and message
        if grade == 'missing':
            action = 'rescan'
            message = f"No coverage for {region_name}. Please scan this region."
        elif grade == 'fair':
            action = 'confirm'
            message = (
                f"{region_name} has limited coverage ({total_px} px, "
                f"{frame_count} frames). Confirm or rescan."
            )
        else:
            action = 'none'
            message = (
                f"{region_name} coverage is {grade} "
                f"({total_px} px across {frame_count} frames)."
            )

        regions[region_name] = {
            'grade': grade,
            'pixel_count': total_px,
            'frames_seen': frame_count,
            'avg_sharpness': round(avg_sharp, 2),
            'action': action,
            'thumbnail_idx': thumbnail_idx,
            'message': message,
        }

    return {'regions': regions}


# ---------------------------------------------------------------------------
# 4. bake_final_model
# ---------------------------------------------------------------------------

def bake_final_model(
    session_dir: str,
    frame_assignments: list,
    profile: dict,
    output_dir: str,
) -> dict:
    """
    Build mesh, bake texture, and export a GLB from confirmed frames.

    Args:
        session_dir:       original scan directory (used to resolve paths).
        frame_assignments: list produced by process_body_scan().
        profile:           body-measurement dict for build_body_mesh().
        output_dir:        destination for GLB and texture artefacts.

    Returns:
        {
          'glb_path':     str,
          'texture_path': str or None,
          'vertex_count': int,
          'face_count':   int,
        }
    """
    os.makedirs(output_dir, exist_ok=True)

    # --- Select best frame per region ---
    best_per_region: dict[str, dict] = {}
    for fa in frame_assignments:
        if fa.get('status') != 'ok':
            continue
        region_pixels = fa.get('region_pixels', {})
        for region_name in BODY_REGIONS:
            px = region_pixels.get(region_name, 0)
            if px == 0:
                continue
            existing = best_per_region.get(region_name)
            if existing is None or px > existing.get('region_pixels', {}).get(region_name, 0):
                best_per_region[region_name] = fa

    confirmed_frames = {fa['frame_path'] for fa in best_per_region.values()}
    logger.info(
        "bake_final_model: %d unique frames selected for %d regions",
        len(confirmed_frames),
        len(best_per_region),
    )

    # --- Build mesh ---
    if not _HAS_SMPL:
        raise RuntimeError("smpl_fitting is not available; cannot build mesh.")

    image_paths = list(confirmed_frames)
    mesh = build_body_mesh(profile=profile, image_paths=image_paths)

    vertices = mesh['vertices']
    faces = mesh['faces']
    vertex_count = int(mesh.get('num_vertices', len(vertices)))
    face_count = int(mesh.get('num_faces', len(faces)))
    logger.info(
        "bake_final_model: mesh built — %d vertices, %d faces",
        vertex_count, face_count,
    )

    # --- Bake texture ---
    texture_path = None
    uvs = mesh.get('uvs')

    if uvs is not None and (_HAS_TEXTURE_BAKE or _HAS_DP_TEXTURE):
        photo_dict: dict[str, np.ndarray] = {}
        iuv_dict: dict[str, np.ndarray] = {}

        for region_name, fa in best_per_region.items():
            fp = fa['frame_path']
            img = cv2.imread(fp)
            if img is None:
                logger.warning("bake_final_model: could not read %s", fp)
                continue
            view_key = region_name
            photo_dict[view_key] = img
            iuv_raw = fa.get('iuv')
            if iuv_raw is not None:
                iuv_array = iuv_raw.get('iuv') if isinstance(iuv_raw, dict) else iuv_raw
                if iuv_array is not None:
                    iuv_dict[view_key] = iuv_array

        if _HAS_TEXTURE_BAKE and photo_dict and iuv_dict:
            try:
                texture_atlas, _weight = bake_from_photos_nn(
                    vertices, faces, uvs, photo_dict, iuv_dict,
                    texture_size=1024,
                )
                texture_path = os.path.join(output_dir, 'body_texture.png')
                cv2.imwrite(texture_path, texture_atlas)
                logger.info("bake_final_model: texture baked via texture_bake → %s", texture_path)
            except Exception as exc:
                logger.error("bake_final_model: texture_bake failed: %s", exc)

        elif _HAS_DP_TEXTURE and photo_dict:
            try:
                image_paths_list = [fa['frame_path'] for fa in best_per_region.values()]
                iuv_maps_list = []
                for fa in best_per_region.values():
                    iuv_raw = fa.get('iuv')
                    if isinstance(iuv_raw, dict):
                        iuv_maps_list.append(iuv_raw.get('iuv'))
                    else:
                        iuv_maps_list.append(iuv_raw)

                result = photo_to_body_texture(
                    image_paths_list,
                    iuv_maps_list,
                    atlas_size=1024,
                    output_dir=output_dir,
                )
                if isinstance(result, dict) and result.get('atlas') is not None:
                    texture_path = os.path.join(output_dir, 'densepose_texture.png')
                    cv2.imwrite(texture_path, result['atlas'])
                elif isinstance(result, str):
                    texture_path = result
                logger.info("bake_final_model: texture baked via densepose_texture → %s", texture_path)
            except Exception as exc:
                logger.error("bake_final_model: densepose_texture failed: %s", exc)
    else:
        if uvs is None:
            logger.warning("bake_final_model: mesh has no UVs; skipping texture bake.")
        else:
            logger.warning("bake_final_model: no texture module available; skipping bake.")

    # --- Export GLB ---
    if not _HAS_MESH_RECON:
        raise RuntimeError("mesh_reconstruction is not available; cannot export GLB.")

    glb_path = os.path.join(output_dir, 'body_scan.glb')
    texture_img = None
    if texture_path and os.path.exists(texture_path):
        texture_img = cv2.imread(texture_path)

    export_glb(
        vertices,
        faces,
        glb_path,
        normals=True,
        uvs=uvs,
        texture_image=texture_img,
    )
    logger.info("bake_final_model: GLB exported → %s", glb_path)

    return {
        'glb_path': glb_path,
        'texture_path': texture_path,
        'vertex_count': vertex_count,
        'face_count': face_count,
    }


# ---------------------------------------------------------------------------
# 5. merge_recapture
# ---------------------------------------------------------------------------

def merge_recapture(
    session_dir: str,
    new_frames_dir: str,
    region: str,
    existing_assignments: list,
) -> dict:
    """
    Process newly captured frames for a specific region and merge into the
    existing frame assignments, replacing lower-quality entries.

    Args:
        session_dir:          original scan folder (for context / output paths).
        new_frames_dir:       folder containing the new frame_*.jpg files.
        region:               BODY_REGIONS key that was recaptured.
        existing_assignments: current list of frame assignment dicts.

    Returns:
        {
          'coverage_report':   dict from analyze_coverage(),
          'task_list':         list of {region, action, message},
          'frame_assignments': updated list,
        }
    """
    if region not in BODY_REGIONS:
        raise ValueError(
            f"merge_recapture: unknown region '{region}'. "
            f"Valid regions: {list(BODY_REGIONS.keys())}"
        )

    new_frame_paths = sorted(
        glob.glob(os.path.join(new_frames_dir, 'frame_*.jpg'))
    )
    if not new_frame_paths:
        logger.warning(
            "merge_recapture: no frame_*.jpg found in %s", new_frames_dir
        )

    new_assignments = []
    for frame_path in new_frame_paths:
        frame_name = os.path.basename(frame_path)
        sharpness = compute_sharpness(frame_path)
        assignment = {
            'frame_path': frame_path,
            'frame_name': frame_name,
            'sharpness': sharpness,
            'iuv': None,
            'region_pixels': {},
            'status': 'pending',
            'recapture_region': region,
        }

        if not _HAS_DENSEPOSE:
            assignment['status'] = 'no_densepose'
            new_assignments.append(assignment)
            continue

        try:
            iuv_result = predict_iuv(frame_path)
            if iuv_result is None:
                assignment['status'] = 'densepose_no_detection'
                new_assignments.append(assignment)
                continue

            assignment['iuv'] = iuv_result
            if isinstance(iuv_result, dict):
                iuv_array = iuv_result.get('iuv')
            else:
                iuv_array = iuv_result

            if iuv_array is None:
                assignment['status'] = 'densepose_empty'
                new_assignments.append(assignment)
                continue

            part_map = iuv_array[:, :, 0] if iuv_array.ndim == 3 else iuv_array
            region_pixels = {}
            for region_name, part_ids in BODY_REGIONS.items():
                mask = np.isin(part_map, part_ids)
                region_pixels[region_name] = int(mask.sum())

            assignment['region_pixels'] = region_pixels
            assignment['status'] = 'ok'

        except Exception as exc:
            logger.error(
                "merge_recapture: DensePose failed on %s: %s", frame_name, exc
            )
            assignment['status'] = 'densepose_error'

        new_assignments.append(assignment)

    # Remove old frames that were primarily covering this region but had lower
    # pixel counts than at least one new frame for the same region.
    new_best_px = max(
        (fa.get('region_pixels', {}).get(region, 0) for fa in new_assignments),
        default=0,
    )

    kept_existing = []
    replaced_count = 0
    for fa in existing_assignments:
        old_px = fa.get('region_pixels', {}).get(region, 0)
        # Only evict frames whose primary region is the recaptured one and
        # which are clearly outclassed by a new frame.
        if old_px > 0 and old_px < new_best_px:
            replaced_count += 1
            logger.debug(
                "merge_recapture: replacing %s for region %s (%d px → %d px)",
                fa.get('frame_name'), region, old_px, new_best_px,
            )
        else:
            kept_existing.append(fa)

    logger.info(
        "merge_recapture: replaced %d old frame(s) for region '%s' with %d new frame(s)",
        replaced_count, region, len(new_assignments),
    )

    merged = kept_existing + new_assignments
    coverage_report = analyze_coverage(merged)

    task_list = [
        {
            'region': region_name,
            'action': info['action'],
            'message': info['message'],
        }
        for region_name, info in coverage_report.get('regions', {}).items()
        if info['action'] != 'none'
    ]

    return {
        'coverage_report': coverage_report,
        'task_list': task_list,
        'frame_assignments': merged,
    }
