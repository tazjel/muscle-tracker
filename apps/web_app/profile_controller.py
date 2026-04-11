"""Customer profile, body composition, devices, scan setup, and health log routes."""
from py4web import action, request, response
from py4web.utils.cors import CORS
from .models import db
from .controllers import (
    _auth_check, _abs_path, _BODY_PROFILE_FIELDS,
    ALLOWED_EXTENSIONS, cors,
)
from .event_hub import broadcast
import os
import logging
import json
import cv2
from datetime import datetime

logger = logging.getLogger(__name__)


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


@action('api/seed_demo', method=['POST'])
@action.uses(db, cors)
def seed_demo():
    """Seed demo customer (id=1) with sample scan data for studio testing."""
    customer = db.customer(1)
    if not customer:
        return dict(status='error', message='Demo customer not found')

    # Update customer 1 profile — Ahmed Bani, 165cm / 65kg
    db(db.customer.id == 1).update(
        name='Ahmed Bani',
        gender='male',
        height_cm=165,
        shoulder_width_cm=43,
        neck_circumference_cm=37,
        chest_circumference_cm=92,
        bicep_circumference_cm=30,
        forearm_circumference_cm=26,
        waist_circumference_cm=78,
        hip_circumference_cm=93,
        thigh_circumference_cm=52,
        calf_circumference_cm=36,
        arm_length_cm=55,
        torso_length_cm=45,
        inseam_cm=74,
        skin_tone_hex='C4956A',
        profile_completed=True,
    )

    from datetime import datetime, timedelta
    import random

    # Create 5 sample scans over 5 weeks (one per muscle group)
    muscle_groups = ['bicep', 'quadricep', 'chest', 'deltoid', 'lat']
    base_date = datetime.now() - timedelta(weeks=5)

    for i, mg in enumerate(muscle_groups):
        scan_date = base_date + timedelta(weeks=i)
        base_vol = 800 + random.randint(-50, 50)
        growth = round(random.uniform(1.5, 4.5), 1)

        db.muscle_scan.insert(
            customer_id=1,
            scan_date=scan_date,
            muscle_group=mg,
            side='both',
            processing_status='complete',
            volume_cm3=base_vol + (i * 15),
            growth_pct=growth,
            shape_score=round(random.uniform(6.0, 9.0), 1),
            shape_grade=['A', 'B', 'A', 'B', 'A'][i],
            definition_score=round(random.uniform(5.0, 8.5), 1),
            definition_grade=['B', 'A', 'B', 'B', 'A'][i],
            circumference_cm=round(30 + i * 2.5 + random.uniform(-1, 1), 1),
            calibrated=True,
        )

    # Create 5 health logs (one per week)
    for i in range(5):
        log_date = base_date + timedelta(weeks=i)
        db.health_log.insert(
            customer_id=1,
            log_date=log_date.date(),
            body_weight_kg=round(63.0 + random.uniform(-0.5, 0.3), 1),
            calories_in=random.randint(1800, 2400),
            sleep_hours=round(random.uniform(6.5, 8.5), 1),
            activity_type=['moderate', 'intense', 'light', 'intense', 'moderate'][i],
            notes=['Leg day', 'Upper body', 'Rest day', 'Full body', 'Cardio'][i],
        )

    db.commit()
    return dict(status='success', message='Seeded 5 scans + 5 health logs for demo customer')


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
    broadcast('customer_updated', {'customer_id': customer_id})
    return dict(status='success', profile_completed=updates['profile_completed'], updated=list(updates.keys()))


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
