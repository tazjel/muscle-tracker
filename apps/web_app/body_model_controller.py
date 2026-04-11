"""Body model generation, deformation, and video scan upload routes."""
from py4web import action, request, response
from py4web.utils.cors import CORS
from .models import db
from .controllers import (
    _auth_check, _abs_path, _BODY_PROFILE_FIELDS,
    ALLOWED_VIDEO_EXTENSIONS, cors,
)
import os
import logging
import json
import numpy as np

logger = logging.getLogger(__name__)


@action('api/customer/<customer_id:int>/body_model', method=['POST'])
@action.uses(db, cors)
def generate_body_model(customer_id):
    """
    Build a parametric body mesh from the customer's stored body profile
    measurements, export it as GLB (+ OBJ fallback), persist in mesh_model.

    Accepts optional JSON body to override individual measurements:
      { "height_cm": 170, "chest_circumference_cm": 100, ... }

    Returns:
      { status, mesh_id, glb_url, obj_url, volume_cm3, num_vertices, num_faces }
    """
    payload, err = _auth_check()
    if err: return err
    req_id = payload.get('customer_id') or payload.get('sub')
    if req_id != 'admin' and str(req_id) != str(customer_id):
        return dict(status='error', message='Access denied')

    customer = db.customer(customer_id)
    if not customer:
        return dict(status='error', message='Customer not found')

    # Build profile from DB fields
    db_profile = {}
    for field in _BODY_PROFILE_FIELDS:
        val = getattr(customer, field, None)
        if val is not None:
            db_profile[field] = val

    # Merge with any overrides from request body
    try:
        overrides = request.json or {}
    except Exception:
        overrides = {}
    profile = {**db_profile, **overrides}

    # ── Cache check: skip rebuild if profile unchanged ────────────────────────
    import hashlib, json as _json
    profile_hash = hashlib.md5(
        _json.dumps(profile, sort_keys=True, default=str).encode()
    ).hexdigest()[:12]

    latest_mesh = db(
        (db.mesh_model.customer_id == customer_id) &
        (db.mesh_model.model_type == 'body')
    ).select(orderby=~db.mesh_model.id, limitby=(0, 1)).first()

    has_images = any(request.files.get(f'{d}_image') for d in ('front', 'back', 'left', 'right'))
    if not has_images and latest_mesh and latest_mesh.glb_path:
        stored_hash = (latest_mesh.notes or '').split('hash:')[-1].strip() if latest_mesh.notes and 'hash:' in (latest_mesh.notes or '') else ''
        if stored_hash == profile_hash and os.path.exists(latest_mesh.glb_path):
            return dict(
                status='success',
                mesh_id=int(latest_mesh.id),
                glb_url=f'/web_app/api/mesh/{latest_mesh.id}.glb',
                obj_url=f'/web_app/api/mesh/{latest_mesh.id}.obj',
                volume_cm3=latest_mesh.volume_cm3 or 0,
                num_vertices=latest_mesh.num_vertices or 0,
                num_faces=latest_mesh.num_faces or 0,
                viewer_url=f'/web_app/static/viewer3d/index.html?model=/web_app/api/mesh/{latest_mesh.id}.glb',
                cached=True,
            )

    try:
        import time
        from core.smpl_fitting import build_body_mesh
        from core.mesh_reconstruction import export_obj, export_glb

        os.makedirs('meshes', exist_ok=True)
        base_name = f'body_{customer_id}_{int(time.time())}'
        obj_path = os.path.join('meshes', base_name + '.obj')
        glb_path = os.path.join('meshes', base_name + '.glb')

        # ── Pre-load all uploaded images once ─────────────────────────────────
        import cv2 as _cv2
        camera_distance_cm = float(
            request.forms.get('camera_distance_cm', '0') or '100'
        )
        cam_h_mm = float(profile.get('camera_height_from_ground_cm', 65)) * 10

        loaded_images = {}
        for _dir in ('front', 'back', 'left', 'right'):
            _img_file = request.files.get(f'{_dir}_image')
            if not _img_file:
                continue
            _tmp_fn   = f'sil_{customer_id}_{_dir}_{int(time.time())}.jpg'
            _tmp_path = os.path.join('uploads', _tmp_fn)
            try:
                _img_file.save(_tmp_path)
                _img = _cv2.imread(_tmp_path)
                if _img is not None:
                    loaded_images[_dir] = {'path': _tmp_path, 'img': _img}
            except Exception:
                logger.warning('Failed to save uploaded image for %s', _dir)

        # ── Direct SMPL path (when photos uploaded) ──────────────────────────
        _use_direct_smpl = bool(loaded_images)
        smpl_result = None

        if _use_direct_smpl:
            try:
                from core.smpl_direct import generate_direct_smpl
                _dist_mm = camera_distance_cm * 10.0
                smpl_result = generate_direct_smpl(
                    {d: v['img'] for d, v in loaded_images.items()},
                    profile=profile,
                    dist_mm=_dist_mm,
                    cam_h_mm=cam_h_mm,
                )
                if smpl_result:
                    logger.info('Direct SMPL pipeline: %d verts, %.0fmm, %s',
                                smpl_result['num_vertices'],
                                smpl_result['height_mm'],
                                smpl_result['hmr_backend'])
            except Exception:
                logger.exception('Direct SMPL pipeline failed — falling back to Anny')
                smpl_result = None

        if smpl_result:
            # ── Direct SMPL succeeded — export ─────────────────────────────────
            verts = smpl_result['vertices']
            faces = smpl_result['faces']
            uvs_for_glb = smpl_result['uvs']
            texture_image = smpl_result['texture_image']
            _volume = smpl_result['volume_cm3']
            _hmr_backend = smpl_result.get('hmr_backend')
            _hmr_confidence = smpl_result.get('hmr_confidence')

            _normal_map = smpl_result.get('normal_map')

            # ── S-N5: Check for per-region skin textures ──────────────────────
            _skin_dir = os.path.join(os.path.dirname(__file__), '..', 'uploads',
                                     'skin', f'customer_{customer_id}')
            if os.path.isdir(_skin_dir) and uvs_for_glb is not None:
                try:
                    from core.skin_patch import CAPTURE_REGIONS, composite_skin_atlas, generate_skin_normal_map
                    from core.texture_factory import get_part_ids
                    _region_textures = {}
                    for _rname in CAPTURE_REGIONS:
                        _tp = os.path.join(_skin_dir, f'tile_{_rname}.png')
                        if os.path.exists(_tp):
                            _region_textures[_rname] = _cv2.imread(_tp)
                    if _region_textures:
                        _part_ids = get_part_ids(len(uvs_for_glb))
                        _skin_atlas = composite_skin_atlas(
                            uvs_for_glb, _part_ids, faces, _region_textures, atlas_size=2048)
                        texture_image = _skin_atlas
                        _normal_map = generate_skin_normal_map(_skin_atlas, strength=10.0)
                        logger.info('Using %d skin regions for body model texture', len(_region_textures))
                except Exception as _skin_err:
                    logger.warning('Skin region compositing in body_model failed: %s', _skin_err)

            export_obj(verts, faces, obj_path)

            # Generate PBR maps inline (before GLB export so they embed in the file)
            _roughness_map = None
            _ao_map = None
            if texture_image is not None and uvs_for_glb is not None:
                try:
                    from core.texture_factory import generate_roughness_map, generate_ao_map
                    _roughness_map = generate_roughness_map(uvs_for_glb, atlas_size=2048, vertices=verts)
                    if _roughness_map is not None and _roughness_map.dtype != np.uint8:
                        _roughness_map = (_roughness_map * 255).astype(np.uint8)
                    _ao_map = generate_ao_map(verts, faces, uvs_for_glb, atlas_size=2048)
                    if _ao_map is not None and _ao_map.dtype != np.uint8:
                        _ao_map = (_ao_map * 255).astype(np.uint8)
                except Exception as e:
                    logger.warning('PBR map generation failed: %s', e)

            glb_path_out = None
            try:
                export_glb(verts, faces, glb_path,
                           uvs=uvs_for_glb, texture_image=texture_image,
                           normal_map=_normal_map,
                           roughness_map=_roughness_map, ao_map=_ao_map)
                glb_path_out = glb_path
            except Exception:
                logger.warning('GLB export failed for SMPL direct %s', base_name)

            mesh_id = db.mesh_model.insert(
                customer_id=customer_id,
                muscle_group='full_body',
                model_type='body',
                obj_path=obj_path,
                glb_path=glb_path_out,
                volume_cm3=_volume,
                num_vertices=int(len(verts)),
                num_faces=int(len(faces)),
                notes=f'hash:{profile_hash} pipeline:smpl_direct',
            )
            db.commit()

            # Generate PBR textures in background (non-blocking)
            import threading as _pbr_t
            _pbr_kw = dict(
                pbr_dir=os.path.join(os.path.dirname(__file__), '..', 'uploads',
                                     f'pbr_{customer_id}_{mesh_id}'),
                albedo=texture_image.copy() if texture_image is not None else None,
                normal_map=_normal_map.copy() if _normal_map is not None else None,
                uvs=uvs_for_glb.copy() if uvs_for_glb is not None else None,
                verts=verts.copy(),
                faces=faces.copy(),
            )
            def _gen_pbr(kw=_pbr_kw):
                if kw['albedo'] is None or kw['uvs'] is None:
                    return
                if os.path.exists(os.path.join(kw['pbr_dir'], 'body_albedo.png')):
                    return
                try:
                    from core.texture_factory import generate_pbr_textures, save_pbr_textures
                    pbr_set = generate_pbr_textures(kw['albedo'], kw['uvs'], kw['verts'],
                                                    kw['faces'], normal_map=kw.get('normal_map'),
                                                    atlas_size=2048, upscale=True)
                    save_pbr_textures(pbr_set, kw['pbr_dir'])
                    logger.info('PBR textures saved to %s', kw['pbr_dir'])
                except Exception as e:
                    logger.warning('PBR texture generation failed: %s', e)
            _pbr_t.Thread(target=_gen_pbr, daemon=True).start()

            logger.info('VIEWER: http://192.168.100.16:8000/web_app/static/viewer3d/index.html?model=/web_app/api/mesh/%s.glb', mesh_id)
            return dict(
                status='success',
                mesh_id=mesh_id,
                glb_url=f'/web_app/api/mesh/{mesh_id}.glb' if glb_path_out else None,
                obj_url=f'/web_app/api/mesh/{mesh_id}.obj',
                volume_cm3=_volume,
                num_vertices=int(len(verts)),
                num_faces=int(len(faces)),
                pipeline='smpl_direct',
                hmr_backend=_hmr_backend,
                hmr_confidence=_hmr_confidence,
                texture_resolution=(
                    f"{texture_image.shape[1]}x{texture_image.shape[0]}"
                    if texture_image is not None else None
                ),
                viewer_url=f'/web_app/static/viewer3d/index.html?model=/web_app/api/mesh/{mesh_id}.glb',
            )

        # ── Fallback 1: MPFB2 template deformation (preferred) ────────────
        _mpfb2_ok = False
        try:
            from core.body_deform import deform_template
            mesh = deform_template(profile)
            _mpfb2_ok = True
            logger.info('MPFB2 template deformation: %d verts', mesh['num_vertices'])
        except Exception as _mpfb_err:
            logger.warning('MPFB2 deformation failed (%s) — falling back to Anny', _mpfb_err)

        # ── Fallback 2: Anny path ────────────────────────────────────────────
        if not _mpfb2_ok:
            mesh = build_body_mesh(
                profile,
                images=[v['img'] for v in loaded_images.values()] or None,
                directions=list(loaded_images.keys()) or None,
            )

        verts = mesh['vertices']
        faces = mesh['faces']
        _anny_uvs = mesh.get('uvs')

        # Silhouette refinement
        silhouette_views = []
        for _dir, _data in loaded_images.items():
            try:
                from core.silhouette_extractor import extract_silhouette
                contour_mm, _mask, _ratio = extract_silhouette(
                    _data['path'], camera_distance_cm
                )
                if contour_mm is not None and len(contour_mm) >= 4:
                    silhouette_views.append({
                        'contour_mm':       contour_mm,
                        'direction':        _dir,
                        'distance_mm':      camera_distance_cm * 10.0,
                        'camera_height_mm': cam_h_mm,
                        '_tmp_path':        _data['path'],
                        'mask':             _mask,
                    })
                    logger.info('Silhouette extracted: %s (%d pts)', _dir, len(contour_mm))
                else:
                    logger.warning('Silhouette extraction produced no contour for %s', _dir)
            except Exception:
                logger.warning('Silhouette extraction failed for %s image', _dir)

        depth_maps = []
        if silhouette_views:
            from core.silhouette_matcher import fit_mesh_to_silhouettes
            try:
                from core.depth_estimator import estimate_depth
                for sv in silhouette_views:
                    _dir = sv['direction']
                    if _dir in loaded_images:
                        depth_result = estimate_depth(
                            loaded_images[_dir]['img'],
                            camera_distance_mm=sv['distance_mm'],
                            body_mask=sv.get('mask'),
                        )
                        if depth_result:
                            depth_result['direction'] = _dir
                            depth_maps.append(depth_result)
            except Exception:
                logger.warning('Depth estimation failed — fitting without depth maps')

            verts = fit_mesh_to_silhouettes(
                verts, faces, silhouette_views,
                depth_maps=depth_maps or None,
            )

        # Texture projection (Anny/MPFB2 path)
        texture_image = None
        uvs_for_glb   = _anny_uvs
        normal_map    = None
        if silhouette_views:
            try:
                from core.uv_unwrap import compute_uvs, DEFAULT_ATLAS
                from core.texture_projector import project_texture
                if uvs_for_glb is None:
                    uvs_for_glb = compute_uvs(verts, mesh['body_part_ids'], DEFAULT_ATLAS)
                cam_views = []
                for sv in silhouette_views:
                    img = _cv2.imread(sv['_tmp_path'])
                    if img is not None:
                        cam_views.append({
                            'image':           img,
                            'direction':       sv['direction'],
                            'distance_mm':     sv['distance_mm'],
                            'focal_mm':        4.0,
                            'sensor_width_mm': 6.4,
                        })
                if cam_views:
                    texture_image, coverage_map = project_texture(
                        verts, faces, uvs_for_glb, cam_views, atlas_size=1024
                    )
                    try:
                        from core.smpl_direct import delight_texture
                        texture_image = delight_texture(texture_image, coverage_map)
                    except Exception:
                        pass
                    try:
                        from core.texture_enhance import enhance_texture_atlas
                        texture_image = enhance_texture_atlas(
                            texture_image, coverage_mask=coverage_map,
                            upscale=True, inpaint=True, target_size=4096,
                        )
                    except Exception:
                        pass
                    try:
                        from core.mesh_reconstruction import _generate_normal_map
                        normal_map = _generate_normal_map(verts, faces, uvs_for_glb, atlas_size=1024)
                    except Exception:
                        normal_map = None
                    if depth_maps and normal_map is not None:
                        try:
                            from core.texture_enhance import depth_to_normal_map
                            import cv2 as _cv2_n
                            for dm in depth_maps:
                                depth_img = dm.get('depth') or dm.get('depth_map')
                                if depth_img is not None:
                                    depth_normals = depth_to_normal_map(depth_img, atlas_size=1024)
                                    normal_map = _cv2_n.addWeighted(normal_map, 0.7, depth_normals, 0.3, 0)
                        except Exception:
                            pass
            except Exception:
                texture_image = None
                uvs_for_glb   = None

        # Export (Anny path)
        export_obj(verts, faces, obj_path)
        glb_path_out = None
        try:
            if texture_image is not None and uvs_for_glb is not None:
                export_glb(verts, faces, glb_path,
                           uvs=uvs_for_glb, texture_image=texture_image,
                           normal_map=normal_map)
            elif uvs_for_glb is not None:
                export_glb(verts, faces, glb_path, uvs=uvs_for_glb)
            else:
                export_glb(verts, faces, glb_path)
            glb_path_out = glb_path
        except Exception:
            logger.warning('GLB export failed for body model %s', base_name)

        mesh_id = db.mesh_model.insert(
            customer_id=customer_id,
            muscle_group='full_body',
            model_type='body',
            obj_path=obj_path,
            glb_path=glb_path_out,
            volume_cm3=mesh['volume_cm3'],
            num_vertices=int(len(verts)),
            num_faces=int(len(faces)),
            notes=f'hash:{profile_hash} pipeline:{"mpfb2" if _mpfb2_ok else "anny"}',
        )
        db.commit()

        _pipeline_name = 'mpfb2' if _mpfb2_ok else 'anny'
        logger.info('VIEWER: http://192.168.100.16:8000/web_app/static/viewer3d/index.html?model=/web_app/api/mesh/%s.glb', mesh_id)
        return dict(
            status='success',
            mesh_id=mesh_id,
            glb_url=f'/web_app/api/mesh/{mesh_id}.glb' if glb_path_out else None,
            obj_url=f'/web_app/api/mesh/{mesh_id}.obj',
            volume_cm3=mesh['volume_cm3'],
            num_vertices=int(len(verts)),
            num_faces=int(len(faces)),
            pipeline=_pipeline_name,
            silhouette_views_used=len(silhouette_views),
            depth_maps_used=len(depth_maps),
            hmr_backend=mesh.get('hmr_backend'),
            hmr_confidence=mesh.get('hmr_confidence'),
            texture_resolution=(
                f"{texture_image.shape[1]}x{texture_image.shape[0]}"
                if texture_image is not None else None
            ),
            viewer_url=f'/web_app/static/viewer3d/index.html?model=/web_app/api/mesh/{mesh_id}.glb',
        )
    except Exception:
        logger.exception('Body model generation failed for customer %d', customer_id)
        return dict(status='error', message='Body model generation failed')


@action('api/customer/<customer_id:int>/update_deformation', method=['POST'])
@action.uses(db, cors)
def update_deformation(customer_id):
    """Fast re-deform MPFB2 template from partial profile updates.

    Accepts JSON body with any subset of body measurement fields.
    Merges with stored profile, runs deform_template(), exports GLB.
    Returns mesh_id + glb_url for instant viewer reload. Target <2s.
    """
    payload, err = _auth_check()
    if err:
        return err

    try:
        import time as _t
        _t0 = _t.time()
        partial = request.json or {}
        if not partial:
            return dict(status='error', message='No measurements provided')

        # Load stored profile
        customer = db.customer(customer_id)
        if not customer:
            return dict(status='error', message='Customer not found')
        stored = {f: getattr(customer, f, None) for f in _BODY_PROFILE_FIELDS}
        merged = {k: v for k, v in stored.items() if v is not None}
        merged.update({k: v for k, v in partial.items() if k in _BODY_PROFILE_FIELDS})

        # Deform template
        from core.body_deform import deform_template
        from core.mesh_reconstruction import export_glb
        mesh = deform_template(merged)

        os.makedirs('meshes', exist_ok=True)
        base_name = f'body_{customer_id}_live_{int(_t.time())}'
        glb_path = os.path.join('meshes', base_name + '.glb')
        export_glb(mesh['vertices'], mesh['faces'], glb_path, uvs=mesh['uvs'])

        mesh_id = db.mesh_model.insert(
            customer_id=customer_id,
            muscle_group='full_body',
            model_type='body',
            glb_path=glb_path,
            volume_cm3=mesh['volume_cm3'],
            num_vertices=mesh['num_vertices'],
            num_faces=mesh['num_faces'],
            notes='pipeline:mpfb2_live',
        )
        db.commit()

        elapsed = _t.time() - _t0
        logger.info('update_deformation customer=%d mesh=%d %.2fs', customer_id, mesh_id, elapsed)
        return dict(
            status='success',
            mesh_id=mesh_id,
            glb_url=f'/web_app/api/mesh/{mesh_id}.glb',
            viewer_url=f'/web_app/static/viewer3d/index.html?model=/web_app/api/mesh/{mesh_id}.glb',
            volume_cm3=mesh['volume_cm3'],
            elapsed_s=round(elapsed, 2),
        )
    except Exception:
        logger.exception('update_deformation failed for customer %d', customer_id)
        return dict(status='error', message='Deformation failed')


@action('api/customer/<customer_id:int>/upload_video_scan', method=['POST'])
@action.uses(db, cors)
def upload_video_scan(customer_id):
    """
    Upload a capture video, run quality gate, extract best frames, persist session.

    Multipart form fields:
      video         — video file (mp4/mov/avi/mkv)
      tracking_json — optional IMU/pose JSON file
      num_frames    — int, target frame count (default 30)
      strict        — '1' to require 270° arc instead of 90°

    Returns:
      { status, session_id, quality_passed, quality_score, quality_report,
        num_frames_extracted, frame_paths, rejection_reasons }
    """
    payload, err = _auth_check()
    if err: return err
    req_id = payload.get('customer_id') or payload.get('sub')
    if req_id != 'admin' and str(req_id) != str(customer_id):
        return dict(status='error', message='Access denied')

    customer = db.customer(customer_id)
    if not customer:
        return dict(status='error', message='Customer not found')

    video_file = request.files.get('video')
    if not video_file:
        return dict(status='error', message='No video file uploaded')

    ext = os.path.splitext(video_file.filename)[1].lower()
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        return dict(status='error', message=f'Invalid video type: {ext}')

    # Save video
    import time
    os.makedirs('uploads/videos', exist_ok=True)
    ts = int(time.time())
    video_path = os.path.join('uploads', 'videos',
                               f'scan_{customer_id}_{ts}{ext}')
    video_file.file.seek(0)
    with open(video_path, 'wb') as fh:
        fh.write(video_file.file.read())

    # Save optional tracking JSON
    tracking_path = None
    tracking_file = request.files.get('tracking_json')
    if tracking_file:
        tracking_path = os.path.join('uploads', 'videos',
                                      f'tracking_{customer_id}_{ts}.json')
        tracking_file.file.seek(0)
        with open(tracking_path, 'wb') as fh:
            fh.write(tracking_file.file.read())

    num_frames = int(request.forms.get('num_frames', '30') or '30')
    strict     = request.forms.get('strict', '0') == '1'

    try:
        from scripts.quality_gate  import check_video_quality
        from core.frame_selector   import select_best_frames, extract_selected_frames
        from core.video_capture    import get_video_info

        # ── Quality gate ──────────────────────────────────────────────────────
        quality_report = check_video_quality(video_path, tracking_path, strict)
        quality_score  = quality_report.get('score', 0)
        quality_passed = quality_report.get('passed', False)

        # ── Frame selection (even if quality failed — caller may proceed) ─────
        frames_dir = os.path.join('uploads', 'videos',
                                   f'frames_{customer_id}_{ts}')
        selected  = select_best_frames(video_path, num_frames=num_frames,
                                       quality_report=quality_report)
        extracted = extract_selected_frames(video_path, selected, frames_dir)

        # ── Video info ────────────────────────────────────────────────────────
        info = get_video_info(video_path)
        duration_ms = round(info.get('duration_s', 0) * 1000)

        # ── Persist session ───────────────────────────────────────────────────
        session_id = db.video_scan_session.insert(
            customer_id=customer_id,
            video_path=video_path,
            tracking_json_path=tracking_path,
            status='FRAMES_EXTRACTED',
            num_frames=len(extracted),
            duration_ms=duration_ms,
            quality_score=quality_score,
            quality_report=json.dumps(quality_report),
        )
        db.commit()

        return dict(
            status='success',
            session_id=session_id,
            quality_passed=quality_passed,
            quality_score=quality_score,
            rejection_reasons=quality_report.get('rejection_reasons', []),
            num_frames_extracted=len(extracted),
            frame_paths=[f['image_path'] for f in extracted],
            duration_ms=duration_ms,
        )

    except Exception:
        logger.exception('Video scan upload failed for customer %d', customer_id)
        return dict(status='error', message='Video processing failed')
