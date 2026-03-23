"""Create clean skin-textured GLB using Object coordinates (seamless).
No UV-dependent noise = no seam artifacts.
"""
import bpy
import math
import mathutils
import os

BASE = r"C:\Users\MiEXCITE\Projects\gtd3d"
TEMPLATE_GLB = os.path.join(BASE, "meshes", "gtd3d_body_template.glb")
OUT_GLB = os.path.join(BASE, "meshes", "demo_pbr.glb")
HDRI = os.path.join(BASE, "assets", "polyhaven", "hdris", "studio_small_09_2k.hdr")

# ── Clean scene ──
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)

# ── Import template ──
bpy.ops.import_scene.gltf(filepath=TEMPLATE_GLB)
body = None
for obj in bpy.data.objects:
    if obj.type == 'MESH':
        if body is None or len(obj.data.vertices) > len(body.data.vertices):
            body = obj
print(f"Body: {body.name}, {len(body.data.vertices)} verts")

# ── Strip non-body objects (helpers, armatures, empties) to preserve vertex count ──
for obj in list(bpy.data.objects):
    if obj != body:
        bpy.data.objects.remove(obj, do_unlink=True)

# ── Clear custom split normals to prevent vertex splitting on export ──
bpy.context.view_layer.objects.active = body
body.select_set(True)
if body.data.has_custom_normals:
    bpy.ops.mesh.customdata_custom_splitnormals_clear()
# Smooth all edges to prevent edge-split vertex duplication in glTF export
for edge in body.data.edges:
    edge.use_edge_sharp = False
for poly in body.data.polygons:
    poly.use_smooth = True
print(f"Body after cleanup: {len(body.data.vertices)} verts (target: 13380)")

bpy.ops.object.select_all(action='DESELECT')
body.select_set(True)
bpy.context.view_layer.objects.active = body
bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
body.location = (0, 0, 0)

# ── Material: skin with Object-space noise (seamless across UV seams) ──
mat = bpy.data.materials.new('CleanSkin')
mat.use_nodes = True
nodes = mat.node_tree.nodes
links = mat.node_tree.links
nodes.clear()

output = nodes.new('ShaderNodeOutputMaterial')
output.location = (600, 0)
bsdf = nodes.new('ShaderNodeBsdfPrincipled')
bsdf.location = (300, 0)
links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

# Object coordinate input (seamless — no UV seam issues)
texcoord = nodes.new('ShaderNodeTexCoord')
texcoord.location = (-900, 0)

# Mix two skin tones with very subtle object-space noise
mix = nodes.new('ShaderNodeMix')
mix.data_type = 'RGBA'
mix.location = (0, 200)
# Warm medium skin
mix.inputs[6].default_value = (0.62, 0.42, 0.32, 1.0)
# Slightly darker for variation
mix.inputs[7].default_value = (0.50, 0.33, 0.24, 1.0)
links.new(mix.outputs[2], bsdf.inputs['Base Color'])

# Very subtle large-scale noise in object space
noise1 = nodes.new('ShaderNodeTexNoise')
noise1.location = (-500, 200)
noise1.inputs['Scale'].default_value = 5.0   # Large scale = smooth variation
noise1.inputs['Detail'].default_value = 3.0
noise1.inputs['Roughness'].default_value = 0.4
links.new(texcoord.outputs['Object'], noise1.inputs['Vector'])

# Clamp noise to very subtle range
ramp = nodes.new('ShaderNodeMapRange')
ramp.location = (-200, 200)
ramp.inputs['From Min'].default_value = 0.3
ramp.inputs['From Max'].default_value = 0.7
ramp.inputs['To Min'].default_value = 0.0
ramp.inputs['To Max'].default_value = 0.12
ramp.clamp = True
links.new(noise1.outputs['Fac'], ramp.inputs['Value'])
links.new(ramp.outputs['Result'], mix.inputs['Factor'])

# Roughness: slight variation in object space
bsdf.inputs['Roughness'].default_value = 0.45
rough_noise = nodes.new('ShaderNodeTexNoise')
rough_noise.location = (-500, -100)
rough_noise.inputs['Scale'].default_value = 30.0
rough_noise.inputs['Detail'].default_value = 4.0
links.new(texcoord.outputs['Object'], rough_noise.inputs['Vector'])

rough_ramp = nodes.new('ShaderNodeMapRange')
rough_ramp.location = (-200, -100)
rough_ramp.inputs['From Min'].default_value = 0.3
rough_ramp.inputs['From Max'].default_value = 0.7
rough_ramp.inputs['To Min'].default_value = 0.38
rough_ramp.inputs['To Max'].default_value = 0.52
links.new(rough_noise.outputs['Fac'], rough_ramp.inputs['Value'])
links.new(rough_ramp.outputs['Result'], bsdf.inputs['Roughness'])

# Bump (fine pore detail, object space) — two layers for realistic skin
bump = nodes.new('ShaderNodeBump')
bump.location = (100, -300)
bump.inputs['Strength'].default_value = 0.15
bump.inputs['Distance'].default_value = 0.001

# Layer 1: medium pore texture (scale 150)
pore_noise = nodes.new('ShaderNodeTexNoise')
pore_noise.location = (-500, -350)
pore_noise.inputs['Scale'].default_value = 150.0
pore_noise.inputs['Detail'].default_value = 8.0
pore_noise.inputs['Roughness'].default_value = 0.8
links.new(texcoord.outputs['Object'], pore_noise.inputs['Vector'])

# Layer 2: micro-pore detail (Musgrave at scale 400 for fine skin texture)
micro_noise = nodes.new('ShaderNodeTexMusgrave')
micro_noise.location = (-500, -550)
micro_noise.musgrave_type = 'FBM'
micro_noise.inputs['Scale'].default_value = 400.0
micro_noise.inputs['Detail'].default_value = 12.0
micro_noise.inputs['Dimension'].default_value = 1.5
micro_noise.inputs['Lacunarity'].default_value = 2.0
links.new(texcoord.outputs['Object'], micro_noise.inputs['Vector'])

# Mix both layers: 70% medium pore + 30% micro detail
pore_mix = nodes.new('ShaderNodeMath')
pore_mix.operation = 'ADD'
pore_mix.location = (-200, -400)
pore_mix.inputs[0].default_value = 0.0  # will be overridden by link
# Scale micro layer contribution
micro_scale = nodes.new('ShaderNodeMath')
micro_scale.operation = 'MULTIPLY'
micro_scale.location = (-350, -550)
micro_scale.inputs[1].default_value = 0.3
links.new(micro_noise.outputs['Fac'], micro_scale.inputs[0])

# Medium layer contribution
med_scale = nodes.new('ShaderNodeMath')
med_scale.operation = 'MULTIPLY'
med_scale.location = (-350, -350)
med_scale.inputs[1].default_value = 0.7
links.new(pore_noise.outputs['Fac'], med_scale.inputs[0])

links.new(med_scale.outputs['Value'], pore_mix.inputs[0])
links.new(micro_scale.outputs['Value'], pore_mix.inputs[1])

links.new(pore_mix.outputs['Value'], bump.inputs['Height'])
links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])

# SSS for skin translucency (low to preserve color in bake)
bsdf.inputs['Subsurface Weight'].default_value = 0.15
bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.4, 0.25)
bsdf.inputs['Subsurface Scale'].default_value = 0.01

body.data.materials.clear()
body.data.materials.append(mat)

# ── HDRI ──
world = bpy.data.worlds.new('Studio')
bpy.context.scene.world = world
world.use_nodes = True
wnodes = world.node_tree.nodes
wlinks = world.node_tree.links
wnodes.clear()
bg = wnodes.new('ShaderNodeBackground')
bg.inputs['Strength'].default_value = 0.2
env_tex = wnodes.new('ShaderNodeTexEnvironment')
env_tex.image = bpy.data.images.load(HDRI)
wo = wnodes.new('ShaderNodeOutputWorld')
wlinks.new(env_tex.outputs['Color'], bg.inputs['Color'])
wlinks.new(bg.outputs['Background'], wo.inputs['Surface'])

# ── 3-point lighting ──
def add_light(name, energy, loc):
    data = bpy.data.lights.new(name, 'AREA')
    data.energy = energy
    data.size = 2.0
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = loc
    d = mathutils.Vector((0, 0, 0.8)) - mathutils.Vector(loc)
    obj.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()

add_light('Key', 250, (1.5, -2.0, 2.0))
add_light('Fill', 80, (-2.0, -1.5, 1.0))
add_light('Rim', 150, (0.0, 2.0, 1.5))

# ── Camera ──
cam_data = bpy.data.cameras.new('Cam')
cam_obj = bpy.data.objects.new('Cam', cam_data)
bpy.context.scene.collection.objects.link(cam_obj)
bpy.context.scene.camera = cam_obj
cam_data.lens = 85

# ── Render settings ──
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 128
scene.render.resolution_x = 768
scene.render.resolution_y = 1024

# ── Bake textures for GLB export (object-space → UV-space) ──
print("Baking albedo...")
TEX = 2048
albedo_img = bpy.data.images.new('bake_albedo', TEX, TEX)
rough_img = bpy.data.images.new('bake_rough', TEX, TEX)
normal_img = bpy.data.images.new('bake_normal', TEX, TEX)

def bake_to_image(bake_type, image, pass_filter=None):
    # Add temp image node as active
    img_node = nodes.new('ShaderNodeTexImage')
    img_node.image = image
    img_node.location = (800, 0)
    for n in nodes:
        n.select = False
    img_node.select = True
    nodes.active = img_node

    scene.render.bake.use_pass_direct = False
    scene.render.bake.use_pass_indirect = False
    scene.render.bake.use_pass_color = True
    scene.cycles.samples = 16  # lower for bake

    bpy.ops.object.bake(type=bake_type)
    image.pack()
    nodes.remove(img_node)

bake_to_image('DIFFUSE', albedo_img)
print("Baking roughness...")
bake_to_image('ROUGHNESS', rough_img)
print("Baking normal...")
bpy.ops.object.bake(type='NORMAL')  # will fail without active img node
# Add temp node for normal bake
img_node = nodes.new('ShaderNodeTexImage')
img_node.image = normal_img
for n in nodes:
    n.select = False
img_node.select = True
nodes.active = img_node
bpy.ops.object.bake(type='NORMAL')
normal_img.pack()
normal_img.colorspace_settings.name = 'Non-Color'
nodes.remove(img_node)

# ── Replace procedural with baked for GLB export ──
nodes.clear()
out2 = nodes.new('ShaderNodeOutputMaterial')
out2.location = (400, 0)
bsdf2 = nodes.new('ShaderNodeBsdfPrincipled')
bsdf2.location = (0, 0)
links.new(bsdf2.outputs['BSDF'], out2.inputs['Surface'])

alb = nodes.new('ShaderNodeTexImage')
alb.image = albedo_img
alb.location = (-400, 200)
links.new(alb.outputs['Color'], bsdf2.inputs['Base Color'])

nrm = nodes.new('ShaderNodeTexImage')
nrm.image = normal_img
nrm.location = (-400, -200)
nm = nodes.new('ShaderNodeNormalMap')
nm.location = (-100, -200)
nm.inputs['Strength'].default_value = 0.5
links.new(nrm.outputs['Color'], nm.inputs['Color'])
links.new(nm.outputs['Normal'], bsdf2.inputs['Normal'])

rgh = nodes.new('ShaderNodeTexImage')
rgh.image = rough_img
rgh.image.colorspace_settings.name = 'Non-Color'
rgh.location = (-400, -500)
links.new(rgh.outputs['Color'], bsdf2.inputs['Roughness'])

bsdf2.inputs['Subsurface Weight'].default_value = 0.2

# ── Export GLB (preserve vertex count — no edge splitting) ──
bpy.ops.export_scene.gltf(
    filepath=OUT_GLB,
    export_format='GLB',
    export_image_format='AUTO',
    export_materials='EXPORT',
    export_cameras=False,
    export_lights=False,
    export_apply=True,       # Apply modifiers before export
)
vert_count = len(body.data.vertices)
print(f"GLB_SAVED: {OUT_GLB} ({os.path.getsize(OUT_GLB)/1024/1024:.1f} MB)")
print(f"VERTEX_COUNT: {vert_count}")
if vert_count != 13380:
    print(f"WARNING: Expected 13380 vertices but got {vert_count}. "
          f"Muscle segmentation highlighting may not work correctly.")

# Copy to viewer static directory
import shutil
viewer_glb = os.path.join(BASE, "web_app", "static", "viewer3d", "demo_pbr.glb")
shutil.copy2(OUT_GLB, viewer_glb)
print(f"Copied to: {viewer_glb}")

# ── Also render front/side/back for preview ──
# Restore procedural material for nicer renders
body.data.materials.clear()
body.data.materials.append(mat)
scene.cycles.samples = 128

angles = {
    'front': (0, -3.0, 0.85),
    'side': (3.0, 0, 0.85),
    'back': (0, 3.0, 0.85),
}
for name, (x, y, z) in angles.items():
    cam_obj.location = (x, y, z)
    d = mathutils.Vector((0, 0, 0.8)) - mathutils.Vector((x, y, z))
    cam_obj.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    out_path = os.path.join(BASE, "captures", f"skin_{name}.png")
    scene.render.filepath = out_path
    bpy.ops.render.render(write_still=True)
    print(f"RENDER_SAVED: {out_path}")
