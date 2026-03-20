"""
texture_factory.py — PBR texture set generator for body meshes.

Generates complete PBR texture sets:
  - Albedo (photo-projected + upscaled)
  - Normal map (DSINE-projected or geometry-based)
  - Regional roughness map (anatomical zones)
  - AO map (crevice darkening)
  - Displacement map (skin micro-detail)

Uses SMPL body-part vertex IDs for anatomical region mapping.
"""
import numpy as np
import cv2
import os
import logging
import pickle

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# SMPL body part segmentation — maps vertex index ranges to regions.
# These are approximate zones based on SMPL topology (6890 vertices).
# Format: (region_name, roughness_value)
REGION_ROUGHNESS = {
    'face':       0.30,
    'lips':       0.20,
    'ears':       0.40,
    'neck':       0.45,
    'chest':      0.50,
    'abdomen':    0.55,
    'upper_back': 0.55,
    'lower_back': 0.55,
    'shoulders':  0.50,
    'upper_arm':  0.50,
    'forearm':    0.55,
    'hands':      0.50,
    'palms':      0.45,
    'elbows':     0.80,
    'knees':      0.80,
    'thighs':     0.55,
    'shins':      0.55,
    'feet':       0.70,
}

# SMPL body part IDs (from SMPL model segmentation)
# Maps SMPL part index → region name
_SMPL_PART_MAP = {
    0: 'abdomen',     # pelvis
    1: 'thighs',      # left upper leg
    2: 'thighs',      # right upper leg
    3: 'abdomen',     # spine1
    4: 'shins',       # left knee
    5: 'shins',       # right knee
    6: 'chest',       # spine2
    7: 'feet',        # left ankle
    8: 'feet',        # right ankle
    9: 'chest',       # spine3
    10: 'feet',       # left foot
    11: 'feet',       # right foot
    12: 'neck',       # neck
    13: 'shoulders',  # left collar
    14: 'shoulders',  # right collar
    15: 'face',       # head
    16: 'upper_arm',  # left shoulder
    17: 'upper_arm',  # right shoulder
    18: 'forearm',    # left elbow
    19: 'forearm',    # right elbow
    20: 'hands',      # left wrist
    21: 'hands',      # right wrist
    22: 'hands',      # left hand
    23: 'hands',      # right hand
}


def _get_smpl_part_ids():
    """
    Load SMPL vertex-to-part assignment.
    Returns (6890,) int array mapping each vertex to a body part index (0-23).
    """
    pkl_paths = [
        os.path.join(_PROJECT_ROOT, 'runpod', 'SMPL_NEUTRAL.pkl'),
        os.path.expanduser('~/.cache/4DHumans/data/smpl/SMPL_NEUTRAL.pkl'),
    ]

    for pkl_path in pkl_paths:
        if not os.path.exists(pkl_path):
            continue
        with open(pkl_path, 'rb') as f:
            data = pickle.load(f, encoding='latin1')

        # SMPL weights matrix: (6890, 24) — each vertex's blend weights to 24 joints
        weights = data.get('weights')
        if weights is not None:
            weights = np.array(weights, dtype=np.float32)
            # Assign each vertex to its dominant joint
            part_ids = weights.argmax(axis=1).astype(np.int32)
            return part_ids

    logger.warning("Could not load SMPL part IDs — using height-based zones")
    return None


def generate_roughness_map(uvs, atlas_size=2048, part_ids=None, vertices=None):
    """
    Generate anatomical roughness map from SMPL body-part assignments.

    Args:
        uvs: (N, 2) float32 UV coordinates
        atlas_size: output texture size
        part_ids: (N,) int — SMPL part ID per vertex (0-23)
        vertices: (N, 3) float32 — vertex positions (used for height-based fallback)

    Returns:
        (atlas_size, atlas_size) float32 roughness map in [0, 1]
    """
    roughness_map = np.full((atlas_size, atlas_size), 0.55, dtype=np.float32)

    if part_ids is None:
        part_ids = _get_smpl_part_ids()

    if part_ids is not None and len(part_ids) == len(uvs):
        # Per-vertex roughness based on SMPL part assignment
        vert_roughness = np.full(len(uvs), 0.55, dtype=np.float32)
        for part_id, region_name in _SMPL_PART_MAP.items():
            mask = part_ids == part_id
            vert_roughness[mask] = REGION_ROUGHNESS.get(region_name, 0.55)

        # Rasterize per-vertex roughness to UV atlas using triangle fill
        u_px = np.clip((uvs[:, 0] * (atlas_size - 1)).astype(int), 0, atlas_size - 1)
        v_px = np.clip(((1 - uvs[:, 1]) * (atlas_size - 1)).astype(int), 0, atlas_size - 1)

        # Point-sample all vertices first
        for i in range(len(uvs)):
            roughness_map[v_px[i], u_px[i]] = vert_roughness[i]

        # Fill triangles if faces are available (from SMPL pkl)
        try:
            pkl_path = None
            for p in [os.path.join(_PROJECT_ROOT, 'runpod', 'SMPL_NEUTRAL.pkl'),
                      os.path.expanduser('~/.cache/4DHumans/data/smpl/SMPL_NEUTRAL.pkl')]:
                if os.path.exists(p):
                    pkl_path = p
                    break
            if pkl_path:
                import pickle
                with open(pkl_path, 'rb') as f:
                    _smpl = pickle.load(f, encoding='latin1')
                faces = np.array(_smpl['f'], dtype=np.int32)
                # Fill each triangle with interpolated roughness
                for fi in range(len(faces)):
                    f = faces[fi]
                    pts = np.array([[u_px[f[0]], v_px[f[0]]],
                                    [u_px[f[1]], v_px[f[1]]],
                                    [u_px[f[2]], v_px[f[2]]]], dtype=np.int32)
                    # Skip degenerate triangles spanning >half the atlas
                    if (pts[:, 0].max() - pts[:, 0].min() > atlas_size // 2 or
                        pts[:, 1].max() - pts[:, 1].min() > atlas_size // 2):
                        continue
                    avg_rough = (vert_roughness[f[0]] + vert_roughness[f[1]] + vert_roughness[f[2]]) / 3.0
                    cv2.fillConvexPoly(roughness_map, pts.reshape(-1, 1, 2), float(avg_rough))
        except Exception:
            pass  # fallback to point-sampled version

    elif vertices is not None:
        # Height-based fallback
        z = vertices[:, 2]
        z_norm = (z - z.min()) / (z.max() - z.min() + 1e-6)

        vert_roughness = np.full(len(uvs), 0.55, dtype=np.float32)
        # Head region (top 15%)
        vert_roughness[z_norm > 0.85] = 0.30
        # Torso (40-85%)
        vert_roughness[(z_norm > 0.40) & (z_norm <= 0.85)] = 0.55
        # Knees (25-35%)
        vert_roughness[(z_norm > 0.25) & (z_norm <= 0.35)] = 0.80
        # Feet (bottom 10%)
        vert_roughness[z_norm < 0.10] = 0.70

        u_px = np.clip((uvs[:, 0] * (atlas_size - 1)).astype(int), 0, atlas_size - 1)
        v_px = np.clip(((1 - uvs[:, 1]) * (atlas_size - 1)).astype(int), 0, atlas_size - 1)

        for i in range(len(uvs)):
            roughness_map[v_px[i], u_px[i]] = vert_roughness[i]

    # Gaussian blur for smooth transitions between zones (gentle — preserve variation)
    kernel_size = atlas_size // 128 | 1
    if kernel_size >= 3:
        roughness_map = cv2.GaussianBlur(roughness_map, (kernel_size, kernel_size), 0)

    return roughness_map


def generate_ao_map(vertices, faces, uvs, atlas_size=2048):
    """
    Generate ambient occlusion map by computing per-vertex AO
    and projecting to UV space.

    Uses simple concavity estimation: vertices in crevices (armpits, groin,
    between fingers) have lower AO values.

    Args:
        vertices: (N, 3) float32
        faces: (F, 3) int
        uvs: (N, 2) float32
        atlas_size: output texture size

    Returns:
        (atlas_size, atlas_size) uint8 AO map (255 = fully lit, 0 = fully occluded)
    """
    # Compute vertex normals
    normals = np.zeros_like(vertices, dtype=np.float32)
    v0 = vertices[faces[:, 0]]
    v1 = vertices[faces[:, 1]]
    v2 = vertices[faces[:, 2]]
    face_normals = np.cross(v1 - v0, v2 - v0)
    fn_lens = np.linalg.norm(face_normals, axis=1, keepdims=True)
    fn_lens[fn_lens < 1e-10] = 1.0
    face_normals /= fn_lens

    for i in range(3):
        np.add.at(normals, faces[:, i], face_normals)
    n_lens = np.linalg.norm(normals, axis=1, keepdims=True)
    n_lens[n_lens < 1e-10] = 1.0
    normals /= n_lens

    # Concavity estimation: average neighbor distance vs normal direction
    # Vertices where neighbors are "above" (in normal direction) are in crevices
    n_verts = len(vertices)
    ao_values = np.ones(n_verts, dtype=np.float32)

    # Build adjacency
    adj = [[] for _ in range(n_verts)]
    for f in faces:
        for i in range(3):
            for j in range(3):
                if i != j:
                    adj[f[i]].append(f[j])

    for vi in range(n_verts):
        if not adj[vi]:
            continue
        neighbors = np.array(list(set(adj[vi])))
        # Vector from vertex to each neighbor
        deltas = vertices[neighbors] - vertices[vi]
        # How much neighbors are "above" this vertex (in normal direction)
        dots = (deltas * normals[vi]).sum(axis=1)
        # If most neighbors are above, vertex is in a crevice
        concavity = np.clip(dots.mean() / (np.linalg.norm(deltas, axis=1).mean() + 1e-6), -1, 1)
        ao_values[vi] = np.clip(0.5 + concavity * 0.5, 0.2, 1.0)

    # Rasterize to UV atlas
    ao_map = np.full((atlas_size, atlas_size), 255, dtype=np.uint8)
    u_px = np.clip((uvs[:, 0] * (atlas_size - 1)).astype(int), 0, atlas_size - 1)
    v_px = np.clip(((1 - uvs[:, 1]) * (atlas_size - 1)).astype(int), 0, atlas_size - 1)

    for i in range(n_verts):
        ao_map[v_px[i], u_px[i]] = int(ao_values[i] * 255)

    # Blur for smooth transitions
    kernel_size = atlas_size // 64 | 1
    ao_map = cv2.GaussianBlur(ao_map, (kernel_size, kernel_size), 0)

    return ao_map


def generate_anatomical_overlay(uvs, atlas_size=2048, part_ids=None, vertices=None):
    """
    Generate anatomical color overlay:
      - Redness at knuckles, knees, elbows
      - Slight vein tints on wrists/forearms
      - AO darkening in crevices (armpits, groin)

    Returns:
        (atlas_size, atlas_size, 3) uint8 BGR overlay image.
        Blend with albedo: result = albedo * (1-alpha) + overlay * alpha
        where alpha is the overlay's deviation from neutral (128,128,128).
    """
    overlay = np.full((atlas_size, atlas_size, 3), 128, dtype=np.uint8)

    if part_ids is None:
        part_ids = _get_smpl_part_ids()

    if part_ids is None or len(part_ids) != len(uvs):
        return overlay

    # Per-vertex color tints (BGR)
    vert_tint = np.full((len(uvs), 3), 128, dtype=np.float32)

    # Redness at joints (elbows: 18,19; knees: 4,5; hands: 22,23)
    for pid in [4, 5, 18, 19]:
        mask = part_ids == pid
        vert_tint[mask] = [118, 118, 148]  # slight red tint (BGR)

    # Vein tints on wrists (20, 21)
    for pid in [20, 21]:
        mask = part_ids == pid
        vert_tint[mask] = [140, 125, 128]  # slight blue tint

    # Rasterize to atlas
    u_px = np.clip((uvs[:, 0] * (atlas_size - 1)).astype(int), 0, atlas_size - 1)
    v_px = np.clip(((1 - uvs[:, 1]) * (atlas_size - 1)).astype(int), 0, atlas_size - 1)

    for i in range(len(uvs)):
        overlay[v_px[i], u_px[i]] = vert_tint[i].astype(np.uint8)

    # Blur heavily for subtle effect
    kernel_size = atlas_size // 16 | 1
    overlay = cv2.GaussianBlur(overlay, (kernel_size, kernel_size), 0)

    return overlay


def generate_pbr_textures(albedo, uvs, vertices, faces,
                          normal_map=None, atlas_size=2048,
                          upscale=True, target_size=4096,
                          coverage_mask=None):
    """
    Generate a complete PBR texture set from photo-projected albedo.

    Args:
        albedo: (H, W, 3) uint8 BGR — photo-projected texture
        uvs: (N, 2) float32 — UV coordinates
        vertices: (N, 3) float32 — mesh vertices
        faces: (F, 3) int — mesh faces
        normal_map: (H, W, 3) uint8 — pre-computed normal map (optional)
        atlas_size: base resolution for generated maps
        upscale: whether to upscale albedo via Real-ESRGAN
        target_size: target resolution after upscale
        coverage_mask: (H, W) float32 — texture coverage weights

    Returns:
        dict with keys:
            'albedo': (H, W, 3) uint8 BGR
            'normal': (H, W, 3) uint8 RGB tangent-space normal map
            'roughness': (H, W) uint8 roughness map (0-255)
            'ao': (H, W) uint8 ambient occlusion map
            'displacement': None (placeholder for future micro-displacement)
            'atlas_size': int — actual output resolution
    """
    # Try cloud GPU for full PBR pipeline (includes upscaling)
    try:
        from core.cloud_gpu import is_configured, cloud_pbr_textures
        if is_configured() and upscale:
            logger.info("Trying cloud GPU for PBR textures...")
            cloud_result = cloud_pbr_textures(
                albedo, uvs, vertices, faces,
                atlas_size=atlas_size, upscale=upscale, target_size=target_size)
            if cloud_result is not None:
                logger.info("PBR textures generated via cloud GPU")
                return cloud_result
            logger.warning("Cloud PBR failed, falling back to local...")
    except Exception as e:
        logger.warning("Cloud PBR unavailable: %s", e)

    result = {}

    # 1. Enhance albedo (upscale + inpaint)
    enhanced_albedo = albedo.copy()
    if upscale:
        try:
            from core.texture_enhance import enhance_texture_atlas
            enhanced_albedo = enhance_texture_atlas(
                albedo,
                coverage_mask=coverage_mask,
                upscale=True,
                inpaint=coverage_mask is not None,
                target_size=target_size,
            )
            logger.info("Albedo enhanced: %s → %s", albedo.shape[:2], enhanced_albedo.shape[:2])
        except Exception as e:
            logger.warning("Texture enhancement failed, using original: %s", e)

    # Apply anatomical overlay
    overlay = generate_anatomical_overlay(uvs, atlas_size)
    # Resize overlay to match albedo
    oh, ow = enhanced_albedo.shape[:2]
    overlay_resized = cv2.resize(overlay, (ow, oh), interpolation=cv2.INTER_LINEAR)
    # Blend: where overlay differs from neutral (128), apply subtle tint
    diff = overlay_resized.astype(np.float32) - 128.0
    blend_strength = 0.15  # subtle
    enhanced_albedo = np.clip(
        enhanced_albedo.astype(np.float32) + diff * blend_strength,
        0, 255
    ).astype(np.uint8)

    result['albedo'] = enhanced_albedo
    actual_size = max(enhanced_albedo.shape[:2])

    # 2. Normal map
    if normal_map is not None:
        # Resize to match albedo resolution
        result['normal'] = cv2.resize(normal_map, (oh, ow), interpolation=cv2.INTER_LINEAR)
    else:
        # Generate from geometry
        from core.mesh_reconstruction import _generate_normal_map
        result['normal'] = _generate_normal_map(vertices, faces, uvs, atlas_size=atlas_size)
        if actual_size > atlas_size:
            result['normal'] = cv2.resize(result['normal'], (ow, oh), interpolation=cv2.INTER_LINEAR)

    # 3. Roughness map
    roughness_float = generate_roughness_map(uvs, atlas_size, vertices=vertices)
    roughness_uint8 = (roughness_float * 255).astype(np.uint8)
    if actual_size > atlas_size:
        roughness_uint8 = cv2.resize(roughness_uint8, (ow, oh), interpolation=cv2.INTER_LINEAR)
    result['roughness'] = roughness_uint8

    # 4. AO map
    ao = generate_ao_map(vertices, faces, uvs, atlas_size=atlas_size)
    if actual_size > atlas_size:
        ao = cv2.resize(ao, (ow, oh), interpolation=cv2.INTER_LINEAR)
    result['ao'] = ao

    # 5. Displacement (placeholder)
    result['displacement'] = None

    result['atlas_size'] = actual_size

    logger.info("PBR texture set generated: albedo=%s, normal=%s, roughness=%s, ao=%s",
                result['albedo'].shape, result['normal'].shape,
                result['roughness'].shape, result['ao'].shape)

    return result


def save_pbr_textures(pbr_set, output_dir, prefix='body'):
    """
    Save PBR texture set to disk as PNG files.

    Args:
        pbr_set: dict from generate_pbr_textures()
        output_dir: directory to save files
        prefix: filename prefix

    Returns:
        dict mapping texture type → file path
    """
    os.makedirs(output_dir, exist_ok=True)
    paths = {}

    for name, data in pbr_set.items():
        if data is None or name == 'atlas_size':
            continue

        path = os.path.join(output_dir, f"{prefix}_{name}.png")

        if isinstance(data, np.ndarray):
            if len(data.shape) == 2:
                cv2.imwrite(path, data)
            else:
                cv2.imwrite(path, data)
            paths[name] = path
            logger.info("Saved %s: %s (%s)", name, path, data.shape)

    return paths


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    print("Texture factory ready")
    print(f"Region roughness zones: {len(REGION_ROUGHNESS)}")
    print(f"SMPL part map: {len(_SMPL_PART_MAP)} parts")
