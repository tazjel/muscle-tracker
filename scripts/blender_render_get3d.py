"""Render the Get3DModels male base body through photorealistic pipeline.

Usage:
    blender --background --python scripts/blender_render_get3d.py

Output: meshes/get3d_render.png
        meshes/get3d_body_final.glb
"""
import bpy
import math
import mathutils
import bmesh
import os

BASE = r"C:\Users\MiEXCITE\Projects\gtd3d"
INPUT_GLB = os.path.join(BASE, "meshes", "get3d_male_base.glb")
SKIN_DIR = os.path.join(BASE, "apps", "uploads", "skin", "freepbr", "human-skin1-bl")
OUT_GLB = os.path.join(BASE, "meshes", "get3d_body_final.glb")
OUT_RENDER = os.path.join(BASE, "meshes", "get3d_render.png")

if not os.path.exists(INPUT_GLB):
    raise SystemExit(f"[ERROR] Not found: {INPUT_GLB}")

scene = bpy.context.scene

# ── Clear default meshes ──────────────────────────────────────
for obj in list(scene.objects):
    if obj.type == 'MESH':
        bpy.data.objects.remove(obj, do_unlink=True)

# ── Import GLB ────────────────────────────────────────────────
print(f"[GLB] Importing: {INPUT_GLB} ({os.path.getsize(INPUT_GLB) / 1e6:.1f} MB)")
bpy.ops.import_scene.gltf(filepath=INPUT_GLB)

# Find largest mesh (the body)
body = None
max_verts = 0
for obj in scene.objects:
    if obj.type == 'MESH':
        vc = len(obj.data.vertices)
        print(f"  Mesh: {obj.name} | {vc} verts | dims={tuple(round(d,1) for d in obj.dimensions)}")
        if vc > max_verts:
            max_verts = vc
            body = obj

if not body:
    raise SystemExit("[ERROR] No mesh imported!")

body.name = "Get3DBody"
print(f"[GLB] Using: {body.name} with {max_verts} verts")

# ── Scale to ~1.75m ──────────────────────────────────────────
max_dim = max(body.dimensions)
if max_dim > 2.5 or max_dim < 1.0:
    sf = 1.75 / max_dim
    body.scale = (sf, sf, sf)
    bpy.context.view_layer.update()
    bpy.ops.object.select_all(action='DESELECT')
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.context.view_layer.update()
    print(f"[SCALE] {max_dim:.1f} -> {max(body.dimensions):.2f}m")

# Check orientation
verts_world = [body.matrix_world @ v.co for v in body.data.vertices]
y_range = max(v.y for v in verts_world) - min(v.y for v in verts_world)
z_range = max(v.z for v in verts_world) - min(v.z for v in verts_world)
x_range = max(v.x for v in verts_world) - min(v.x for v in verts_world)
print(f"[ORIENT] X={x_range:.2f} Y={y_range:.2f} Z={z_range:.2f}")

if y_range > z_range * 1.5:
    print("[ORIENT] Y-up detected, rotating to Z-up")
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

# ── Check existing materials ──────────────────────────────────
print(f"\n[MAT] Existing materials on mesh: {len(body.data.materials)}")
has_textures = False
for i, mat in enumerate(body.data.materials):
    if mat:
        print(f"  [{i}] {mat.name}")
        if mat.use_nodes:
            for node in mat.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image:
                    print(f"       -> texture: {node.image.name} ({node.image.size[0]}x{node.image.size[1]})")
                    has_textures = True

# Only replace material if no good textures exist
if not has_textures:
    print("[MAT] No textures found, applying photorealistic skin...")
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

    body.data.materials.clear()
    body.data.materials.append(mat)
else:
    print("[MAT] Keeping existing textured materials")
    # Still add SSS to existing materials
    for mat in body.data.materials:
        if mat and mat.use_nodes:
            for node in mat.node_tree.nodes:
                if node.type == 'BSDF_PRINCIPLED':
                    try:
                        node.inputs['Subsurface Weight'].default_value = 0.25
                        node.inputs['Subsurface Radius'].default_value = (0.8, 0.3, 0.15)
                        node.inputs['Subsurface Scale'].default_value = 0.01
                        print(f"  Added SSS to {mat.name}")
                    except Exception:
                        pass

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

# ── Floor ─────────────────────────────────────────────────────
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

# ── Render ────────────────────────────────────────────────────
scene.render.engine = 'CYCLES'
scene.render.resolution_x = 1024
scene.render.resolution_y = 1024
scene.render.resolution_percentage = 100
scene.cycles.samples = 128  # faster preview for 4M vert model
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

# ── Export GLB (decimated for viewer) ─────────────────────────
# 4M verts is too heavy for Three.js — decimate first
if max_verts > 100000:
    print(f"[DECIMATE] {max_verts} verts -> targeting ~50K for web viewer")
    bpy.ops.object.select_all(action='DESELECT')
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    mod = body.modifiers.new("Decimate", 'DECIMATE')
    ratio = 50000 / max_verts
    mod.ratio = max(ratio, 0.01)
    print(f"[DECIMATE] Ratio: {mod.ratio:.4f}")

bpy.ops.object.select_all(action='DESELECT')
body.select_set(True)
bpy.context.view_layer.objects.active = body
bpy.ops.export_scene.gltf(
    filepath=OUT_GLB, use_selection=True, export_format='GLB',
    export_apply=True, export_image_format='AUTO',
    export_materials='EXPORT', export_normals=True,
)
print(f"[EXPORT] {OUT_GLB}")

# ── Render ────────────────────────────────────────────────────
scene.render.filepath = OUT_RENDER
scene.render.image_settings.file_format = 'PNG'
print("[RENDER] Starting Cycles 128 samples @ 1024x1024...")
bpy.ops.render.render(write_still=True)
print(f"[RENDER] Done: {OUT_RENDER}")
