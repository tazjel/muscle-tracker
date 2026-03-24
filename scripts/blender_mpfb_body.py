"""Generate muscular athletic body using MPFB (MakeHuman Plugin for Blender).

Usage:
    blender --background --python scripts/blender_mpfb_body.py

Output: meshes/mpfb_athletic_body.glb
        meshes/mpfb_render.png
"""
import bpy
import math
import mathutils
import os
import sys

BASE = r"C:\Users\MiEXCITE\Projects\gtd3d"
OUT_GLB = os.path.join(BASE, "meshes", "mpfb_athletic_body.glb")
OUT_RENDER = os.path.join(BASE, "meshes", "mpfb_render.png")
SKIN_DIR = os.path.join(BASE, "apps", "uploads", "skin", "freepbr", "human-skin1-bl")

scene = bpy.context.scene

# ── Clear default mesh objects ─────────────────────────────────
for obj in list(scene.objects):
    if obj.type == 'MESH':
        bpy.data.objects.remove(obj, do_unlink=True)

# ── Load MPFB ──────────────────────────────────────────────────
print("[MPFB] Checking availability...")
try:
    from bl_ext.user_default import mpfb
    print(f"[MPFB] Module loaded: {mpfb}")
except ImportError:
    print("[ERROR] MPFB not available")
    sys.exit(1)

# List operators
print("\n[MPFB] Available operators:")
ops = []
if hasattr(bpy.ops, 'mpfb'):
    for op in dir(bpy.ops.mpfb):
        if not op.startswith('_'):
            ops.append(op)
            print(f"  bpy.ops.mpfb.{op}")

# ── Try MPFB Services API (programmatic, no UI) ───────────────
print("\n[MPFB] Trying services API for programmatic body generation...")
try:
    from bl_ext.user_default.mpfb.services.humanservice import HumanService
    print(f"[MPFB] HumanService: {HumanService}")
    # List methods
    for attr in sorted(dir(HumanService)):
        if not attr.startswith('_'):
            print(f"  HumanService.{attr}")
except ImportError as e:
    print(f"[MPFB] No HumanService: {e}")

try:
    from bl_ext.user_default.mpfb.services.targetservice import TargetService
    print(f"\n[MPFB] TargetService: {TargetService}")
    for attr in sorted(dir(TargetService)):
        if not attr.startswith('_'):
            print(f"  TargetService.{attr}")
except ImportError as e:
    print(f"[MPFB] No TargetService: {e}")

try:
    from bl_ext.user_default.mpfb.services.objectservice import ObjectService
    print(f"\n[MPFB] ObjectService: {ObjectService}")
    for attr in sorted(dir(ObjectService)):
        if not attr.startswith('_'):
            print(f"  ObjectService.{attr}")
except ImportError as e:
    print(f"[MPFB] No ObjectService: {e}")

# ── Try to create human via operator ───────────────────────────
print("\n[MPFB] Creating human body...")
try:
    # The create_human operator in MPFB v2 creates from the new human panel
    result = bpy.ops.mpfb.create_human()
    print(f"[MPFB] create_human result: {result}")
except Exception as e:
    print(f"[MPFB] create_human failed: {e}")
    # Try alternative approaches
    try:
        # Some MPFB versions use different operator names
        if 'add_human' in ops:
            result = bpy.ops.mpfb.add_human()
            print(f"[MPFB] add_human result: {result}")
    except Exception as e2:
        print(f"[MPFB] add_human also failed: {e2}")

# ── Check what was created ─────────────────────────────────────
print("\n[SCENE] Objects after MPFB:")
body = None
for obj in bpy.data.objects:
    if obj.type == 'MESH':
        body = obj
        vcount = len(obj.data.vertices) if obj.data else 0
        print(f"  {obj.name} | type={obj.type} | verts={vcount} | dims={tuple(round(d,2) for d in obj.dimensions)}")
    else:
        print(f"  {obj.name} | type={obj.type}")

if not body:
    print("[ERROR] No body mesh created. Trying to explore MPFB internals...")
    # Dig deeper into MPFB module structure
    try:
        import importlib
        mpfb_pkg = importlib.import_module('bl_ext.user_default.mpfb')
        print(f"\n[MPFB] Package dir: {[x for x in dir(mpfb_pkg) if not x.startswith('_')]}")

        # Try to find the human creation code
        for submod_name in ['entities', 'services', 'ui', 'operators']:
            try:
                submod = importlib.import_module(f'bl_ext.user_default.mpfb.{submod_name}')
                print(f"  mpfb.{submod_name}: {[x for x in dir(submod) if not x.startswith('_')][:20]}")
            except Exception as e:
                print(f"  mpfb.{submod_name}: {e}")
    except Exception as e:
        print(f"[ERROR] Can't explore: {e}")
    sys.exit(1)

# ── Apply muscular targets if available ────────────────────────
print("\n[MPFB] Checking for shape keys / targets...")
if body.data.shape_keys:
    keys = body.data.shape_keys.key_blocks
    print(f"  Found {len(keys)} shape keys:")
    muscle_keys = []
    for key in keys:
        if any(term in key.name.lower() for term in ['muscle', 'athletic', 'bulk', 'tone', 'weight', 'mass', 'fit']):
            muscle_keys.append(key)
            print(f"    * {key.name} = {key.value}")
        elif len(keys) < 50:  # Print all if not too many
            print(f"      {key.name} = {key.value}")

    # Crank up muscle/athletic sliders
    for key in muscle_keys:
        key.value = 0.8
        print(f"  Set {key.name} = 0.8")
else:
    print("  No shape keys found")

# ── Apply scale / position ─────────────────────────────────────
body.name = "MPFBBody"
max_dim = max(body.dimensions)
target_height = 1.75  # meters

if max_dim < 0.1 or max_dim > 10:
    sf = target_height / max_dim
    body.scale = (sf, sf, sf)
    bpy.context.view_layer.update()
    bpy.ops.object.select_all(action='DESELECT')
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.context.view_layer.update()
    print(f"[SCALE] {max_dim:.2f} -> {max(body.dimensions):.2f}m")

# Check orientation — rotate if needed (Y-up to Z-up)
import bmesh
verts_world = [body.matrix_world @ v.co for v in body.data.vertices]
y_range = max(v.y for v in verts_world) - min(v.y for v in verts_world)
z_range = max(v.z for v in verts_world) - min(v.z for v in verts_world)

if y_range > z_range * 1.5:  # Y-up model
    print(f"[ORIENT] Y-up detected (Y={y_range:.2f}, Z={z_range:.2f}), rotating to Z-up")
    bm = bmesh.new()
    bm.from_mesh(body.data)
    rot_mat = mathutils.Matrix.Rotation(math.radians(-90), 4, 'X')
    bmesh.ops.transform(bm, matrix=rot_mat, verts=bm.verts)
    bm.to_mesh(body.data)
    bm.free()
    body.data.update()
    bpy.context.view_layer.update()

# Center on XY, feet on Z=0
verts_world = [body.matrix_world @ v.co for v in body.data.vertices]
min_z = min(v.z for v in verts_world)
cx = sum(v.x for v in verts_world) / len(verts_world)
cy = sum(v.y for v in verts_world) / len(verts_world)
body.location.x -= cx
body.location.y -= cy
body.location.z -= min_z
bpy.context.view_layer.update()

verts_world = [body.matrix_world @ v.co for v in body.data.vertices]
print(f"[POS] X: {min(v.x for v in verts_world):.2f} to {max(v.x for v in verts_world):.2f}")
print(f"[POS] Y: {min(v.y for v in verts_world):.2f} to {max(v.y for v in verts_world):.2f}")
print(f"[POS] Z: {min(v.z for v in verts_world):.2f} to {max(v.z for v in verts_world):.2f}")

# ── Photorealistic Skin Material ──────────────────────────────
mat = bpy.data.materials.new(name="PhotorealisticSkin")
mat.use_nodes = True
tree = mat.node_tree
nodes_mat = tree.nodes
links_mat = tree.links
nodes_mat.clear()

mat_output = nodes_mat.new('ShaderNodeOutputMaterial')
mat_output.location = (600, 0)

bsdf = nodes_mat.new('ShaderNodeBsdfPrincipled')
bsdf.location = (200, 0)
links_mat.new(bsdf.outputs[0], mat_output.inputs[0])

bsdf.inputs['Base Color'].default_value = (0.82, 0.65, 0.55, 1.0)
bsdf.inputs['Metallic'].default_value = 0.0
bsdf.inputs['Roughness'].default_value = 0.45
bsdf.inputs['Specular IOR Level'].default_value = 0.4
bsdf.inputs['Subsurface Weight'].default_value = 0.35
bsdf.inputs['Subsurface Radius'].default_value = (0.8, 0.3, 0.15)
bsdf.inputs['Subsurface Scale'].default_value = 0.01
bsdf.inputs['Sheen Weight'].default_value = 0.15
bsdf.inputs['Sheen Roughness'].default_value = 0.5
bsdf.inputs['Coat Weight'].default_value = 0.04
bsdf.inputs['Coat Roughness'].default_value = 0.3

# UV tiling
uv_scale = nodes_mat.new('ShaderNodeMapping')
uv_scale.location = (-800, 0)
uv_scale.inputs['Scale'].default_value = (3.0, 5.0, 1.0)
uv_input = nodes_mat.new('ShaderNodeTexCoord')
uv_input.location = (-1000, 0)
links_mat.new(uv_input.outputs['UV'], uv_scale.inputs['Vector'])

def load_tex(filename, colorspace='sRGB'):
    path = os.path.join(SKIN_DIR, filename)
    if os.path.exists(path):
        img = bpy.data.images.load(path)
        img.colorspace_settings.name = colorspace
        tex = nodes_mat.new('ShaderNodeTexImage')
        tex.image = img
        links_mat.new(uv_scale.outputs[0], tex.inputs['Vector'])
        return tex
    print(f"[WARN] Not found: {path}")
    return None

tex_albedo = load_tex("human-skin1_albedo.png", 'sRGB')
if tex_albedo:
    tex_albedo.location = (-400, 200)

tex_normal = load_tex("human-skin1_normal-ogl.png", 'Non-Color')
if tex_normal:
    tex_normal.location = (-400, -200)
    nmap = nodes_mat.new('ShaderNodeNormalMap')
    nmap.location = (0, -200)
    nmap.inputs['Strength'].default_value = 1.0
    links_mat.new(tex_normal.outputs[0], nmap.inputs['Color'])
    links_mat.new(nmap.outputs[0], bsdf.inputs['Normal'])

tex_rough = load_tex("human-skin1_roughness.png", 'Non-Color')
if tex_rough:
    tex_rough.location = (-400, 0)
    links_mat.new(tex_rough.outputs[0], bsdf.inputs['Roughness'])

tex_ao = load_tex("human-skin1_ao.png", 'Non-Color')
if tex_ao and tex_albedo:
    tex_ao.location = (-400, 400)
    ao_mix = nodes_mat.new('ShaderNodeMixRGB')
    ao_mix.blend_type = 'MULTIPLY'
    ao_mix.location = (-100, 300)
    ao_mix.inputs['Fac'].default_value = 0.8
    links_mat.new(tex_albedo.outputs[0], ao_mix.inputs['Color1'])
    links_mat.new(tex_ao.outputs[0], ao_mix.inputs['Color2'])
    links_mat.new(ao_mix.outputs[0], bsdf.inputs['Base Color'])
elif tex_albedo:
    links_mat.new(tex_albedo.outputs[0], bsdf.inputs['Base Color'])

tex_height = load_tex("human-skin1_height.png", 'Non-Color')
if tex_height:
    tex_height.location = (-400, -400)
    disp = nodes_mat.new('ShaderNodeDisplacement')
    disp.location = (200, -400)
    disp.inputs['Scale'].default_value = 0.002
    disp.inputs['Midlevel'].default_value = 0.5
    links_mat.new(tex_height.outputs[0], disp.inputs['Height'])
    links_mat.new(disp.outputs[0], mat_output.inputs['Displacement'])

# Assign material
body.data.materials.clear()
body.data.materials.append(mat)
print("[MAT] Assigned PhotorealisticSkin")

# ── Lighting — 3-point studio ─────────────────────────────────
for obj in list(scene.objects):
    if obj.type == 'LIGHT':
        bpy.data.objects.remove(obj, do_unlink=True)

def add_area_light(name, loc, rot_deg, color, power, size=2.0):
    data = bpy.data.lights.new(name, 'AREA')
    data.energy = power
    data.color = color
    data.size = size
    data.size_y = size
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = tuple(math.radians(r) for r in rot_deg)
    return obj

add_area_light('KeyLight',    (2, -2, 2.5),   (-30, 15, -45), (1.0, 0.96, 0.92), 1500, 2.0)
add_area_light('FillLight',   (-2, -1, 1.5),  (-20, -15, 30), (0.85, 0.9, 1.0),  600, 3.0)
add_area_light('RimLight',    (0, 3, 1.5),    (15, 0, 180),   (1.0, 0.93, 0.85), 800, 1.5)
add_area_light('BounceLight', (0, 0, -0.3),   (90, 0, 0),     (0.9, 0.85, 0.8),  200, 4.0)

# ── Studio Floor ──────────────────────────────────────────────
bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, 0))
floor = bpy.context.active_object
floor.name = "StudioFloor"
floor_mat = bpy.data.materials.new("FloorMat")
floor_mat.use_nodes = True
floor_bsdf = floor_mat.node_tree.nodes['Principled BSDF']
floor_bsdf.inputs['Base Color'].default_value = (0.12, 0.12, 0.14, 1.0)
floor_bsdf.inputs['Roughness'].default_value = 0.8
floor.data.materials.append(floor_mat)

# ── World ─────────────────────────────────────────────────────
world = bpy.data.worlds['World']
bg = world.node_tree.nodes['Background']
bg.inputs[0].default_value = (0.18, 0.18, 0.22, 1.0)
bg.inputs[1].default_value = 0.3

# ── Camera ────────────────────────────────────────────────────
cam = scene.camera
if cam:
    cam.data.lens = 40
    cam.data.dof.use_dof = True
    cam.data.dof.focus_distance = 3.0
    cam.data.dof.aperture_fstop = 4.0
    cam.location = (0.5, -4.5, 0.85)
    constraint = cam.constraints.new(type='TRACK_TO')
    constraint.target = body
    constraint.track_axis = 'TRACK_NEGATIVE_Z'
    constraint.up_axis = 'UP_Y'
    bpy.context.view_layer.update()
    bpy.ops.object.select_all(action='DESELECT')
    cam.select_set(True)
    bpy.context.view_layer.objects.active = cam
    bpy.ops.constraint.apply(constraint=constraint.name)
    print(f"[CAM] At {cam.location}")

# ── Render Settings ───────────────────────────────────────────
scene.render.engine = 'CYCLES'
scene.render.resolution_x = 2048
scene.render.resolution_y = 2048
scene.render.resolution_percentage = 100
scene.cycles.samples = 256
scene.cycles.use_denoising = True
scene.cycles.denoiser = 'OPENIMAGEDENOISE'

try:
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'CUDA'
    prefs.get_devices()
    scene.cycles.device = 'GPU'
    print("[RENDER] GPU mode")
except Exception:
    print("[RENDER] CPU mode")

# ── Export GLB ────────────────────────────────────────────────
bpy.ops.object.select_all(action='DESELECT')
body.select_set(True)
bpy.context.view_layer.objects.active = body
bpy.ops.export_scene.gltf(
    filepath=OUT_GLB, use_selection=True, export_format='GLB',
    export_apply=True, export_image_format='AUTO',
    export_materials='EXPORT', export_normals=True, export_tangents=True,
)
print(f"[EXPORT] {OUT_GLB}")

# ── Render ────────────────────────────────────────────────────
scene.render.filepath = OUT_RENDER
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_depth = '16'

print("[RENDER] Starting Cycles 256 samples @ 2048x2048...")
bpy.ops.render.render(write_still=True)
print(f"[RENDER] Done: {OUT_RENDER}")
