"""Skin texture, PBR textures, room assets, and render routes."""
from py4web import action, request, response, abort
from py4web.utils.cors import CORS
from .models import db
from .controllers import (
    _auth_check, _abs_path, _render_jobs, _do_render,
    cors,
)
import os
import logging
import numpy as np
from datetime import datetime

logger = logging.getLogger(__name__)


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
    from py4web import HTTP
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
def serve_polyhaven_asset(asset_path):
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


@action('api/customer/<customer_id:int>/render', method=['POST'])
@action.uses(db, cors)
def render_body_model(customer_id):
    """Trigger async Blender Cycles render. Returns job_id immediately."""
    import time
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
    import time
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
