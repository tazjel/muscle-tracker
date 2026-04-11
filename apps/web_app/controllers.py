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
import time
from datetime import datetime
from .event_hub import broadcast, subscribe, unsubscribe, get_recent

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

# Body profile field list (shared with profile_controller and body_model_controller)
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

# Render job state (shared with texture_controller)
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


# --- HEALTH & GPU STATUS ---

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


# --- SERVER-SENT EVENTS ---

@action('api/events', method=['GET'])
@action.uses(cors)
def sse_stream():
    """SSE endpoint for real-time studio updates.

    Clients connect with EventSource and receive JSON events.
    Supports Last-Event-ID header for reconnection.
    """
    response.headers['Content-Type'] = 'text/event-stream'
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['Connection'] = 'keep-alive'
    response.headers['X-Accel-Buffering'] = 'no'  # Disable nginx buffering

    # Check for reconnection
    last_id = int(request.headers.get('Last-Event-ID', 0))

    sub = subscribe()
    try:
        # Send missed events on reconnect
        missed = get_recent(since_id=last_id)
        for event in missed:
            yield f"id: {event['id']}\nevent: {event['type']}\ndata: {json.dumps(event['data'])}\n\n"

        # Stream new events
        while True:
            if sub['queue']:
                event = sub['queue'].popleft()
                yield f"id: {event['id']}\nevent: {event['type']}\ndata: {json.dumps(event['data'])}\n\n"
            else:
                # Send keepalive comment every 15s
                yield ": keepalive\n\n"
                time.sleep(1)
    except GeneratorExit:
        pass
    finally:
        unsubscribe(sub)


# --- STATIC FILE SERVING ---

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


# --- SHARED HELPERS ---

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
