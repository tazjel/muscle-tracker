"""MPFB v3: Direct shape key + TargetService bake (best of both approaches).

Sets male shape keys directly (proven to work), then uses TargetService.bake_targets()
for clean mesh output (no artifacts).

Usage: blender --background --python scripts/blender_mpfb_v3.py
Output: meshes/mpfb_v3_body.glb + meshes/mpfb_v3_render.png
"""
import bpy, math, mathutils, bmesh, os, sys

BASE = r"C:\Users\MiEXCITE\Projects\gtd3d"
OUT_GLB = os.path.join(BASE, "meshes", "mpfb_v3_body.glb")
OUT_RENDER = os.path.join(BASE, "meshes", "mpfb_v3_render.png")
SKIN_DIR = os.path.join(BASE, "apps", "uploads", "skin", "freepbr", "human-skin1-bl")

scene = bpy.context.scene
for obj in list(scene.objects):
    if obj.type == 'MESH':
        bpy.data.objects.remove(obj, do_unlink=True)

# Create human
from bl_ext.user_default.mpfb.services.targetservice import TargetService
bpy.ops.mpfb.create_human()

body = None
for obj in bpy.data.objects:
    if obj.type == 'MESH':
        body = obj
        break
if not body:
    sys.exit("[ERROR] No body")

print(f"[BODY] {body.name}: {len(body.data.vertices)} verts")

# ── Set shape keys directly (v1 approach — proven male) ───────
if body.data.shape_keys:
    keys = body.data.shape_keys.key_blocks
    print(f"\n[SHAPE] {len(keys)} keys, setting male + athletic...")
    for key in keys:
        n = key.name
        # Male ethnic keys to 1.0
        if '$ma' in n and '$fe' not in n and 'universal' not in n:
            key.value = 1.0
            print(f"  MALE: {n} = 1.0")
        # Female ethnic keys to 0.0
        elif '$fe' in n and '$ma' not in n and 'universal' not in n:
            key.value = 0.0
            print(f"  FEM OFF: {n} = 0.0")
        # Universal male to 1.0
        elif 'universal' in n and '$ma' in n:
            key.value = 1.0
            print(f"  UNI MALE: {n} = 1.0")
        # Universal female to 0.0
        elif 'universal' in n and '$fe' in n:
            key.value = 0.0
            print(f"  UNI FEM OFF: {n} = 0.0")
        # Cup keys to 0
        elif 'cup' in n.lower():
            key.value = 0.0
            print(f"  CUP OFF: {n} = 0.0")

# ── Bake using TargetService (v2 approach — clean output) ─────
print("\n[BAKE] Using TargetService.bake_targets()...")
try:
    TargetService.bake_targets(body)
    print("  bake_targets OK")
except Exception as e:
    print(f"  bake_targets failed: {e}, using fallback...")
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

bpy.context.view_layer.update()
body.name = "MPFBv3Male"
print(f"[BODY] {len(body.data.vertices)} verts, dims={tuple(round(d,2) for d in body.dimensions)}")

# ── Scale + Orient + Center ───────────────────────────────────
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

verts_world = [body.matrix_world @ v.co for v in body.data.vertices]
min_z = min(v.z for v in verts_world)
max_z = max(v.z for v in verts_world)
body.location.x -= sum(v.x for v in verts_world) / len(verts_world)
body.location.y -= sum(v.y for v in verts_world) / len(verts_world)
body.location.z -= min_z
bpy.context.view_layer.update()
height = max_z - min_z
print(f"[POS] Height: {height:.2f}m")

# Aim empty
aim = bpy.data.objects.new("Aim", None)
bpy.context.collection.objects.link(aim)
aim.location = (0, 0, height * 0.45)

# ── Skin Material (full PBR) ─────────────────────────────────
mat = bpy.data.materials.new("MaleSkinV3")
mat.use_nodes = True
tree = mat.node_tree
N = tree.nodes; L = tree.links; N.clear()

out_n = N.new('ShaderNodeOutputMaterial'); out_n.location = (600, 0)
bsdf = N.new('ShaderNodeBsdfPrincipled'); bsdf.location = (200, 0)
L.new(bsdf.outputs[0], out_n.inputs[0])
bsdf.inputs['Base Color'].default_value = (0.75, 0.58, 0.48, 1)
bsdf.inputs['Roughness'].default_value = 0.45
bsdf.inputs['Subsurface Weight'].default_value = 0.3
bsdf.inputs['Subsurface Radius'].default_value = (0.8, 0.3, 0.15)
bsdf.inputs['Subsurface Scale'].default_value = 0.01

uvm = N.new('ShaderNodeMapping'); uvm.inputs['Scale'].default_value = (3, 5, 1)
uvi = N.new('ShaderNodeTexCoord')
L.new(uvi.outputs['UV'], uvm.inputs['Vector'])

def ltx(fn, cs='sRGB'):
    p = os.path.join(SKIN_DIR, fn)
    if not os.path.exists(p): return None
    img = bpy.data.images.load(p); img.colorspace_settings.name = cs
    t = N.new('ShaderNodeTexImage'); t.image = img
    L.new(uvm.outputs[0], t.inputs['Vector'])
    return t

ta = ltx("human-skin1_albedo.png")
tn = ltx("human-skin1_normal-ogl.png", 'Non-Color')
tr = ltx("human-skin1_roughness.png", 'Non-Color')
tao = ltx("human-skin1_ao.png", 'Non-Color')
th = ltx("human-skin1_height.png", 'Non-Color')

if tn:
    nm = N.new('ShaderNodeNormalMap')
    L.new(tn.outputs[0], nm.inputs['Color']); L.new(nm.outputs[0], bsdf.inputs['Normal'])
if tr:
    L.new(tr.outputs[0], bsdf.inputs['Roughness'])
if tao and ta:
    mx = N.new('ShaderNodeMixRGB'); mx.blend_type = 'MULTIPLY'; mx.inputs['Fac'].default_value = 0.8
    L.new(ta.outputs[0], mx.inputs['Color1']); L.new(tao.outputs[0], mx.inputs['Color2'])
    L.new(mx.outputs[0], bsdf.inputs['Base Color'])
elif ta:
    L.new(ta.outputs[0], bsdf.inputs['Base Color'])
if th:
    d = N.new('ShaderNodeDisplacement'); d.inputs['Scale'].default_value = 0.002
    L.new(th.outputs[0], d.inputs['Height']); L.new(d.outputs[0], out_n.inputs['Displacement'])

body.data.materials.clear()
body.data.materials.append(mat)

# ── Lighting + Floor + World ──────────────────────────────────
for o in list(scene.objects):
    if o.type == 'LIGHT': bpy.data.objects.remove(o, do_unlink=True)

def al(name, loc, rot, col, pwr, sz=2):
    d = bpy.data.lights.new(name, 'AREA'); d.energy = pwr; d.color = col; d.size = sz
    o = bpy.data.objects.new(name, d); bpy.context.collection.objects.link(o)
    o.location = loc; o.rotation_euler = tuple(math.radians(r) for r in rot)

al('Key', (2,-2,2.5), (-30,15,-45), (1,.96,.92), 1500, 2)
al('Fill', (-2,-1,1.5), (-20,-15,30), (.85,.9,1), 600, 3)
al('Rim', (0,3,1.5), (15,0,180), (1,.93,.85), 800, 1.5)
al('Bnc', (0,0,-0.3), (90,0,0), (.9,.85,.8), 200, 4)

bpy.ops.mesh.primitive_plane_add(size=20, location=(0,0,0))
fl = bpy.context.active_object
fm = bpy.data.materials.new("Floor"); fm.use_nodes = True
fm.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (.12,.12,.14,1)
fm.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = 0.8
fl.data.materials.append(fm)

bg = bpy.data.worlds['World'].node_tree.nodes['Background']
bg.inputs[0].default_value = (.18,.18,.22,1); bg.inputs[1].default_value = 0.3

# ── Camera ────────────────────────────────────────────────────
cam = scene.camera
cam.data.lens = 50; cam.data.dof.use_dof = True
cam.data.dof.focus_distance = 5.0; cam.data.dof.aperture_fstop = 5.6
cam.location = (0.6, -5.0, height * 0.45)
c = cam.constraints.new(type='TRACK_TO')
c.target = aim; c.track_axis = 'TRACK_NEGATIVE_Z'; c.up_axis = 'UP_Y'
bpy.context.view_layer.update()
bpy.ops.object.select_all(action='DESELECT')
cam.select_set(True); bpy.context.view_layer.objects.active = cam
bpy.ops.constraint.apply(constraint=c.name)

# ── Render + Export ───────────────────────────────────────────
scene.render.engine = 'CYCLES'
scene.render.resolution_x = 2048; scene.render.resolution_y = 2048
scene.cycles.samples = 256; scene.cycles.use_denoising = True
scene.cycles.denoiser = 'OPENIMAGEDENOISE'
try:
    p = bpy.context.preferences.addons['cycles'].preferences
    p.compute_device_type = 'CUDA'; p.get_devices(); scene.cycles.device = 'GPU'
except: pass

bpy.ops.object.select_all(action='DESELECT')
body.select_set(True); bpy.context.view_layer.objects.active = body
bpy.ops.export_scene.gltf(filepath=OUT_GLB, use_selection=True, export_format='GLB',
    export_apply=True, export_materials='EXPORT', export_normals=True, export_tangents=True)
print(f"[EXPORT] {OUT_GLB}")

scene.render.filepath = OUT_RENDER
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_depth = '16'
print("[RENDER] Cycles 256 @ 2048...")
bpy.ops.render.render(write_still=True)
print(f"[DONE] {OUT_RENDER}")
