from py4web import action, request, abort, URL
from .models import db, MUSCLE_GROUPS, VOLUME_MODELS
import os
import sys
import logging
import json

logger = logging.getLogger(__name__)

API_TOKEN = os.environ.get('MUSCLE_TRACKER_API_TOKEN', 'dev-secret-token')

def require_api_token():
    token = request.headers.get('Authorization')
    if not token or token.replace('Bearer ', '') != API_TOKEN:
        abort(401, "Unauthorized: Invalid or missing API token")

# Add project root to path for core imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from core.vision_medical import analyze_muscle_growth
from core.volumetrics import estimate_muscle_volume, compare_volumes
from core.segmentation import score_muscle_shape, AVAILABLE_TEMPLATES
from core.symmetry import compare_symmetry
from core.progress import analyze_trend, calculate_correlation

# File upload constraints
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff'}
MAX_FILE_SIZE_MB = 15
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


# --- DASHBOARD ---

@action('index')
@action.uses('index.html', db)
def index():
    customers = db(db.customer.is_active == True).select(
        orderby=db.customer.name)
    return dict(customers=customers)


# --- CUSTOMER MANAGEMENT ---

@action('api/customers', method=['GET'])
@action.uses(db)
def list_customers():
    require_api_token()
    customers = db(db.customer.is_active == True).select().as_list()
    return dict(status='success', customers=customers)


@action('api/customers', method=['POST'])
@action.uses(db)
def create_customer():
    require_api_token()
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
@action.uses(db)
def upload_scan(customer_id):
    require_api_token()
    # Validate customer exists
    customer = db.customer(customer_id)
    if not customer:
        return dict(status='error', message='Customer not found')

    # Get uploaded files
    front = request.files.get('front')
    side = request.files.get('side')

    if not front or not side:
        return dict(status='error', message='Both front and side images required')

    # Validate file types
    for f in (front, side):
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            return dict(status='error',
                        message=f'Invalid file type: {ext}. Allowed: {", ".join(ALLOWED_EXTENSIONS)}')

    # Validate file sizes
    for f in (front, side):
        f.file.seek(0, 2)  # Seek to end
        size = f.file.tell()
        f.file.seek(0)     # Reset
        if size > MAX_FILE_SIZE_BYTES:
            return dict(status='error',
                        message=f'File too large: {size // (1024*1024)}MB (max {MAX_FILE_SIZE_MB}MB)')

    # Optional parameters
    muscle_group = request.forms.get('muscle_group', 'bicep')
    scan_side = request.forms.get('side', 'front')
    marker_size = float(request.forms.get('marker_size', '20.0'))
    volume_model = request.forms.get('volume_model', 'elliptical_cylinder')
    shape_template = request.forms.get('shape_template')

    if muscle_group not in MUSCLE_GROUPS:
        return dict(status='error', message=f'Invalid muscle group. Options: {MUSCLE_GROUPS}')

    # Store files
    front_filename = db.muscle_scan.img_front.store(front.file, front.filename)
    side_filename = db.muscle_scan.img_side.store(side.file, side.filename)

    front_path = os.path.join('uploads', front_filename)
    side_path = os.path.join('uploads', side_filename)

    try:
        # Get height from customer profile for pose calibration if available
        user_height_cm = customer.height_cm

        # 1. Analyze both views
        res_f = analyze_muscle_growth(front_path, front_path, marker_size, align=False, muscle_group=muscle_group, user_height_cm=user_height_cm)
        res_s = analyze_muscle_growth(side_path, side_path, marker_size, align=False, muscle_group=muscle_group, user_height_cm=user_height_cm)

        if "error" in res_f or "error" in res_s:
            error_msg = res_f.get("error", "") or res_s.get("error", "")
            return dict(status='error', message=f'Vision analysis failed: {error_msg}')

        # 2. Extract metrics
        unit = "mm" if res_f.get("calibrated") else "px"
        area = res_f['metrics'].get(f'area_a_{unit}2', 0.0)
        width = res_f['metrics'].get(f'width_a_{unit}', 0.0)
        height = res_f['metrics'].get(f'height_a_{unit}', 0.0)

        area_side = res_s['metrics'].get(f'area_a_{unit}2', 0.0)
        width_side = res_s['metrics'].get(f'width_a_{unit}', 0.0)

        # 3. Calculate volume
        vol_result = estimate_muscle_volume(area, area_side, width, width_side, volume_model)
        vol_cm3 = vol_result.get('volume_cm3', 0.0)

        # 4. Shape scoring (if template specified)
        shape_score = None
        shape_grade = None
        if shape_template and shape_template in AVAILABLE_TEMPLATES:
            contour = res_f['raw_data']['contour_a']
            shape_result = score_muscle_shape(contour, shape_template)
            shape_score = shape_result.get('score')
            shape_grade = shape_result.get('grade')

        # 5. Compare to previous scan
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

        # 6. Save to database
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

    except Exception as e:
        logger.exception("Scan processing failed for customer %d", customer_id)
        return dict(status='error', message='Scan processing failed. Please try again.')


# --- REPORTS ---

@action('api/customer/<customer_id:int>/scans', method=['GET'])
@action.uses(db)
def customer_scans(customer_id):
    require_api_token()
    customer = db.customer(customer_id)
    if not customer:
        return dict(status='error', message='Customer not found')

    muscle_group = request.params.get('muscle_group')
    query = db.muscle_scan.customer_id == customer_id
    if muscle_group:
        query &= db.muscle_scan.muscle_group == muscle_group

    scans = db(query).select(orderby=~db.muscle_scan.scan_date).as_list()

    # Strip raw image data from response
    for scan in scans:
        scan.pop('img_front', None)
        scan.pop('img_side', None)

    return dict(status='success', customer=customer.name, scans=scans)


@action('api/customer/<customer_id:int>/progress', method=['GET'])
@action.uses(db)
def customer_progress(customer_id):
    require_api_token()
    customer = db.customer(customer_id)
    if not customer:
        return dict(status='error', message='Customer not found')

    muscle_group = request.params.get('muscle_group')
    query = db.muscle_scan.customer_id == customer_id
    if muscle_group:
        query &= db.muscle_scan.muscle_group == muscle_group

    scans = db(query).select(orderby=db.muscle_scan.scan_date).as_list()
    trend = analyze_trend(scans)

    # Optionally correlate with health data
    health_logs = db(db.health_log.customer_id == customer_id).select().as_list()
    correlation = None
    if len(health_logs) >= 3:
        correlation = calculate_correlation(scans, health_logs)

    return dict(status='success', trend=trend, correlation=correlation)


@action('api/customer/<customer_id:int>/symmetry', method=['POST'])
@action.uses(db)
def customer_symmetry(customer_id):
    require_api_token()
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

    # Store temporarily for analysis
    left_filename = db.muscle_scan.img_front.store(left.file, left.filename)
    right_filename = db.muscle_scan.img_front.store(right.file, right.filename)

    left_path = os.path.join('uploads', left_filename)
    right_path = os.path.join('uploads', right_filename)

    try:
        result = compare_symmetry(left_path, right_path, marker_size, muscle_group)

        if "error" in result:
            return dict(status='error', message=result['error'])

        # Save assessment
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

    except Exception as e:
        logger.exception("Symmetry analysis failed for customer %d", customer_id)
        return dict(status='error', message='Symmetry analysis failed')


# --- HEALTH LOGGING ---

@action('api/customer/<customer_id:int>/health_log', method=['POST'])
@action.uses(db)
def add_health_log(customer_id):
    require_api_token()
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
@action.uses(db)
def get_health_logs(customer_id):
    require_api_token()
    customer = db.customer(customer_id)
    if not customer:
        return dict(status='error', message='Customer not found')

    logs = db(db.health_log.customer_id == customer_id).select(
        orderby=~db.health_log.log_date).as_list()
    return dict(status='success', logs=logs)


# --- REFERENCE DATA ---

@action('api/muscle_groups', method=['GET'])
def get_muscle_groups():
    return dict(muscle_groups=MUSCLE_GROUPS)


@action('api/shape_templates', method=['GET'])
def get_shape_templates():
    return dict(templates=AVAILABLE_TEMPLATES)


@action('api/volume_models', method=['GET'])
def get_volume_models():
    return dict(models=VOLUME_MODELS)
