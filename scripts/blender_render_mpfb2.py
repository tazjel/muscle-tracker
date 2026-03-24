"""Render MPFB2 template body with Cycles SSS skin material.
Output: captures/mpfb2_skin_render.png (1024x1024)
"""
import bpy
import math
import mathutils
import os

BASE = r"C:\Users\MiEXCITE\Projects\gtd3d"
GLB = os.path.join(BASE, "meshes", "gtd3d_body_template.glb")
OUT = os.path.join(BASE, "captures", "mpfb2_skin_render.png")

# ── Clean scene ──
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)

# ── Import GLB ──
bpy.ops.import_scene.gltf(filepath=GLB)
body = None
for obj in bpy.data.objects:
    if obj.type == 'MESH':
        if body is None or len(obj.data.vertices) > len(body.data.vertices):
            body = obj
print(f"Body: {body.name}, {len(body.data.vertices)} verts")

# ── Center body ──
bpy.ops.object.select_all(action='DESELECT')
body.select_set(True)
bpy.context.view_layer.objects.active = body
bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
body.location = (0, 0, 0)

# ── Skin material with SSS ──
mat = bpy.data.materials.new('SkinPBR')
mat.use_nodes = True
nodes = mat.node_tree.nodes
links = mat.node_tree.links
nodes.clear()

output = nodes.new('ShaderNodeOutputMaterial')
bsdf = nodes.new('ShaderNodeBsdfPrincipled')
bsdf.location = (-300, 0)
output.location = (200, 0)

# Warm skin tone
bsdf.inputs['Base Color'].default_value = (0.72, 0.52, 0.42, 1.0)
bsdf.inputs['Roughness'].default_value = 0.45
bsdf.inputs['Metallic'].default_value = 0.0
# SSS for skin translucency
bsdf.inputs['Subsurface Weight'].default_value = 0.3
bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.4, 0.25)
bsdf.inputs['Subsurface Scale'].default_value = 0.01

links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

body.data.materials.clear()
body.data.materials.append(mat)

# ── Camera ──
cam_data = bpy.data.cameras.new('Camera')
cam_obj = bpy.data.objects.new('Camera', cam_data)
bpy.context.scene.collection.objects.link(cam_obj)
bpy.context.scene.camera = cam_obj

cam_obj.location = (0, -2.8, 0.85)
cam_obj.rotation_euler = (math.radians(82), 0, 0)
cam_data.lens = 85

# ── Lighting: 3-point ──
def add_light(name, energy, loc, light_type='AREA'):
    data = bpy.data.lights.new(name, light_type)
    data.energy = energy
    if light_type == 'AREA':
        data.size = 2.0
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = loc
    # Point at origin
    direction = mathutils.Vector((0, 0, 0.8)) - mathutils.Vector(loc)
    obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    return obj

add_light('Key', 300, (1.5, -2.0, 2.0))
add_light('Fill', 100, (-2.0, -1.5, 1.0))
add_light('Rim', 200, (0.0, 2.0, 1.5))

# ── HDRI environment ──
hdri_path = os.path.join(BASE, "assets", "polyhaven", "hdris", "studio_small_09_2k.hdr")
if os.path.exists(hdri_path):
    world = bpy.data.worlds.new('SkinWorld')
    bpy.context.scene.world = world
    world.use_nodes = True
    wnodes = world.node_tree.nodes
    wlinks = world.node_tree.links
    wnodes.clear()
    bg = wnodes.new('ShaderNodeBackground')
    bg.inputs['Strength'].default_value = 0.3
    env = wnodes.new('ShaderNodeTexEnvironment')
    env.image = bpy.data.images.load(hdri_path)
    wo = wnodes.new('ShaderNodeOutputWorld')
    wlinks.new(env.outputs['Color'], bg.inputs['Color'])
    wlinks.new(bg.outputs['Background'], wo.inputs['Surface'])

# ── Render settings ──
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 128
scene.render.resolution_x = 1024
scene.render.resolution_y = 1024
scene.render.film_transparent = True
scene.render.filepath = OUT

# Dark background
if not bpy.context.scene.world:
    bpy.context.scene.world = bpy.data.worlds.new('Dark')
    bpy.context.scene.world.use_nodes = True

bpy.ops.render.render(write_still=True)
print(f"SAVED: {OUT}")
