from py4web import action, request, response, URL
from .models import db
from .controllers import _auth_check
import os
import logging
import base64
from core.cloud_gpu import cloud_train_splat, cloud_anchor_splat

logger = logging.getLogger(__name__)

# --- CINEMATIC SCAN PIPELINE ---

@action('api/cinematic_status', method=['GET'])
def cinematic_status():
    """Verify that the Cinematic Controller is loaded and healthy."""
    return dict(status='success', module='cinematic_controller', version='6.0-beta')


@action('api/customer/<customer_id:int>/cinematic_scan', method=['POST'])
@action.uses(db)
def cinematic_scan(customer_id):
    """
    Trigger a 3D Gaussian Splat (3DGS) training job from a video session.
    Delegates to RunPod Serverless (Action: train_splat).
    """
    payload, err = _auth_check(customer_id)
    if err: return err

    session_id = request.json.get('session_id')
    session = db.video_scan_session(session_id)
    if not session or session.customer_id != customer_id:
        return dict(status='error', message='Video session not found')

    if not os.path.exists(session.video_path):
        return dict(status='error', message='Video file missing on server')

    try:
        # 1. Read video bytes
        with open(session.video_path, 'rb') as f:
            video_bytes = f.read()

        # 2. Delegate to RunPod
        logger.info(f"Triggering RunPod 3DGS training for session {session_id}...")
        splat_url = cloud_train_splat(video_bytes)

        if splat_url:
            # 3. Update session status
            session.update_record(status='SPLAT_READY', splat_url=splat_url)
            db.commit()
            return dict(status='success', splat_url=splat_url)
        else:
            return dict(status='error', message='RunPod training failed')

    except Exception as e:
        logger.exception("Cinematic scan failed")
        return dict(status='error', message=str(e))


@action('api/customer/<customer_id:int>/anchor_splat', method=['POST'])
@action.uses(db)
def anchor_splat(customer_id):
    """
    Bind a trained Gaussian Splat to the latest MPFB2 mesh vertices.
    Delegates to RunPod (Action: anchor_splat).
    """
    payload, err = _auth_check(customer_id)
    if err: return err

    session_id = request.json.get('session_id')
    mesh_id = request.json.get('mesh_id')
    
    session = db.video_scan_session(session_id)
    mesh = db.mesh_model(mesh_id)
    
    if not session or not mesh:
        return dict(status='error', message='Session or Mesh not found')

    try:
        # 1. Load mesh vertices (placeholder logic - usually from .glb or .obj)
        # For prototype, we assume vertices are available or mapped.
        import numpy as np
        mock_verts = np.random.rand(13380, 3).astype(np.float32)

        # 2. Delegate to RunPod for alignment
        logger.info(f"Anchoring Splat {session.splat_url} to Mesh {mesh_id}...")
        result = cloud_anchor_splat(session.splat_url, mock_verts)

        if result:
            return dict(status='success', anchors=result.get('anchors_count'))
        else:
            return dict(status='error', message='Anchoring failed')

    except Exception as e:
        logger.exception("Splat anchoring failed")
        return dict(status='error', message=str(e))
