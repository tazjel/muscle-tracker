"""GTD3D Studio, viewer, and body scan result routes."""
from py4web import action, request, response, URL
from ombott import static_file
from py4web.utils.cors import CORS
from .models import db
from .controllers import cors
import os
import logging
import json

logger = logging.getLogger(__name__)


@action('studio_v2')
@action.uses('studio_v2.html', db)
def studio_v2():
    """GTD3D Studio v2 — unified single-page editor."""
    return dict()


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
        with urllib.request.urlopen(url, timeout=2) as resp:
            return json.loads(resp.read().decode())
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
        req = urllib.request.Request(
            url,
            data=json.dumps({'action': cmd, 'value': val}).encode(),
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return dict(status='success', detail=resp.read().decode())
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
