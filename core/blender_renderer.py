"""
blender_renderer.py — Blender Cycles subprocess wrapper.

Renders any GLB mesh in a configured scene via Blender's background mode.
Supports PBR materials with true SSS, room environments, and multi-angle renders.

Usage:
    from core.blender_renderer import render_body
    images = render_body('meshes/body_1.glb', room='home', quality='draft')
"""
import os
import shutil
import subprocess
import tempfile
import json
import logging

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Find Blender executable
_BLENDER_PATHS = [
    shutil.which('blender'),
    r'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe',
    r'C:\Program Files\Blender Foundation\Blender 4.3\blender.exe',
    r'C:\Program Files\Blender Foundation\Blender 4.2\blender.exe',
    r'C:\Program Files\Blender Foundation\Blender 4.1\blender.exe',
    '/usr/bin/blender',
    '/snap/bin/blender',
]

# Quality presets (portrait orientation for full-body framing)
QUALITY_PRESETS = {
    'draft': {'samples': 64, 'resolution': (720, 1280), 'denoiser': True},
    'preview': {'samples': 128, 'resolution': (1080, 1920), 'denoiser': True},
    'production': {'samples': 512, 'resolution': (1440, 2560), 'denoiser': True},
    'ultra': {'samples': 1024, 'resolution': (2160, 3840), 'denoiser': True},
}

# Camera angle presets
# After -90° X rotation: body stands Z-up, front faces +Y.
# Room is 4×6m (±2 X, ±3 Y), so cameras stay inside ±1.8/±2.8.
CAMERA_ANGLES = {
    'front':         {'pos': (0, 2.8, 0.85),   'target': (0, 0, 0.85)},
    'front_high':    {'pos': (0, 2.5, 1.6),    'target': (0, 0, 0.85)},
    'side_left':     {'pos': (-1.8, 0, 0.85),  'target': (0, 0, 0.85)},
    'side_right':    {'pos': (1.8, 0, 0.85),   'target': (0, 0, 0.85)},
    'back':          {'pos': (0, -2.8, 0.85),  'target': (0, 0, 0.85)},
    'three_quarter': {'pos': (1.5, 2.2, 1.0),  'target': (0, 0, 0.85)},
    'hero':          {'pos': (1.5, 2.5, 0.7),  'target': (0, 0, 0.85)},
}

# Room configs
ROOM_CONFIGS = {
    'studio': {
        'hdri': 'studio_small_09',
        'floor': None,
        'walls': None,
        'description': 'Clean studio with HDRI lighting',
    },
    'home': {
        'hdri': 'modern_buildings_2',
        'floor': 'wood_floor_deck',
        'walls': 'painted_plaster',
        'ceiling': 'plaster_1',
        'description': 'Home room with wood floor and painted walls',
    },
    'gym': {
        'hdri': 'industrial_workshop_foundry',
        'floor': 'rubber_floor',
        'walls': 'concrete_wall_008',
        'ceiling': 'concrete_floor_02',
        'description': 'Gym with rubber floor and concrete walls',
    },
    'outdoor': {
        'hdri': 'kloppenheim_06_puresky',
        'floor': None,
        'walls': None,
        'description': 'Outdoor with sky HDRI',
    },
}


def find_blender():
    """Find Blender executable. Returns path or None."""
    for p in _BLENDER_PATHS:
        if p and os.path.isfile(p):
            return p
    return None


def _generate_render_script(config):
    """
    Generate a Blender Python script from render configuration.

    Args:
        config: dict with all render parameters

    Returns:
        str — Python script content
    """
    # Serialize config as JSON for the Blender script to parse
    config_json = json.dumps(config).replace('\\', '\\\\').replace("'", "\\'")

    script = f'''
import bpy
import json
import math
import os
import sys

# ── Parse config ────────────────────────────────────────────────────────
config = json.loads('{config_json}')

# ── Clear scene ─────────────────────────────────────────────────────────
bpy.ops.wm.read_factory_settings(use_empty=True)

# ── Render engine ───────────────────────────────────────────────────────
bpy.context.scene.render.engine = 'CYCLES'
prefs = bpy.context.preferences.addons.get('cycles')
if prefs:
    prefs.preferences.compute_device_type = 'CUDA'
bpy.context.scene.cycles.device = 'GPU'
bpy.context.scene.cycles.samples = config['samples']
bpy.context.scene.cycles.use_denoising = config.get('denoiser', True)
bpy.context.scene.cycles.denoiser = 'OPENIMAGEDENOISE'

# Resolution
res = config['resolution']
bpy.context.scene.render.resolution_x = res[0]
bpy.context.scene.render.resolution_y = res[1]
bpy.context.scene.render.resolution_percentage = 100

# Color management
bpy.context.scene.view_settings.view_transform = 'AgX'
bpy.context.scene.view_settings.look = 'AgX - Base Contrast'

# ── Import mesh ─────────────────────────────────────────────────────────
mesh_path = config['mesh_path']
if mesh_path.lower().endswith('.glb') or mesh_path.lower().endswith('.gltf'):
    bpy.ops.import_scene.gltf(filepath=mesh_path)
elif mesh_path.lower().endswith('.obj'):
    bpy.ops.wm.obj_import(filepath=mesh_path)

# Find the imported mesh
body_obj = None
for obj in bpy.context.scene.objects:
    if obj.type == 'MESH':
        body_obj = obj
        break

if body_obj is None:
    print("ERROR: No mesh found after import")
    sys.exit(1)

# ── Auto-detect orientation, scale, and center ────────────────────────
# Our GLBs store Z-up coordinates, but glTF spec says Y-up.
# Blender's glTF importer applies Y-up→Z-up transform, but since our
# data is already Z-up, the body ends up lying along -Y.
# Fix: directly rotate mesh vertices via bmesh when needed.
import mathutils
import bmesh

def get_world_bbox(obj):
    return [obj.matrix_world @ mathutils.Vector(v.co) for v in obj.data.vertices]

def bbox_ranges(verts):
    xs = [v.x for v in verts]; ys = [v.y for v in verts]; zs = [v.z for v in verts]
    return (min(xs),max(xs)), (min(ys),max(ys)), (min(zs),max(zs))

bbox = get_world_bbox(body_obj)
(xlo,xhi),(ylo,yhi),(zlo,zhi) = bbox_ranges(bbox)
y_range = yhi - ylo
z_range = zhi - zlo
print(f"Import bbox: X=[{{xlo:.3f}},{{xhi:.3f}}] Y=[{{ylo:.3f}},{{yhi:.3f}}] Z=[{{zlo:.3f}},{{zhi:.3f}}]")

# If Y extent >> Z extent, body is lying down → rotate -90° around X via bmesh
if y_range > z_range * 1.5:
    bpy.context.view_layer.objects.active = body_obj
    body_obj.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(body_obj.data)
    # -90° X to stand up from lying along -Y
    rot_mat = mathutils.Matrix.Rotation(-math.pi / 2, 4, 'X')
    bmesh.ops.transform(bm, matrix=rot_mat, verts=bm.verts)
    bmesh.update_edit_mesh(body_obj.data)
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.update()
    bbox = get_world_bbox(body_obj)
    (xlo,xhi),(ylo,yhi),(zlo,zhi) = bbox_ranges(bbox)
    print(f"After rotation fix: X=[{{xlo:.3f}},{{xhi:.3f}}] Y=[{{ylo:.3f}},{{yhi:.3f}}] Z=[{{zlo:.3f}},{{zhi:.3f}}]")

raw_height = zhi - zlo
print(f"Raw height: {{raw_height:.4f}}")

# Auto-scale to ~1.75m if way off
target_height = 1.75
if raw_height > 0:
    if 0.5 < raw_height < 2.5:
        scale_factor = 1.0  # already in meters
    else:
        scale_factor = target_height / raw_height

    if abs(scale_factor - 1.0) > 0.01:
        body_obj.scale *= scale_factor
        bpy.context.view_layer.update()
        bbox = get_world_bbox(body_obj)
        (xlo,xhi),(ylo,yhi),(zlo,zhi) = bbox_ranges(bbox)
        print(f"Scale: {{scale_factor:.4f}}x → height ~{{zhi-zlo:.3f}}m")

# Center XY and put feet on ground
body_obj.location.x -= (xlo + xhi) / 2
body_obj.location.y -= (ylo + yhi) / 2
body_obj.location.z -= zlo
bpy.context.view_layer.update()

bbox = get_world_bbox(body_obj)
(xlo,xhi),(ylo,yhi),(zlo,zhi) = bbox_ranges(bbox)
body_height = zhi - zlo
print(f"Final: height={{body_height:.3f}}m, Z=[{{zlo:.3f}},{{zhi:.3f}}]")

# ── Save existing texture images before rebuilding material ────────────
existing_images = []
if body_obj.data.materials:
    for mat_slot in body_obj.data.materials:
        if mat_slot and mat_slot.use_nodes:
            for n in mat_slot.node_tree.nodes:
                if n.type == 'TEX_IMAGE' and n.image:
                    existing_images.append(n.image)

# ── SSS Skin Material ──────────────────────────────────────────────────
mat = body_obj.data.materials[0] if body_obj.data.materials else bpy.data.materials.new("SkinPBR")
if not body_obj.data.materials:
    body_obj.data.materials.append(mat)

mat.use_nodes = True
nodes = mat.node_tree.nodes
links = mat.node_tree.links
nodes.clear()

output = nodes.new('ShaderNodeOutputMaterial')
output.location = (600, 0)

principled = nodes.new('ShaderNodeBsdfPrincipled')
principled.location = (200, 0)
links.new(principled.outputs['BSDF'], output.inputs['Surface'])

# Base skin properties
principled.inputs['Roughness'].default_value = 0.55
principled.inputs['Metallic'].default_value = 0.0

# True SSS (the key photorealism feature)
principled.inputs['Subsurface Weight'].default_value = 0.35
principled.inputs['Subsurface Radius'].default_value = (0.8, 0.3, 0.15)
principled.inputs['Subsurface Scale'].default_value = 0.01

# Specular
principled.inputs['Specular IOR Level'].default_value = 0.5
principled.inputs['Coat Weight'].default_value = 0.06
principled.inputs['Coat Roughness'].default_value = 0.3

# Load PBR textures if provided
textures = config.get('textures', {{}})

if textures.get('albedo') and os.path.exists(textures['albedo']):
    tex_node = nodes.new('ShaderNodeTexImage')
    tex_node.location = (-400, 200)
    tex_node.image = bpy.data.images.load(textures['albedo'])
    links.new(tex_node.outputs['Color'], principled.inputs['Base Color'])
elif existing_images:
    # Re-use existing texture from GLB import (saved before nodes.clear())
    tex_node = nodes.new('ShaderNodeTexImage')
    tex_node.location = (-400, 200)
    tex_node.image = existing_images[0]
    links.new(tex_node.outputs['Color'], principled.inputs['Base Color'])
else:
    principled.inputs['Base Color'].default_value = (0.769, 0.584, 0.416, 1.0)

if textures.get('normal') and os.path.exists(textures['normal']):
    nmap_node = nodes.new('ShaderNodeTexImage')
    nmap_node.location = (-400, -100)
    nmap_node.image = bpy.data.images.load(textures['normal'])
    nmap_node.image.colorspace_settings.name = 'Non-Color'
    normal_node = nodes.new('ShaderNodeNormalMap')
    normal_node.location = (-100, -100)
    normal_node.inputs['Strength'].default_value = 1.0
    links.new(nmap_node.outputs['Color'], normal_node.inputs['Color'])
    links.new(normal_node.outputs['Normal'], principled.inputs['Normal'])

if textures.get('roughness') and os.path.exists(textures['roughness']):
    rough_node = nodes.new('ShaderNodeTexImage')
    rough_node.location = (-400, -300)
    rough_node.image = bpy.data.images.load(textures['roughness'])
    rough_node.image.colorspace_settings.name = 'Non-Color'
    links.new(rough_node.outputs['Color'], principled.inputs['Roughness'])

if textures.get('ao') and os.path.exists(textures['ao']):
    ao_node = nodes.new('ShaderNodeTexImage')
    ao_node.location = (-600, 200)
    ao_node.image = bpy.data.images.load(textures['ao'])
    ao_node.image.colorspace_settings.name = 'Non-Color'
    mix_node = nodes.new('ShaderNodeMixRGB')
    mix_node.location = (-200, 200)
    mix_node.blend_type = 'MULTIPLY'
    mix_node.inputs['Fac'].default_value = 0.5
    # Reconnect: albedo → mix → base color
    for link in list(links):
        if link.to_socket == principled.inputs['Base Color']:
            links.new(link.from_socket, mix_node.inputs['Color1'])
            links.remove(link)
            break
    links.new(ao_node.outputs['Color'], mix_node.inputs['Color2'])
    links.new(mix_node.outputs['Color'], principled.inputs['Base Color'])

# ── HDRI Environment ───────────────────────────────────────────────────
hdri_path = config.get('hdri_path')
if hdri_path and os.path.exists(hdri_path):
    world = bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    wn = world.node_tree.nodes
    wl = world.node_tree.links
    wn.clear()

    bg = wn.new('ShaderNodeBackground')
    bg.inputs['Strength'].default_value = 1.2
    env_tex = wn.new('ShaderNodeTexEnvironment')
    env_tex.image = bpy.data.images.load(hdri_path)
    mapping = wn.new('ShaderNodeMapping')
    tex_coord = wn.new('ShaderNodeTexCoord')
    output_w = wn.new('ShaderNodeOutputWorld')

    wl.new(tex_coord.outputs['Generated'], mapping.inputs['Vector'])
    wl.new(mapping.outputs['Vector'], env_tex.inputs['Vector'])
    wl.new(env_tex.outputs['Color'], bg.inputs['Color'])
    wl.new(bg.outputs['Background'], output_w.inputs['Surface'])
else:
    # Default studio-like world
    world = bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.05, 0.05, 0.06, 1)
    world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.5

# ── Room geometry ──────────────────────────────────────────────────────
room_cfg = config.get('room')
if room_cfg and room_cfg.get('build', False):
    room_w, room_h, room_d = 4.0, 3.0, 6.0
    hw, hd = room_w / 2, room_d / 2

    room_textures = config.get('room_textures', {{}})

    def make_wall_material(name, tex_path=None, color=(0.9, 0.87, 0.83, 1)):
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        n = mat.node_tree.nodes
        l = mat.node_tree.links
        bsdf = n['Principled BSDF']
        bsdf.inputs['Roughness'].default_value = 0.8
        if tex_path and os.path.exists(tex_path):
            tex = n.new('ShaderNodeTexImage')
            tex.image = bpy.data.images.load(tex_path)
            coord = n.new('ShaderNodeTexCoord')
            mapping = n.new('ShaderNodeMapping')
            mapping.inputs['Scale'].default_value = (2, 2, 2)
            l.new(coord.outputs['UV'], mapping.inputs['Vector'])
            l.new(mapping.outputs['Vector'], tex.inputs['Vector'])
            l.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
        else:
            bsdf.inputs['Base Color'].default_value = color
        return mat

    # Floor
    floor_tex = room_textures.get('floor', {{}}).get('diff')
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0))
    floor = bpy.context.active_object
    floor.scale = (room_w, room_d, 1)
    floor.name = 'Floor'
    floor.data.materials.append(make_wall_material('FloorMat', floor_tex, (0.83, 0.81, 0.77, 1)))

    # Back wall
    wall_tex = room_textures.get('wall', {{}}).get('diff')
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, -hd, room_h / 2))
    back = bpy.context.active_object
    back.rotation_euler = (math.pi / 2, 0, 0)
    back.scale = (room_w, room_h, 1)
    back.name = 'BackWall'
    back.data.materials.append(make_wall_material('WallMat', wall_tex))

    # Side walls
    bpy.ops.mesh.primitive_plane_add(size=1, location=(-hw, 0, room_h / 2))
    lw = bpy.context.active_object
    lw.rotation_euler = (math.pi / 2, 0, math.pi / 2)
    lw.scale = (room_d, room_h, 1)
    lw.name = 'LeftWall'
    lw.data.materials.append(make_wall_material('WallMat_L', wall_tex))

    bpy.ops.mesh.primitive_plane_add(size=1, location=(hw, 0, room_h / 2))
    rw = bpy.context.active_object
    rw.rotation_euler = (math.pi / 2, 0, -math.pi / 2)
    rw.scale = (room_d, room_h, 1)
    rw.name = 'RightWall'
    rw.data.materials.append(make_wall_material('WallMat_R', wall_tex))

    # Ceiling
    ceil_tex = room_textures.get('ceiling', {{}}).get('diff')
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, room_h))
    ceiling = bpy.context.active_object
    ceiling.rotation_euler = (math.pi, 0, 0)
    ceiling.scale = (room_w, room_d, 1)
    ceiling.name = 'Ceiling'
    ceiling.data.materials.append(make_wall_material('CeilMat', ceil_tex, (0.78, 0.77, 0.72, 1)))

# ── Lights ─────────────────────────────────────────────────────────────
# Key light
key = bpy.data.lights.new("Key", type='AREA')
key.energy = 500
key.size = 2.0
key.color = (1.0, 0.95, 0.9)
key_obj = bpy.data.objects.new("Key", key)
key_obj.location = (2, -2, 2.5)
key_obj.rotation_euler = (0.9, 0, 0.5)
bpy.context.collection.objects.link(key_obj)

# Fill light
fill = bpy.data.lights.new("Fill", type='AREA')
fill.energy = 200
fill.size = 3.0
fill.color = (0.85, 0.9, 1.0)
fill_obj = bpy.data.objects.new("Fill", fill)
fill_obj.location = (-2.5, -1.5, 2)
fill_obj.rotation_euler = (0.8, 0, -0.6)
bpy.context.collection.objects.link(fill_obj)

# Rim light
rim = bpy.data.lights.new("Rim", type='AREA')
rim.energy = 300
rim.size = 1.5
rim.color = (1.0, 0.98, 0.95)
rim_obj = bpy.data.objects.new("Rim", rim)
rim_obj.location = (0, 2.5, 2.2)
rim_obj.rotation_euler = (-0.7, 0, math.pi)
bpy.context.collection.objects.link(rim_obj)

# ── Camera ──────────────────────────────────────────────────────────────
angles = config.get('camera_angles', ['front'])
output_paths = []

for angle_name in angles:
    angle_cfg = config.get('angle_presets', {{}}).get(angle_name)
    if not angle_cfg:
        continue

    cam_data = bpy.data.cameras.new("Camera")
    cam_data.lens = config.get('lens_mm', 85)
    cam_data.sensor_width = 36

    # Depth of field
    if config.get('dof', False):
        cam_data.dof.use_dof = True
        cam_data.dof.aperture_fstop = config.get('fstop', 2.8)

    cam_obj = bpy.data.objects.new("Camera", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    bpy.context.scene.camera = cam_obj

    pos = angle_cfg['pos']
    target = angle_cfg['target']
    cam_obj.location = pos

    # Point camera at target
    direction = (target[0] - pos[0], target[1] - pos[1], target[2] - pos[2])
    cam_obj.rotation_euler = (
        math.atan2(math.sqrt(direction[0]**2 + direction[1]**2), direction[2]) - math.pi,
        0,
        math.atan2(direction[0], -direction[1])
    )

    # Use track-to constraint for precise aiming
    track = cam_obj.constraints.new('TRACK_TO')
    empty = bpy.data.objects.new("CamTarget", None)
    empty.location = target
    bpy.context.collection.objects.link(empty)
    track.target = empty
    track.track_axis = 'TRACK_NEGATIVE_Z'
    track.up_axis = 'UP_Y'

    # Output path
    out_dir = config.get('output_dir', '/tmp/renders')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"render_{{angle_name}}.png")
    bpy.context.scene.render.filepath = out_path
    bpy.context.scene.render.image_settings.file_format = 'PNG'
    bpy.context.scene.render.image_settings.color_mode = 'RGB'
    bpy.context.scene.render.image_settings.compression = 15

    # Render
    print(f"Rendering {{angle_name}}...")
    bpy.ops.render.render(write_still=True)
    output_paths.append(out_path)
    print(f"Saved: {{out_path}}")

    # Clean up camera objects for next angle
    bpy.data.objects.remove(cam_obj)
    bpy.data.objects.remove(empty)

# Write output manifest
manifest = {{"renders": output_paths, "status": "success"}}
manifest_path = os.path.join(config.get('output_dir', '/tmp/renders'), 'manifest.json')
with open(manifest_path, 'w') as f:
    json.dump(manifest, f, indent=2)
print(f"Manifest: {{manifest_path}}")
'''
    return script


def render_body(mesh_path, room='studio', quality='draft',
                angles=None, textures=None, output_dir=None,
                lens_mm=35, dof=False, fstop=2.8,
                hdri_path=None, timeout=600):
    """
    Render a body mesh using Blender Cycles.

    Args:
        mesh_path: path to GLB/OBJ mesh
        room: room type ('studio', 'home', 'gym', 'outdoor') or None
        quality: quality preset ('draft', 'preview', 'production', 'ultra')
        angles: list of camera angle names, or int for N evenly-spaced angles.
                Default: ['front']
        textures: dict of PBR texture paths {'albedo': ..., 'normal': ..., etc.}
        output_dir: where to save renders. Default: temp directory
        lens_mm: camera focal length
        dof: enable depth of field
        fstop: aperture for DOF
        hdri_path: override HDRI path (otherwise uses room default)
        timeout: max render time in seconds

    Returns:
        dict with 'renders' (list of image paths), 'output_dir', 'status'
    """
    blender = find_blender()
    if blender is None:
        logger.error("Blender not found. Install Blender or add to PATH.")
        return {'status': 'error', 'message': 'Blender not found', 'renders': []}

    mesh_path = os.path.abspath(mesh_path)
    if not os.path.exists(mesh_path):
        return {'status': 'error', 'message': f'Mesh not found: {mesh_path}', 'renders': []}

    # Resolve angles
    if angles is None:
        angles = ['front']
    elif isinstance(angles, int):
        all_angles = list(CAMERA_ANGLES.keys())
        step = max(1, len(all_angles) // angles)
        angles = all_angles[:angles * step:step][:angles]

    # Quality preset
    preset = QUALITY_PRESETS.get(quality, QUALITY_PRESETS['draft'])

    # Output directory
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix='gtd3d_render_')
    os.makedirs(output_dir, exist_ok=True)

    # Resolve HDRI from asset cache
    room_cfg = ROOM_CONFIGS.get(room, {})
    if hdri_path is None and room_cfg.get('hdri'):
        try:
            from core.asset_cache import download_hdri
            hdri_path = download_hdri(room_cfg['hdri'], '2k')
        except Exception as e:
            logger.warning("Could not download HDRI: %s", e)

    # Resolve room textures from asset cache
    room_textures = {}
    build_room = room in ('home', 'gym')
    if build_room:
        try:
            from core.asset_cache import get_asset_set
            asset_set_name = f'room_{room}'
            assets = get_asset_set(asset_set_name, download=True)
            if assets:
                room_textures = assets.get('textures', {})
        except Exception as e:
            logger.warning("Could not load room textures: %s", e)

    # Build render config
    config = {
        'mesh_path': mesh_path.replace('\\', '/'),
        'samples': preset['samples'],
        'resolution': list(preset['resolution']),
        'denoiser': preset.get('denoiser', True),
        'camera_angles': angles,
        'angle_presets': {k: {'pos': list(v['pos']), 'target': list(v['target'])}
                         for k, v in CAMERA_ANGLES.items()},
        'textures': textures or {},
        'hdri_path': (hdri_path or '').replace('\\', '/'),
        'room': {'build': build_room} if build_room else None,
        'room_textures': {k: {mk: mv.replace('\\', '/') for mk, mv in v.items()}
                          for k, v in room_textures.items()} if room_textures else {},
        'output_dir': output_dir.replace('\\', '/'),
        'lens_mm': lens_mm,
        'dof': dof,
        'fstop': fstop,
    }

    # Generate and write Blender script
    script = _generate_render_script(config)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False,
                                      dir=output_dir) as f:
        f.write(script)
        script_path = f.name

    logger.info("Rendering %s with Blender Cycles (%s quality, %d angles)",
                os.path.basename(mesh_path), quality, len(angles))

    # Run Blender
    try:
        result = subprocess.run(
            [blender, '--background', '--python', script_path],
            capture_output=True, text=True, timeout=timeout,
            cwd=_PROJECT_ROOT,
        )

        if result.returncode != 0:
            logger.error("Blender failed:\n%s", result.stderr[-2000:] if result.stderr else "no stderr")
            return {
                'status': 'error',
                'message': f'Blender exit code {result.returncode}',
                'stderr': result.stderr[-1000:] if result.stderr else '',
                'renders': [],
                'output_dir': output_dir,
            }

        # Read manifest
        manifest_path = os.path.join(output_dir, 'manifest.json')
        if os.path.exists(manifest_path):
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)
            renders = [p for p in manifest.get('renders', []) if os.path.exists(p)]
        else:
            # Find PNG files in output dir
            renders = [os.path.join(output_dir, f) for f in os.listdir(output_dir)
                      if f.endswith('.png')]

        logger.info("Render complete: %d images in %s", len(renders), output_dir)
        return {
            'status': 'success',
            'renders': renders,
            'output_dir': output_dir,
        }

    except subprocess.TimeoutExpired:
        logger.error("Blender render timed out after %ds", timeout)
        return {'status': 'error', 'message': 'Render timed out', 'renders': [],
                'output_dir': output_dir}
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    blender = find_blender()
    print(f"Blender: {blender or 'NOT FOUND'}")
    print(f"Quality presets: {list(QUALITY_PRESETS.keys())}")
    print(f"Camera angles: {list(CAMERA_ANGLES.keys())}")
    print(f"Room types: {list(ROOM_CONFIGS.keys())}")
