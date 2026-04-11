"""Dashboard, reporting, and data export routes."""
from py4web import action, request, response, abort
from py4web.utils.cors import CORS
from .models import db
from .controllers import (
    _auth_check, _abs_path,
    ALLOWED_EXTENSIONS, MAX_FILE_SIZE_MB, MAX_FILE_SIZE_BYTES, cors,
)
import os
import logging
import cv2

from core.progress import analyze_trend, calculate_correlation
from core.symmetry import compare_symmetry
from core.report_generator import generate_clinical_report

logger = logging.getLogger(__name__)


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
