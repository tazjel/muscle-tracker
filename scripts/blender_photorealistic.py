#!/usr/bin/env python3
"""Photorealistic body render — Anny GLB + FreePBR + Cycles SSS.

Usage:
    blender --background --python scripts/blender_photorealistic.py

Output: meshes/photorealistic_render.png  (2048x2048)
        meshes/photorealistic_body.glb    (full PBR)
"""

import bpy
import math
import mathutils
import os

BASE = r"C:\Users\MiEXCITE\Projects\gtd3d"
ANNY_GLB = os.path.join(BASE, "meshes", "anny_skinned.glb")
if not os.path.exists(ANNY_GLB):
    ANNY_GLB = os.path.join(BASE, "web_app", "static", "viewer3d", "anny_skinned.glb")
SKIN_DIR = os.path.join(BASE, "apps", "uploads", "skin", "freepbr", "human-skin1-bl")
OUT_RENDER = os.path.join(BASE, "meshes", "photorealistic_render.png")
OUT_GLB = os.path.join(BASE, "meshes", "photorealistic_body.glb")

scene = bpy.context.scene

# ── Delete default cube only, keep camera & light ────────────
for obj in list(scene.objects):
    if obj.type == 'MESH':
        bpy.data.objects.remove(obj, do_unlink=True)

# ── Import Anny GLB ──────────────────────────────────────────
print(f"[GLB] Importing: {ANNY_GLB}")
bpy.ops.import_scene.gltf(filepath=ANNY_GLB)

body = None
for obj in scene.objects:
    if obj.type == 'MESH':
        body = obj
        break

if not body:
    raise SystemExit("[ERROR] No mesh imported!")

body.name = "Body"
print(f"[GLB] {body.name}: {len(body.data.vertices)} verts, dims={body.dimensions}")

# ── Scale to meters ──────────────────────────────────────────
max_dim = max(body.dimensions)
if max_dim > 10:
    sf = 1.7 / max_dim
    body.scale = (sf, sf, sf)
    bpy.context.view_layer.update()
    # Apply scale to mesh data
    bpy.ops.object.select_all(action='DESELECT')
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.context.view_layer.update()
    print(f"[SCALE] {max_dim:.0f} -> {max(body.dimensions):.2f}m")

# Body is Y-up: height in Y (-0.7 to 1.0), width in X, depth in Z
# Rotate mesh data directly using bmesh to make it Z-up
import bmesh
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

# ── Photorealistic Skin Material ─────────────────────────────
mat = bpy.data.materials.new(name="PhotorealisticSkin")
mat.use_nodes = True
tree = mat.node_tree
nodes_mat = tree.nodes
links_mat = tree.links
nodes_mat.clear()

# Output node
mat_output = nodes_mat.new('ShaderNodeOutputMaterial')
mat_output.location = (600, 0)

# Principled BSDF with SSS
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

# Albedo
tex_albedo = load_tex("human-skin1_albedo.png", 'sRGB')
if tex_albedo:
    tex_albedo.location = (-400, 200)

# Normal
tex_normal = load_tex("human-skin1_normal-ogl.png", 'Non-Color')
if tex_normal:
    tex_normal.location = (-400, -200)
    nmap = nodes_mat.new('ShaderNodeNormalMap')
    nmap.location = (0, -200)
    nmap.inputs['Strength'].default_value = 1.0
    links_mat.new(tex_normal.outputs[0], nmap.inputs['Color'])
    links_mat.new(nmap.outputs[0], bsdf.inputs['Normal'])
    print("[TEX] Normal")

# Roughness
tex_rough = load_tex("human-skin1_roughness.png", 'Non-Color')
if tex_rough:
    tex_rough.location = (-400, 0)
    links_mat.new(tex_rough.outputs[0], bsdf.inputs['Roughness'])
    print("[TEX] Roughness")

# AO * Albedo
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
    print("[TEX] AO * Albedo")
elif tex_albedo:
    links_mat.new(tex_albedo.outputs[0], bsdf.inputs['Base Color'])
    print("[TEX] Albedo (no AO)")

# Height → displacement
tex_height = load_tex("human-skin1_height.png", 'Non-Color')
if tex_height:
    tex_height.location = (-400, -400)
    disp = nodes_mat.new('ShaderNodeDisplacement')
    disp.location = (200, -400)
    disp.inputs['Scale'].default_value = 0.002
    disp.inputs['Midlevel'].default_value = 0.5
    links_mat.new(tex_height.outputs[0], disp.inputs['Height'])
    links_mat.new(disp.outputs[0], mat_output.inputs['Displacement'])
    print("[TEX] Height/displacement")

# Assign material
body.data.materials.clear()
body.data.materials.append(mat)
print("[MAT] Assigned PhotorealisticSkin")

# ── Lighting — 3-point studio ────────────────────────────────
# Remove default light
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

# Body is Z-up: front=-Y, height 0-1.7m in Z
add_area_light('KeyLight',    (2, -2, 2.5),   (-30, 15, -45), (1.0, 0.96, 0.92), 1500, 2.0)
add_area_light('FillLight',   (-2, -1, 1.5),  (-20, -15, 30), (0.85, 0.9, 1.0),  600, 3.0)
add_area_light('RimLight',    (0, 3, 1.5),    (15, 0, 180),   (1.0, 0.93, 0.85), 800, 1.5)
add_area_light('BounceLight', (0, 0, -0.3),   (90, 0, 0),     (0.9, 0.85, 0.8),  200, 4.0)
print("[LIGHT] 4-point studio")

# ── Studio Floor ─────────────────────────────────────────────
bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, 0))
floor = bpy.context.active_object
floor.name = "StudioFloor"
floor_mat = bpy.data.materials.new("FloorMat")
floor_mat.use_nodes = True
floor_bsdf = floor_mat.node_tree.nodes['Principled BSDF']
floor_bsdf.inputs['Base Color'].default_value = (0.12, 0.12, 0.14, 1.0)
floor_bsdf.inputs['Roughness'].default_value = 0.8
floor.data.materials.append(floor_mat)
print("[FLOOR] Studio floor added")

# ── World ────────────────────────────────────────────────────
world = bpy.data.worlds['World']
bg = world.node_tree.nodes['Background']
bg.inputs[0].default_value = (0.18, 0.18, 0.22, 1.0)
bg.inputs[1].default_value = 0.3

# ── Camera — portrait 85mm ───────────────────────────────────
cam = scene.camera
if cam:
    cam.data.lens = 85
    cam.data.dof.use_dof = True
    cam.data.dof.focus_distance = 3.0
    cam.data.dof.aperture_fstop = 4.0
    # Body stands Z-up: height 1.7m, feet Z=0, front is -Y
    # Full body shot: camera at hip height, wide enough for head+feet+margin
    cam.location = (0.5, -4.5, 0.85)
    cam.data.lens = 40  # slightly wide for full body with margin
    # Use constraint to look at body
    constraint = cam.constraints.new(type='TRACK_TO')
    constraint.target = body
    constraint.track_axis = 'TRACK_NEGATIVE_Z'
    constraint.up_axis = 'UP_Y'
    bpy.context.view_layer.update()
    # Bake constraint to rotation
    bpy.ops.object.select_all(action='DESELECT')
    cam.select_set(True)
    bpy.context.view_layer.objects.active = cam
    bpy.ops.constraint.apply(constraint=constraint.name)
    print(f"[CAM] At {cam.location}, rot={cam.rotation_euler}")
else:
    print("[WARN] No camera in scene!")

# ── Render Settings — Cycles ─────────────────────────────────
scene.render.engine = 'CYCLES'
scene.render.resolution_x = 2048
scene.render.resolution_y = 2048
scene.render.resolution_percentage = 100
scene.cycles.samples = 512
scene.cycles.use_denoising = True
scene.cycles.denoiser = 'OPENIMAGEDENOISE'

# Try GPU
try:
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'CUDA'
    prefs.get_devices()
    scene.cycles.device = 'GPU'
    print("[RENDER] GPU mode")
except Exception:
    print("[RENDER] CPU mode (no GPU)")

# ── Export GLB ───────────────────────────────────────────────
bpy.ops.object.select_all(action='DESELECT')
body.select_set(True)
bpy.context.view_layer.objects.active = body
bpy.ops.export_scene.gltf(
    filepath=OUT_GLB, use_selection=True, export_format='GLB',
    export_apply=True, export_image_format='AUTO',
    export_materials='EXPORT', export_normals=True, export_tangents=True,
)
print(f"[EXPORT] {OUT_GLB}")

# ── Render ───────────────────────────────────────────────────
scene.render.filepath = OUT_RENDER
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_depth = '16'

print("[RENDER] Starting Cycles 512 samples @ 2048x2048...")
bpy.ops.render.render(write_still=True)
print(f"[RENDER] Done: {OUT_RENDER}")
