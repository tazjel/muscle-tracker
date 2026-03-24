"""Generate muscular MALE body using MPFB — push male + muscle shape keys.

Usage:
    blender --background --python scripts/blender_mpfb_male.py

Output: meshes/mpfb_male_body.glb
        meshes/mpfb_male_render.png
"""
import bpy
import math
import mathutils
import os
import sys

BASE = r"C:\Users\MiEXCITE\Projects\gtd3d"
OUT_GLB = os.path.join(BASE, "meshes", "mpfb_male_body.glb")
OUT_RENDER = os.path.join(BASE, "meshes", "mpfb_male_render.png")
SKIN_DIR = os.path.join(BASE, "apps", "uploads", "skin", "freepbr", "human-skin1-bl")

scene = bpy.context.scene

# Clear default meshes
for obj in list(scene.objects):
    if obj.type == 'MESH':
        bpy.data.objects.remove(obj, do_unlink=True)

# Load MPFB
from bl_ext.user_default import mpfb

# ── Explore MPFB properties for male/muscle settings ──────────
# Check if there are scene properties we can set BEFORE creating the human
print("[MPFB] Checking scene properties for human creation...")
props_found = []
for prop in dir(bpy.context.scene):
    if 'mpfb' in prop.lower():
        props_found.append(prop)
if props_found:
    print(f"  Scene MPFB props: {props_found[:30]}")

# Check window manager props (MPFB often stores settings there)
for prop in dir(bpy.context.window_manager):
    if 'mpfb' in prop.lower():
        props_found.append(prop)

print(f"  Total MPFB props found: {len(props_found)}")

# Try to find and set gender/phenotype before creation
try:
    # MPFB v2 uses HumanService for configuration
    from bl_ext.user_default.mpfb.services.humanservice import HumanService
    print(f"\n[MPFB] HumanService methods:")
    for attr in sorted(dir(HumanService)):
        if not attr.startswith('_'):
            print(f"  {attr}")
except Exception as e:
    print(f"  HumanService: {e}")

# Try to access the new human properties panel settings
try:
    from bl_ext.user_default.mpfb.ui.newhuman import newhumanuiproperties
    print(f"\n[MPFB] NewHuman UI properties:")
    for attr in sorted(dir(newhumanuiproperties)):
        if not attr.startswith('_'):
            print(f"  {attr}")
except Exception as e:
    print(f"  NewHuman props: {e}")

# ── Create the human ──────────────────────────────────────────
print("\n[MPFB] Creating human...")
result = bpy.ops.mpfb.create_human()
print(f"[MPFB] Result: {result}")

# Find the body
body = None
for obj in bpy.data.objects:
    if obj.type == 'MESH':
        body = obj
        break

if not body:
    print("[ERROR] No body created!")
    sys.exit(1)

print(f"[BODY] {body.name}: {len(body.data.vertices)} verts, dims={tuple(round(d,2) for d in body.dimensions)}")

# ── Manipulate shape keys for MALE + MUSCULAR ─────────────────
print("\n[SHAPE KEYS] All keys:")
if body.data.shape_keys:
    keys = body.data.shape_keys.key_blocks
    for key in keys:
        print(f"  {key.name} = {key.value:.3f}")

    # Set male shape keys to max, female to 0
    for key in keys:
        name_lower = key.name.lower()
        # MPFB key naming: $md = macro detail, $ma = male, $fe = female
        # $mu = muscle, $wg = weight, $yn = young
        if '$ma' in key.name and '$fe' not in key.name:
            key.value = 1.0
            print(f"  -> SET MALE: {key.name} = 1.0")
        elif '$fe' in key.name and '$ma' not in key.name:
            key.value = 0.0
            print(f"  -> SET FEMALE OFF: {key.name} = 0.0")

        # Universal keys with muscle/weight
        if 'universal' in name_lower and '$ma' in key.name:
            key.value = 1.0
            print(f"  -> SET UNIVERSAL MALE: {key.name} = 1.0")
        elif 'universal' in name_lower and '$fe' in key.name:
            key.value = 0.0
            print(f"  -> UNSET UNIVERSAL FEMALE: {key.name} = 0.0")

        # Muscle keys — max them
        if '$mu' in key.name or 'muscle' in name_lower:
            key.value = min(key.value + 0.5, 1.0)
            print(f"  -> BOOST MUSCLE: {key.name} = {key.value:.2f}")

        # Cup size keys — zero them (male body)
        if 'cup' in name_lower:
            key.value = 0.0
            print(f"  -> ZERO CUP: {key.name} = 0.0")

    # Print final values
    print("\n[SHAPE KEYS] Final values:")
    for key in keys:
        print(f"  {key.name} = {key.value:.3f}")
else:
    print("  No shape keys!")

# ── Try MPFB target service for more muscle detail ────────────
try:
    from bl_ext.user_default.mpfb.services.targetservice import TargetService
    print("\n[TARGETS] Checking available targets...")
    for attr in sorted(dir(TargetService)):
        if not attr.startswith('_') and ('target' in attr.lower() or 'get' in attr.lower() or 'set' in attr.lower() or 'apply' in attr.lower()):
            print(f"  TargetService.{attr}")

    # Try to get/set macro targets
    try:
        targets = TargetService.get_default_macro_info_dict()
        print(f"\n[TARGETS] Default macro info: {list(targets.keys())[:20]}")
    except Exception as e:
        print(f"  get_default_macro_info_dict: {e}")

    try:
        targets = TargetService.get_target_stack(body)
        print(f"\n[TARGETS] Target stack: {targets}")
    except Exception as e:
        print(f"  get_target_stack: {e}")

except Exception as e:
    print(f"[TARGETS] {e}")

# ── Apply shape key changes to mesh ───────────────────────────
# Bake the shape keys into the mesh
bpy.ops.object.select_all(action='DESELECT')
body.select_set(True)
bpy.context.view_layer.objects.active = body

# Apply shape keys as basis
if body.data.shape_keys:
    # Set the mix and apply
    body.shape_key_add(name="MixResult", from_mix=True)
    # Remove all shape keys except the mix
    while body.data.shape_keys and len(body.data.shape_keys.key_blocks) > 1:
        body.active_shape_key_index = 0
        bpy.ops.object.shape_key_remove()
    if body.data.shape_keys:
        bpy.ops.object.shape_key_remove()
    print("[SHAPE] Applied shape keys to mesh")

bpy.context.view_layer.update()

# ── Scale / Orient ────────────────────────────────────────────
body.name = "MPFBMale"
max_dim = max(body.dimensions)
if max_dim < 1.0 or max_dim > 10:
    sf = 1.78 / max_dim  # 178cm tall male
    body.scale = (sf, sf, sf)
    bpy.context.view_layer.update()
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.context.view_layer.update()
    print(f"[SCALE] {max_dim:.2f} -> {max(body.dimensions):.2f}m")

# Check orientation
import bmesh
verts_world = [body.matrix_world @ v.co for v in body.data.vertices]
y_range = max(v.y for v in verts_world) - min(v.y for v in verts_world)
z_range = max(v.z for v in verts_world) - min(v.z for v in verts_world)
if y_range > z_range * 1.5:
    print(f"[ORIENT] Y-up -> Z-up rotation")
    bm = bmesh.new()
    bm.from_mesh(body.data)
    rot_mat = mathutils.Matrix.Rotation(math.radians(-90), 4, 'X')
    bmesh.ops.transform(bm, matrix=rot_mat, verts=bm.verts)
    bm.to_mesh(body.data)
    bm.free()
    body.data.update()
    bpy.context.view_layer.update()

# Center + feet on floor
verts_world = [body.matrix_world @ v.co for v in body.data.vertices]
min_z = min(v.z for v in verts_world)
cx = sum(v.x for v in verts_world) / len(verts_world)
cy = sum(v.y for v in verts_world) / len(verts_world)
body.location.x -= cx
body.location.y -= cy
body.location.z -= min_z
bpy.context.view_layer.update()

verts_world = [body.matrix_world @ v.co for v in body.data.vertices]
height = max(v.z for v in verts_world) - min(v.z for v in verts_world)
print(f"[POS] Height: {height:.2f}m, Z: {min(v.z for v in verts_world):.2f} to {max(v.z for v in verts_world):.2f}")

# ── Photorealistic Skin Material ──────────────────────────────
mat = bpy.data.materials.new(name="MaleSkin")
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

# Slightly darker/warmer skin tone for male
bsdf.inputs['Base Color'].default_value = (0.72, 0.55, 0.45, 1.0)
bsdf.inputs['Metallic'].default_value = 0.0
bsdf.inputs['Roughness'].default_value = 0.5
bsdf.inputs['Specular IOR Level'].default_value = 0.4
bsdf.inputs['Subsurface Weight'].default_value = 0.3
bsdf.inputs['Subsurface Radius'].default_value = (0.8, 0.3, 0.15)
bsdf.inputs['Subsurface Scale'].default_value = 0.01
bsdf.inputs['Sheen Weight'].default_value = 0.1
bsdf.inputs['Coat Weight'].default_value = 0.03

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
    return None

tex_albedo = load_tex("human-skin1_albedo.png", 'sRGB')
if tex_albedo:
    tex_albedo.location = (-400, 200)

tex_normal = load_tex("human-skin1_normal-ogl.png", 'Non-Color')
if tex_normal:
    tex_normal.location = (-400, -200)
    nmap = nodes_mat.new('ShaderNodeNormalMap')
    nmap.location = (0, -200)
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
    links_mat.new(tex_height.outputs[0], disp.inputs['Height'])
    links_mat.new(disp.outputs[0], mat_output.inputs['Displacement'])

body.data.materials.clear()
body.data.materials.append(mat)
print("[MAT] Male skin applied")

# ── Lighting ──────────────────────────────────────────────────
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

add_area_light('KeyLight',    (2, -2, 2.5),   (-30, 15, -45), (1.0, 0.96, 0.92), 1500, 2.0)
add_area_light('FillLight',   (-2, -1, 1.5),  (-20, -15, 30), (0.85, 0.9, 1.0),  600, 3.0)
add_area_light('RimLight',    (0, 3, 1.5),    (15, 0, 180),   (1.0, 0.93, 0.85), 800, 1.5)
add_area_light('BounceLight', (0, 0, -0.3),   (90, 0, 0),     (0.9, 0.85, 0.8),  200, 4.0)

# Floor
bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, 0))
floor = bpy.context.active_object
floor.name = "StudioFloor"
floor_mat = bpy.data.materials.new("FloorMat")
floor_mat.use_nodes = True
floor_bsdf = floor_mat.node_tree.nodes['Principled BSDF']
floor_bsdf.inputs['Base Color'].default_value = (0.12, 0.12, 0.14, 1.0)
floor_bsdf.inputs['Roughness'].default_value = 0.8
floor.data.materials.append(floor_mat)

# World
world = bpy.data.worlds['World']
bg = world.node_tree.nodes['Background']
bg.inputs[0].default_value = (0.18, 0.18, 0.22, 1.0)
bg.inputs[1].default_value = 0.3

# Camera
cam = scene.camera
if cam:
    cam.data.lens = 50
    cam.data.dof.use_dof = True
    cam.data.dof.focus_distance = 4.0
    cam.data.dof.aperture_fstop = 5.6
    cam.location = (0.5, -3.8, 0.9)
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

# Render
scene.render.engine = 'CYCLES'
scene.render.resolution_x = 2048
scene.render.resolution_y = 2048
scene.cycles.samples = 256
scene.cycles.use_denoising = True
scene.cycles.denoiser = 'OPENIMAGEDENOISE'

try:
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'CUDA'
    prefs.get_devices()
    scene.cycles.device = 'GPU'
except Exception:
    pass

# Export GLB
bpy.ops.object.select_all(action='DESELECT')
body.select_set(True)
bpy.context.view_layer.objects.active = body
bpy.ops.export_scene.gltf(
    filepath=OUT_GLB, use_selection=True, export_format='GLB',
    export_apply=True, export_image_format='AUTO',
    export_materials='EXPORT', export_normals=True, export_tangents=True,
)
print(f"[EXPORT] {OUT_GLB}")

# Render
scene.render.filepath = OUT_RENDER
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_depth = '16'
print("[RENDER] Cycles 256 @ 2048x2048...")
bpy.ops.render.render(write_still=True)
print(f"[DONE] {OUT_RENDER}")
