"""MPFB v3 High-Fidelity: Optimized for Cinematic Scan v5.5.
Uses stabilized phenotype targets and PBR textures.

Usage: blender --background --python scripts/blender_mpfb_v3.py
"""
import bpy, math, mathutils, bmesh, os, sys

BASE = r"C:\Users\MiEXCITE\Projects\gtd3d"
OUT_GLB = os.path.join(BASE, "meshes", "mpfb_v3_body.glb")
OUT_RENDER = os.path.join(BASE, "meshes", "mpfb_v3_render.png")
PBR_DIR = os.path.join(BASE, "apps", "uploads", "pbr_1_15")

scene = bpy.context.scene
for obj in list(scene.objects):
    if obj.type == 'MESH': bpy.data.objects.remove(obj, do_unlink=True)

# Create human
bpy.ops.mpfb.create_human()
body = next(obj for obj in bpy.data.objects if obj.type == 'MESH')

# ── Stabilized Phenotype ────────────────────────────────────
if body.data.shape_keys:
    keys = body.data.shape_keys.key_blocks
    for key in keys:
        n = key.name.lower()
        key.value = 0.0 # Start clean
        
        # Male Athletic Balance (avoid 1.0 extremes)
        if 'male' in n and 'universal' in n: key.value = 1.0
        if 'athletic' in n: key.value = 0.6
        if 'muscle' in n: key.value = 0.5
        if 'weight' in n: key.value = 0.2
        if 'height' in n: key.value = 0.5

# ── Stabilize Mesh ──────────────────────────────────────────
bpy.ops.object.select_all(action='DESELECT')
body.select_set(True); bpy.context.view_layer.objects.active = body
body.shape_key_add(name="StableMix", from_mix=True)
while len(body.data.shape_keys.key_blocks) > 1:
    body.active_shape_key_index = 0
    bpy.ops.object.shape_key_remove(all=False)
bpy.ops.object.shape_key_remove(all=True)

# Height Normalization
sf = 1.82 / max(body.dimensions)
body.scale = (sf, sf, sf)
bpy.ops.object.transform_apply(scale=True)
body.location.z -= min(v.co.z * sf for v in body.data.vertices)

# ── High-Fidelity PBR ───────────────────────────────────────
mat = bpy.data.materials.new("CinematicSkin")
mat.use_nodes = True
N = mat.node_tree.nodes; L = mat.node_tree.links; N.clear()
out = N.new('ShaderNodeOutputMaterial')
bsdf = N.new('ShaderNodeBsdfPrincipled'); bsdf.location = (-200, 0)
L.new(bsdf.outputs[0], out.inputs[0])

def ltx(fn, cs='sRGB'):
    p = os.path.join(PBR_DIR, fn)
    if not os.path.exists(p): return None
    img = bpy.data.images.load(p); img.colorspace_settings.name = cs
    t = N.new('ShaderNodeTexImage'); t.image = img
    return t

ta = ltx("body_albedo.png")
tn = ltx("body_normal.png", 'Non-Color')
tr = ltx("body_roughness.png", 'Non-Color')

if ta: L.new(ta.outputs[0], bsdf.inputs['Base Color'])
if tr: L.new(tr.outputs[0], bsdf.inputs['Roughness'])
if tn:
    nm = N.new('ShaderNodeNormalMap')
    L.new(tn.outputs[0], nm.inputs['Color']); L.new(nm.outputs[0], bsdf.inputs['Normal'])

body.data.materials.clear(); body.data.materials.append(mat)

# ── Cinematic Lighting ──────────────────────────────────────
for o in list(scene.objects):
    if o.type == 'LIGHT' or o.name == 'Plane': bpy.data.objects.remove(o, do_unlink=True)

def al(name, loc, rot, col, pwr, sz=3):
    d = bpy.data.lights.new(name, 'AREA'); d.energy = pwr; d.color = col; d.size = sz
    o = bpy.data.objects.new(name, d); bpy.context.collection.objects.link(o)
    o.location = loc; o.rotation_euler = [math.radians(r) for r in rot]

al('Key', (4,-4,4), (-35,20,-45), (1,1,1), 3000)
al('Fill', (-4,-2,2), (-20,-20,40), (.8,.9,1), 1000)
al('Rim', (0,5,3), (20,0,180), (1,.8,.6), 2000)

# ── Render ──────────────────────────────────────────────────
scene.render.engine = 'CYCLES'
scene.render.resolution_x = 1024; scene.render.resolution_y = 1024
scene.cycles.samples = 128
scene.camera.location = (0, -6.5, 0.9)
scene.camera.rotation_euler = (math.radians(90), 0, 0)
scene.render.filepath = OUT_RENDER
bpy.ops.render.render(write_still=True)

# Export
bpy.ops.export_scene.gltf(filepath=OUT_GLB, use_selection=True, export_format='GLB', export_apply=True)
print(f"[SUCCESS] v5.5 Scan Ready: {OUT_GLB}")
