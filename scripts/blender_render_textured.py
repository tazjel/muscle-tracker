"""Render the demo_pbr.glb with Cycles from 3 angles.
Output: captures/skin_front.png, captures/skin_side.png, captures/skin_back.png
"""
import bpy
import math
import mathutils
import os

BASE = r"C:\Users\MiEXCITE\Projects\gtd3d"
GLB = os.path.join(BASE, "meshes", "demo_pbr.glb")
OUT_DIR = os.path.join(BASE, "captures")

# ── Clean ──
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)

# ── Import ──
bpy.ops.import_scene.gltf(filepath=GLB)
body = None
for obj in bpy.data.objects:
    if obj.type == 'MESH':
        if body is None or len(obj.data.vertices) > len(body.data.vertices):
            body = obj
print(f"Body: {body.name}, {len(body.data.vertices)} verts")

# Center
bpy.ops.object.select_all(action='DESELECT')
body.select_set(True)
bpy.context.view_layer.objects.active = body
bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
body.location = (0, 0, 0)

# ── HDRI environment ──
hdri = os.path.join(BASE, "assets", "polyhaven", "hdris", "studio_small_09_2k.hdr")
world = bpy.data.worlds.new('StudioWorld')
bpy.context.scene.world = world
world.use_nodes = True
wnodes = world.node_tree.nodes
wlinks = world.node_tree.links
wnodes.clear()
bg = wnodes.new('ShaderNodeBackground')
bg.inputs['Strength'].default_value = 0.5
env = wnodes.new('ShaderNodeTexEnvironment')
env.image = bpy.data.images.load(hdri)
wo = wnodes.new('ShaderNodeOutputWorld')
wlinks.new(env.outputs['Color'], bg.inputs['Color'])
wlinks.new(bg.outputs['Background'], wo.inputs['Surface'])

# ── 3-point lighting ──
def add_light(name, energy, loc):
    data = bpy.data.lights.new(name, 'AREA')
    data.energy = energy
    data.size = 2.0
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = loc
    direction = mathutils.Vector((0, 0, 0.8)) - mathutils.Vector(loc)
    obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()

add_light('Key', 250, (1.5, -2.0, 2.0))
add_light('Fill', 80, (-2.0, -1.5, 1.0))
add_light('Rim', 150, (0.0, 2.0, 1.5))

# ── Camera ──
cam_data = bpy.data.cameras.new('Camera')
cam_obj = bpy.data.objects.new('Camera', cam_data)
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
scene.render.film_transparent = False
# Dark studio background
bg.inputs['Strength'].default_value = 0.15

# ── Render 3 angles ──
angles = {
    'front': (0, -3.0, 0.85, 82),
    'side': (3.0, 0, 0.85, 82),
    'back': (0, 3.0, 0.85, 82),
}

for name, (x, y, z, tilt) in angles.items():
    cam_obj.location = (x, y, z)
    # Look at body center
    direction = mathutils.Vector((0, 0, 0.8)) - mathutils.Vector((x, y, z))
    cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()

    out_path = os.path.join(OUT_DIR, f"skin_{name}.png")
    scene.render.filepath = out_path
    bpy.ops.render.render(write_still=True)
    print(f"SAVED: {out_path}")
