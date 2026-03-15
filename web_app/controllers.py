from py4web import action, request, response, abort, URL
from py4web.utils.cors import CORS
from .models import db, MUSCLE_GROUPS, VOLUME_MODELS
import os
import sys
import logging
import json
import cv2
import numpy as np
from datetime import datetime

logger = logging.getLogger(__name__)

# Initialize CORS
cors = CORS()

# Add project root to path for core imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from core.auth import create_token, verify_token as verify_jwt
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

@action('api/health', method=['GET'])
def health_check():
    """Health check endpoint for Docker/load balancer."""
    return dict(
        status='ok',
        version='4.0',
        timestamp=str(datetime.utcnow()),
    )


@action('index')
@action.uses('index.html', db)
def index():
    customers = db(db.customer.is_active == True).select(orderby=db.customer.name)
    return dict(customers=customers)


# --- CUSTOMER MANAGEMENT ---

@action('api/customers', method=['GET'])
@action.uses(db, cors)
def list_customers():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return dict(status='error', message='Authentication required')
    payload = verify_jwt(token)
    if not payload:
        return dict(status='error', message='Invalid or expired token')
    
    if payload.get('role') != 'admin':
        return dict(status='error', message='Admin access required')
        
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
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return dict(status='error', message='Authentication required')
    payload = verify_jwt(token)
    if not payload:
        return dict(status='error', message='Invalid or expired token')
    requesting_customer_id = payload.get('customer_id') or payload.get('sub')
    
    if requesting_customer_id != 'admin' and str(requesting_customer_id) != str(customer_id):
        return dict(status='error', message='Access denied')

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
        db.audit_log.insert(
            customer_id=customer_id,
            action='upload_scan',
            resource_id=str(res.get('scan_id')),
            ip_address=request.environ.get('REMOTE_ADDR', 'unknown')
        )
        db.commit()
    
    return res


@action('api/upload_video/<customer_id:int>', method=['POST'])
@action.uses(db, cors)
def upload_video(customer_id):
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return dict(status='error', message='Authentication required')
    payload = verify_jwt(token)
    if not payload:
        return dict(status='error', message='Invalid or expired token')
    requesting_customer_id = payload.get('customer_id') or payload.get('sub')
    
    if requesting_customer_id != 'admin' and str(requesting_customer_id) != str(customer_id):
        return dict(status='error', message='Access denied')

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
        db.audit_log.insert(
            customer_id=customer_id,
            action='upload_video',
            resource_id=str(res.get('scan_id')),
            ip_address=request.environ.get('REMOTE_ADDR', 'unknown')
        )
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

        # Calibration ratio (px to mm)
        ratio_mm_per_px = res_f.get('ratio', 1.0)
        pixels_per_cm = 10.0 / ratio_mm_per_px if ratio_mm_per_px > 0 else 1.0

        unit = "mm" if res_f.get("calibrated") else "px"
        area = res_f['metrics'].get(f'area_a_{unit}2', 0.0)
        width = res_f['metrics'].get(f'width_a_{unit}', 0.0)
        height = res_f['metrics'].get(f'height_a_{unit}', 0.0)
        area_side = res_s['metrics'].get(f'area_a_{unit}2', 0.0)
        width_side = res_s['metrics'].get(f'width_a_{unit}', 0.0)

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

        # 5. Circumference estimate
        circumference_cm = None
        contour_front = res_f.get('raw_data', {}).get('contour_a') if 'raw_data' in res_f else None
        pixels_per_mm = 1.0 / ratio_mm_per_px if ratio_mm_per_px > 0 else 1.0
        if contour_front is not None and pixels_per_mm > 0:
            circ_result = estimate_circumference(contour_front, pixels_per_mm)
            circumference_cm = circ_result.get('circumference_cm')

        # 6. Definition score
        definition_score = None
        definition_grade = None
        if _HAS_DEFINITION_SCORER and contour_front is not None:
            try:
                front_img = cv2.imread(front_path)
                if front_img is not None:
                    def_result = score_muscle_definition(front_img, contour_front, muscle_group)
                    definition_score = def_result.get('overall_definition')
                    definition_grade = def_result.get('grade')
            except Exception:
                logger.warning("Definition scoring failed, skipping", exc_info=True)

        # 7. Measurement overlay — save annotated image
        annotated_filename = None
        if contour_front is not None:
            try:
                front_img = cv2.imread(front_path)
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
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return dict(status='error', message='Authentication required')
    payload = verify_jwt(token)
    if not payload:
        return dict(status='error', message='Invalid or expired token')
    requesting_customer_id = payload.get('customer_id') or payload.get('sub')
    
    if requesting_customer_id != 'admin' and str(requesting_customer_id) != str(customer_id):
        return dict(status='error', message='Access denied')

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
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return dict(status='error', message='Authentication required')
    payload = verify_jwt(token)
    if not payload:
        return dict(status='error', message='Invalid or expired token')
    requesting_customer_id = payload.get('customer_id') or payload.get('sub')
    
    if requesting_customer_id != 'admin' and str(requesting_customer_id) != str(customer_id):
        return dict(status='error', message='Access denied')

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
        pdf_path = generate_clinical_report(
            scan_result,
            volume_result=volume_result,
            shape_result=shape_result,
            output_path=temp_path,
            patient_name=customer.name,
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
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return dict(status='error', message='Authentication required')
    payload = verify_jwt(token)
    if not payload:
        return dict(status='error', message='Invalid or expired token')
    requesting_customer_id = payload.get('customer_id') or payload.get('sub')
    
    if requesting_customer_id != 'admin' and str(requesting_customer_id) != str(customer_id):
        return dict(status='error', message='Access denied')

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
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return dict(status='error', message='Authentication required')
    payload = verify_jwt(token)
    if not payload:
        return dict(status='error', message='Invalid or expired token')
    requesting_customer_id = payload.get('customer_id') or payload.get('sub')
    
    if requesting_customer_id != 'admin' and str(requesting_customer_id) != str(customer_id):
        return dict(status='error', message='Access denied')

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
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return dict(status='error', message='Authentication required')
    payload = verify_jwt(token)
    if not payload:
        return dict(status='error', message='Invalid or expired token')

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
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return dict(status='error', message='Authentication required')
    payload = verify_jwt(token)
    if not payload:
        return dict(status='error', message='Invalid or expired token')

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
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return dict(status='error', message='Authentication required')
    payload = verify_jwt(token)
    if not payload:
        return dict(status='error', message='Invalid or expired token')
    requesting_customer_id = payload.get('customer_id') or payload.get('sub')
    
    if requesting_customer_id != 'admin' and str(requesting_customer_id) != str(customer_id):
        return dict(status='error', message='Access denied')

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
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return dict(status='error', message='Authentication required')
    payload = verify_jwt(token)
    if not payload:
        return dict(status='error', message='Invalid or expired token')
    requesting_customer_id = payload.get('customer_id') or payload.get('sub')
    
    if requesting_customer_id != 'admin' and str(requesting_customer_id) != str(customer_id):
        return dict(status='error', message='Access denied')

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
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return dict(status='error', message='Authentication required')
    payload = verify_jwt(token)
    if not payload:
        return dict(status='error', message='Invalid or expired token')
    requesting_customer_id = payload.get('customer_id') or payload.get('sub')
    if requesting_customer_id != 'admin' and str(requesting_customer_id) != str(customer_id):
        return dict(status='error', message='Access denied')

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
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return dict(status='error', message='Authentication required')
    payload = verify_jwt(token)
    if not payload:
        return dict(status='error', message='Invalid or expired token')
    requesting_customer_id = payload.get('customer_id') or payload.get('sub')
    if requesting_customer_id != 'admin' and str(requesting_customer_id) != str(customer_id):
        return dict(status='error', message='Access denied')

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

    front_fn = db.muscle_scan.img_front.store(front_file.file, front_file.filename)
    side_fn  = db.muscle_scan.img_front.store(side_file.file, side_file.filename)
    front_path = os.path.join('uploads', front_fn)
    side_path  = os.path.join('uploads', side_fn)

    try:
        from core.vision_medical import analyze_muscle_growth
        from core.mesh_reconstruction import reconstruct_mesh_from_silhouettes, export_obj, generate_mesh_preview_image
        from core.mesh_volume import compute_mesh_volume_cm3

        res_f = analyze_muscle_growth(front_path, front_path, marker_size, align=False, muscle_group=muscle_group)
        res_s = analyze_muscle_growth(side_path,  side_path,  marker_size, align=False, muscle_group=muscle_group)

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
        os.makedirs('meshes', exist_ok=True)
        import time
        base_name  = f'mesh_{customer_id}_{int(time.time())}'
        obj_path   = os.path.join('meshes', base_name + '.obj')
        prev_path  = os.path.join('meshes', base_name + '_preview.png')

        export_obj(mesh_data['vertices'], mesh_data['faces'], obj_path)

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
            preview_path=prev_path if preview_url else None,
            volume_cm3=mesh_data.get('volume_cm3'),
            num_vertices=mesh_data.get('num_vertices'),
            num_faces=mesh_data.get('num_faces'),
        )
        db.commit()

        return dict(
            status='success',
            mesh_id=mesh_id,
            mesh_url=f'/meshes/{base_name}.obj',
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


@action('api/customer/<customer_id:int>/compare_3d', method=['POST'])
@action.uses(db, cors)
def compare_3d(customer_id):
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return dict(status='error', message='Authentication required')
    payload = verify_jwt(token)
    if not payload:
        return dict(status='error', message='Invalid or expired token')
    requesting_customer_id = payload.get('customer_id') or payload.get('sub')
    if requesting_customer_id != 'admin' and str(requesting_customer_id) != str(customer_id):
        return dict(status='error', message='Access denied')

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


# --- DASHBOARD ENDPOINTS ---

@action('api/customer/<customer_id:int>/body_map', method=['GET'])
@action.uses(db, cors)
def customer_body_map(customer_id):
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return dict(status='error', message='Authentication required')
    payload = verify_jwt(token)
    if not payload:
        return dict(status='error', message='Invalid or expired token')
    requesting_customer_id = payload.get('customer_id') or payload.get('sub')
    if requesting_customer_id != 'admin' and str(requesting_customer_id) != str(customer_id):
        return dict(status='error', message='Access denied')

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
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return dict(status='error', message='Authentication required')
    payload = verify_jwt(token)
    if not payload:
        return dict(status='error', message='Invalid or expired token')
    requesting_customer_id = payload.get('customer_id') or payload.get('sub')
    if requesting_customer_id != 'admin' and str(requesting_customer_id) != str(customer_id):
        return dict(status='error', message='Access denied')

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
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return dict(status='error', message='Authentication required')
    payload = verify_jwt(token)
    if not payload:
        return dict(status='error', message='Invalid or expired token')
    requesting_customer_id = payload.get('customer_id') or payload.get('sub')
    if requesting_customer_id != 'admin' and str(requesting_customer_id) != str(customer_id):
        return dict(status='error', message='Access denied')

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
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return dict(status='error', message='Authentication required')
    payload = verify_jwt(token)
    if not payload:
        return dict(status='error', message='Invalid or expired token')
    requesting_customer_id = payload.get('customer_id') or payload.get('sub')
    if requesting_customer_id != 'admin' and str(requesting_customer_id) != str(customer_id):
        return dict(status='error', message='Access denied')

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
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return dict(status='error', message='Authentication required')
    payload = verify_jwt(token)
    if not payload:
        return dict(status='error', message='Invalid or expired token')
    requesting_customer_id = payload.get('customer_id') or payload.get('sub')
    if requesting_customer_id != 'admin' and str(requesting_customer_id) != str(customer_id):
        return dict(status='error', message='Access denied')

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
