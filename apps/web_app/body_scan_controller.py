"""Body scan pipeline routes: upload, tasks, thumbnail, confirm, re-capture, finalize, live scan."""
from py4web import action, request, response, abort
from py4web.utils.cors import CORS
from .models import db
from .controllers import cors
import os
import logging
import json
import numpy as np
import cv2
import base64

logger = logging.getLogger(__name__)


@action('api/customer/<customer_id:int>/body_scan_debug', method=['GET'])
def body_scan_debug(customer_id):
    """Debug: confirm body_scan routes loaded."""
    return dict(status='ok', customer_id=customer_id, module=__name__)


@action('api/customer/<customer_id:int>/body_scan', method=['POST'])
@action.uses(db)
def upload_body_scan(customer_id):
    """Upload multi-pass body scan frames with sensor data."""
    import uuid as _uuid
    from core.body_scan_pipeline import process_body_scan

    customer = db.customer(customer_id)
    if not customer:
        return dict(status='error', message='Customer not found')

    session_id = str(_uuid.uuid4())[:8]

    # Create storage directory
    frames_dir = os.path.join('uploads', 'body_scans', f'{customer_id}_{session_id}')
    os.makedirs(frames_dir, exist_ok=True)

    # Save uploaded frames
    frame_count = 0
    for key in sorted(request.vars):
        if key.startswith('frame_'):
            file_data = request.vars[key]
            if hasattr(file_data, 'file'):
                frame_path = os.path.join(frames_dir, f'{key}.jpg')
                with open(frame_path, 'wb') as f:
                    f.write(file_data.file.read())
                frame_count += 1

    if frame_count == 0:
        return dict(status='error', message='No frames uploaded')

    # Parse metadata
    sensor_log = json.loads(request.forms.get('sensor_log', '[]'))
    pass_config = json.loads(request.forms.get('pass_config', '[]'))

    # Save sensor log
    sensor_path = os.path.join(frames_dir, 'sensor_log.json')
    with open(sensor_path, 'w') as f:
        json.dump(sensor_log, f)

    # Create session record
    session_row_id = db.body_scan_session.insert(
        customer_id=customer_id,
        session_id=session_id,
        status='UPLOADED',
        num_frames=frame_count,
        frames_dir=frames_dir,
        sensor_log_path=sensor_path,
        pass_config=json.dumps(pass_config),
    )
    db.commit()

    # Get customer profile for processing
    profile = {
        'height_cm': float(customer.get('height_cm') or 170),
        'weight_kg': float(customer.get('weight_kg') or 70),
        'gender': customer.get('gender') or 'male',
    }

    # Run processing pipeline
    try:
        db(db.body_scan_session.id == session_row_id).update(status='PROCESSING')
        db.commit()

        output_dir = os.path.join(frames_dir, 'output')
        os.makedirs(output_dir, exist_ok=True)

        result = process_body_scan(frames_dir, sensor_log, pass_config, profile, output_dir)

        # Save frame assignments to DB
        for fa in result.get('frame_assignments', []):
            db.body_part_assignment.insert(
                session_id=session_row_id,
                frame_index=fa.get('frame_index', 0),
                frame_path=fa.get('frame_path', ''),
                pass_number=fa.get('pass_number', 1),
                distance_m=fa.get('distance_m', 2.5),
                compass_deg=fa.get('compass_deg', 0),
                body_parts_detected=json.dumps(fa.get('body_parts_detected', [])),
                primary_body_region=fa.get('primary_body_region', ''),
                coverage_score=fa.get('coverage_score', 0),
                sharpness_score=fa.get('sharpness_score', 0),
            )

        coverage_json = json.dumps(result.get('coverage_report', {}))
        db(db.body_scan_session.id == session_row_id).update(
            status='COVERAGE_ANALYZED',
            coverage_report=coverage_json,
        )
        db.commit()

        return dict(
            session_id=session_id,
            status='COVERAGE_ANALYZED',
            num_frames=frame_count,
            coverage_report=result.get('coverage_report', {}),
            task_list=result.get('task_list', []),
        )
    except Exception as e:
        logger.exception('Body scan processing failed')
        db(db.body_scan_session.id == session_row_id).update(status='UPLOADED')
        db.commit()
        return dict(status='error', message=str(e), session_id=session_id)


@action('api/customer/<customer_id:int>/body_scan/<session_id>/tasks', method=['GET'])
@action.uses(db)
def get_body_scan_tasks(customer_id, session_id):
    """Get coverage report and task list for a body scan session."""
    session = db(
        (db.body_scan_session.customer_id == customer_id) &
        (db.body_scan_session.session_id == session_id)
    ).select().first()

    if not session:
        abort(404, 'Session not found')

    coverage_report = json.loads(session.coverage_report or '{}')

    # Build task list from coverage report
    task_list = []
    regions = coverage_report.get('regions', {})
    for region_name, info in regions.items():
        task_list.append({
            'region': region_name,
            'grade': info.get('grade', 'unknown'),
            'action': info.get('action', 'confirm'),
            'thumbnail_idx': info.get('thumbnail_idx', 0),
            'message': info.get('message', ''),
            'pixel_count': info.get('pixel_count', 0),
            'frames_seen': info.get('frames_seen', 0),
        })

    # Get per-frame assignments
    assignments = db(db.body_part_assignment.session_id == session.id).select(
        orderby=db.body_part_assignment.frame_index
    )
    frames = [{
        'index': a.frame_index,
        'region': a.primary_body_region,
        'grade': 'confirmed' if a.user_confirmed else ('rejected' if a.user_confirmed is False else 'pending'),
        'sharpness': a.sharpness_score,
    } for a in assignments]

    return dict(
        session_id=session_id,
        status=session.status,
        coverage_report=coverage_report,
        task_list=task_list,
        frames=frames,
    )


@action('api/customer/<customer_id:int>/body_scan/<session_id>/thumbnail/<frame_idx:int>', method=['GET'])
@action.uses(db)
def get_body_scan_thumbnail(customer_id, session_id, frame_idx):
    """Return a downscaled thumbnail of a scan frame."""
    session = db(
        (db.body_scan_session.customer_id == customer_id) &
        (db.body_scan_session.session_id == session_id)
    ).select().first()

    if not session:
        abort(404, 'Session not found')

    frame_path = os.path.join(session.frames_dir, f'frame_{str(frame_idx).zfill(3)}.jpg')
    if not os.path.exists(frame_path):
        abort(404, 'Frame not found')

    # Resize to 320px wide thumbnail
    img = cv2.imread(frame_path)
    if img is not None:
        h, w = img.shape[:2]
        if w > 320:
            scale = 320 / w
            img = cv2.resize(img, (320, int(h * scale)))
        _, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 80])
        response.headers['Content-Type'] = 'image/jpeg'
        return buf.tobytes()

    # Fallback: serve original
    response.headers['Content-Type'] = 'image/jpeg'
    with open(frame_path, 'rb') as f:
        return f.read()


@action('api/customer/<customer_id:int>/body_scan/<session_id>/confirm', method=['POST'])
@action.uses(db)
def confirm_body_scan(customer_id, session_id):
    """Accept per-region user confirmations and update body_part_assignment records."""
    session = db(
        (db.body_scan_session.customer_id == customer_id) &
        (db.body_scan_session.session_id == session_id)
    ).select().first()

    if not session:
        abort(404, 'Session not found')

    try:
        payload = request.json if request.json else {}
    except Exception:
        return dict(status='error', message='Invalid JSON body')

    confirmations = payload.get('confirmations', [])
    if not isinstance(confirmations, list):
        return dict(status='error', message='confirmations must be an array')

    try:
        for conf in confirmations:
            region = conf.get('region')
            confirmed = conf.get('confirmed')
            correction = conf.get('user_correction') or conf.get('action')

            if region is None or confirmed is None:
                continue

            updates = {'user_confirmed': bool(confirmed)}
            if not confirmed and correction:
                updates['user_correction'] = str(correction)[:32]

            db(
                (db.body_part_assignment.session_id == session.id) &
                (db.body_part_assignment.primary_body_region == region)
            ).update(**updates)

        db.commit()

        # Rebuild task list from coverage report
        coverage_report = json.loads(session.coverage_report or '{}')
        task_list = []
        for region_name, info in coverage_report.get('regions', {}).items():
            task_list.append({
                'region': region_name,
                'grade': info.get('grade', 'unknown'),
                'action': info.get('action', 'confirm'),
                'message': info.get('message', ''),
            })

        return dict(
            session_id=session_id,
            status=session.status,
            task_list=task_list,
        )
    except Exception as e:
        logger.exception('confirm_body_scan failed')
        return dict(status='error', message=str(e))


@action('api/customer/<customer_id:int>/body_scan/<session_id>/re_capture', method=['POST'])
@action.uses(db)
def re_capture_body_scan(customer_id, session_id):
    """Accept new frames for a specific region and merge them into the session."""
    from core.body_scan_pipeline import merge_recapture

    session = db(
        (db.body_scan_session.customer_id == customer_id) &
        (db.body_scan_session.session_id == session_id)
    ).select().first()

    if not session:
        abort(404, 'Session not found')

    region = request.forms.get('region', '').strip()
    if not region:
        return dict(status='error', message='region field is required')

    # Save incoming frames into a recapture sub-directory
    new_frames_dir = os.path.join(session.frames_dir, f'recapture_{region}')
    os.makedirs(new_frames_dir, exist_ok=True)

    frame_count = 0
    for key in sorted(request.vars):
        if key.startswith('frame_'):
            file_data = request.vars[key]
            if hasattr(file_data, 'file'):
                frame_path = os.path.join(new_frames_dir, f'{key}.jpg')
                with open(frame_path, 'wb') as f:
                    f.write(file_data.file.read())
                frame_count += 1

    if frame_count == 0:
        return dict(status='error', message='No frames uploaded')

    try:
        # Build existing assignment list from DB
        existing_rows = db(db.body_part_assignment.session_id == session.id).select(
            orderby=db.body_part_assignment.frame_index
        )
        existing_assignments = [{
            'frame_index': r.frame_index,
            'frame_path': r.frame_path,
            'pass_number': r.pass_number,
            'distance_m': r.distance_m,
            'compass_deg': r.compass_deg,
            'body_parts_detected': json.loads(r.body_parts_detected or '[]'),
            'primary_body_region': r.primary_body_region,
            'coverage_score': r.coverage_score,
            'sharpness_score': r.sharpness_score,
            'status': 'ok',
        } for r in existing_rows]

        result = merge_recapture(session.frames_dir, new_frames_dir, region, existing_assignments)

        # Replace DB assignments with merged result
        db(db.body_part_assignment.session_id == session.id).delete()
        for fa in result.get('frame_assignments', []):
            db.body_part_assignment.insert(
                session_id=session.id,
                frame_index=fa.get('frame_index', 0),
                frame_path=fa.get('frame_path', ''),
                pass_number=fa.get('pass_number', 1),
                distance_m=fa.get('distance_m', 2.5),
                compass_deg=fa.get('compass_deg', 0),
                body_parts_detected=json.dumps(fa.get('body_parts_detected', [])),
                primary_body_region=fa.get('primary_body_region', ''),
                coverage_score=fa.get('coverage_score', 0),
                sharpness_score=fa.get('sharpness_score', 0),
            )

        coverage_json = json.dumps(result.get('coverage_report', {}))
        db(db.body_scan_session.id == session.id).update(
            status='COVERAGE_ANALYZED',
            coverage_report=coverage_json,
        )
        db.commit()

        return dict(
            session_id=session_id,
            coverage_report=result.get('coverage_report', {}),
            task_list=result.get('task_list', []),
        )
    except Exception as e:
        logger.exception('re_capture_body_scan failed')
        return dict(status='error', message=str(e))


@action('api/customer/<customer_id:int>/body_scan/<session_id>/finalize', method=['POST'])
@action.uses(db)
def finalize_body_scan(customer_id, session_id):
    """Bake final GLB model from confirmed frame assignments."""
    from core.body_scan_pipeline import bake_final_model

    session = db(
        (db.body_scan_session.customer_id == customer_id) &
        (db.body_scan_session.session_id == session_id)
    ).select().first()

    if not session:
        abort(404, 'Session not found')

    try:
        db(db.body_scan_session.id == session.id).update(status='BAKING')
        db.commit()

        # Collect confirmed frame assignments (fall back to all if none confirmed)
        confirmed_rows = db(
            (db.body_part_assignment.session_id == session.id) &
            (db.body_part_assignment.user_confirmed == True)
        ).select(orderby=db.body_part_assignment.frame_index)

        if not confirmed_rows:
            confirmed_rows = db(
                db.body_part_assignment.session_id == session.id
            ).select(orderby=db.body_part_assignment.frame_index)

        frame_assignments = [{
            'frame_index': r.frame_index,
            'frame_path': r.frame_path,
            'pass_number': r.pass_number,
            'distance_m': r.distance_m,
            'compass_deg': r.compass_deg,
            'body_parts_detected': json.loads(r.body_parts_detected or '[]'),
            'primary_body_region': r.primary_body_region,
            'coverage_score': r.coverage_score,
            'sharpness_score': r.sharpness_score,
            'status': 'ok',
        } for r in confirmed_rows]

        # Get customer profile
        customer = db.customer(customer_id)
        profile = {
            'height_cm': float((customer and customer.get('height_cm')) or 170),
            'weight_kg': float((customer and customer.get('weight_kg')) or 70),
            'gender': (customer and customer.get('gender')) or 'male',
        }

        output_dir = os.path.join(session.frames_dir, 'output')
        os.makedirs(output_dir, exist_ok=True)

        result = bake_final_model(session.frames_dir, frame_assignments, profile, output_dir)

        glb_path = result.get('glb_path', '')
        texture_path = result.get('texture_path', '')

        db(db.body_scan_session.id == session.id).update(
            status='COMPLETE',
            glb_path=glb_path,
            texture_path=texture_path,
            mesh_path=glb_path,
        )
        db.commit()

        glb_url = ''
        if glb_path and os.path.exists(glb_path):
            glb_url = '/web_app/' + glb_path.replace('\\', '/')

        return dict(
            session_id=session_id,
            status='COMPLETE',
            glb_url=glb_url,
            viewer_url=f'/web_app/body_viewer?session={session_id}',
        )
    except Exception as e:
        logger.exception('finalize_body_scan failed')
        db(db.body_scan_session.id == session.id).update(status='ERROR')
        db.commit()
        return dict(status='error', message=str(e))


# =========================================================================
# LIVE SCAN — continuous frame-by-frame scanning with real-time coverage
# =========================================================================

@action('api/customer/<customer_id:int>/live_scan/start', method=['POST'])
@action.uses(db)
def start_live_scan(customer_id):
    """Create a live scan session. APK streams frames one at a time."""
    import uuid as _uuid
    response.headers['Content-Type'] = 'application/json'
    response.headers['Access-Control-Allow-Origin'] = '*'

    customer = db.customer(customer_id)
    if not customer:
        abort(404, 'Customer not found')

    body = request.json or {}
    distance_min = float(body.get('distance_min_m', 0.1))
    distance_max = float(body.get('distance_max_m', 2.5))

    session_id = str(_uuid.uuid4())[:8]
    frames_dir = os.path.join('uploads', 'live_scans', f'{customer_id}_{session_id}')
    os.makedirs(frames_dir, exist_ok=True)

    db.body_scan_session.insert(
        customer_id=customer_id,
        session_id=session_id,
        status='LIVE_ACTIVE',
        num_frames=0,
        frames_dir=frames_dir,
        scan_mode='live',
        distance_min_m=distance_min,
        distance_max_m=distance_max,
        coverage_pct=0.0,
        coverage_report=json.dumps({'regions': {}}),
    )
    db.commit()

    return dict(
        status='ok',
        session_id=session_id,
        frames_dir=frames_dir,
    )


@action('api/customer/<customer_id:int>/live_scan/<session_id>/frame', method=['POST'])
@action.uses(db)
def upload_live_frame(customer_id, session_id):
    """Receive a single frame + sensor metadata during live scan."""
    from core.body_scan_pipeline import process_single_frame, analyze_coverage, BODY_REGIONS
    response.headers['Content-Type'] = 'application/json'
    response.headers['Access-Control-Allow-Origin'] = '*'

    session = db(
        (db.body_scan_session.customer_id == customer_id) &
        (db.body_scan_session.session_id == session_id) &
        (db.body_scan_session.scan_mode == 'live')
    ).select().first()

    if not session:
        abort(404, 'Live scan session not found')

    frame_file = request.POST.get('frame')
    if not frame_file or not hasattr(frame_file, 'file'):
        return dict(status='error', message='No frame file')

    metadata = {}
    meta_raw = request.POST.get('metadata', '{}')
    try:
        metadata = json.loads(meta_raw)
    except Exception:
        pass

    # Atomic increment to prevent race condition on concurrent frame uploads
    import time as _time
    frame_index = session.num_frames or 0
    frame_name = f'frame_{frame_index:03d}_{int(_time.time()*1000)%10000}.jpg'
    frame_path = os.path.join(session.frames_dir, frame_name)
    with open(frame_path, 'wb') as f:
        f.write(frame_file.file.read())

    try:
        result = process_single_frame(frame_path)
    except Exception as exc:
        logger.error("process_single_frame failed on %s: %s", frame_path, exc)
        result = {'region_pixels': {}, 'primary_region': None, 'sharpness': 0, 'status': 'error'}

    region_pixels = result.get('region_pixels', {})
    primary_region = result.get('primary_region')

    # Save IUV map to disk so finalize can bake textures
    iuv_raw = result.get('iuv')
    iuv_path = None
    if iuv_raw is not None:
        iuv_array = iuv_raw.get('iuv') if isinstance(iuv_raw, dict) else iuv_raw
        if iuv_array is not None:
            iuv_path = frame_path.replace('.jpg', '_iuv.npy')
            np.save(iuv_path, iuv_array)

    # Store full region_pixels JSON so coverage analysis can reconstruct per-region data
    db.body_part_assignment.insert(
        session_id=session.id,
        frame_index=frame_index,
        frame_path=frame_path,
        pass_number=1,
        distance_m=metadata.get('distance_m', 1.0),
        compass_deg=metadata.get('compass_deg', 0),
        body_parts_detected=json.dumps(region_pixels),  # full per-region pixel counts
        primary_body_region=primary_region,
        coverage_score=sum(region_pixels.values()),
        sharpness_score=result.get('sharpness', 0),
        thumbnail_path=iuv_path,  # reuse field to store IUV .npy path
    )

    new_count = frame_index + 1
    update_fields = {'num_frames': new_count}

    if new_count % 5 == 0 or new_count <= 3:
        all_rows = db(
            db.body_part_assignment.session_id == session.id
        ).select(orderby=db.body_part_assignment.frame_index)

        frame_assignments = []
        for r in all_rows:
            # Parse stored region_pixels (could be dict or old-format list)
            rp = {}
            try:
                parsed = json.loads(r.body_parts_detected or '{}')
                if isinstance(parsed, dict):
                    rp = parsed
            except Exception:
                pass
            frame_assignments.append({
                'frame_path': r.frame_path,
                'frame_name': os.path.basename(r.frame_path),
                'sharpness': r.sharpness_score or 0,
                'region_pixels': rp,
                'status': 'ok' if rp else 'no_densepose',
            })

        coverage_report = analyze_coverage(frame_assignments)
        regions = coverage_report.get('regions', {})
        good_count = sum(1 for r in regions.values() if r.get('grade') in ('excellent', 'good'))
        coverage_pct = (good_count / max(len(regions), 1)) * 100

        update_fields['coverage_report'] = json.dumps(coverage_report)
        update_fields['coverage_pct'] = coverage_pct

        if coverage_pct >= 100:
            update_fields['status'] = 'LIVE_SUFFICIENT'

    db(db.body_scan_session.id == session.id).update(**update_fields)
    db.commit()

    return dict(
        status='ok',
        frame_index=frame_index,
        regions_detected=list(k for k, v in region_pixels.items() if v > 0),
    )


@action('api/customer/<customer_id:int>/live_scan/<session_id>/status', method=['GET'])
@action.uses(db)
def live_scan_status(customer_id, session_id):
    """Poll endpoint: returns coverage progress and guidance for the APK."""
    response.headers['Content-Type'] = 'application/json'
    response.headers['Access-Control-Allow-Origin'] = '*'

    session = db(
        (db.body_scan_session.customer_id == customer_id) &
        (db.body_scan_session.session_id == session_id) &
        (db.body_scan_session.scan_mode == 'live')
    ).select().first()

    if not session:
        abort(404, 'Live scan session not found')

    coverage_report = {}
    try:
        coverage_report = json.loads(session.coverage_report or '{}')
    except Exception:
        pass

    regions = coverage_report.get('regions', {})
    guidance = []
    region_labels = {
        'front_torso': 'Face the camera for front torso',
        'back_torso': 'Turn around to show your back',
        'right_arm': 'Show your right arm',
        'left_arm': 'Show your left arm',
        'right_leg': 'Show your right leg',
        'left_leg': 'Show your left leg',
        'head': 'Move closer for head/face detail',
    }
    for region_name, info in regions.items():
        if info.get('action') in ('re-capture', 'confirm') and info.get('grade') in ('missing', 'fair'):
            guidance.append({
                'region': region_name,
                'grade': info.get('grade', 'missing'),
                'message': region_labels.get(region_name, f'Capture {region_name}'),
            })

    for rn in ['front_torso', 'back_torso', 'right_arm', 'left_arm', 'right_leg', 'left_leg', 'head']:
        if rn not in regions:
            guidance.append({
                'region': rn,
                'grade': 'missing',
                'message': region_labels.get(rn, f'Capture {rn}'),
            })

    ready = session.status == 'LIVE_SUFFICIENT' or (session.coverage_pct or 0) >= 100

    return dict(
        session_id=session_id,
        status=session.status,
        num_frames=session.num_frames or 0,
        coverage_pct=session.coverage_pct or 0,
        coverage_report=coverage_report,
        guidance=guidance,
        ready_to_finalize=ready,
    )


@action('api/customer/<customer_id:int>/live_scan/<session_id>/finalize', method=['POST'])
@action.uses(db)
def finalize_live_scan(customer_id, session_id):
    """Bake final GLB from live scan frames."""
    response.headers['Content-Type'] = 'application/json'
    response.headers['Access-Control-Allow-Origin'] = '*'

    session = db(
        (db.body_scan_session.customer_id == customer_id) &
        (db.body_scan_session.session_id == session_id) &
        (db.body_scan_session.scan_mode == 'live')
    ).select().first()

    if not session:
        abort(404, 'Live scan session not found')

    # Return cached result if already complete
    if session.status == 'COMPLETE' and session.glb_path and os.path.exists(session.glb_path):
        glb_url = '/web_app/' + session.glb_path.replace('\\', '/')
        return dict(
            session_id=session_id,
            status='COMPLETE',
            glb_url=glb_url,
            viewer_url=f'/web_app/body_viewer?session={session_id}',
        )

    try:
        db(db.body_scan_session.id == session.id).update(status='BAKING')
        db.commit()

        all_rows = db(
            db.body_part_assignment.session_id == session.id
        ).select(orderby=db.body_part_assignment.frame_index)

        if not all_rows:
            db(db.body_scan_session.id == session.id).update(status='LIVE_ACTIVE')
            db.commit()
            return dict(status='error', message='No frames in session')

        def _safe_json(s, default):
            try:
                return json.loads(s) if s else default
            except Exception:
                return default

        customer = db.customer(customer_id)
        profile = {
            'height_cm': float((customer and customer.get('height_cm')) or 170),
            'weight_kg': float((customer and customer.get('weight_kg')) or 70),
            'gender': (customer and customer.get('gender')) or 'male',
        }

        output_dir = os.path.join(session.frames_dir, 'output')
        os.makedirs(output_dir, exist_ok=True)

        # --- Try RunPod GPU first, fall back to local ---
        RUNPOD_API_KEY = os.environ.get('RUNPOD_API_KEY', '')
        RUNPOD_ENDPOINT = os.environ.get('RUNPOD_ENDPOINT', '')
        use_runpod = bool(RUNPOD_API_KEY and RUNPOD_ENDPOINT)
        logger.info("finalize_live_scan: use_runpod=%s endpoint=%s", use_runpod, RUNPOD_ENDPOINT)

        if use_runpod:
            result = _finalize_via_runpod(
                all_rows, _safe_json, profile, output_dir,
                RUNPOD_API_KEY, RUNPOD_ENDPOINT, session_id,
            )
        else:
            result = _finalize_local(
                all_rows, _safe_json, profile, output_dir, session,
            )

        glb_path = result.get('glb_path', '')
        texture_path = result.get('texture_path', '')

        db(db.body_scan_session.id == session.id).update(
            status='COMPLETE',
            glb_path=glb_path,
            texture_path=texture_path,
            mesh_path=glb_path,
            vertex_count=result.get('vertex_count', 0),
            face_count=result.get('face_count', 0),
        )
        db.commit()

        glb_url = ''
        if glb_path and os.path.exists(glb_path):
            glb_url = '/web_app/' + glb_path.replace('\\', '/')

        return dict(
            session_id=session_id,
            status='COMPLETE',
            glb_url=glb_url,
            viewer_url=f'/web_app/body_viewer?session={session_id}',
        )
    except Exception as e:
        logger.exception('finalize_live_scan failed')
        db(db.body_scan_session.id == session.id).update(status='ERROR')
        db.commit()
        return dict(status='error', message=str(e))


def _finalize_local(all_rows, _safe_json, profile, output_dir, session):
    """Original local CPU bake (fallback)."""
    from core.body_scan_pipeline import bake_final_model
    frame_assignments = []
    for r in all_rows:
        fa = {
            'frame_index': r.frame_index,
            'frame_path': r.frame_path,
            'pass_number': r.pass_number,
            'distance_m': r.distance_m,
            'compass_deg': r.compass_deg,
            'body_parts_detected': _safe_json(r.body_parts_detected, []),
            'primary_body_region': r.primary_body_region,
            'coverage_score': r.coverage_score,
            'sharpness_score': r.sharpness_score,
            'region_pixels': _safe_json(r.body_parts_detected, {}),
            'status': 'ok',
            'iuv': None,
        }
        iuv_path = r.thumbnail_path
        if iuv_path and os.path.exists(iuv_path):
            try:
                fa['iuv'] = {'iuv': np.load(iuv_path)}
            except Exception as exc:
                logger.warning("Could not load IUV from %s: %s", iuv_path, exc)
        frame_assignments.append(fa)
    return bake_final_model(session.frames_dir, frame_assignments, profile, output_dir)


def _finalize_via_runpod(all_rows, _safe_json, profile, output_dir,
                         api_key, endpoint_id, session_id):
    """Send frames to RunPod GPU for HMR2.0 mesh fit + texture bake."""
    import requests as req
    import time

    # Build frames payload — base64 encode each frame image + IUV
    frames_payload = []
    for r in all_rows:
        frame_path = r.frame_path
        if not frame_path or not os.path.exists(frame_path):
            continue
        with open(frame_path, 'rb') as f:
            image_b64 = base64.b64encode(f.read()).decode('ascii')
        iuv_b64 = None
        iuv_path = r.thumbnail_path
        if iuv_path and os.path.exists(iuv_path):
            try:
                iuv_arr = np.load(iuv_path)
                _, buf = cv2.imencode('.png', iuv_arr)
                iuv_b64 = base64.b64encode(buf.tobytes()).decode('ascii')
            except Exception:
                pass
        frames_payload.append({
            'image_b64': image_b64,
            'iuv_b64': iuv_b64,
            'region': r.primary_body_region or f'view_{r.frame_index}',
            'sharpness': float(r.sharpness_score or 0),
        })

    logger.info("RunPod: sending %d frames to live_scan_bake", len(frames_payload))

    # Submit async job
    run_url = f"https://api.runpod.io/v2/{endpoint_id}/run"
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    payload = {
        'input': {
            'action': 'live_scan_bake',
            'frames': frames_payload,
            'profile': profile,
        }
    }
    resp = req.post(run_url, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    job_data = resp.json()
    job_id = job_data.get('id')
    logger.info("RunPod job submitted: %s", job_id)

    # Poll for completion (up to 10 minutes)
    status_url = f"https://api.runpod.io/v2/{endpoint_id}/status/{job_id}"
    deadline = time.time() + 600
    while time.time() < deadline:
        time.sleep(5)
        sr = req.get(status_url, headers=headers, timeout=15)
        sd = sr.json()
        status = sd.get('status', '')
        logger.info("RunPod job %s status: %s", job_id, status)
        if status == 'COMPLETED':
            output = sd.get('output', {})
            if output.get('status') != 'success':
                raise RuntimeError(f"RunPod bake failed: {output.get('message', 'unknown')}")

            # Decode GLB and save
            glb_b64 = output.get('glb_b64', '')
            glb_path = os.path.join(output_dir, 'body_scan.glb')
            with open(glb_path, 'wb') as f:
                f.write(base64.b64decode(glb_b64))
            logger.info("RunPod GLB saved: %s (%d verts, %d faces, %.1f%% coverage)",
                        glb_path, output.get('vertex_count', 0),
                        output.get('face_count', 0),
                        output.get('texture_coverage', 0) * 100)
            return {
                'glb_path': glb_path,
                'texture_path': None,
                'vertex_count': output.get('vertex_count', 0),
                'face_count': output.get('face_count', 0),
            }
        elif status == 'FAILED':
            raise RuntimeError(f"RunPod job failed: {sd.get('error', 'unknown')}")

    raise RuntimeError("RunPod job timed out after 10 minutes")
