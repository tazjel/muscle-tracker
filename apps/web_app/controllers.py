from py4web import action, request, response, abort, URL
from ombott import static_file
from py4web.utils.cors import CORS
from .models import db, MUSCLE_GROUPS, VOLUME_MODELS
import os
import sys
import logging
import json
import base64
import cv2
import numpy as np
from datetime import datetime

logger = logging.getLogger(__name__)

# --- STATIC ASSETS ---

@action('meshes/<filename:path>', method=['GET'])
def serve_mesh(filename):
    """Serve models from the root meshes/ directory."""
    logger.info("Serving mesh: %s", filename)
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'meshes'))
    return static_file(filename, root=root)


@action('uploads/<filepath:path>', method=['GET'])
def serve_upload(filepath):
    """Serve files from the uploads/ directory (GLB models, textures, etc.)."""
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'uploads'))
    return static_file(filepath, root=root)


@action('assets/<filename:path>', method=['GET'])
def serve_asset(filename):
    """Serve HDRI/textures from the root assets/ directory."""
    logger.info("Serving asset: %s", filename)
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'assets'))
    return static_file(filename, root=root)

# Initialize CORS
cors = CORS()

# Add project root to path for core imports
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

def _abs_path(*parts):
    """Return an absolute path relative to the project root."""
    return os.path.join(PROJECT_ROOT, *parts)
from core.auth import create_token, verify_token as verify_jwt, hash_password, verify_password
from core.vision_medical import analyze_muscle_growth
from core.volumetrics import estimate_muscle_volume, compare_volumes
from core.volumetrics_advanced import slice_volume_estimate
from core.segmentation import score_muscle_shape, AVAILABLE_TEMPLATES
from core.symmetry import compare_symmetry
from core.progress import analyze_trend, calculate_correlation
from core.pose_analyzer import analyze_pose
from core.report_generator import generate_clinical_report
from core.keyframe_extractor import extract_keyframes, save_keyframes
from core.muscle_classifier import classify_with_confidence
from core.circumference import estimate_circumference
from core.measurement_overlay import draw_measurement_overlay
try:
    from core.definition_scorer import score_muscle_definition
    _HAS_DEFINITION_SCORER = True
except ImportError:
    _HAS_DEFINITION_SCORER = False

# File upload constraints
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff'}
ALLOWED_VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv'}
MAX_FILE_SIZE_MB = 15
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


# --- AUTH ---

@action('api/login', method=['POST'])
@action('api/auth/token', method=['POST'])
@action.uses(db, cors)
def login():
    """
    Issue a JWT token. Accepts email or customer_id.
    If the customer has a password_hash set, password is required.
    """
    data = request.json or {}
    email = data.get('email', '').strip()
    customer_id = data.get('customer_id')
    password = data.get('password', '')

    customer = None
    if email:
        customer = db(db.customer.email == email).select().first()
    elif customer_id:
        customer = db.customer(customer_id)

    if not customer:
        response.status = 404
        return dict(status='error', message='Customer not found')

    # If customer has a password set, require it
    if customer.password_hash:
        if not password or not verify_password(password, customer.password_hash):
            response.status = 401
            return dict(status='error', message='Invalid password')

    token = create_token(customer.id, role='user')
    return dict(status='success', token=token, customer_id=customer.id, name=customer.name)


@action('api/auth/admin_token', method=['POST'])
@action.uses(cors)
def auth_admin_token():
    """
    Issue an admin JWT token.
    """
    data = request.json or {}
    secret = data.get('admin_secret', '')
    expected = os.environ.get('MUSCLE_TRACKER_ADMIN_SECRET', 'dev-admin-secret')

    if not secret or secret != expected:
        abort(401, "Invalid admin secret")

    token = create_token('admin', role='admin')
    return dict(status='success', token=token, role='admin')


# --- DASHBOARD ---

@action('api/health', method=['GET'])
def health_check():
    """Health check endpoint for Docker/load balancer."""
    return dict(
        status='ok',
        version='4.0',
        timestamp=str(datetime.utcnow()),
    )


@action('api/gpu_status', method=['GET'])
@action.uses(cors)
def gpu_status():
    """Check RunPod GPU worker availability."""
    try:
        from core.cloud_gpu import is_configured, RUNPOD_ENDPOINT
        if not is_configured():
            return dict(status='success', gpu='unavailable',
                       message='RunPod not configured (RUNPOD_API_KEY or RUNPOD_ENDPOINT missing)')

        import urllib.request, json, os
        api_key = os.environ.get('RUNPOD_API_KEY', '')
        url = f"https://api.runpod.ai/v2/{RUNPOD_ENDPOINT}/health"
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        }
        req = urllib.request.Request(url, headers=headers, method='GET')
        with urllib.request.urlopen(req, timeout=10) as resp:
            health = json.loads(resp.read().decode())

        workers = health.get('workers', {})
        return dict(
            status='success',
            gpu='available',
            endpoint=RUNPOD_ENDPOINT,
            workers_ready=workers.get('ready', 0),
            workers_running=workers.get('running', 0),
            workers_throttled=workers.get('throttled', 0),
            jobs_in_queue=health.get('jobs', {}).get('inQueue', 0),
            tasks_supported=['hmr', 'rembg', 'dsine', 'texture_upscale', 'pbr_textures', 'train_splat', 'anchor_splat', 'bake_cinematic'],
        )

    except Exception as e:
        return dict(status='success', gpu='error', message=str(e))


@action('index')
@action.uses('index.html', db)
def index():
    customers = db(db.customer.is_active == True).select(orderby=db.customer.name)
    return dict(customers=customers)


# --- CUSTOMER MANAGEMENT ---

@action('api/customers', method=['GET'])
@action.uses(db, cors)
def list_customers():
    """List all customers with scan counts (for customer selector)."""
    payload, err = _auth_check()
    if err: return err
    rows = db(db.customer.id > 0).select(
        db.customer.id,
        db.customer.name,
        db.customer.email,
        db.customer.gender,
        db.customer.profile_completed,
        orderby=db.customer.id
    )
    result = []
    for r in rows:
        mesh_count = db(db.mesh_model.customer_id == r.id).count()
        result.append(dict(
            id=int(r.id),
            name=r.name or f'Customer {r.id}',
            email=r.email,
            gender=r.gender if r.gender else '',
            profile_completed=bool(r.profile_completed),
            mesh_count=mesh_count,
        ))
    return dict(status='success', customers=result)


@action('api/customers', method=['POST'])
@action.uses(db, cors)
def create_customer():
    # Registration is public
    name = request.json.get('name', '').strip()
    email = request.json.get('email', '').strip()

    if not name or not email:
        return dict(status='error', message='Name and email are required')

    existing = db(db.customer.email == email).count()
    if existing > 0:
        return dict(status='error', message='Email already registered')

    customer_id = db.customer.insert(
        name=name,
        email=email,
        date_of_birth=request.json.get('date_of_birth'),
        gender=request.json.get('gender'),
        height_cm=request.json.get('height_cm'),
        weight_kg=request.json.get('weight_kg'),
        notes=request.json.get('notes'),
    )
    db.commit()
    return dict(status='success', customer_id=customer_id)


# --- SCAN UPLOAD & PROCESSING ---

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


def _process_and_save_scan(customer, customer_id, front_path, side_path, front_filename, side_filename, muscle_group, scan_side, marker_size, volume_model, shape_template, camera_distance_cm=None):
    try:
        user_height_cm = customer.height_cm
        res_f = analyze_muscle_growth(front_path, front_path, marker_size, align=False, muscle_group=muscle_group, user_height_cm=user_height_cm, camera_distance_cm=camera_distance_cm)
        res_s = analyze_muscle_growth(side_path, side_path, marker_size, align=False, muscle_group=muscle_group, user_height_cm=user_height_cm, camera_distance_cm=camera_distance_cm)

        if "error" in res_f:
            error_msg = res_f.get("error", "")
            return dict(status='error', message=f'Vision analysis failed: {error_msg}')

        # Calibration ratio (px to mm)
        ratio_mm_per_px = res_f.get('ratio', 1.0)
        pixels_per_cm = 10.0 / ratio_mm_per_px if ratio_mm_per_px > 0 else 1.0

        unit = "mm" if res_f.get("calibrated") else "px"
        area = res_f['metrics'].get(f'area_a_{unit}2', 0.0)
        width = res_f['metrics'].get(f'width_a_{unit}', 0.0)
        height = res_f['metrics'].get(f'height_a_{unit}', 0.0)

        # Side view — if analysis failed (no person), estimate depth as 65% of front
        side_ok = "error" not in res_s
        if side_ok:
            area_side = res_s['metrics'].get(f'area_a_{unit}2', 0.0)
            width_side = res_s['metrics'].get(f'width_a_{unit}', 0.0)
            if width_side <= 0:
                side_ok = False
        if not side_ok:
            width_side = width * 0.65
            area_side = area * 0.65
            logger.info("Side view unusable — estimating depth as 65%% of front width")

        # 3. Calculate volume
        vol_result = estimate_muscle_volume(area, area_side, width, width_side, volume_model)
        vol_cm3 = vol_result.get('volume_cm3', 0.0)

        # Advanced slice-based volume
        adv_vol = None
        if res_f.get('calibrated') and 'raw_data' in res_f:
            contour = res_f['raw_data'].get('contour_a')
            if contour is not None:
                adv_vol = slice_volume_estimate(contour, pixels_per_cm)

        # 4. Shape scoring (if template specified)
        shape_score = None
        shape_grade = None
        if shape_template and shape_template in AVAILABLE_TEMPLATES:
            contour = res_f['raw_data']['contour_a']
            shape_result = score_muscle_shape(contour, shape_template)
            shape_score = shape_result.get('score')
            shape_grade = shape_result.get('grade')

        # 5. Circumference estimate — prefer two-view elliptical from calibrated widths
        circumference_cm = None
        contour_front = res_f.get('raw_data', {}).get('contour_a') if 'raw_data' in res_f else None
        if res_f.get('calibrated') and width > 0 and width_side > 0:
            from core.circumference import estimate_circumference_from_two_views
            circ_mm = estimate_circumference_from_two_views(width, width_side)
            circumference_cm = round(circ_mm / 10.0, 2) if circ_mm > 0 else None
        elif contour_front is not None:
            pixels_per_mm = 1.0 / ratio_mm_per_px if ratio_mm_per_px > 0 else 1.0
            if pixels_per_mm > 0:
                circ_result = estimate_circumference(contour_front, pixels_per_mm)
                circumference_cm = circ_result.get('circumference_cm')

        # 6. Definition score — use the processed image that contour was extracted from
        processed_front_img = res_f.get('raw_data', {}).get('img_a')
        definition_score = None
        definition_grade = None
        if _HAS_DEFINITION_SCORER and contour_front is not None and processed_front_img is not None:
            try:
                def_result = score_muscle_definition(processed_front_img, contour_front, muscle_group)
                definition_score = def_result.get('overall_definition')
                definition_grade = def_result.get('grade')
            except Exception:
                logger.warning("Definition scoring failed, skipping", exc_info=True)

        # 7. Measurement overlay — save annotated image
        annotated_filename = None
        if contour_front is not None:
            try:
                front_img = processed_front_img if processed_front_img is not None else cv2.imread(front_path)
                if front_img is not None:
                    annotated = draw_measurement_overlay(
                        front_img, contour_front,
                        res_f.get('metrics', {}),
                        calibrated=res_f.get('calibrated', False)
                    )
                    ann_name = 'ann_' + front_filename
                    ann_path = os.path.join('uploads', ann_name)
                    cv2.imwrite(ann_path, annotated)
                    annotated_filename = ann_name
            except Exception:
                logger.warning("Measurement overlay failed, skipping", exc_info=True)

        growth_pct = None
        volume_delta = None
        # Only compare against calibrated scans — uncalibrated volumes are
        # in pixel units and would produce misleading growth percentages.
        prev_scan = db(
            (db.muscle_scan.customer_id == customer_id) &
            (db.muscle_scan.muscle_group == muscle_group) &
            (db.muscle_scan.calibrated == True)
        ).select(orderby=~db.muscle_scan.scan_date, limitby=(0, 1)).first()

        if prev_scan and prev_scan.volume_cm3:
            volume_delta = vol_cm3 - prev_scan.volume_cm3
            if prev_scan.volume_cm3 > 0:
                growth_pct = (volume_delta / prev_scan.volume_cm3) * 100

        detection_conf = res_f.get('confidence', {}).get('detection', 0)
        scan_id = db.muscle_scan.insert(
            customer_id=customer_id,
            muscle_group=muscle_group,
            side=scan_side,
            img_front=front_filename,
            img_side=side_filename,
            marker_size_mm=marker_size,
            calibrated=res_f.get('calibrated', False),
            area_mm2=area,
            width_mm=width,
            height_mm=height,
            volume_cm3=vol_cm3,
            volume_model=volume_model,
            shape_score=shape_score,
            shape_grade=shape_grade,
            growth_pct=growth_pct,
            volume_delta_cm3=volume_delta,
            detection_confidence=detection_conf,
            circumference_cm=circumference_cm,
            definition_score=definition_score,
            definition_grade=definition_grade,
            annotated_img=annotated_filename,
        )
        db.commit()

        return dict(
            status='success',
            scan_id=scan_id,
            volume_cm3=vol_cm3,
            advanced_volume=adv_vol,
            area_mm2=area,
            shape_score=shape_score,
            shape_grade=shape_grade,
            growth_pct=round(growth_pct, 2) if growth_pct else None,
            volume_delta_cm3=round(volume_delta, 2) if volume_delta else None,
            calibrated=res_f.get('calibrated', False),
            circumference_cm=round(circumference_cm, 2) if circumference_cm else None,
            circumference_inches=round(circumference_cm / 2.54, 2) if circumference_cm else None,
            definition_score=definition_score,
            definition_grade=definition_grade,
            annotated_img_url=f'/uploads/{annotated_filename}' if annotated_filename else None,
        )
    except Exception:
        logger.exception("Scan processing failed for customer %d", customer_id)
        return dict(status='error', message='Scan processing failed. Please try again.')


# --- REPORTS ---

@action('api/customer/<customer_id:int>/scans', method=['GET'])
@action.uses(db, cors)
def customer_scans(customer_id):
    payload, err = _auth_check(customer_id)
    if err: return err

    customer = db.customer(customer_id)
    if not customer:
        return dict(status='error', message='Customer not found')

    muscle_group = request.params.get('muscle_group')
    query = db.muscle_scan.customer_id == customer_id
    if muscle_group:
        query &= db.muscle_scan.muscle_group == muscle_group

    scans = db(query).select(orderby=~db.muscle_scan.scan_date).as_list()
    for scan in scans:
        scan.pop('img_front', None)
        scan.pop('img_side', None)

    return dict(status='success', customer=customer.name, scans=scans)


@action('api/customer/<customer_id:int>/report/<scan_id:int>', method=['GET'])
@action.uses(db, cors)
def generate_report(customer_id, scan_id):
    payload, err = _auth_check(customer_id)
    if err: return err

    customer = db.customer(customer_id)
    if not customer:
        abort(404, "Customer not found")

    scan = db.muscle_scan(scan_id)
    if not scan or scan.customer_id != customer_id:
        abort(404, "Scan not found")

    import tempfile
    fd, temp_path = tempfile.mkstemp(suffix='.png')
    os.close(fd)

    unit_prefix = "mm" if scan.calibrated else "px"
    scan_result = {
        "status": "Success",
        "verdict": "Stable",
        "metrics": {
            f"area_a_{unit_prefix}2": scan.area_mm2 or 0,
            f"width_a_{unit_prefix}": scan.width_mm or 0,
            f"height_a_{unit_prefix}": scan.height_mm or 0,
            "growth_pct": scan.growth_pct or 0,
        },
        "confidence": {"detection": scan.detection_confidence or 0},
    }

    volume_result = {
        "volume_cm3": scan.volume_cm3 or 0,
        "model": scan.volume_model or "elliptical_cylinder",
        "height_mm": scan.height_mm or 0,
    }

    shape_result = None
    if scan.shape_score is not None:
        shape_result = {"score": scan.shape_score, "grade": scan.shape_grade}

    # v5 extras
    annotated_bgr = None
    if scan.annotated_img:
        ann_path = os.path.join('uploads', scan.annotated_img)
        if os.path.exists(ann_path):
            annotated_bgr = cv2.imread(ann_path)

    definition_result = None
    if scan.definition_score is not None:
        definition_result = {'overall_definition': scan.definition_score,
                             'grade': scan.definition_grade}

    # Latest body composition for this customer
    body_comp_row = db(
        db.body_composition_log.customer_id == customer_id
    ).select(orderby=~db.body_composition_log.assessed_on, limitby=(0, 1)).first()
    body_comp_data = None
    if body_comp_row:
        body_comp_data = {
            'bmi': body_comp_row.bmi,
            'estimated_body_fat_pct': body_comp_row.body_fat_pct,
            'lean_mass_kg': body_comp_row.lean_mass_kg,
            'waist_to_hip_ratio': body_comp_row.waist_hip_ratio,
            'classification': body_comp_row.classification,
            'confidence': body_comp_row.confidence,
        }

    # Latest mesh preview for this customer + muscle group
    mesh_prev_path = None
    mesh_row = db(
        (db.mesh_model.customer_id == customer_id) &
        (db.mesh_model.muscle_group == scan.muscle_group)
    ).select(orderby=~db.mesh_model.created_on, limitby=(0, 1)).first()
    if mesh_row and mesh_row.preview_path and os.path.exists(mesh_row.preview_path):
        mesh_prev_path = mesh_row.preview_path

    try:
        pdf_path = generate_clinical_report(
            scan_result,
            volume_result=volume_result,
            shape_result=shape_result,
            output_path=temp_path,
            patient_name=customer.name,
            scan_date=str(scan.scan_date)[:10],
            circumference_cm=scan.circumference_cm,
            definition_result=definition_result,
            body_composition=body_comp_data,
            annotated_image_bgr=annotated_bgr,
            mesh_preview_path=mesh_prev_path,
        )
        response.headers['Content-Type'] = 'application/pdf'
        with open(pdf_path, 'rb') as f:
            data = f.read()
        
        db.audit_log.insert(
            customer_id=customer_id,
            action='get_report',
            resource_id=str(scan_id),
            ip_address=request.environ.get('REMOTE_ADDR', 'unknown')
        )
        db.commit()
        
        return data
    finally:
        # We need to check both temp_path and pdf_path because the generator 
        # might append .pdf if we didn't include it.
        for p in (temp_path, temp_path + ".pdf"):
            if os.path.exists(p):
                os.remove(p)


@action('api/customer/<customer_id:int>/progress', method=['GET'])
@action.uses(db, cors)
def customer_progress(customer_id):
    payload, err = _auth_check(customer_id)
    if err: return err

    customer = db.customer(customer_id)
    if not customer:
        return dict(status='error', message='Customer not found')

    muscle_group = request.params.get('muscle_group')
    query = db.muscle_scan.customer_id == customer_id
    if muscle_group:
        query &= db.muscle_scan.muscle_group == muscle_group

    scans = db(query).select(orderby=db.muscle_scan.scan_date).as_list()
    trend = analyze_trend(scans)

    health_logs = db(db.health_log.customer_id == customer_id).select().as_list()
    correlation = None
    if len(health_logs) >= 3:
        correlation = calculate_correlation(scans, health_logs)

    # ── Circumference trend ──────────────────────────────────────────────────
    circumference_trend = [
        {
            'date':          str(s.get('scan_date', ''))[:10],
            'muscle_group':  s.get('muscle_group'),
            'circumference_cm': s.get('circumference_cm'),
        }
        for s in scans if s.get('circumference_cm') is not None
    ]

    # Circumference regression projection (same logic as volume)
    circ_projection = None
    if len(circumference_trend) >= 2:
        from core.progress import _linear_regression, _parse_date
        circ_dates  = [_parse_date(r['date']) for r in circumference_trend]
        circ_vals   = [r['circumference_cm'] for r in circumference_trend]
        day0        = circ_dates[0]
        offsets     = [(d - day0).days for d in circ_dates]
        slope, _    = _linear_regression(offsets, circ_vals)
        circ_latest = circ_vals[-1]
        circ_projection = {
            'direction':      'gaining' if slope > 0.001 else 'losing' if slope < -0.001 else 'stable',
            'daily_rate_cm':  round(slope, 4),
            'projected_30d_cm': round(circ_latest + slope * 30, 2),
        }

    # ── Definition trend ─────────────────────────────────────────────────────
    definition_trend = [
        {
            'date':           str(s.get('scan_date', ''))[:10],
            'muscle_group':   s.get('muscle_group'),
            'definition_score': s.get('definition_score'),
            'definition_grade': s.get('definition_grade'),
        }
        for s in scans if s.get('definition_score') is not None
    ]

    # ── Body composition trend ───────────────────────────────────────────────
    comp_logs = db(
        db.body_composition_log.customer_id == customer_id
    ).select(orderby=db.body_composition_log.assessed_on).as_list()

    body_composition_trend = [
        {
            'date':           str(c.get('assessed_on', ''))[:10],
            'body_fat_pct':   c.get('body_fat_pct'),
            'lean_mass_kg':   c.get('lean_mass_kg'),
            'bmi':            c.get('bmi'),
            'classification': c.get('classification'),
        }
        for c in comp_logs
    ]

    return dict(
        status='success',
        trend=trend,
        correlation=correlation,
        circumference_trend=circumference_trend,
        circumference_projection=circ_projection,
        definition_trend=definition_trend,
        body_composition_trend=body_composition_trend,
    )


@action('api/customer/<customer_id:int>/symmetry', method=['POST'])
@action.uses(db, cors)
def customer_symmetry(customer_id):
    payload, err = _auth_check(customer_id)
    if err: return err

    customer = db.customer(customer_id)
    if not customer:
        return dict(status='error', message='Customer not found')

    left = request.files.get('left')
    right = request.files.get('right')

    if not left or not right:
        return dict(status='error', message='Both left and right images required')

    for f in (left, right):
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            return dict(status='error', message=f'Invalid file type: {ext}')

    muscle_group = request.forms.get('muscle_group', 'bicep')
    marker_size = float(request.forms.get('marker_size', '20.0'))

    left_filename = db.muscle_scan.img_front.store(left.file, left.filename)
    right_filename = db.muscle_scan.img_front.store(right.file, right.filename)

    left_path = os.path.join('uploads', left_filename)
    right_path = os.path.join('uploads', right_filename)

    try:
        result = compare_symmetry(left_path, right_path, marker_size, muscle_group)
        if "error" in result:
            return dict(status='error', message=result['error'])

        db.symmetry_assessment.insert(
            customer_id=customer_id,
            muscle_group=muscle_group,
            composite_imbalance_pct=result['symmetry_indices']['composite_pct'],
            dominant_side=result['dominant_side'],
            risk_level=result['risk_level'],
            verdict=result['verdict'],
        )
        db.commit()
        return dict(status='success', **result)
    except Exception:
        logger.exception("Symmetry analysis failed for customer %d", customer_id)
        return dict(status='error', message='Symmetry analysis failed')


# --- POSE ANALYSIS & CLASSIFICATION ---

@action('api/pose_check', method=['POST'])
@action.uses(db, cors)
def pose_check():
    payload, err = _auth_check()
    if err: return err

    image_file = request.files.get('image')
    if not image_file:
        return dict(status='error', message='Image file is required')

    ext = os.path.splitext(image_file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return dict(status='error', message=f'Invalid file type: {ext}')

    image_file.file.seek(0, 2)
    size = image_file.file.tell()
    image_file.file.seek(0)
    if size > MAX_FILE_SIZE_BYTES:
        return dict(status='error', message=f'File too large (max {MAX_FILE_SIZE_MB}MB)')

    muscle_group = request.forms.get('muscle_group', 'bicep')
    temp_filename = db.muscle_scan.img_front.store(image_file.file, image_file.filename)
    temp_path = os.path.join('uploads', temp_filename)

    try:
        img = cv2.imread(temp_path)
        if img is None:
            return dict(status='error', message='Failed to decode image')
        result = analyze_pose(img, muscle_group)
        return dict(status='success', **result)
    except Exception as e:
        logger.exception("Pose check failed")
        return dict(status='error', message=str(e))


@action('api/classify_muscle', method=['POST'])
@action.uses(db, cors)
def classify_muscle():
    """
    POST a single image, get back the auto-detected muscle group.
    """
    payload, err = _auth_check()
    if err: return err

    image_file = request.files.get('image')
    if not image_file:
        return dict(status='error', message='No image provided')

    ext = os.path.splitext(image_file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return dict(status='error', message=f'Invalid file type: {ext}')

    file_bytes = np.frombuffer(image_file.file.read(), np.uint8)
    image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    if image is None:
        return dict(status='error', message='Could not decode image')

    result = classify_with_confidence(image)
    return dict(status='ok', **result)


# --- HEALTH LOGGING ---

@action('api/customer/<customer_id:int>/health_log', method=['POST'])
@action.uses(db, cors)
def add_health_log(customer_id):
    payload, err = _auth_check(customer_id)
    if err: return err

    customer = db.customer(customer_id)
    if not customer:
        return dict(status='error', message='Customer not found')

    data = request.json or {}
    log_id = db.health_log.insert(
        customer_id=customer_id,
        calories_in=data.get('calories_in'),
        protein_g=data.get('protein_g'),
        carbs_g=data.get('carbs_g'),
        fat_g=data.get('fat_g'),
        water_ml=data.get('water_ml'),
        activity_type=data.get('activity_type'),
        activity_duration_min=data.get('activity_duration_min'),
        sleep_hours=data.get('sleep_hours'),
        body_weight_kg=data.get('body_weight_kg'),
        notes=data.get('notes'),
    )
    db.commit()
    return dict(status='success', log_id=log_id)


@action('api/customer/<customer_id:int>/health_logs', method=['GET'])
@action.uses(db, cors)
def get_health_logs(customer_id):
    payload, err = _auth_check(customer_id)
    if err: return err

    customer = db.customer(customer_id)
    if not customer:
        return dict(status='error', message='Customer not found')

    logs = db(db.health_log.customer_id == customer_id).select(orderby=~db.health_log.log_date).as_list()
    return dict(status='success', logs=logs)


# --- REFERENCE DATA ---

@action('api/muscle_groups', method=['GET'])
@action.uses(cors)
def get_muscle_groups():
    return dict(muscle_groups=MUSCLE_GROUPS)


@action('api/shape_templates', method=['GET'])
@action.uses(cors)
def get_shape_templates():
    return dict(templates=AVAILABLE_TEMPLATES)


@action('api/volume_models', method=['GET'])
@action.uses(cors)
def get_volume_models():
    return dict(models=VOLUME_MODELS)


# --- BODY COMPOSITION ---

@action('api/customer/<customer_id:int>/body_composition', method=['POST'])
@action.uses(db, cors)
def body_composition(customer_id):
    payload, err = _auth_check(customer_id)
    if err: return err

    customer = db.customer(customer_id)
    if not customer:
        return dict(status='error', message='Customer not found')

    image_file = request.files.get('image')
    if not image_file:
        return dict(status='error', message='Image file required')

    ext = os.path.splitext(image_file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return dict(status='error', message=f'Invalid file type: {ext}')

    data = request.forms
    weight_kg  = float(data.get('weight_kg') or customer.weight_kg or 0) or None
    height_cm  = float(data.get('height_cm') or customer.height_cm or 0) or None
    gender     = data.get('gender') or customer.gender or 'male'

    img_filename = db.muscle_scan.img_front.store(image_file.file, image_file.filename)
    img_path     = os.path.join('uploads', img_filename)

    try:
        from core.body_composition import estimate_body_composition, estimate_lean_mass, generate_composition_visual
        img = cv2.imread(img_path)
        if img is None:
            return dict(status='error', message='Could not decode image')

        landmarks = {}
        try:
            from core.body_segmentation import segment_body
            seg = segment_body(img)
            if seg and 'landmarks' in seg:
                landmarks = seg['landmarks']
        except Exception:
            pass

        result = estimate_body_composition(
            landmarks=landmarks,
            user_weight_kg=weight_kg,
            user_height_cm=height_cm,
            gender=gender,
        )

        if weight_kg and result.get('estimated_body_fat_pct') is not None:
            lean = estimate_lean_mass(weight_kg, result['estimated_body_fat_pct'])
            result.update(lean)

        # Save annotated visual
        visual_path = None
        try:
            visual = generate_composition_visual(img, landmarks, result)
            if visual is not None:
                vis_name = 'comp_' + img_filename
                vis_path = os.path.join('uploads', vis_name)
                cv2.imwrite(vis_path, visual)
                visual_path = f'/uploads/{vis_name}'
        except Exception:
            pass

        log_id = db.body_composition_log.insert(
            customer_id=customer_id,
            bmi=result.get('bmi'),
            body_fat_pct=result.get('estimated_body_fat_pct'),
            lean_mass_kg=result.get('lean_mass_kg'),
            waist_hip_ratio=result.get('waist_to_hip_ratio'),
            classification=result.get('classification'),
            confidence=result.get('confidence'),
            visual_img=visual_path,
        )
        db.commit()

        return dict(
            status='success',
            log_id=log_id,
            visual_url=visual_path,
            **result,
        )
    except Exception:
        logger.exception('Body composition failed for customer %d', customer_id)
        return dict(status='error', message='Body composition analysis failed')


# --- 3D MESH RECONSTRUCTION ---

@action('api/customer/<customer_id:int>/reconstruct_3d', method=['POST'])
@action.uses(db, cors)
def reconstruct_3d(customer_id):
    payload, err = _auth_check(customer_id)
    if err: return err

    customer = db.customer(customer_id)
    if not customer:
        return dict(status='error', message='Customer not found')

    front_file = request.files.get('front')
    side_file  = request.files.get('side')
    if not front_file or not side_file:
        return dict(status='error', message='Both front and side images required')

    for f in (front_file, side_file):
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            return dict(status='error', message=f'Invalid file type: {ext}')

    muscle_group = request.forms.get('muscle_group', 'bicep')
    marker_size  = float(request.forms.get('marker_size', '20.0'))
    camera_distance_cm = float(request.forms.get('camera_distance_cm', '0') or '0') or None

    front_fn = db.muscle_scan.img_front.store(front_file.file, front_file.filename)
    side_fn  = db.muscle_scan.img_front.store(side_file.file, side_file.filename)
    front_path = os.path.join('uploads', front_fn)
    side_path  = os.path.join('uploads', side_fn)

    try:
        from core.vision_medical import analyze_muscle_growth
        from core.mesh_reconstruction import reconstruct_mesh_from_silhouettes, export_obj, export_glb, generate_mesh_preview_image
        from core.mesh_volume import compute_mesh_volume_cm3

        res_f = analyze_muscle_growth(front_path, front_path, marker_size, align=False, muscle_group=muscle_group, camera_distance_cm=camera_distance_cm)
        res_s = analyze_muscle_growth(side_path,  side_path,  marker_size, align=False, muscle_group=muscle_group, camera_distance_cm=camera_distance_cm)

        if 'error' in res_f or 'error' in res_s:
            return dict(status='error', message='Vision analysis failed on one or both images')

        contour_front = res_f.get('raw_data', {}).get('contour_a')
        contour_side  = res_s.get('raw_data', {}).get('contour_a')
        if contour_front is None or contour_side is None:
            return dict(status='error', message='Could not extract muscle contours')

        ratio_f = res_f.get('ratio', 1.0)
        ratio_s = res_s.get('ratio', 1.0)
        ppm_f   = 1.0 / ratio_f if ratio_f > 0 else 1.0
        ppm_s   = 1.0 / ratio_s if ratio_s > 0 else 1.0

        mesh_data = reconstruct_mesh_from_silhouettes(contour_front, contour_side, ppm_f, ppm_s)
        if not mesh_data or mesh_data.get('num_vertices', 0) == 0:
            return dict(status='error', message='3D reconstruction produced empty mesh')

        # Precise volume from mesh
        precise_vol = compute_mesh_volume_cm3(mesh_data['vertices'], mesh_data['faces'])
        if precise_vol > 0:
            mesh_data['volume_cm3'] = precise_vol

        # Save OBJ
        os.makedirs(_abs_path('meshes'), exist_ok=True)
        import time
        base_name  = f'mesh_{customer_id}_{int(time.time())}'
        obj_path   = _abs_path('meshes', base_name + '.obj')
        prev_path  = _abs_path('meshes', base_name + '_preview.png')

        export_obj(mesh_data['vertices'], mesh_data['faces'], obj_path)

        # GLB export (preferred format for 3D viewer)
        glb_path = _abs_path('meshes', base_name + '.glb')
        glb_url  = None
        try:
            export_glb(mesh_data['vertices'], mesh_data['faces'], glb_path)
            glb_url = f'/meshes/{base_name}.glb'
        except Exception:
            logger.warning('GLB export failed for mesh %s — OBJ fallback only', base_name)
            glb_path = None

        preview_url = None
        try:
            generate_mesh_preview_image(mesh_data['vertices'], mesh_data['faces'], prev_path)
            preview_url = f'/meshes/{base_name}_preview.png'
        except Exception:
            pass

        mesh_id = db.mesh_model.insert(
            customer_id=customer_id,
            muscle_group=muscle_group,
            obj_path=obj_path,
            glb_path=glb_path,
            preview_path=prev_path if preview_url else None,
            volume_cm3=mesh_data.get('volume_cm3'),
            num_vertices=mesh_data.get('num_vertices'),
            num_faces=mesh_data.get('num_faces'),
        )
        db.commit()

        return dict(
            status='success',
            mesh_id=mesh_id,
            mesh_url=glb_url or f'/meshes/{base_name}.obj',
            glb_url=glb_url,
            obj_url=f'/meshes/{base_name}.obj',
            preview_url=preview_url,
            volume_cm3=mesh_data.get('volume_cm3'),
            num_vertices=mesh_data.get('num_vertices'),
            num_faces=mesh_data.get('num_faces'),
        )
    except Exception:
        logger.exception('3D reconstruction failed for customer %d', customer_id)
        return dict(status='error', message='3D reconstruction failed')


@action('api/mesh/<mesh_id:int>.obj', method=['GET'])
@action.uses(db, cors)
def serve_mesh_obj(mesh_id):
    mesh = db.mesh_model(mesh_id)
    if not mesh or not mesh.obj_path or not os.path.exists(mesh.obj_path):
        abort(404, 'Mesh not found')
    response.headers['Content-Type'] = 'text/plain'
    with open(mesh.obj_path, 'r') as f:
        return f.read()


@action('/static/<filename:path>', method=['GET'])
def serve_static(filename):
    """Serve static files with manual MIME type overrides for 3D assets."""
    logger.info("Serving static: %s", filename)
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), 'static'))
    
    # MIME Type Fix for 3D assets
    if filename.endswith('.glb'):
        response.headers['Content-Type'] = 'model/gltf-binary'
    elif filename.endswith('.hdr'):
        response.headers['Content-Type'] = 'image/vnd.radiance'
        
    return static_file(filename, root=root)


@action('api/mesh/<mesh_id:int>.glb', method=['GET'])
@action.uses(db, cors)
def serve_mesh_glb(mesh_id):
    """Serve the GLB binary for the 3D viewer (?model= param)."""
    mesh = db.mesh_model(mesh_id)
    if not mesh:
        abort(404, 'Mesh not found')
    # Fall back to OBJ if GLB was never generated
    glb = getattr(mesh, 'glb_path', None)
    logger.info("serve_mesh_glb: id=%d path=%s", mesh_id, glb)
    if not glb or not os.path.exists(glb):
        logger.error("GLB missing at path: %s", glb)
        abort(404, 'GLB not available for this mesh — use .obj endpoint')
    response.headers['Content-Type']        = 'model/gltf-binary'
    response.headers['Content-Disposition'] = f'inline; filename="mesh_{mesh_id}.glb"'
    with open(glb, 'rb') as f:
        return f.read()


@action('api/mesh/template.glb', method=['GET'])
@action.uses(cors)
def serve_template_glb():
    """Serve the MPFB2 template GLB (default body before any customisation)."""
    path = os.path.join('meshes', 'gtd3d_body_template.glb')
    if not os.path.exists(path):
        abort(404, 'Template mesh not generated yet')
    response.headers['Content-Type'] = 'model/gltf-binary'
    response.headers['Content-Disposition'] = 'inline; filename="gtd3d_body_template.glb"'
    with open(path, 'rb') as f:
        return f.read()


@action('api/customer/<customer_id:int>/meshes', method=['GET'])
@action.uses(db, cors)
def list_meshes(customer_id):
    """Return list of mesh models for a customer — used by viewer comparison dropdown."""
    # payload, err = _auth_check()
    # if err: return err
    rows = db(db.mesh_model.customer_id == customer_id).select(
        db.mesh_model.id,
        db.mesh_model.muscle_group,
        db.mesh_model.model_type,
        db.mesh_model.volume_cm3,
        db.mesh_model.created_on,
        orderby=~db.mesh_model.id
    )
    return dict(
        status='success',
        meshes=[dict(
            id=int(r.id),
            muscle_group=r.muscle_group or 'body',
            model_type=r.model_type or 'body',
            volume_cm3=round(float(r.volume_cm3), 1) if r.volume_cm3 else None,
            created_on=str(r.created_on)[:16] if r.created_on else '',
        ) for r in rows]
    )


@action('api/customer/<customer_id:int>/room_texture', method=['POST'])
@action.uses(db, cors)
def upload_room_texture(customer_id):
    """Upload a photo texture for a room surface (floor, ceiling, wall_*)."""
    payload, err = _auth_check()
    if err: return err
    surface = request.forms.get('surface', '')
    valid = ['floor', 'ceiling', 'wall_front', 'wall_back', 'wall_left', 'wall_right']
    if surface not in valid:
        return dict(status='error', message=f'surface must be one of: {valid}')
    upload = request.files.get('image')
    if not upload:
        return dict(status='error', message='No image file provided')
    uploads_dir = _abs_path('uploads', 'room')
    os.makedirs(uploads_dir, exist_ok=True)
    fname = f'room_{customer_id}_{surface}{os.path.splitext(upload.filename)[1]}'
    fpath = os.path.join(uploads_dir, fname)
    upload.save(fpath, overwrite=True)
    # Upsert: remove old entry for this customer+surface
    db((db.room_texture.customer_id == customer_id) &
       (db.room_texture.surface == surface)).delete()
    db.room_texture.insert(customer_id=customer_id, surface=surface, image_path=fpath)
    db.commit()
    return dict(status='success', surface=surface, url=f'/web_app/api/customer/{customer_id}/room_texture/{surface}')


@action('api/customer/<customer_id:int>/room_texture/<surface>', method=['GET'])
@action.uses(db, cors)
def serve_room_texture(customer_id, surface):
    """Serve a room texture image."""
    row = db((db.room_texture.customer_id == customer_id) &
             (db.room_texture.surface == surface)).select().first()
    if not row or not row.image_path or not os.path.exists(row.image_path):
        abort(404, 'Texture not found')
    ext = os.path.splitext(row.image_path)[1].lower()
    ct = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png'}.get(ext.lstrip('.'), 'image/jpeg')
    response.headers['Content-Type'] = ct
    with open(row.image_path, 'rb') as f:
        return f.read()


@action('api/customer/<customer_id:int>/room_textures', method=['GET'])
@action.uses(db, cors)
def list_room_textures(customer_id):
    """Return all room texture URLs for a customer."""
    payload, err = _auth_check()
    if err: return err
    rows = db(db.room_texture.customer_id == customer_id).select()
    # Map surface names: wall_front→front, wall_back→back, etc.
    textures = []
    for r in rows:
        viewer_surface = r.surface.replace('wall_', '') if r.surface.startswith('wall_') else r.surface
        textures.append(dict(
            surface=viewer_surface,
            url=f'/web_app/api/customer/{customer_id}/room_texture/{r.surface}',
        ))
    return dict(status='success', textures=textures)


@action('api/customer/<customer_id:int>/compare_3d', method=['POST'])
@action.uses(db, cors)
def compare_3d(customer_id):
    payload, err = _auth_check(customer_id)
    if err: return err

    data = request.json or {}
    before_id = data.get('mesh_id_before')
    after_id  = data.get('mesh_id_after')
    if not before_id or not after_id:
        return dict(status='error', message='mesh_id_before and mesh_id_after required')

    mesh_before = db.mesh_model(before_id)
    mesh_after  = db.mesh_model(after_id)
    if not mesh_before or not mesh_after:
        return dict(status='error', message='One or both meshes not found')
    if mesh_before.customer_id != customer_id or mesh_after.customer_id != customer_id:
        return dict(status='error', message='Access denied')

    try:
        from core.mesh_reconstruction import export_obj
        from core.mesh_comparison import compare_meshes, export_colored_obj
        import numpy as np

        def _load_obj_verts_faces(path):
            verts, faces = [], []
            with open(path) as f:
                for line in f:
                    parts = line.split()
                    if not parts:
                        continue
                    if parts[0] == 'v':
                        verts.append([float(x) for x in parts[1:4]])
                    elif parts[0] == 'f':
                        faces.append([int(x) - 1 for x in parts[1:4]])
            return np.array(verts), np.array(faces)

        vb, fb = _load_obj_verts_faces(mesh_before.obj_path)
        va, fa = _load_obj_verts_faces(mesh_after.obj_path)

        result = compare_meshes(
            {'vertices': vb, 'faces': fb, 'volume_cm3': mesh_before.volume_cm3},
            {'vertices': va, 'faces': fa, 'volume_cm3': mesh_after.volume_cm3},
        )

        import time
        colored_name = f'compare_{customer_id}_{int(time.time())}.obj'
        colored_path = os.path.join('meshes', colored_name)
        export_colored_obj(va, fa, result['displacement_map'], colored_path)

        return dict(
            status='success',
            mean_growth_mm=round(result['mean_growth_mm'], 3),
            max_growth_mm=round(result['max_growth_mm'], 3),
            volume_change_cm3=round(result['volume_change_cm3'], 3),
            colored_mesh_url=f'/meshes/{colored_name}',
        )
    except Exception:
        logger.exception('3D comparison failed for customer %d', customer_id)
        return dict(status='error', message='3D comparison failed')


@action('api/customer/<customer_id:int>/compare_meshes', method=['POST'])
@action.uses(db, cors)
def compare_meshes_heatmap(customer_id):
    """Return per-vertex heatmap values for growth visualization in the 3D viewer."""
    payload, err = _auth_check()
    if err: return err

    data = request.json or {}
    mesh_id_old = int(data.get('mesh_id_old', 0))
    mesh_id_new = int(data.get('mesh_id_new', 0))
    if not mesh_id_old or not mesh_id_new:
        return dict(status='error', message='mesh_id_old and mesh_id_new required')

    old_row = db.mesh_model[mesh_id_old]
    new_row = db.mesh_model[mesh_id_new]
    if not old_row or not new_row:
        return dict(status='error', message='Mesh not found')
    if old_row.customer_id != customer_id or new_row.customer_id != customer_id:
        return dict(status='error', message='Access denied')
    if not old_row.glb_path or not new_row.glb_path:
        return dict(status='error', message='GLB path missing for one or both meshes')

    try:
        import numpy as np
        import struct as _struct
        import pygltflib as _pygltflib

        # Resolve relative paths (meshes/ lives at project root, two dirs above __file__)
        # __file__ = apps/web_app/controllers.py → go up twice to project root
        _root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        def _abs(p):
            p = p.replace('\\', '/')
            return p if os.path.isabs(p) else os.path.join(_root, p)

        def _load_verts(path):
            try:
                gltf = _pygltflib.GLTF2().load(path)
                acc = gltf.accessors[gltf.meshes[0].primitives[0].attributes.POSITION]
                bv  = gltf.bufferViews[acc.bufferView]
                blob = gltf.binary_blob()
                data = blob[bv.byteOffset: bv.byteOffset + bv.byteLength]
                v = np.array(_struct.unpack(f'<{acc.count * 3}f', data)).reshape(acc.count, 3)
                return v.astype(np.float32)
            except Exception:
                return None

        verts_old = _load_verts(_abs(old_row.glb_path))
        verts_new = _load_verts(_abs(new_row.glb_path))
        if verts_old is None or verts_new is None:
            return dict(status='error', message='Could not load mesh vertices from GLB')

        if len(verts_old) == len(verts_new):
            disp = np.linalg.norm(verts_new - verts_old, axis=1)
        else:
            # Different vertex counts — nearest-vertex match
            from scipy.spatial import cKDTree
            tree = cKDTree(verts_old)
            _, idx = tree.query(verts_new)
            disp = np.linalg.norm(verts_new - verts_old[idx], axis=1)

        # Normalize to [0, 1] using 95th-percentile cap to avoid outliers dominating
        cap = float(np.percentile(disp, 95)) or 1.0
        heatmap = np.clip(disp / cap, 0.0, 1.0)

        return dict(
            status='success',
            heatmap_values=heatmap.tolist(),
            displacements_mm=disp.tolist(),
            max_displacement_mm=round(float(disp.max()), 2),
            mean_displacement_mm=round(float(disp.mean()), 2),
            num_vertices=int(len(heatmap)),
        )
    except Exception:
        logger.exception('compare_meshes_heatmap failed for customer %d', customer_id)
        return dict(status='error', message='Mesh comparison failed')


# --- DASHBOARD ENDPOINTS ---

@action('api/customer/<customer_id:int>/body_map', method=['GET'])
@action.uses(db, cors)
def customer_body_map(customer_id):
    payload, err = _auth_check(customer_id)
    if err: return err

    scans = db(db.muscle_scan.customer_id == customer_id).select(
        orderby=~db.muscle_scan.scan_date
    ).as_list()

    # Latest scan per muscle group
    latest = {}
    for s in scans:
        mg = s['muscle_group']
        if mg not in latest:
            latest[mg] = s

    muscle_groups = []
    for mg, s in latest.items():
        muscle_groups.append({
            'muscle_group':   mg,
            'scan_date':      str(s.get('scan_date', '')),
            'volume_cm3':     s.get('volume_cm3'),
            'shape_score':    s.get('shape_score'),
            'shape_grade':    s.get('shape_grade'),
            'growth_pct':     s.get('growth_pct'),
            'definition_score': s.get('definition_score'),
            'definition_grade': s.get('definition_grade'),
            'circumference_cm': s.get('circumference_cm'),
            'annotated_img_url': f'/uploads/{s["annotated_img"]}' if s.get('annotated_img') else None,
        })

    return dict(status='success', muscle_groups=muscle_groups)


@action('api/customer/<customer_id:int>/quick_stats', method=['GET'])
@action.uses(db, cors)
def customer_quick_stats(customer_id):
    payload, err = _auth_check(customer_id)
    if err: return err

    scans = db(db.muscle_scan.customer_id == customer_id).select(
        orderby=~db.muscle_scan.scan_date
    ).as_list()

    total_scans      = len(scans)
    active_groups    = len(set(s['muscle_group'] for s in scans))
    growths          = [s['growth_pct'] for s in scans if s.get('growth_pct') is not None]
    best_growth_pct  = round(max(growths), 2) if growths else None
    best_muscle      = None
    if growths:
        for s in scans:
            if s.get('growth_pct') == max(growths):
                best_muscle = s['muscle_group']
                break

    def_scores = [s['definition_score'] for s in scans if s.get('definition_score') is not None]
    avg_definition = round(sum(def_scores) / len(def_scores), 1) if def_scores else None

    # Days active
    dates = sorted(set(
        str(s['scan_date'])[:10] for s in scans if s.get('scan_date')
    ))
    days_active = (
        (
            __import__('datetime').date.fromisoformat(dates[-1]) -
            __import__('datetime').date.fromisoformat(dates[0])
        ).days
        if len(dates) >= 2 else 0
    )

    # Streak (weekly — same as dashboard JS logic)
    streak = 0
    if dates:
        from datetime import date
        streak = 1
        prev   = date.fromisoformat(dates[-1])
        for d_str in reversed(dates[:-1]):
            d = date.fromisoformat(d_str)
            if (prev - d).days <= 7:
                streak += 1
                prev = d
            else:
                break

    # Latest body composition
    latest_comp = db(
        db.body_composition_log.customer_id == customer_id
    ).select(orderby=~db.body_composition_log.assessed_on, limitby=(0, 1)).first()

    return dict(
        status='success',
        total_scans=total_scans,
        active_muscle_groups=active_groups,
        best_growth_pct=best_growth_pct,
        best_muscle=best_muscle,
        avg_definition_score=avg_definition,
        days_active=days_active,
        current_streak=streak,
        body_fat_pct=latest_comp.body_fat_pct if latest_comp else None,
        lean_mass_kg=latest_comp.lean_mass_kg if latest_comp else None,
    )


@action('api/customer/<customer_id:int>/progress_summary', method=['GET'])
@action.uses(db, cors)
def customer_progress_summary(customer_id):
    payload, err = _auth_check(customer_id)
    if err: return err

    muscle_group = request.params.get('muscle_group')
    query = db.muscle_scan.customer_id == customer_id
    if muscle_group:
        query &= db.muscle_scan.muscle_group == muscle_group

    scans = db(query).select(orderby=db.muscle_scan.scan_date).as_list()

    # Strip raw image filenames, include all metrics
    for s in scans:
        s.pop('img_front', None)
        s.pop('img_side', None)
        s['scan_date'] = str(s.get('scan_date', ''))
        if s.get('annotated_img'):
            s['annotated_img_url'] = f'/uploads/{s["annotated_img"]}'
        s.pop('annotated_img', None)

    # Body comp history
    comp_history = db(
        db.body_composition_log.customer_id == customer_id
    ).select(orderby=db.body_composition_log.assessed_on).as_list()
    for c in comp_history:
        c['assessed_on'] = str(c.get('assessed_on', ''))

    return dict(
        status='success',
        scans=scans,
        body_composition_history=comp_history,
    )


# --- SESSION REPORT ---

@action('api/customer/<customer_id:int>/session_report', method=['POST'])
@action.uses(db, cors)
def generate_session_report_endpoint(customer_id):
    payload, err = _auth_check(customer_id)
    if err: return err

    customer = db.customer(customer_id)
    if not customer:
        return dict(status='error', message='Customer not found')

    # Option A: scan_id provided — generate from stored scan
    scan_id = (request.json or {}).get('scan_id') or request.forms.get('scan_id')
    if scan_id:
        scan = db.muscle_scan(int(scan_id))
        if not scan or scan.customer_id != customer_id:
            return dict(status='error', message='Scan not found')

        from core.session_report import generate_session_report
        import tempfile

        front_path = os.path.join('uploads', scan.img_front) if scan.img_front else None
        image_bgr  = cv2.imread(front_path) if front_path and os.path.exists(front_path) else None

        scan_results = {
            'patient_name':   customer.name,
            'scan_date':      str(scan.scan_date)[:10],
            'muscle_group':   scan.muscle_group,
            'image_bgr':      image_bgr,
            'metrics':        {
                'area_mm2':         scan.area_mm2,
                'width_mm':         scan.width_mm,
                'height_mm':        scan.height_mm,
                'circumference_cm': scan.circumference_cm,
            },
            'volume_cm3':     scan.volume_cm3,
            'circumference_cm': scan.circumference_cm,
            'shape_score':    scan.shape_score,
            'shape_grade':    scan.shape_grade,
            'definition':     {'overall_definition': scan.definition_score, 'grade': scan.definition_grade}
                              if scan.definition_score else None,
            'growth_analysis': {'growth_pct': scan.growth_pct, 'area_change_mm2': scan.volume_delta_cm3}
                               if scan.growth_pct is not None else None,
        }

        fd, tmp = tempfile.mkstemp(suffix='.pdf')
        os.close(fd)
        try:
            pdf_path = generate_session_report(scan_results, output_path=tmp)
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = (
                f'attachment; filename="session_report_{customer.name}_{str(scan.scan_date)[:10]}.pdf"'
            )
            with open(pdf_path, 'rb') as f:
                return f.read()
        finally:
            for p in (tmp, tmp.replace('.pdf', '') + '.pdf'):
                if os.path.exists(p):
                    os.remove(p)

    # Option B: image uploaded directly
    image_file = request.files.get('image')
    if not image_file:
        return dict(status='error', message='Provide scan_id or upload an image')

    ext = os.path.splitext(image_file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return dict(status='error', message=f'Invalid file type: {ext}')

    img_fn   = db.muscle_scan.img_front.store(image_file.file, image_file.filename)
    img_path = os.path.join('uploads', img_fn)
    image_bgr = cv2.imread(img_path)

    from core.session_report import generate_session_report
    from core.pipeline import full_scan_pipeline
    import tempfile

    muscle_group = request.forms.get('muscle_group', 'bicep')
    pipe_result  = full_scan_pipeline(
        img_path,
        user_weight_kg=float(request.forms.get('weight_kg') or customer.weight_kg or 0) or None,
        user_height_cm=float(request.forms.get('height_cm') or customer.height_cm or 0) or None,
        gender=request.forms.get('gender') or customer.gender or 'male',
        muscle_group=muscle_group,
        marker_size_mm=float(request.forms.get('marker_size', '20.0')),
    )

    scan_results = {
        'patient_name':    customer.name,
        'scan_date':       __import__('datetime').datetime.now().strftime('%Y-%m-%d'),
        'muscle_group':    muscle_group,
        'image_bgr':       image_bgr,
        'metrics':         pipe_result.get('metrics', {}),
        'volume_cm3':      pipe_result.get('volume_cm3'),
        'circumference_cm': pipe_result.get('circumference_cm'),
        'shape_score':     pipe_result.get('shape_score'),
        'shape_grade':     pipe_result.get('shape_grade'),
        'definition':      {'overall_definition': pipe_result.get('definition_score'),
                            'grade': pipe_result.get('definition_grade')}
                           if pipe_result.get('definition_score') else None,
        'body_composition': pipe_result.get('body_composition'),
    }

    fd, tmp = tempfile.mkstemp(suffix='.pdf')
    os.close(fd)
    try:
        pdf_path = generate_session_report(scan_results, output_path=tmp)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = (
            f'attachment; filename="session_report_{customer.name}.pdf"'
        )
        with open(pdf_path, 'rb') as f:
            return f.read()
    finally:
        for p in (tmp, tmp.replace('.pdf', '') + '.pdf'):
            if os.path.exists(p):
                os.remove(p)


# --- DATA EXPORT ---

@action('api/customer/<customer_id:int>/export', method=['GET'])
@action.uses(db, cors)
def export_data(customer_id):
    payload, err = _auth_check(customer_id)
    if err: return err

    customer = db.customer(customer_id)
    if not customer:
        return dict(status='error', message='Customer not found')

    fmt = request.params.get('format', 'csv').lower()

    scans = db(db.muscle_scan.customer_id == customer_id).select(
        orderby=db.muscle_scan.scan_date
    ).as_list()

    fields = [
        'scan_date', 'muscle_group', 'side', 'calibrated',
        'volume_cm3', 'area_mm2', 'width_mm', 'height_mm',
        'circumference_cm', 'shape_score', 'shape_grade',
        'definition_score', 'definition_grade',
        'growth_pct', 'volume_delta_cm3', 'detection_confidence',
    ]

    if fmt == 'json':
        export_rows = []
        for s in scans:
            row = {k: s.get(k) for k in fields}
            row['scan_date'] = str(row.get('scan_date', ''))
            export_rows.append(row)
        response.headers['Content-Type'] = 'application/json'
        response.headers['Content-Disposition'] = (
            f'attachment; filename="scans_{customer.name}.json"'
        )
        import json as _json
        return _json.dumps({'customer': customer.name, 'scans': export_rows}, indent=2)

    # Default: CSV
    import io
    import csv
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields)
    writer.writeheader()
    for s in scans:
        row = {k: s.get(k) for k in fields}
        row['scan_date'] = str(row.get('scan_date', ''))
        writer.writerow(row)

    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = (
        f'attachment; filename="scans_{customer.name}.csv"'
    )
    return buf.getvalue()


# --- LIVE ANALYSIS ---

@action('api/live_analyze', method=['POST'])
@action.uses(cors)
def live_analyze():
    """Fast single-frame analysis for live camera mode. No DB writes."""
    import base64
    data = request.json or {}
    frame_b64    = data.get('frame_base64', '')
    muscle_group = data.get('muscle_group', 'bicep')

    if not frame_b64:
        return dict(status='error', message='frame_base64 required')

    try:
        img_bytes = base64.b64decode(frame_b64)
        img_arr   = np.frombuffer(img_bytes, np.uint8)
        img       = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
        if img is None:
            return dict(status='error', message='Could not decode frame')

        # Write to temp file for analysis
        import tempfile
        fd, tmp_path = tempfile.mkstemp(suffix='.jpg')
        os.close(fd)
        cv2.imwrite(tmp_path, img)

        from core.vision_medical import analyze_muscle_growth
        from core.circumference import estimate_circumference

        res = analyze_muscle_growth(tmp_path, tmp_path, 20.0, align=False, muscle_group=muscle_group)
        os.remove(tmp_path)

        if 'error' in res:
            return dict(status='error', message=res['error'])

        contour = res.get('raw_data', {}).get('contour_a')
        circ_cm = None
        if contour is not None:
            ratio   = res.get('ratio', 1.0)
            ppm     = 1.0 / ratio if ratio > 0 else 1.0
            circ    = estimate_circumference(contour, ppm)
            circ_cm = circ.get('circumference_cm')

        unit    = 'mm' if res.get('calibrated') else 'px'
        metrics = res.get('metrics', {})

        return dict(
            status='success',
            calibrated=res.get('calibrated', False),
            area=metrics.get(f'area_a_{unit}2'),
            width=metrics.get(f'width_a_{unit}'),
            height=metrics.get(f'height_a_{unit}'),
            circumference_cm=round(circ_cm, 2) if circ_cm else None,
            contour_points=contour.reshape(-1, 2).tolist() if contour is not None else [],
        )
    except Exception:
        logger.exception('Live analysis error')
        return dict(status='error', message='Analysis failed')


@action('api/<path:path>', method=['OPTIONS'])
@action.uses(cors)
def api_options(path):
    return ""


# --- AUTO MODE 2: GUIDED SESSION UPLOAD ---

@action('api/customer/<customer_id:int>/upload_session', method=['POST'])
@action.uses(db, cors)
def upload_session(customer_id):
    """
    Receives a burst session from Auto Mode 2:
    - Multiple image files (frame_000.jpg, frame_001.jpg, ...)
    - JSON field 'sensor_log': list of per-frame sensor readings
    - Field 'muscle_group'
    Returns coverage analysis + progress % + next instructions.
    """
    payload, err = _auth_check(customer_id)
    if err: return err

    customer = db.customer(customer_id)
    if not customer:
        return dict(status='error', message='Customer not found')

    import tempfile, shutil
    from core.session_analyzer import analyze_session

    muscle_group = request.forms.get('muscle_group', 'quadricep')

    # Parse sensor log
    sensor_log_raw = request.forms.get('sensor_log', '[]')
    try:
        frames_with_sensors = json.loads(sensor_log_raw)
    except Exception:
        frames_with_sensors = []

    # Save all uploaded frames to a temp directory
    tmp_dir = tempfile.mkdtemp(prefix='session_')
    image_paths = {}
    try:
        saved_count = 0
        for key in request.files:
            f = request.files[key]
            if not f or not f.filename:
                continue
            ext = os.path.splitext(f.filename)[1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                continue
            dest = os.path.join(tmp_dir, f.filename)
            f.file.seek(0)
            with open(dest, 'wb') as out:
                out.write(f.file.read())
            image_paths[f.filename] = dest
            saved_count += 1

        if saved_count == 0:
            return dict(status='error', message='No valid image frames received')

        # If sensor log is empty or short, synthesize minimal entries
        if not frames_with_sensors:
            frames_with_sensors = [
                {'filename': fname, 'compass_deg': None, 'pitch_deg': None,
                 'accel_x': 0, 'accel_y': 0, 'accel_z': 9.8,
                 'gyro_x': 0, 'gyro_y': 0, 'gyro_z': 0,
                 'mag_x': 0, 'mag_y': 0, 'mag_z': 0}
                for fname in image_paths
            ]

        # Run coverage analysis
        result = analyze_session(frames_with_sensors, image_paths)

        # Persist session summary in DB (health_log reused as session log)
        try:
            db.health_log.insert(
                customer_id=customer_id,
                log_date=datetime.now(),
                notes=json.dumps({
                    'type': 'auto2_session',
                    'muscle_group': muscle_group,
                    'progress_pct': result['progress_pct'],
                    'covered_zones': result['covered_zones'],
                    'frames': saved_count,
                })
            )
            db.commit()
        except Exception:
            pass  # Don't fail the request if logging fails

        return dict(
            status='success',
            progress_pct=result['progress_pct'],
            is_complete=result['is_complete'],
            covered_zones=result['covered_zones'],
            missing_required=result['missing_required'],
            missing_bonus=result['missing_bonus'],
            instructions=result['instructions'],
            detail=result['detail'],
            priority_zone=result['priority_zone'],
            frame_stats=result['frame_stats'],
            muscle_group=muscle_group,
        )

    except Exception:
        logger.exception('Session analysis failed for customer %d', customer_id)
        return dict(status='error', message='Session analysis failed')
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@action('api/customer/<customer_id:int>/profile_status', method=['GET'])
@action.uses(db, cors)
def profile_status(customer_id):
    """Returns the latest Auto Mode 2 session progress for a customer."""
    payload, err = _auth_check()
    if err: return err

    rows = db(
        (db.health_log.customer_id == customer_id) &
        (db.health_log.notes.contains('"type": "auto2_session"'))
    ).select(orderby=~db.health_log.id, limitby=(0, 1))

    if not rows:
        return dict(status='success', has_session=False, progress_pct=0)

    try:
        data = json.loads(rows[0].notes)
        return dict(
            status='success',
            has_session=True,
            progress_pct=data.get('progress_pct', 0),
            covered_zones=data.get('covered_zones', []),
            muscle_group=data.get('muscle_group', ''),
        )
    except Exception:
        return dict(status='success', has_session=False, progress_pct=0)


# =============================================================================
# BODY PROFILE + DEVICE PROFILE (T0.2)
# =============================================================================

_BODY_PROFILE_FIELDS = [
    'height_cm', 'weight_kg',
    'shoulder_width_cm', 'neck_to_shoulder_cm', 'shoulder_to_head_cm',
    'arm_length_cm', 'upper_arm_length_cm', 'forearm_length_cm',
    'torso_length_cm', 'inseam_cm', 'floor_to_knee_cm',
    'knee_to_belly_cm', 'back_buttock_to_knee_cm',
    'head_circumference_cm', 'neck_circumference_cm',
    'chest_circumference_cm', 'bicep_circumference_cm',
    'forearm_circumference_cm', 'hand_circumference_cm',
    'waist_circumference_cm', 'hip_circumference_cm',
    'thigh_circumference_cm', 'quadricep_circumference_cm',
    'calf_circumference_cm', 'skin_tone_hex',
    'muscle_factor', 'weight_factor', 'gender_factor', 'gender',
]


def _auth_check(customer_id=None):
    """Verify JWT and optionally check customer access.

    Args:
        customer_id: If provided, verify the token holder can access this customer's data.

    Returns:
        (payload, None) on success, or (None, error_dict) on failure.
        Sets response.status to appropriate HTTP code on failure.
    """
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        response.status = 401
        return None, dict(status='error', message='Authentication required')
    payload = verify_jwt(token)
    if not payload:
        response.status = 401
        return None, dict(status='error', message='Invalid or expired token')
    if customer_id is not None:
        sub = payload.get('customer_id') or payload.get('sub')
        if sub != 'admin' and str(sub) != str(customer_id):
            response.status = 403
            return None, dict(status='error', message='Access denied')
    return payload, None


@action('api/customer/<customer_id:int>/reset_profile', method=['POST'])
@action.uses(db, cors)
def reset_body_profile(customer_id):
    payload, err = _auth_check()
    if err: return err
    customer = db.customer[customer_id]
    
    # Defaults
    defaults = {
        'height_cm': 168,
        'weight_kg': 63,
        'gender': 'male',
        'muscle_factor': 0.5,
        'weight_factor': 0.5,
        'gender_factor': 1.0,
        'chest_circumference_cm': 97,
        'waist_circumference_cm': 90,
        'hip_circumference_cm': 92,
        'thigh_circumference_cm': 53,
        'calf_circumference_cm': 34,
        'bicep_circumference_cm': 32,
        'forearm_circumference_cm': 29,
        'neck_circumference_cm': 35,
        'shoulder_width_cm': 37,
        'skin_tone_hex': 'C4956A',
    }
    customer.update_record(**defaults)
    db.commit()
    return dict(status='success', message='Profile reset to defaults')


@action('api/customer/<customer_id:int>/body_profile', method=['GET'])
@action.uses(db, cors)
def get_body_profile(customer_id):
    payload, err = _auth_check()
    if err: return err
    customer = db.customer[customer_id]
    if not customer:
        return dict(status='error', message='Customer not found')
    profile = {f: getattr(customer, f, None) for f in _BODY_PROFILE_FIELDS}
    profile['profile_completed'] = customer.profile_completed
    return dict(status='success', profile=profile)


@action('api/customer/<customer_id:int>/progress_report', method=['GET'])
@action.uses(db, cors)
def progress_report(customer_id):
    """Aggregate customer data for progress report page."""
    payload, err = _auth_check()
    if err: return err
    customer = db.customer[customer_id]
    if not customer:
        return dict(status='error', message='Customer not found')

    # Profile
    profile = {f: getattr(customer, f, None) for f in _BODY_PROFILE_FIELDS}
    profile['name'] = customer.name or ''
    profile['gender'] = customer.gender if hasattr(customer, 'gender') else ''

    # Mesh history (all body meshes, newest first)
    meshes = db(db.mesh_model.customer_id == customer_id).select(
        db.mesh_model.id,
        db.mesh_model.volume_cm3,
        db.mesh_model.num_vertices,
        db.mesh_model.num_faces,
        db.mesh_model.created_on,
        orderby=~db.mesh_model.id
    )
    mesh_list = [dict(
        id=int(r.id),
        volume_cm3=round(float(r.volume_cm3), 1) if r.volume_cm3 else None,
        vertices=r.num_vertices,
        faces=r.num_faces,
        date=str(r.created_on)[:16] if r.created_on else '',
    ) for r in meshes]

    # Volume trend (oldest → newest for chart)
    volume_trend = [
        dict(date=m['date'], volume=m['volume_cm3'])
        for m in reversed(mesh_list) if m['volume_cm3']
    ]

    # Body composition history
    comp_rows = db(
        db.body_composition_log.customer_id == customer_id
    ).select(orderby=db.body_composition_log.assessed_on)
    comp_history = [dict(
        date=str(r.assessed_on)[:16] if r.assessed_on else '',
        body_fat_pct=r.body_fat_pct,
        lean_mass_kg=r.lean_mass_kg,
    ) for r in comp_rows]

    # Key circumferences for progress tracking
    circ_fields = ['chest_circumference_cm', 'waist_circumference_cm',
                   'hip_circumference_cm', 'bicep_circumference_cm',
                   'thigh_circumference_cm', 'calf_circumference_cm']
    circumferences = {f.replace('_circumference_cm', '').replace('_cm', ''): getattr(customer, f, None)
                      for f in circ_fields if getattr(customer, f, None)}

    return dict(
        status='success',
        profile=profile,
        meshes=mesh_list,
        volume_trend=volume_trend,
        body_composition=comp_history,
        circumferences=circumferences,
        total_scans=len(mesh_list),
    )


@action('api/mesh/<mesh_id:int>/screenshot', method=['POST'])
@action.uses(db, cors)
def save_mesh_screenshot(mesh_id):
    """Save a screenshot PNG for a mesh (thumbnail for report/timeline)."""
    payload, err = _auth_check()
    if err: return err
    mesh = db.mesh_model[mesh_id]
    if not mesh:
        return dict(status='error', message='Mesh not found')
    data = request.json or {}
    b64 = data.get('image', '')
    if not b64:
        return dict(status='error', message='No image data')
    import base64
    try:
        img_bytes = base64.b64decode(b64.split(',')[-1])
    except Exception:
        return dict(status='error', message='Invalid base64 image')
    screenshots_dir = os.path.join(os.path.dirname(__file__), '..', 'uploads', 'screenshots')
    os.makedirs(screenshots_dir, exist_ok=True)
    fname = f'mesh_{mesh_id}.png'
    fpath = os.path.join(screenshots_dir, fname)
    with open(fpath, 'wb') as f:
        f.write(img_bytes)
    mesh.update_record(screenshot_path=fpath)
    db.commit()
    return dict(status='success', path=fname)


@action('api/customer/<customer_id:int>/skin_texture', method=['POST'])
@action.uses(db, cors)
def upload_skin_texture(customer_id):
    """
    Upload a skin photo and process into tileable PBR texture maps.

    Accepts:
      image    — photo file (JPEG/PNG)
      distance — capture distance in cm (optional, for metadata)
      size     — output texture size (default 1024, power of 2)
    """
    payload, err = _auth_check()
    if err: return err

    upload = request.files.get('image')
    if not upload:
        return dict(status='error', message='No image file provided')

    distance = request.forms.get('distance', '30')
    tex_size = int(request.forms.get('size', '1024'))
    tex_size = min(max(tex_size, 256), 4096)

    uploads_dir = os.path.join(os.path.dirname(__file__), '..', 'uploads', 'skin')
    os.makedirs(uploads_dir, exist_ok=True)
    ext = os.path.splitext(upload.filename or 'photo.jpg')[1] or '.jpg'
    raw_fname = f'skin_raw_{customer_id}_{distance}cm{ext}'
    raw_path = os.path.join(uploads_dir, raw_fname)
    upload.save(raw_path, overwrite=True)

    try:
        from core.skin_texture import process_skin_photo
        output_dir = os.path.join(uploads_dir, f'customer_{customer_id}')
        paths = process_skin_photo(raw_path, output_dir, size=tex_size)
    except Exception as e:
        return dict(status='error', message=f'Processing failed: {e}')

    return dict(
        status='success',
        distance_cm=distance,
        size=tex_size,
        textures={
            'albedo':    f'/web_app/api/customer/{customer_id}/skin_texture/albedo',
            'normal':    f'/web_app/api/customer/{customer_id}/skin_texture/normal',
            'roughness': f'/web_app/api/customer/{customer_id}/skin_texture/roughness',
        }
    )


@action('api/customer/<customer_id:int>/skin_texture/<tex_type>', method=['GET'])
@action.uses(cors)
def serve_skin_texture(customer_id, tex_type):
    """Serve a processed skin texture PNG (albedo, normal, or roughness)."""
    valid = {'albedo', 'normal', 'roughness'}
    if tex_type not in valid:
        return dict(status='error', message=f'Type must be one of: {sorted(valid)}')

    uploads_dir = os.path.join(os.path.dirname(__file__), '..', 'uploads', 'skin',
                               f'customer_{customer_id}')
    fpath = os.path.join(uploads_dir, f'skin_{tex_type}.png')
    if not os.path.exists(fpath):
        abort(404, f'No {tex_type} texture for customer {customer_id}')

    response.headers['Content-Type'] = 'image/png'
    response.headers['Cache-Control'] = 'public, max-age=3600'
    with open(fpath, 'rb') as f:
        return f.read()


@action('api/customer/<customer_id:int>/skin_region/<region>', method=['POST'])
@action.uses(db, cors)
def upload_skin_region(customer_id, region):
    """
    Upload a close-up skin photo for a specific body region.
    Generates tileable texture, recomposites UV atlas, re-exports GLB.

    Args (form/multipart):
        image: JPEG/PNG close-up skin photo
        region: one of forearm, abdomen, chest, thigh, calf, upper_arm, etc.
    """
    payload, err = _auth_check()
    if err: return err

    from core.skin_patch import CAPTURE_REGIONS, make_tileable, composite_skin_atlas
    if region not in CAPTURE_REGIONS:
        return dict(status='error',
                    message=f'Unknown region: {region}. Valid: {sorted(CAPTURE_REGIONS.keys())}')

    upload = request.files.get('image')
    if not upload:
        return dict(status='error', message='No image file provided')

    # Save raw photo
    skin_dir = os.path.join(os.path.dirname(__file__), '..', 'uploads', 'skin',
                            f'customer_{customer_id}')
    os.makedirs(skin_dir, exist_ok=True)
    ext = os.path.splitext(upload.filename or 'photo.jpg')[1] or '.jpg'
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    raw_path = os.path.join(skin_dir, f'raw_{region}_{ts}{ext}')
    upload.save(raw_path, overwrite=True)

    # Generate tileable texture
    import cv2 as _cv2_sr
    img = _cv2_sr.imread(raw_path)
    if img is None:
        return dict(status='error', message='Could not read image')

    tile = make_tileable(img, out_size=512, patch_size=48, overlap=12)
    tile_path = os.path.join(skin_dir, f'tile_{region}.png')
    _cv2_sr.imwrite(tile_path, tile)

    # Load all existing region tiles for this customer
    region_textures = {}
    for rname in CAPTURE_REGIONS:
        tp = os.path.join(skin_dir, f'tile_{rname}.png')
        if os.path.exists(tp):
            region_textures[rname] = _cv2_sr.imread(tp)

    # Composite into full atlas
    try:
        from core.texture_factory import get_part_ids
        import pickle as _pkl_sr
        pkl_path = os.path.join(os.path.dirname(__file__), '..', '..', 'runpod', 'SMPL_NEUTRAL.pkl')
        with open(pkl_path, 'rb') as f:
            _smpl = _pkl_sr.load(f, encoding='latin1')
        faces = np.array(_smpl['f'], dtype=np.int32)

        from core.smpl_direct import _load_canonical_uvs, cylindrical_uvs
        from core.smpl_optimizer import smpl_forward
        verts, _ = smpl_forward(np.zeros(10))
        uvs = _load_canonical_uvs()
        if uvs is None:
            uvs = cylindrical_uvs(verts)

        part_ids = get_part_ids(len(uvs))

        atlas = composite_skin_atlas(uvs, part_ids, faces, region_textures, atlas_size=2048)
        atlas_path = os.path.join(skin_dir, 'skin_atlas.png')
        _cv2_sr.imwrite(atlas_path, atlas)

        # Generate PBR maps from skin atlas
        from core.skin_patch import generate_skin_normal_map
        from core.texture_factory import generate_roughness_map
        normal_map = generate_skin_normal_map(atlas, strength=10.0)
        roughness_float = generate_roughness_map(uvs, atlas_size=2048, vertices=verts)
        roughness_map = (roughness_float * 255).astype(np.uint8) if roughness_float is not None else None

        # Save PBR maps for debugging
        _cv2_sr.imwrite(os.path.join(skin_dir, 'skin_normal.png'), normal_map)
        if roughness_map is not None:
            _cv2_sr.imwrite(os.path.join(skin_dir, 'skin_roughness.png'), roughness_map)

        # Re-export GLB with skin texture + PBR maps
        latest_mesh = db(db.mesh_model.customer_id == customer_id).select(
            orderby=~db.mesh_model.id).first()
        if latest_mesh and latest_mesh.glb_path:
            from core.mesh_reconstruction import export_glb
            verts_m = verts / 1000.0
            export_glb(verts_m, faces, latest_mesh.glb_path,
                        uvs=uvs, texture_image=atlas,
                        normal_map=normal_map, roughness_map=roughness_map)
            logger.info('Re-exported GLB with skin PBR for customer %s (region: %s)',
                        customer_id, region)

    except Exception as e:
        logger.warning('Skin region compositing skipped (non-fatal): %s', e)
        latest_mesh = None

    return dict(
        status='success',
        region=region,
        regions_available=list(region_textures.keys()),
        regions_remaining=[r for r in CAPTURE_REGIONS if r not in region_textures],
        glb_url=f'/web_app/api/mesh/{latest_mesh.id}.glb' if latest_mesh else None,
        viewer_url=(f'/web_app/static/viewer3d/index.html?model=/web_app/api/mesh/{latest_mesh.id}.glb'
                    if latest_mesh else None),
    )


@action('api/customer/<customer_id:int>/skin_regions', method=['GET'])
@action.uses(cors)
def list_skin_regions(customer_id):
    """List available and missing skin regions for a customer."""
    from core.skin_patch import CAPTURE_REGIONS, MINIMUM_REGIONS
    skin_dir = os.path.join(os.path.dirname(__file__), '..', 'uploads', 'skin',
                            f'customer_{customer_id}')
    available = []
    for rname in CAPTURE_REGIONS:
        if os.path.exists(os.path.join(skin_dir, f'tile_{rname}.png')):
            available.append(rname)
    return dict(
        status='success',
        available=available,
        missing=[r for r in CAPTURE_REGIONS if r not in available],
        minimum_required=MINIMUM_REGIONS,
        coverage_pct=round(len(available) / len(CAPTURE_REGIONS) * 100, 1),
    )


@action('api/customer/<customer_id:int>/skin_region/<region>/photos', method=['GET'])
@action.uses(cors)
def list_skin_region_photos(customer_id, region):
    """List all raw photos captured for a skin region."""
    from core.skin_patch import CAPTURE_REGIONS
    if region not in CAPTURE_REGIONS:
        return dict(status='error', message=f'Unknown region: {region}')

    skin_dir = os.path.join(os.path.dirname(__file__), '..', 'uploads', 'skin',
                            f'customer_{customer_id}')
    photos = []
    if os.path.isdir(skin_dir):
        import glob as _glob
        for ext in ('*.jpg', '*.jpeg', '*.png'):
            for p in _glob.glob(os.path.join(skin_dir, f'raw_{region}_*{ext}')):
                fname = os.path.basename(p)
                photos.append({
                    'filename': fname,
                    'url': f'/web_app/api/customer/{customer_id}/skin_photo/{fname}',
                    'size': os.path.getsize(p),
                    'mtime': os.path.getmtime(p),
                })
        # Also check legacy non-timestamped files
        for ext in ('.jpg', '.jpeg', '.png'):
            legacy = os.path.join(skin_dir, f'raw_{region}{ext}')
            if os.path.exists(legacy):
                fname = os.path.basename(legacy)
                if not any(ph['filename'] == fname for ph in photos):
                    photos.append({
                        'filename': fname,
                        'url': f'/web_app/api/customer/{customer_id}/skin_photo/{fname}',
                        'size': os.path.getsize(legacy),
                        'mtime': os.path.getmtime(legacy),
                    })
    photos.sort(key=lambda x: x['mtime'], reverse=True)
    # Mark which one is currently selected (has tile)
    tile_path = os.path.join(skin_dir, f'tile_{region}.png')
    return dict(
        status='success',
        region=region,
        photos=photos,
        has_tile=os.path.exists(tile_path) if os.path.isdir(skin_dir) else False,
    )


@action('api/customer/<customer_id:int>/skin_photo/<filename>', method=['GET'])
@action.uses(cors)
def serve_skin_photo(customer_id, filename):
    """Serve a raw skin photo for preview/thumbnail."""
    import re
    if not re.match(r'^raw_[a-z_]+.*\.(jpg|jpeg|png)$', filename, re.I):
        raise HTTP(400, 'Invalid filename')
    skin_dir = os.path.join(os.path.dirname(__file__), '..', 'uploads', 'skin',
                            f'customer_{customer_id}')
    fpath = os.path.join(skin_dir, filename)
    if not os.path.exists(fpath):
        raise HTTP(404, 'Photo not found')
    ext = os.path.splitext(filename)[1].lower()
    ct = 'image/jpeg' if ext in ('.jpg', '.jpeg') else 'image/png'
    response.headers['Content-Type'] = ct
    response.headers['Cache-Control'] = 'max-age=300'
    return open(fpath, 'rb').read()


@action('api/customer/<customer_id:int>/skin_region/<region>/select', method=['POST'])
@action.uses(db, cors)
def select_skin_photo(customer_id, region):
    """Select a specific raw photo as the source for this region's tile texture."""
    payload, err = _auth_check()
    if err: return err

    from core.skin_patch import CAPTURE_REGIONS, make_tileable, composite_skin_atlas
    if region not in CAPTURE_REGIONS:
        return dict(status='error', message=f'Unknown region: {region}')

    data = request.json or {}
    photo_filename = data.get('photo')
    if not photo_filename:
        return dict(status='error', message='Missing "photo" field')

    skin_dir = os.path.join(os.path.dirname(__file__), '..', 'uploads', 'skin',
                            f'customer_{customer_id}')
    raw_path = os.path.join(skin_dir, photo_filename)
    if not os.path.exists(raw_path):
        return dict(status='error', message=f'Photo not found: {photo_filename}')

    import cv2 as _cv2_sel
    img = _cv2_sel.imread(raw_path)
    if img is None:
        return dict(status='error', message='Could not read image')

    # Re-tile from selected photo
    tile = make_tileable(img, out_size=512, patch_size=48, overlap=12)
    tile_path = os.path.join(skin_dir, f'tile_{region}.png')
    _cv2_sel.imwrite(tile_path, tile)

    # Re-composite atlas
    region_textures = {}
    for rname in CAPTURE_REGIONS:
        tp = os.path.join(skin_dir, f'tile_{rname}.png')
        if os.path.exists(tp):
            region_textures[rname] = _cv2_sel.imread(tp)

    latest_mesh = None
    try:
        from core.texture_factory import get_part_ids
        import pickle as _pkl_sel
        pkl_path = os.path.join(os.path.dirname(__file__), '..', '..', 'runpod', 'SMPL_NEUTRAL.pkl')
        with open(pkl_path, 'rb') as f:
            _smpl = _pkl_sel.load(f, encoding='latin1')
        faces = np.array(_smpl['f'], dtype=np.int32)

        from core.smpl_direct import _load_canonical_uvs, cylindrical_uvs
        from core.smpl_optimizer import smpl_forward
        verts, _ = smpl_forward(np.zeros(10))
        uvs = _load_canonical_uvs()
        if uvs is None:
            uvs = cylindrical_uvs(verts)

        part_ids = get_part_ids(len(uvs))
        atlas = composite_skin_atlas(uvs, part_ids, faces, region_textures, atlas_size=2048)
        atlas_path = os.path.join(skin_dir, 'skin_atlas.png')
        _cv2_sel.imwrite(atlas_path, atlas)

        from core.skin_patch import generate_skin_normal_map
        from core.texture_factory import generate_roughness_map
        normal_map = generate_skin_normal_map(atlas, strength=10.0)
        roughness_float = generate_roughness_map(uvs, atlas_size=2048, vertices=verts)
        roughness_map = (roughness_float * 255).astype(np.uint8) if roughness_float is not None else None

        latest_mesh = db(db.mesh_model.customer_id == customer_id).select(
            orderby=~db.mesh_model.id).first()
        if latest_mesh and latest_mesh.glb_path:
            from core.mesh_reconstruction import export_glb
            verts_m = verts / 1000.0
            export_glb(verts_m, faces, latest_mesh.glb_path,
                        uvs=uvs, texture_image=atlas,
                        normal_map=normal_map, roughness_map=roughness_map)

    except Exception as e:
        logger.warning('Skin select compositing skipped (non-fatal): %s', e)
        latest_mesh = None

    return dict(
        status='success',
        region=region,
        selected_photo=photo_filename,
        regions_available=list(region_textures.keys()),
        glb_url=f'/web_app/api/mesh/{latest_mesh.id}.glb' if latest_mesh else None,
    )


@action('api/customer/<customer_id:int>/pbr_textures', method=['GET'])
@action.uses(db, cors)
def get_pbr_textures(customer_id):
    """Return URLs to PBR texture maps for customer's latest body mesh."""
    payload, err = _auth_check()
    if err: return err

    latest_mesh = db(
        (db.mesh_model.customer_id == customer_id) &
        (db.mesh_model.model_type == 'body')
    ).select(orderby=~db.mesh_model.id, limitby=(0, 1)).first()
    if not latest_mesh:
        return dict(status='error', message='No body mesh found for customer')

    mesh_id = latest_mesh.id
    pbr_dir = os.path.join(os.path.dirname(__file__), '..', 'uploads',
                           f'pbr_{customer_id}_{mesh_id}')

    # Generate on-demand if not already cached
    if not os.path.exists(os.path.join(pbr_dir, 'body_albedo.png')):
        try:
            import pygltflib, struct
            import numpy as np
            import cv2
            from core.texture_factory import generate_pbr_textures, save_pbr_textures

            glb_path = latest_mesh.glb_path
            if not glb_path or not os.path.exists(glb_path):
                return dict(status='error', message='GLB mesh not found on disk')

            gltf = pygltflib.GLTF2().load(glb_path)
            blob = gltf.binary_blob()

            acc = gltf.accessors[gltf.meshes[0].primitives[0].attributes.POSITION]
            bv = gltf.bufferViews[acc.bufferView]
            n_v = acc.count
            verts = np.array(struct.unpack(f'<{n_v*3}f',
                blob[bv.byteOffset:bv.byteOffset+bv.byteLength])).reshape(n_v, 3).astype(np.float32)

            ia = gltf.accessors[gltf.meshes[0].primitives[0].indices]
            ibv = gltf.bufferViews[ia.bufferView]
            fmt = 'I' if ia.componentType == 5125 else 'H'
            faces = np.array(struct.unpack(f'<{ia.count}{fmt}',
                blob[ibv.byteOffset:ibv.byteOffset+ibv.byteLength])).reshape(-1, 3).astype(np.int32)

            prim = gltf.meshes[0].primitives[0]
            uvs = None
            if hasattr(prim.attributes, 'TEXCOORD_0') and prim.attributes.TEXCOORD_0 is not None:
                ua = gltf.accessors[prim.attributes.TEXCOORD_0]
                ubv = gltf.bufferViews[ua.bufferView]
                uvs = np.array(struct.unpack(f'<{ua.count*2}f',
                    blob[ubv.byteOffset:ubv.byteOffset+ubv.byteLength])).reshape(-1, 2).astype(np.float32)

            albedo = None
            if gltf.images:
                img0 = gltf.images[0]
                if img0.bufferView is not None:
                    i0bv = gltf.bufferViews[img0.bufferView]
                    img_bytes = blob[i0bv.byteOffset:i0bv.byteOffset+i0bv.byteLength]
                    arr = np.frombuffer(img_bytes, dtype=np.uint8)
                    albedo = cv2.imdecode(arr, cv2.IMREAD_COLOR)

            if uvs is None:
                from core.uv_canonical import get_canonical_uvs
                uvs = get_canonical_uvs()
            if albedo is None:
                return dict(status='error', message='No albedo texture in GLB')

            pbr_set = generate_pbr_textures(albedo, uvs, verts, faces,
                                            atlas_size=2048, upscale=True)
            save_pbr_textures(pbr_set, pbr_dir)
        except Exception as e:
            logger.error('PBR texture generation failed: %s', e)
            return dict(status='error', message=f'PBR generation failed: {e}')

    base = f'/web_app/api/customer/{customer_id}/pbr_textures'
    textures = {}
    valid_types = ('albedo', 'normal', 'roughness', 'ao', 'definition', 'displacement')
    for tex_type in valid_types:
        if os.path.exists(os.path.join(pbr_dir, f'body_{tex_type}.png')):
            textures[tex_type] = f'{base}/{tex_type}'
    if not textures:
        return dict(status='error', message='No PBR textures on disk')
    return dict(status='success', textures=textures, mesh_id=int(mesh_id))


@action('api/customer/<customer_id:int>/pbr_textures/<tex_type>', method=['GET'])
@action.uses(db, cors)
def serve_pbr_texture(customer_id, tex_type):
    """Serve a PBR texture PNG (albedo, normal, roughness, ao, definition, displacement)."""
    valid = {'albedo', 'normal', 'roughness', 'ao', 'definition', 'displacement'}
    if tex_type not in valid:
        abort(400, f'Type must be one of: {sorted(valid)}')

    latest_mesh = db(
        (db.mesh_model.customer_id == customer_id) &
        (db.mesh_model.model_type == 'body')
    ).select(orderby=~db.mesh_model.id, limitby=(0, 1)).first()
    if not latest_mesh:
        abort(404, 'No body mesh found')

    fpath = os.path.join(os.path.dirname(__file__), '..', 'uploads',
                         f'pbr_{customer_id}_{latest_mesh.id}', f'body_{tex_type}.png')
    if not os.path.exists(fpath):
        abort(404, f'No {tex_type} PBR texture for customer {customer_id}')

    response.headers['Content-Type'] = 'image/png'
    response.headers['Cache-Control'] = 'public, max-age=3600'
    with open(fpath, 'rb') as f:
        return f.read()


@action('api/room_assets/<room_type>', method=['GET'])
@action.uses(cors)
def get_room_assets(room_type):
    """Return PolyHaven texture serve-URLs for a room type (home/gym/studio/outdoor)."""
    valid = {'home', 'gym', 'studio', 'outdoor'}
    if room_type not in valid:
        return dict(status='error', message=f'room_type must be one of {sorted(valid)}')

    set_name = f'room_{room_type}' if room_type in ('home', 'gym') else room_type
    try:
        from core.asset_cache import get_asset_set
        assets = get_asset_set(set_name, download=False)
    except Exception as e:
        logger.warning('Asset cache error: %s', e)
        assets = None

    if not assets or (not assets.get('hdris') and not assets.get('textures')):
        # Kick off background download, return empty now
        import threading as _bt
        def _dl():
            try:
                from core.asset_cache import get_asset_set
                get_asset_set(set_name, download=True)
            except Exception:
                pass
        _bt.Thread(target=_dl, daemon=True).start()
        return dict(status='success', room_type=room_type, hdri_url=None,
                    floor_diff=None, wall_diff=None, ceiling_diff=None,
                    message='Assets downloading in background, retry in 60s')

    _polyhaven_base = os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..', 'assets', 'polyhaven'))

    def _asset_url(path):
        if not path or not os.path.exists(path):
            return None
        rel = os.path.relpath(path, _polyhaven_base).replace(os.sep, '/')
        return f'/web_app/api/asset/{rel}'

    result = dict(status='success', room_type=room_type)
    result['hdri_url'] = _asset_url(assets['hdris'][0]) if assets.get('hdris') else None
    textures = assets.get('textures', {})
    result['floor_diff'] = _asset_url((textures.get('floor') or {}).get('diff'))
    result['wall_diff'] = _asset_url((textures.get('wall') or {}).get('diff'))
    result['ceiling_diff'] = _asset_url((textures.get('ceiling') or {}).get('diff'))
    return result


@action('api/asset/<asset_path:path>', method=['GET'])
@action.uses(cors)
def serve_asset(asset_path):
    """Serve cached PolyHaven assets (HDRIs, textures)."""
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'assets', 'polyhaven'))
    full_path = os.path.abspath(os.path.join(base, asset_path))
    if not full_path.startswith(base):
        abort(403)
    if not os.path.exists(full_path):
        abort(404)
    ext = os.path.splitext(full_path)[1].lower()
    ctype = {'.hdr': 'application/octet-stream', '.jpg': 'image/jpeg',
             '.png': 'image/png', '.exr': 'application/octet-stream'}.get(ext, 'application/octet-stream')
    response.headers['Content-Type'] = ctype
    response.headers['Cache-Control'] = 'public, max-age=86400'
    with open(full_path, 'rb') as f:
        return f.read()


_render_jobs = {}  # job_id → {status, renders, error, started, customer_id}


def _do_render(job_id, mesh_path, room, quality, angles):
    """Background thread: run Blender render and store result in _render_jobs."""
    try:
        from core.blender_renderer import render_body
        result = render_body(mesh_path, room=room, quality=quality, angles=angles)
        _render_jobs[job_id].update({
            'status': result['status'],
            'renders': result.get('renders', []),
            'output_dir': result.get('output_dir', ''),
            'error': result.get('message') if result['status'] != 'success' else None,
        })
    except Exception as e:
        _render_jobs[job_id].update({'status': 'error', 'error': str(e)})


@action('api/customer/<customer_id:int>/render', method=['POST'])
@action.uses(db, cors)
def render_body_model(customer_id):
    """Trigger async Blender Cycles render. Returns job_id immediately."""
    payload, err = _auth_check()
    if err: return err

    latest_mesh = db(
        (db.mesh_model.customer_id == customer_id) &
        (db.mesh_model.model_type == 'body')
    ).select(orderby=~db.mesh_model.id, limitby=(0, 1)).first()
    if not latest_mesh or not latest_mesh.glb_path:
        return dict(status='error', message='No GLB mesh found for customer')
    if not os.path.exists(latest_mesh.glb_path):
        return dict(status='error', message='GLB file missing on disk')

    body = request.json or {}
    room = body.get('room', 'studio')
    quality = body.get('quality', 'draft')
    angles = body.get('angles', 1)

    import uuid, threading
    job_id = str(uuid.uuid4())[:8]
    _render_jobs[job_id] = {
        'status': 'running',
        'customer_id': customer_id,
        'started': time.time(),
        'renders': [],
        'error': None,
    }
    threading.Thread(
        target=_do_render,
        args=(job_id, latest_mesh.glb_path, room, quality, angles),
        daemon=True,
    ).start()

    return dict(status='success', job_id=job_id, message='Render started')


@action('api/customer/<customer_id:int>/render/<job_id>', method=['GET'])
@action.uses(cors)
def render_status(customer_id, job_id):
    """Poll render job status."""
    job = _render_jobs.get(job_id)
    if not job:
        return dict(status='error', message='Job not found')

    result = dict(
        status=job['status'],
        elapsed=round(time.time() - job['started'], 1),
        job_id=job_id,
    )
    if job['status'] == 'success' and job.get('renders'):
        # Convert local paths → serveable URLs
        result['renders'] = [
            f'/web_app/api/render_image/{job_id}/{os.path.basename(p)}'
            for p in job['renders']
        ]
    if job.get('error'):
        result['error'] = job['error']
    return result


@action('api/render_image/<job_id>/<filename>', method=['GET'])
@action.uses(cors)
def serve_render_image(job_id, filename):
    """Serve a rendered PNG from a completed render job."""
    job = _render_jobs.get(job_id)
    if not job or not job.get('output_dir'):
        abort(404)
    fpath = os.path.join(job['output_dir'], filename)
    if not os.path.exists(fpath) or not fpath.endswith('.png'):
        abort(404)
    response.headers['Content-Type'] = 'image/png'
    response.headers['Cache-Control'] = 'public, max-age=3600'
    with open(fpath, 'rb') as f:
        return f.read()


@action('api/customer/<customer_id:int>/body_profile', method=['POST'])
@action.uses(db, cors)
def update_body_profile(customer_id):
    payload, err = _auth_check()
    if err: return err
    customer = db.customer[customer_id]
    if not customer:
        return dict(status='error', message='Customer not found')
    data = request.json or {}
    updates = {}
    for field in _BODY_PROFILE_FIELDS:
        if field in data and data[field] is not None:
            if field == 'skin_tone_hex':
                updates[field] = str(data[field])[:8]
            else:
                try:
                    updates[field] = float(data[field])
                except (ValueError, TypeError):
                    pass
    # Mark complete when height + weight + at least 3 circumferences are filled
    all_vals = {**{f: getattr(customer, f, None) for f in _BODY_PROFILE_FIELDS}, **updates}
    circs = [f for f in _BODY_PROFILE_FIELDS if 'circumference' in f]
    filled_circs = sum(1 for f in circs if all_vals.get(f))
    updates['profile_completed'] = bool(
        all_vals.get('height_cm') and all_vals.get('weight_kg') and filled_circs >= 3
    )
    customer.update_record(**updates)
    db.commit()
    return dict(status='success', profile_completed=updates['profile_completed'], updated=list(updates.keys()))


# --- DEVICE PROFILE ---

@action('api/customer/<customer_id:int>/devices', method=['GET'])
@action.uses(db, cors)
def get_devices(customer_id):
    payload, err = _auth_check()
    if err: return err
    devices = db(db.device_profile.customer_id == customer_id).select(
        orderby=db.device_profile.id)
    return dict(status='success', devices=[r.as_dict() for r in devices])


@action('api/customer/<customer_id:int>/devices', method=['POST'])
@action.uses(db, cors)
def add_or_update_device(customer_id):
    payload, err = _auth_check()
    if err: return err
    data = request.json or {}
    serial = (data.get('device_serial') or '').strip()
    existing = None
    if serial:
        existing = db(
            (db.device_profile.customer_id == customer_id) &
            (db.device_profile.device_serial == serial)
        ).select().first()

    def _flt(key, default=0.0):
        try: return float(data.get(key) or default)
        except (ValueError, TypeError): return default

    def _int(key, default=0):
        try: return int(data.get(key) or default)
        except (ValueError, TypeError): return default

    fields = dict(
        customer_id=customer_id,
        device_name=(data.get('device_name') or '').strip(),
        device_serial=serial,
        role=data.get('role', 'front'),
        orientation=data.get('orientation', 'portrait'),
        camera_height_from_ground_cm=_flt('camera_height_from_ground_cm'),
        distance_to_subject_cm=_flt('distance_to_subject_cm', 100.0),
        sensor_width_mm=_flt('sensor_width_mm'),
        focal_length_mm=_flt('focal_length_mm'),
        screen_width_px=_int('screen_width_px'),
        screen_height_px=_int('screen_height_px'),
        tap_x=_int('tap_x'),
        tap_y=_int('tap_y'),
        notes=data.get('notes', ''),
    )
    if existing:
        existing.update_record(**fields)
        db.commit()
        return dict(status='success', device_id=existing.id, action='updated')
    device_id = db.device_profile.insert(**fields)
    db.commit()
    return dict(status='success', device_id=device_id, action='created')


@action('api/customer/<customer_id:int>/devices/<device_id:int>', method=['DELETE'])
@action.uses(db, cors)
def delete_device(customer_id, device_id):
    payload, err = _auth_check()
    if err: return err
    db(
        (db.device_profile.id == device_id) &
        (db.device_profile.customer_id == customer_id)
    ).delete()
    db.commit()
    return dict(status='success')


# --- SCAN SETUP ---

@action('api/customer/<customer_id:int>/scan_setup', method=['POST'])
@action.uses(db, cors)
def save_scan_setup(customer_id):
    payload, err = _auth_check()
    if err: return err
    data = request.json or {}
    try:
        dist = float(data.get('distance_to_subject_cm') or 100.0)
    except (ValueError, TypeError):
        dist = 100.0
    setup_id = db.scan_setup.insert(
        customer_id=customer_id,
        distance_to_subject_cm=dist,
        lighting=data.get('lighting', ''),
        clothing=data.get('clothing', ''),
        notes=data.get('notes', ''),
    )
    db.commit()
    return dict(status='success', setup_id=setup_id)


# --- CALIBRATION QUESTIONS ---

@action('api/customer/<customer_id:int>/calibration_questions', method=['GET'])
@action.uses(db, cors)
def calibration_questions(customer_id):
    """Return prioritised list of missing measurements Sonnet should ask the user."""
    payload, err = _auth_check()
    if err: return err
    customer = db.customer[customer_id]
    if not customer:
        return dict(status='error', message='Customer not found')
    devices = db(db.device_profile.customer_id == customer_id).select()
    questions = []

    if not customer.height_cm:
        questions.append(dict(id='height_cm', type='number', unit='cm',
            question='How tall are you?',
            hint='Stand against a wall, mark the top of your head, measure from floor.',
            priority='required'))
    if not customer.weight_kg:
        questions.append(dict(id='weight_kg', type='number', unit='kg',
            question='What is your weight?', priority='required'))

    if not devices:
        questions.append(dict(id='camera_height_from_ground_cm', type='number', unit='cm',
            question='How high is the phone camera from the floor?',
            hint='Measure from floor to the camera lens. Chair height + where the device sits.',
            priority='important'))
        questions.append(dict(id='distance_to_subject_cm', type='number', unit='cm',
            question='How far do you stand from the phone?',
            hint='Measure the straight-line distance from camera to where you stand.',
            priority='important'))

    latest_scan = db(db.muscle_scan.customer_id == customer_id).select(
        orderby=~db.muscle_scan.scan_date, limitby=(0, 1)).first()
    target = (latest_scan.muscle_group if latest_scan else 'bicep')

    _muscle_q = {
        'bicep':     ('bicep_circumference_cm',    'What is your relaxed bicep circumference?',
                      'Wrap tape around the widest part of your upper arm, arm hanging at side.'),
        'quadricep': ('quadricep_circumference_cm', 'What is your quadricep circumference?',
                      'Wrap tape around the widest part of your thigh, standing upright.'),
        'calf':      ('calf_circumference_cm',      'What is your calf circumference?',
                      'Wrap tape around the widest part of your calf.'),
        'chest':     ('chest_circumference_cm',     'What is your chest circumference?',
                      'Wrap tape at nipple height, arms at sides, relaxed breath.'),
        'hamstring': ('thigh_circumference_cm',     'What is your thigh circumference?',
                      'Wrap tape around the widest part of your thigh.'),
    }
    if target in _muscle_q:
        field, q, hint = _muscle_q[target]
        if not getattr(customer, field, None):
            questions.append(dict(id=field, type='number', unit='cm',
                question=q, hint=hint, priority='helpful'))

    return dict(
        status='success',
        questions=questions,
        profile_completed=bool(customer.profile_completed),
        remaining=len(questions),
    )


# ── T3.2: Body model from measurements ───────────────────────────────────────

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
        # Reused for HMR shape prediction, silhouette extraction, depth
        # estimation, and texture projection — avoids multiple file saves.
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
        # Uses HMR2.0 → rembg → cylindrical UV → UV rasterization → delight
        # Falls back to Anny path if direct SMPL fails or no images
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


# ── Live deformation endpoint ─────────────────────────────────────────────────

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


# ── T4.2: Video scan upload + quality gate + frame extraction ─────────────────

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


# --- GTD3D STUDIO v2 (Unified) ---

@action('studio_v2')
@action.uses('studio_v2.html', db)
def studio_v2():
    """GTD3D Studio v2 — unified single-page editor."""
    return dict()


# --- GTD3D STUDIO (v5.5 Cinematic) ---

@action('studio')
@action.uses('studio.html', db)
def studio():
    return dict(phone_ip="192.168.100.2")

@action('studio/dashboard/<customer_id:int>')
def studio_dashboard(customer_id):
    import os
    save_dir = os.path.join('scripts', 'dual_captures', str(customer_id))
    if not os.path.exists(save_dir):
        return dict(captures=[])
        
    files = []
    for f in os.listdir(save_dir):
        if f.endswith('.jpg'):
            files.append({
                'filename': f,
                'url': URL('api/studio/snapshot', customer_id=customer_id, filename=f)
            })
    files.sort(key=lambda x: x['filename'], reverse=True)
    return dict(captures=files[:10])

@action('studio/process/<customer_id:int>', method=['POST'])
def studio_process(customer_id):
    import os
    import json
    from core.pipeline import full_scan_pipeline
    
    save_dir = os.path.join('scripts', 'dual_captures', str(customer_id))
    if not os.path.exists(save_dir):
        return dict(status='error', message='No captures found')
        
    files = [f for f in os.listdir(save_dir) if f.endswith('.jpg')]
    front = next((f for f in files if f.startswith('front')), None)
    side = next((f for f in files if f.startswith('side')), None)
    
    if not front or not side:
        return dict(status='error', message='Missing required angles (front/side)')
        
    front_path = os.path.join(save_dir, front)
    side_path = os.path.join(save_dir, side)
    
    row = db.customer[customer_id]
    
    try:
        result = full_scan_pipeline(
            image_front_path=front_path,
            image_side_path=side_path,
            user_height_cm=row.height_cm if row else 170,
            user_weight_kg=row.weight_kg if row else 70,
            muscle_group='quadricep',
            gender=row.gender.lower() if row and row.gender else 'male',
            output_dir=os.path.join('apps', 'web_app', 'uploads', str(customer_id))
        )
        
        mesh_id = db.mesh_model.insert(
            customer_id=customer_id,
            volume_cm3=result.get('volume_cm3', 0),
            mesh_data=json.dumps(result.get('mesh_data', {}))
        )
        db.commit()
        return dict(status='success', mesh_id=mesh_id, metrics=result)
    except Exception as e:
        return dict(status='error', message=str(e))

@action('api/studio/snapshot/<customer_id:int>/<filename>')
def studio_snapshot_file(customer_id, filename):
    import os
    from ombott import static_file
    save_dir = os.path.join('scripts', 'dual_captures', str(customer_id))
    return static_file(filename, root=save_dir)

@action('api/studio/upload_frame/<customer_id:int>', method=['POST'])
def studio_upload_frame(customer_id):
    import os
    import json
    upload = request.files.get('frame')
    metadata_str = request.forms.get('metadata')
    
    if not upload:
        return dict(status='error', message='No frame uploaded')
        
    metadata = json.loads(metadata_str) if metadata_str else {}
    phase = metadata.get('phase', 'unknown')
    ts = metadata.get('timestamp', '0')
    
    save_dir = os.path.join('scripts', 'dual_captures', str(customer_id))
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
        
    filename = f"{phase}_{ts}.jpg"
    filepath = os.path.join(save_dir, filename)
    upload.save(filepath)
    
    meta_path = filepath.replace('.jpg', '.json')
    with open(meta_path, 'w') as f:
        json.dump(metadata, f, indent=4)
        
    return dict(status='success', filepath=filepath)

@action('api/studio/sensors')
def studio_sensors():
    """Proxy sensor data from the phone to avoid CORS issues."""
    import urllib.request
    ip = request.query.get('ip')
    if not ip: return dict(status='error', message='No IP provided')
    
    try:
        url = f"http://{ip}:8080/sensors"
        with urllib.request.urlopen(url, timeout=2) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        logger.warning("Sensor proxy failed for %s: %s", ip, e)
        return dict(status='error', message=str(e))

@action('api/studio/control', method=['POST'])
def studio_control():
    """Proxy control commands to the phone."""
    import urllib.request
    data = request.json or {}
    ip = data.get('ip')
    cmd = data.get('action')
    val = data.get('value')
    
    if not ip or not cmd:
        return dict(status='error', message='Missing IP or command')
    
    try:
        url = f"http://{ip}:8080/control"
        # IP Webcam Pro usually expects GET or form-data for controls, but let's try JSON if that's what's sent
        # Standard IP Webcam: /settings/fflash?set=on or similar.
        # But if the companion app/IP webcam pro uses a custom /control endpoint, we match that.
        
        req = urllib.request.Request(
            url, 
            data=json.dumps({'action': cmd, 'value': val}).encode(),
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            return dict(status='success', detail=response.read().decode())
    except Exception as e:
        logger.error("Control proxy failed: %s", e)
        return dict(status='error', message=str(e))

@action('viewer')
@action.uses('viewer.html')
def viewer():
    return dict()


@action('body_viewer', method=['GET'])
@action.uses('body_viewer.html')
def body_viewer():
    """Serve the enhanced body scan 3D viewer."""
    return dict()


@action('api/body_scan_result', method=['GET'])
@action.uses(db)
def body_scan_result():
    """Return session result data for the 3D viewer."""
    session_id = request.params.get('session')
    if not session_id:
        response.status = 400
        return dict(status='error', message='Missing session parameter')

    session = db(db.body_scan_session.session_id == session_id).select().first()
    if not session:
        response.status = 404
        return dict(status='error', message='Session not found')

    coverage = json.loads(session.coverage_report or '{}')
    regions = coverage.get('regions', {})
    total_regions = len(regions)
    good_regions = sum(
        1 for r in regions.values()
        if r.get('grade') in ('excellent', 'good')
    )
    coverage_pct = (good_regions / total_regions * 100) if total_regions > 0 else 0

    glb_url = ''
    vertex_count = session.vertex_count or 0
    face_count = session.face_count or 0
    if session.glb_path and os.path.exists(session.glb_path):
        glb_url = '/web_app/' + session.glb_path.replace('\\', '/')

    return dict(
        session_id=session_id,
        status=session.status,
        glb_url=glb_url,
        coverage_pct=round(coverage_pct, 1),
        vertex_count=vertex_count,
        face_count=face_count,
        created_on=str(session.created_on) if session.created_on else '',
        coverage_report=coverage,
    )


# --- BODY SCAN ENDPOINTS ---

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
    from core.body_scan_pipeline import bake_final_model
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
