"""Quick re-render of MPFB male + Get3D + Anny with FIXED camera targeting.

Camera aims at mid-body empty, not feet origin.

Usage:
    blender --background --python scripts/blender_rerender_all.py -- mpfb
    blender --background --python scripts/blender_rerender_all.py -- get3d
    blender --background --python scripts/blender_rerender_all.py -- anny
"""
import bpy
import math
import mathutils
import bmesh
import os
import sys

BASE = r"C:\Users\MiEXCITE\Projects\gtd3d"
SKIN_DIR = os.path.join(BASE, "apps", "uploads", "skin", "freepbr", "human-skin1-bl")

# Parse which model to render
argv = sys.argv
mode = "mpfb"
if "--" in argv:
    mode = argv[argv.index("--") + 1]

MODELS = {
    "mpfb": {
        "glb": os.path.join(BASE, "meshes", "mpfb_male_body.glb"),
        "out_render": os.path.join(BASE, "meshes", "mpfb_male_render.png"),
        "out_glb": None,  # already exported
        "res": 2048,
        "samples": 256,
    },
    "get3d": {
        "glb": os.path.join(BASE, "meshes", "get3d_male_base.glb"),
        "out_render": os.path.join(BASE, "meshes", "get3d_render.png"),
        "out_glb": os.path.join(BASE, "meshes", "get3d_body_final.glb"),
        "res": 1024,
        "samples": 128,
    },
    "anny": {
        "glb": os.path.join(BASE, "meshes", "anny_skinned.glb"),
        "out_render": os.path.join(BASE, "meshes", "anny_render.png"),
        "out_glb": None,
        "res": 2048,
        "samples": 256,
    },
    "nosmpl": {
        "glb": os.path.join(BASE, "meshes", "nosmpl_body.glb"),
        "out_render": os.path.join(BASE, "meshes", "nosmpl_render.png"),
        "out_glb": None,
        "res": 1024,
        "samples": 128,
    },
}

cfg = MODELS[mode]
print(f"[MODE] {mode}: {cfg['glb']}")

scene = bpy.context.scene

# Clear meshes
for obj in list(scene.objects):
    if obj.type == 'MESH':
        bpy.data.objects.remove(obj, do_unlink=True)

# Import
bpy.ops.import_scene.gltf(filepath=cfg['glb'])

# Find largest mesh
body = None
max_verts = 0
for obj in scene.objects:
    if obj.type == 'MESH':
        vc = len(obj.data.vertices)
        if vc > max_verts:
            max_verts = vc
            body = obj

if not body:
    raise SystemExit("[ERROR] No mesh!")

body.name = f"{mode}_body"
print(f"[BODY] {body.name}: {max_verts} verts, dims={tuple(round(d,1) for d in body.dimensions)}")

# Scale to ~1.75m
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

# Check orientation — rotate Y-up to Z-up if needed
verts_world = [body.matrix_world @ v.co for v in body.data.vertices]
y_range = max(v.y for v in verts_world) - min(v.y for v in verts_world)
z_range = max(v.z for v in verts_world) - min(v.z for v in verts_world)

if y_range > z_range * 1.5:
    print(f"[ORIENT] Y-up ({y_range:.2f}) > Z ({z_range:.2f}), rotating")
    bm = bmesh.new()
    bm.from_mesh(body.data)
    rot_mat = mathutils.Matrix.Rotation(math.radians(-90), 4, 'X')
    bmesh.ops.transform(bm, matrix=rot_mat, verts=bm.verts)
    bm.to_mesh(body.data)
    bm.free()
    body.data.update()
    bpy.context.view_layer.update()

# Center XY, feet on Z=0
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

# ── Create aim target at mid-body ─────────────────────────────
aim = bpy.data.objects.new("CamTarget", None)
bpy.context.collection.objects.link(aim)
aim.location = (0, 0, height * 0.45)  # slightly below center (belly button level)
aim.empty_display_size = 0.1
print(f"[AIM] Target at Z={aim.location.z:.2f}")

# ── Check materials — apply skin if no textures ───────────────
has_textures = False
for mat in body.data.materials:
    if mat and mat.use_nodes:
        for node in mat.node_tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image:
                has_textures = True
                break

if not has_textures:
    mat = bpy.data.materials.new(name="SkinPBR")
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

    bsdf.inputs['Base Color'].default_value = (0.75, 0.58, 0.48, 1.0)
    bsdf.inputs['Roughness'].default_value = 0.45
    bsdf.inputs['Specular IOR Level'].default_value = 0.4
    bsdf.inputs['Subsurface Weight'].default_value = 0.3
    bsdf.inputs['Subsurface Radius'].default_value = (0.8, 0.3, 0.15)
    bsdf.inputs['Subsurface Scale'].default_value = 0.01

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
    tex_normal = load_tex("human-skin1_normal-ogl.png", 'Non-Color')
    tex_rough = load_tex("human-skin1_roughness.png", 'Non-Color')
    tex_ao = load_tex("human-skin1_ao.png", 'Non-Color')

    if tex_normal:
        nmap = nodes_mat.new('ShaderNodeNormalMap')
        links_mat.new(tex_normal.outputs[0], nmap.inputs['Color'])
        links_mat.new(nmap.outputs[0], bsdf.inputs['Normal'])
    if tex_rough:
        links_mat.new(tex_rough.outputs[0], bsdf.inputs['Roughness'])
    if tex_ao and tex_albedo:
        ao_mix = nodes_mat.new('ShaderNodeMixRGB')
        ao_mix.blend_type = 'MULTIPLY'
        ao_mix.inputs['Fac'].default_value = 0.8
        links_mat.new(tex_albedo.outputs[0], ao_mix.inputs['Color1'])
        links_mat.new(tex_ao.outputs[0], ao_mix.inputs['Color2'])
        links_mat.new(ao_mix.outputs[0], bsdf.inputs['Base Color'])
    elif tex_albedo:
        links_mat.new(tex_albedo.outputs[0], bsdf.inputs['Base Color'])

    body.data.materials.clear()
    body.data.materials.append(mat)
    print("[MAT] PBR skin applied")

# ── Lighting ──────────────────────────────────────────────────
for obj in list(scene.objects):
    if obj.type == 'LIGHT':
        bpy.data.objects.remove(obj, do_unlink=True)

def add_area_light(name, loc, rot_deg, color, power, size=2.0):
    data = bpy.data.lights.new(name, 'AREA')
    data.energy = power
    data.color = color
    data.size = size
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = tuple(math.radians(r) for r in rot_deg)

add_area_light('Key',    (2, -2, 2.5),   (-30, 15, -45), (1.0, 0.96, 0.92), 1500, 2.0)
add_area_light('Fill',   (-2, -1, 1.5),  (-20, -15, 30), (0.85, 0.9, 1.0),  600, 3.0)
add_area_light('Rim',    (0, 3, 1.5),    (15, 0, 180),   (1.0, 0.93, 0.85), 800, 1.5)
add_area_light('Bounce', (0, 0, -0.3),   (90, 0, 0),     (0.9, 0.85, 0.8),  200, 4.0)

# Floor
bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, 0))
floor = bpy.context.active_object
floor_mat = bpy.data.materials.new("Floor")
floor_mat.use_nodes = True
floor_mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.12, 0.12, 0.14, 1.0)
floor_mat.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = 0.8
floor.data.materials.append(floor_mat)

# World
world = bpy.data.worlds['World']
bg = world.node_tree.nodes['Background']
bg.inputs[0].default_value = (0.18, 0.18, 0.22, 1.0)
bg.inputs[1].default_value = 0.3

# ── Camera — TRACK_TO the mid-body empty ──────────────────────
cam = scene.camera
if cam:
    cam.data.lens = 50
    cam.data.dof.use_dof = True
    cam.data.dof.focus_distance = 4.5
    cam.data.dof.aperture_fstop = 5.6
    # Position: front-right, at belly height, far enough for full body + margin
    cam.location = (0.6, -5.0, height * 0.45)

    constraint = cam.constraints.new(type='TRACK_TO')
    constraint.target = aim  # AIM AT MID-BODY, NOT FEET
    constraint.track_axis = 'TRACK_NEGATIVE_Z'
    constraint.up_axis = 'UP_Y'
    bpy.context.view_layer.update()

    bpy.ops.object.select_all(action='DESELECT')
    cam.select_set(True)
    bpy.context.view_layer.objects.active = cam
    bpy.ops.constraint.apply(constraint=constraint.name)
    print(f"[CAM] At {cam.location}, aiming at Z={aim.location.z:.2f}")

# ── Render ────────────────────────────────────────────────────
scene.render.engine = 'CYCLES'
scene.render.resolution_x = cfg['res']
scene.render.resolution_y = cfg['res']
scene.cycles.samples = cfg['samples']
scene.cycles.use_denoising = True
scene.cycles.denoiser = 'OPENIMAGEDENOISE'

try:
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'CUDA'
    prefs.get_devices()
    scene.cycles.device = 'GPU'
except Exception:
    pass

# Export GLB if needed (with decimation for large models)
if cfg['out_glb']:
    if max_verts > 100000:
        mod = body.modifiers.new("Decimate", 'DECIMATE')
        mod.ratio = max(50000 / max_verts, 0.01)

    bpy.ops.object.select_all(action='DESELECT')
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.export_scene.gltf(
        filepath=cfg['out_glb'], use_selection=True, export_format='GLB',
        export_apply=True, export_materials='EXPORT', export_normals=True,
    )
    print(f"[EXPORT] {cfg['out_glb']}")

# Render
scene.render.filepath = cfg['out_render']
scene.render.image_settings.file_format = 'PNG'
print(f"[RENDER] {mode}: Cycles {cfg['samples']} @ {cfg['res']}x{cfg['res']}...")
bpy.ops.render.render(write_still=True)
print(f"[DONE] {cfg['out_render']}")
