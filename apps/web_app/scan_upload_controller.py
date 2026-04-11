"""Scan upload and processing routes."""
from py4web import action, request, response
from py4web.utils.cors import CORS
from .models import db, MUSCLE_GROUPS
from .controllers import (
    _auth_check, _abs_path, _process_and_save_scan,
    ALLOWED_EXTENSIONS, ALLOWED_VIDEO_EXTENSIONS,
    MAX_FILE_SIZE_MB, MAX_FILE_SIZE_BYTES, cors,
)
import os
import logging

from core.keyframe_extractor import extract_keyframes, save_keyframes

logger = logging.getLogger(__name__)


@action('api/upload_scan/<customer_id:int>', method=['POST'])
@action.uses(db, cors)
def upload_scan(customer_id):
    payload, err = _auth_check(customer_id)
    if err: return err

    customer = db.customer(customer_id)
    if not customer:
        return dict(status='error', message='Customer not found')

    front = request.files.get('front')
    side = request.files.get('side')

    if not front or not side:
        return dict(status='error', message='Both front and side images required')

    for f in (front, side):
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            return dict(status='error', message=f'Invalid file type: {ext}. Allowed: {", ".join(ALLOWED_EXTENSIONS)}')

    for f in (front, side):
        f.file.seek(0, 2)
        size = f.file.tell()
        f.file.seek(0)
        if size > MAX_FILE_SIZE_BYTES:
            return dict(status='error', message=f'File too large: {size // (1024*1024)}MB (max {MAX_FILE_SIZE_MB}MB)')

    muscle_group = request.forms.get('muscle_group', 'bicep')
    scan_side = request.forms.get('side', 'front')
    marker_size = float(request.forms.get('marker_size', '20.0'))
    volume_model = request.forms.get('volume_model', 'elliptical_cylinder')
    shape_template = request.forms.get('shape_template')
    camera_distance_cm = float(request.forms.get('camera_distance_cm', '0') or '0') or None

    if muscle_group not in MUSCLE_GROUPS:
        return dict(status='error', message=f'Invalid muscle group. Options: {MUSCLE_GROUPS}')

    front_filename = db.muscle_scan.img_front.store(front.file, front.filename)
    side_filename = db.muscle_scan.img_side.store(side.file, side.filename)

    front_path = _abs_path('uploads', front_filename)
    side_path = _abs_path('uploads', side_filename)

    res = _process_and_save_scan(customer, customer_id, front_path, side_path, front_filename, side_filename, muscle_group, scan_side, marker_size, volume_model, shape_template, camera_distance_cm=camera_distance_cm)

    if res.get('status') == 'success':
        db.audit_log.insert(
            customer_id=customer_id,
            action='upload_scan',
            resource_id=str(res.get('scan_id')),
            ip_address=request.environ.get('REMOTE_ADDR', 'unknown')
        )
        db.commit()

    return res


@action('api/upload_quad_scan/<customer_id:int>', method=['POST'])
@action.uses(db, cors)
def upload_quad_scan(customer_id):
    """Accept 4 images (front, back, left_side, right_side) from dual-device scan."""
    payload, err = _auth_check(customer_id)
    if err: return err

    customer = db.customer(customer_id)
    if not customer:
        return dict(status='error', message='Customer not found')

    front = request.files.get('front')
    back = request.files.get('back')
    left_side = request.files.get('left_side')
    right_side = request.files.get('right_side')

    if not all([front, back, left_side, right_side]):
        return dict(status='error', message='All 4 images required: front, back, left_side, right_side')

    for f in (front, back, left_side, right_side):
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            return dict(status='error', message=f'Invalid file type: {ext}')
        f.file.seek(0, 2)
        size = f.file.tell()
        f.file.seek(0)
        if size > MAX_FILE_SIZE_BYTES:
            return dict(status='error', message=f'File too large: {size // (1024*1024)}MB (max {MAX_FILE_SIZE_MB}MB)')

    muscle_group = request.forms.get('muscle_group', 'quadricep')
    camera_distance_cm = float(request.forms.get('camera_distance_cm', '0') or '0') or None
    scan_side = request.forms.get('side', 'front')
    marker_size = float(request.forms.get('marker_size', '20.0'))
    volume_model = request.forms.get('volume_model', 'elliptical_cylinder')
    shape_template = request.forms.get('shape_template')

    if muscle_group not in MUSCLE_GROUPS:
        return dict(status='error', message=f'Invalid muscle group. Options: {MUSCLE_GROUPS}')

    # Store all 4 images
    front_fn = db.muscle_scan.img_front.store(front.file, front.filename)
    left_fn = db.muscle_scan.img_side.store(left_side.file, left_side.filename)
    back_fn = db.muscle_scan.img_front.store(back.file, back.filename)
    right_fn = db.muscle_scan.img_side.store(right_side.file, right_side.filename)

    front_path = _abs_path('uploads', front_fn)
    left_path = _abs_path('uploads', left_fn)
    back_path = _abs_path('uploads', back_fn)
    right_path = _abs_path('uploads', right_fn)

    # Process Pair A: front + left_side
    res_a = _process_and_save_scan(customer, customer_id, front_path, left_path,
                                    front_fn, left_fn, muscle_group, scan_side,
                                    marker_size, volume_model, shape_template,
                                    camera_distance_cm=camera_distance_cm)

    # Process Pair B: back + right_side
    res_b = _process_and_save_scan(customer, customer_id, back_path, right_path,
                                    back_fn, right_fn, muscle_group, 'back',
                                    marker_size, volume_model, shape_template,
                                    camera_distance_cm=camera_distance_cm)

    # Average results from both pairs for higher confidence
    if res_a.get('status') == 'success' and res_b.get('status') == 'success':
        avg_vol = (res_a.get('volume_cm3', 0) + res_b.get('volume_cm3', 0)) / 2
        avg_circ = None
        if res_a.get('circumference_cm') and res_b.get('circumference_cm'):
            avg_circ = (res_a['circumference_cm'] + res_b['circumference_cm']) / 2

        db.audit_log.insert(
            customer_id=customer_id,
            action='upload_quad_scan',
            resource_id=f"{res_a.get('scan_id')},{res_b.get('scan_id')}",
            ip_address=request.environ.get('REMOTE_ADDR', 'unknown')
        )
        db.commit()

        return dict(
            status='success',
            scan_mode='quad',
            scan_id_front=res_a.get('scan_id'),
            scan_id_back=res_b.get('scan_id'),
            volume_cm3=round(avg_vol, 2),
            volume_front_cm3=res_a.get('volume_cm3'),
            volume_back_cm3=res_b.get('volume_cm3'),
            circumference_cm=round(avg_circ, 2) if avg_circ else res_a.get('circumference_cm'),
            calibrated=res_a.get('calibrated', False),
            shape_score=res_a.get('shape_score'),
            shape_grade=res_a.get('shape_grade'),
            growth_pct=res_a.get('growth_pct'),
            definition_score=res_a.get('definition_score'),
            definition_grade=res_a.get('definition_grade'),
            annotated_img_url=res_a.get('annotated_img_url'),
        )
    elif res_a.get('status') == 'success':
        return dict(**res_a, scan_mode='quad_partial', note='Back pair failed, using front pair only')
    elif res_b.get('status') == 'success':
        return dict(**res_b, scan_mode='quad_partial', note='Front pair failed, using back pair only')
    else:
        return dict(status='error', message='Both scan pairs failed')


@action('api/upload_video/<customer_id:int>', method=['POST'])
@action.uses(db, cors)
def upload_video(customer_id):
    payload, err = _auth_check(customer_id)
    if err: return err

    customer = db.customer(customer_id)
    if not customer:
        return dict(status='error', message='Customer not found')

    video = request.files.get('video')
    if not video:
        return dict(status='error', message='Video file required')

    ext = os.path.splitext(video.filename)[1].lower()
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        return dict(status='error', message=f'Invalid video type: {ext}')

    video_filename = db.muscle_scan.img_front.store(video.file, video.filename)
    video_path = _abs_path('uploads', video_filename)

    frames = extract_keyframes(video_path, num_frames=3)
    if len(frames) < 2:
        return dict(status='error', message='Failed to extract enough keyframes from video')

    uploads_dir = _abs_path('uploads')
    kf_paths = save_keyframes(frames, uploads_dir)

    front_path = kf_paths[0]
    side_path = kf_paths[1]
    front_filename = os.path.basename(front_path)
    side_filename = os.path.basename(side_path)

    muscle_group = request.forms.get('muscle_group', 'bicep')
    scan_side = request.forms.get('side', 'front')
    marker_size = float(request.forms.get('marker_size', '20.0'))
    volume_model = request.forms.get('volume_model', 'elliptical_cylinder')
    shape_template = request.forms.get('shape_template')
    camera_distance_cm = float(request.forms.get('camera_distance_cm', '0') or '0') or None

    res = _process_and_save_scan(customer, customer_id, front_path, side_path, front_filename, side_filename, muscle_group, scan_side, marker_size, volume_model, shape_template, camera_distance_cm=camera_distance_cm)

    if res.get('status') == 'success':
        db.audit_log.insert(
            customer_id=customer_id,
            action='upload_video',
            resource_id=str(res.get('scan_id')),
            ip_address=request.environ.get('REMOTE_ADDR', 'unknown')
        )
        db.commit()

    return res
