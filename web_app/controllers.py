from py4web import action, request, response, abort, URL
from py4web.utils.cors import CORS
from .models import db, MUSCLE_GROUPS, VOLUME_MODELS
import os
import sys
import logging
import json
import cv2

logger = logging.getLogger(__name__)

# Initialize CORS
cors = CORS()

# Add project root to path for core imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from core.auth import create_token, verify_token as verify_jwt
from core.vision_medical import analyze_muscle_growth
from core.volumetrics import estimate_muscle_volume, compare_volumes
from core.segmentation import score_muscle_shape, AVAILABLE_TEMPLATES
from core.symmetry import compare_symmetry
from core.progress import analyze_trend, calculate_correlation
from core.pose_analyzer import analyze_pose
from core.report_generator import generate_clinical_report
from core.keyframe_extractor import extract_keyframes, save_keyframes

# Legacy static token for backward compatibility in dev mode
_LEGACY_DEV_TOKEN = os.environ.get('MUSCLE_TRACKER_API_TOKEN', 'dev-secret-token')


def require_auth():
    """
    Authenticate the request via JWT or legacy static token.
    """
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        abort(401, "Unauthorized: Missing Authorization header")

    token = auth_header[7:]  # Strip 'Bearer '

    # Try JWT first
    payload = verify_jwt(token)
    if payload is not None:
        request._auth_payload = payload
        return payload

    # Fall back to legacy static token (dev mode)
    if token == _LEGACY_DEV_TOKEN:
        payload = {'sub': 'dev', 'role': 'admin'}
        request._auth_payload = payload
        return payload

    abort(401, "Unauthorized: Invalid or expired token")


def require_customer_auth(customer_id):
    """
    Enforce authentication and ensure the requesting user owns the data.
    """
    payload = require_auth()
    requesting_customer_id = payload.get('sub')
    
    # In dev mode with legacy token, sub is 'dev'
    if requesting_customer_id == 'dev':
        return requesting_customer_id

    if str(requesting_customer_id) != str(customer_id):
        abort(403, "Access denied: You do not have permission to access this resource")
    
    return requesting_customer_id


# File upload constraints
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff'}
ALLOWED_VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv'}
MAX_FILE_SIZE_MB = 15
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


# --- AUTH ---

@action('api/auth/token', method=['POST'])
@action.uses(db, cors)
def auth_token():
    """
    Issue a JWT token. Accepts email or customer_id.
    """
    data = request.json or {}
    email = data.get('email', '').strip()
    customer_id = data.get('customer_id')

    if email:
        customer = db(db.customer.email == email).select().first()
        if not customer:
            return dict(status='error', message='Customer not found')
        token = create_token(customer.id, role='user')
        return dict(status='success', token=token, customer_id=customer.id, name=customer.name)

    if customer_id:
        customer = db.customer(customer_id)
        if not customer:
            return dict(status='error', message='Customer not found')
        token = create_token(customer.id, role='user')
        return dict(status='success', token=token, customer_id=customer.id, name=customer.name)

    return dict(status='error', message='Provide email or customer_id')


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

@action('index')
@action.uses('index.html', db)
def index():
    customers = db(db.customer.is_active == True).select(orderby=db.customer.name)
    return dict(customers=customers)


# --- CUSTOMER MANAGEMENT ---

@action('api/customers', method=['GET'])
@action.uses(db, cors)
def list_customers():
    payload = require_auth()
    if payload.get('role') != 'admin':
        abort(403, "Admin access required")
    customers = db(db.customer.is_active == True).select().as_list()
    return dict(status='success', customers=customers)


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
    auth_id = require_customer_auth(customer_id)
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

    if muscle_group not in MUSCLE_GROUPS:
        return dict(status='error', message=f'Invalid muscle group. Options: {MUSCLE_GROUPS}')

    front_filename = db.muscle_scan.img_front.store(front.file, front.filename)
    side_filename = db.muscle_scan.img_side.store(side.file, side.filename)

    front_path = os.path.join('uploads', front_filename)
    side_path = os.path.join('uploads', side_filename)

    res = _process_and_save_scan(customer, customer_id, front_path, side_path, front_filename, side_filename, muscle_group, scan_side, marker_size, volume_model, shape_template)
    
    if res.get('status') == 'success':
        db.audit_log.insert(customer_id=auth_id if auth_id != 'dev' else customer_id, action='upload_scan', resource_id=str(res.get('scan_id')), ip_address=request.environ.get('REMOTE_ADDR', 'unknown'))
        db.commit()
    
    return res


@action('api/upload_video/<customer_id:int>', method=['POST'])
@action.uses(db, cors)
def upload_video(customer_id):
    auth_id = require_customer_auth(customer_id)
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
    video_path = os.path.join('uploads', video_filename)

    frames = extract_keyframes(video_path, num_frames=3)
    if len(frames) < 2:
        return dict(status='error', message='Failed to extract enough keyframes from video')

    uploads_dir = 'uploads'
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

    res = _process_and_save_scan(customer, customer_id, front_path, side_path, front_filename, side_filename, muscle_group, scan_side, marker_size, volume_model, shape_template)
    
    if res.get('status') == 'success':
        db.audit_log.insert(customer_id=auth_id if auth_id != 'dev' else customer_id, action='upload_video', resource_id=str(res.get('scan_id')), ip_address=request.environ.get('REMOTE_ADDR', 'unknown'))
        db.commit()
        
    return res


def _process_and_save_scan(customer, customer_id, front_path, side_path, front_filename, side_filename, muscle_group, scan_side, marker_size, volume_model, shape_template):
    try:
        user_height_cm = customer.height_cm
        res_f = analyze_muscle_growth(front_path, front_path, marker_size, align=False, muscle_group=muscle_group, user_height_cm=user_height_cm)
        res_s = analyze_muscle_growth(side_path, side_path, marker_size, align=False, muscle_group=muscle_group, user_height_cm=user_height_cm)

        if "error" in res_f or "error" in res_s:
            error_msg = res_f.get("error", "") or res_s.get("error", "")
            return dict(status='error', message=f'Vision analysis failed: {error_msg}')

        unit = "mm" if res_f.get("calibrated") else "px"
        area = res_f['metrics'].get(f'area_a_{unit}2', 0.0)
        width = res_f['metrics'].get(f'width_a_{unit}', 0.0)
        height = res_f['metrics'].get(f'height_a_{unit}', 0.0)
        area_side = res_s['metrics'].get(f'area_a_{unit}2', 0.0)
        width_side = res_s['metrics'].get(f'width_a_{unit}', 0.0)

        vol_result = estimate_muscle_volume(area, area_side, width, width_side, volume_model)
        vol_cm3 = vol_result.get('volume_cm3', 0.0)

        shape_score = None
        shape_grade = None
        if shape_template and shape_template in AVAILABLE_TEMPLATES:
            contour = res_f['raw_data']['contour_a']
            shape_result = score_muscle_shape(contour, shape_template)
            shape_score = shape_result.get('score')
            shape_grade = shape_result.get('grade')

        growth_pct = None
        volume_delta = None
        prev_scan = db(
            (db.muscle_scan.customer_id == customer_id) &
            (db.muscle_scan.muscle_group == muscle_group)
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
        )
        db.commit()

        return dict(
            status='success',
            scan_id=scan_id,
            volume_cm3=vol_cm3,
            area_mm2=area,
            shape_score=shape_score,
            shape_grade=shape_grade,
            growth_pct=round(growth_pct, 2) if growth_pct else None,
            volume_delta_cm3=round(volume_delta, 2) if volume_delta else None,
            calibrated=res_f.get('calibrated', False),
        )
    except Exception:
        logger.exception("Scan processing failed for customer %d", customer_id)
        return dict(status='error', message='Scan processing failed. Please try again.')


# --- REPORTS ---

@action('api/customer/<customer_id:int>/scans', method=['GET'])
@action.uses(db, cors)
def customer_scans(customer_id):
    require_customer_auth(customer_id)
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
    auth_id = require_customer_auth(customer_id)
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

    try:
        generate_clinical_report(
            scan_result,
            volume_result=volume_result,
            shape_result=shape_result,
            output_path=temp_path,
            patient_name=customer.name,
        )
        response.headers['Content-Type'] = 'image/png'
        with open(temp_path, 'rb') as f:
            data = f.read()
        
        db.audit_log.insert(customer_id=auth_id if auth_id != 'dev' else customer_id, action='get_report', resource_id=str(scan_id), ip_address=request.environ.get('REMOTE_ADDR', 'unknown'))
        db.commit()
        
        return data
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@action('api/customer/<customer_id:int>/progress', method=['GET'])
@action.uses(db, cors)
def customer_progress(customer_id):
    require_customer_auth(customer_id)
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

    return dict(status='success', trend=trend, correlation=correlation)


@action('api/customer/<customer_id:int>/symmetry', method=['POST'])
@action.uses(db, cors)
def customer_symmetry(customer_id):
    require_customer_auth(customer_id)
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


# --- POSE ANALYSIS ---

@action('api/pose_check', method=['POST'])
@action.uses(db, cors)
def pose_check():
    # Pose check is public for helping users capture good images
    require_auth()
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


# --- HEALTH LOGGING ---

@action('api/customer/<customer_id:int>/health_log', method=['POST'])
@action.uses(db, cors)
def add_health_log(customer_id):
    auth_id = require_customer_auth(customer_id)
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
    require_customer_auth(customer_id)
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


@action('api/<path:path>', method=['OPTIONS'])
@action.uses(cors)
def api_options(path):
    return ""
