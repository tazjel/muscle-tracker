"""Generate athletic male body using MPFB TargetService API (proper method).

Usage:
    blender --background --python scripts/blender_mpfb_v2.py

Output: meshes/mpfb_v2_body.glb
        meshes/mpfb_v2_render.png
"""
import bpy
import math
import mathutils
import bmesh
import os
import sys

BASE = r"C:\Users\MiEXCITE\Projects\gtd3d"
OUT_GLB = os.path.join(BASE, "meshes", "mpfb_v2_body.glb")
OUT_RENDER = os.path.join(BASE, "meshes", "mpfb_v2_render.png")
SKIN_DIR = os.path.join(BASE, "apps", "uploads", "skin", "freepbr", "human-skin1-bl")

scene = bpy.context.scene

# Clear default meshes
for obj in list(scene.objects):
    if obj.type == 'MESH':
        bpy.data.objects.remove(obj, do_unlink=True)

# ── Create MPFB Human ────────────────────────────────────────
from bl_ext.user_default import mpfb
from bl_ext.user_default.mpfb.services.targetservice import TargetService

print("[MPFB] Creating human...")
bpy.ops.mpfb.create_human()

body = None
for obj in bpy.data.objects:
    if obj.type == 'MESH':
        body = obj
        break

if not body:
    sys.exit("[ERROR] No body created")

print(f"[BODY] {body.name}: {len(body.data.vertices)} verts")

# ── Use TargetService to set male + athletic ──────────────────
print("\n[TARGETS] Current stack:")
stack = TargetService.get_target_stack(body)
for t in stack:
    print(f"  {t['target']} = {t['value']:.3f}")

# Get macro info
macro = TargetService.get_default_macro_info_dict()
print(f"\n[MACRO] Available: {list(macro.keys())}")
print(f"[MACRO] Values: {macro}")

# Try to set macro targets using the proper API
print("\n[TARGETS] Setting male + athletic via TargetService...")

# Set male targets high, female targets to 0
for t in stack:
    target_name = t['target']
    if '$ma' in target_name and '$fe' not in target_name:
        TargetService.set_target_value(body, target_name, 1.0)
        print(f"  SET {target_name} = 1.0 (male)")
    elif '$fe' in target_name and '$ma' not in target_name:
        TargetService.set_target_value(body, target_name, 0.0)
        print(f"  SET {target_name} = 0.0 (female off)")
    elif 'universal' in target_name and '$ma' in target_name:
        TargetService.set_target_value(body, target_name, 1.0)
        print(f"  SET {target_name} = 1.0 (universal male)")
    elif 'universal' in target_name and '$fe' in target_name:
        TargetService.set_target_value(body, target_name, 0.0)
        print(f"  SET {target_name} = 0.0 (universal female off)")
    elif 'cup' in target_name.lower():
        TargetService.set_target_value(body, target_name, 0.0)
        print(f"  SET {target_name} = 0.0 (no cups)")

# Reapply macro details for proper interpolation
print("\n[TARGETS] Reapplying macro details...")
try:
    TargetService.reapply_macro_details(body)
    print("  reapply_macro_details OK")
except Exception as e:
    print(f"  reapply_macro_details: {e}")

bpy.context.view_layer.update()

# Verify
print("\n[TARGETS] After update:")
stack = TargetService.get_target_stack(body)
for t in stack:
    print(f"  {t['target']} = {t['value']:.3f}")

# Bake targets to mesh
print("\n[BAKE] Baking targets...")
try:
    TargetService.bake_targets(body)
    print("  bake_targets OK")
except Exception as e:
    print(f"  bake_targets: {e}")
    # Fallback: apply shape keys manually
    bpy.ops.object.select_all(action='DESELECT')
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    if body.data.shape_keys:
        body.shape_key_add(name="Mix", from_mix=True)
        while body.data.shape_keys and len(body.data.shape_keys.key_blocks) > 1:
            body.active_shape_key_index = 0
            bpy.ops.object.shape_key_remove()
        if body.data.shape_keys:
            bpy.ops.object.shape_key_remove()
        print("  Fallback shape key bake OK")

bpy.context.view_layer.update()
body.name = "MPFBv2"
print(f"[BODY] Final: {len(body.data.vertices)} verts, dims={tuple(round(d,2) for d in body.dimensions)}")

# ── Scale + Orient ────────────────────────────────────────────
max_dim = max(body.dimensions)
if max_dim < 1.0 or max_dim > 2.5:
    sf = 1.78 / max_dim
    body.scale = (sf, sf, sf)
    bpy.context.view_layer.update()
    bpy.ops.object.select_all(action='DESELECT')
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.context.view_layer.update()

# Orientation check
verts_world = [body.matrix_world @ v.co for v in body.data.vertices]
y_range = max(v.y for v in verts_world) - min(v.y for v in verts_world)
z_range = max(v.z for v in verts_world) - min(v.z for v in verts_world)
if y_range > z_range * 1.5:
    bm = bmesh.new()
    bm.from_mesh(body.data)
    bmesh.ops.transform(bm, matrix=mathutils.Matrix.Rotation(math.radians(-90), 4, 'X'), verts=bm.verts)
    bm.to_mesh(body.data)
    bm.free()
    body.data.update()
    bpy.context.view_layer.update()

# Center + feet on floor
verts_world = [body.matrix_world @ v.co for v in body.data.vertices]
min_z = min(v.z for v in verts_world)
max_z = max(v.z for v in verts_world)
cx = sum(v.x for v in verts_world) / len(verts_world)
cy = sum(v.y for v in verts_world) / len(verts_world)
body.location.x -= cx
body.location.y -= cy
body.location.z -= min_z
bpy.context.view_layer.update()

height = max_z - min_z
print(f"[POS] Height: {height:.2f}m")

# Aim target at mid-body
aim = bpy.data.objects.new("CamTarget", None)
bpy.context.collection.objects.link(aim)
aim.location = (0, 0, height * 0.45)

# ── Skin Material ─────────────────────────────────────────────
mat = bpy.data.materials.new(name="MaleSkinV2")
mat.use_nodes = True
tree = mat.node_tree
nodes_mat = tree.nodes
links_mat = tree.links
nodes_mat.clear()

out_node = nodes_mat.new('ShaderNodeOutputMaterial')
out_node.location = (600, 0)
bsdf = nodes_mat.new('ShaderNodeBsdfPrincipled')
bsdf.location = (200, 0)
links_mat.new(bsdf.outputs[0], out_node.inputs[0])

bsdf.inputs['Base Color'].default_value = (0.75, 0.58, 0.48, 1.0)
bsdf.inputs['Roughness'].default_value = 0.45
bsdf.inputs['Specular IOR Level'].default_value = 0.4
bsdf.inputs['Subsurface Weight'].default_value = 0.3
bsdf.inputs['Subsurface Radius'].default_value = (0.8, 0.3, 0.15)
bsdf.inputs['Subsurface Scale'].default_value = 0.01
bsdf.inputs['Sheen Weight'].default_value = 0.1
bsdf.inputs['Coat Weight'].default_value = 0.03

uv_scale = nodes_mat.new('ShaderNodeMapping')
uv_scale.location = (-800, 0)
uv_scale.inputs['Scale'].default_value = (3.0, 5.0, 1.0)
uv_input = nodes_mat.new('ShaderNodeTexCoord')
uv_input.location = (-1000, 0)
links_mat.new(uv_input.outputs['UV'], uv_scale.inputs['Vector'])

def load_tex(filename, cs='sRGB'):
    p = os.path.join(SKIN_DIR, filename)
    if os.path.exists(p):
        img = bpy.data.images.load(p)
        img.colorspace_settings.name = cs
        tex = nodes_mat.new('ShaderNodeTexImage')
        tex.image = img
        links_mat.new(uv_scale.outputs[0], tex.inputs['Vector'])
        return tex
    return None

t_alb = load_tex("human-skin1_albedo.png")
t_nrm = load_tex("human-skin1_normal-ogl.png", 'Non-Color')
t_rgh = load_tex("human-skin1_roughness.png", 'Non-Color')
t_ao = load_tex("human-skin1_ao.png", 'Non-Color')
t_hgt = load_tex("human-skin1_height.png", 'Non-Color')

if t_nrm:
    nmap = nodes_mat.new('ShaderNodeNormalMap')
    nmap.inputs['Strength'].default_value = 1.0
    links_mat.new(t_nrm.outputs[0], nmap.inputs['Color'])
    links_mat.new(nmap.outputs[0], bsdf.inputs['Normal'])
if t_rgh:
    links_mat.new(t_rgh.outputs[0], bsdf.inputs['Roughness'])
if t_ao and t_alb:
    mix = nodes_mat.new('ShaderNodeMixRGB')
    mix.blend_type = 'MULTIPLY'
    mix.inputs['Fac'].default_value = 0.8
    links_mat.new(t_alb.outputs[0], mix.inputs['Color1'])
    links_mat.new(t_ao.outputs[0], mix.inputs['Color2'])
    links_mat.new(mix.outputs[0], bsdf.inputs['Base Color'])
elif t_alb:
    links_mat.new(t_alb.outputs[0], bsdf.inputs['Base Color'])
if t_hgt:
    disp = nodes_mat.new('ShaderNodeDisplacement')
    disp.inputs['Scale'].default_value = 0.002
    links_mat.new(t_hgt.outputs[0], disp.inputs['Height'])
    links_mat.new(disp.outputs[0], out_node.inputs['Displacement'])

body.data.materials.clear()
body.data.materials.append(mat)

# ── Lighting ──────────────────────────────────────────────────
for obj in list(scene.objects):
    if obj.type == 'LIGHT':
        bpy.data.objects.remove(obj, do_unlink=True)

def add_light(name, loc, rot, color, power, size=2.0):
    d = bpy.data.lights.new(name, 'AREA')
    d.energy = power; d.color = color; d.size = size
    o = bpy.data.objects.new(name, d)
    bpy.context.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = tuple(math.radians(r) for r in rot)

add_light('Key',  (2,-2,2.5),  (-30,15,-45), (1,.96,.92), 1500, 2)
add_light('Fill', (-2,-1,1.5), (-20,-15,30), (.85,.9,1),  600, 3)
add_light('Rim',  (0,3,1.5),   (15,0,180),   (1,.93,.85), 800, 1.5)
add_light('Bnc',  (0,0,-0.3),  (90,0,0),     (.9,.85,.8), 200, 4)

# Floor
bpy.ops.mesh.primitive_plane_add(size=20, location=(0,0,0))
fl = bpy.context.active_object
fm = bpy.data.materials.new("Floor")
fm.use_nodes = True
fm.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (.12,.12,.14,1)
fm.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = 0.8
fl.data.materials.append(fm)

# World
bg = bpy.data.worlds['World'].node_tree.nodes['Background']
bg.inputs[0].default_value = (.18,.18,.22,1)
bg.inputs[1].default_value = 0.3

# Camera
cam = scene.camera
cam.data.lens = 50
cam.data.dof.use_dof = True
cam.data.dof.focus_distance = 5.0
cam.data.dof.aperture_fstop = 5.6
cam.location = (0.6, -5.0, height * 0.45)

c = cam.constraints.new(type='TRACK_TO')
c.target = aim
c.track_axis = 'TRACK_NEGATIVE_Z'
c.up_axis = 'UP_Y'
bpy.context.view_layer.update()
bpy.ops.object.select_all(action='DESELECT')
cam.select_set(True)
bpy.context.view_layer.objects.active = cam
bpy.ops.constraint.apply(constraint=c.name)

# Render
scene.render.engine = 'CYCLES'
scene.render.resolution_x = 2048
scene.render.resolution_y = 2048
scene.cycles.samples = 256
scene.cycles.use_denoising = True
scene.cycles.denoiser = 'OPENIMAGEDENOISE'
try:
    p = bpy.context.preferences.addons['cycles'].preferences
    p.compute_device_type = 'CUDA'; p.get_devices()
    scene.cycles.device = 'GPU'
except: pass

# Export
bpy.ops.object.select_all(action='DESELECT')
body.select_set(True)
bpy.context.view_layer.objects.active = body
bpy.ops.export_scene.gltf(
    filepath=OUT_GLB, use_selection=True, export_format='GLB',
    export_apply=True, export_materials='EXPORT',
    export_normals=True, export_tangents=True,
)
print(f"[EXPORT] {OUT_GLB}")

scene.render.filepath = OUT_RENDER
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_depth = '16'
print("[RENDER] Cycles 256 @ 2048x2048...")
bpy.ops.render.render(write_still=True)
print(f"[DONE] {OUT_RENDER}")
