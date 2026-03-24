"""Bake PBR skin material into MPFB2 template GLB for demo viewing.
Output: meshes/demo_pbr.glb (GLB with embedded albedo + normal textures)
"""
import bpy
import math
import mathutils
import os
import numpy as np

BASE = r"C:\Users\MiEXCITE\Projects\gtd3d"
TEMPLATE_GLB = os.path.join(BASE, "meshes", "gtd3d_body_template.glb")
OUT_GLB = os.path.join(BASE, "meshes", "demo_pbr.glb")
TEX_SIZE = 2048

# ── Clean scene ──
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)

# ── Import template GLB ──
bpy.ops.import_scene.gltf(filepath=TEMPLATE_GLB)
body = None
for obj in bpy.data.objects:
    if obj.type == 'MESH':
        if body is None or len(obj.data.vertices) > len(body.data.vertices):
            body = obj

print(f"Body: {body.name}, {len(body.data.vertices)} verts")
bpy.ops.object.select_all(action='DESELECT')
body.select_set(True)
bpy.context.view_layer.objects.active = body

# ── Create skin material with procedural texture ──
mat = bpy.data.materials.new('SkinPBR')
mat.use_nodes = True
nodes = mat.node_tree.nodes
links = mat.node_tree.links
nodes.clear()

output = nodes.new('ShaderNodeOutputMaterial')
output.location = (600, 0)

bsdf = nodes.new('ShaderNodeBsdfPrincipled')
bsdf.location = (300, 0)
links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

# ── Albedo: warm skin with subtle variation ──
# Base skin color mixed with noise for pore-like variation
mix_rgb = nodes.new('ShaderNodeMix')
mix_rgb.data_type = 'RGBA'
mix_rgb.location = (-100, 200)
mix_rgb.inputs['Factor'].default_value = 0.08

# Warm skin base
mix_rgb.inputs[6].default_value = (0.68, 0.49, 0.38, 1.0)  # A (base skin)
# Slightly darker variation
mix_rgb.inputs[7].default_value = (0.55, 0.38, 0.28, 1.0)  # B (darker)

links.new(mix_rgb.outputs[2], bsdf.inputs['Base Color'])

# Noise for skin variation
noise = nodes.new('ShaderNodeTexNoise')
noise.location = (-400, 300)
noise.inputs['Scale'].default_value = 80.0
noise.inputs['Detail'].default_value = 8.0
noise.inputs['Roughness'].default_value = 0.7
links.new(noise.outputs['Fac'], mix_rgb.inputs['Factor'])

# ── SSS ──
bsdf.inputs['Subsurface Weight'].default_value = 0.25
bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.4, 0.25)
bsdf.inputs['Subsurface Scale'].default_value = 0.008

# ── Roughness with variation ──
rough_noise = nodes.new('ShaderNodeTexNoise')
rough_noise.location = (-400, -100)
rough_noise.inputs['Scale'].default_value = 120.0
rough_noise.inputs['Detail'].default_value = 6.0

rough_ramp = nodes.new('ShaderNodeMapRange')
rough_ramp.location = (-100, -100)
rough_ramp.inputs['From Min'].default_value = 0.0
rough_ramp.inputs['From Max'].default_value = 1.0
rough_ramp.inputs['To Min'].default_value = 0.35
rough_ramp.inputs['To Max'].default_value = 0.55
links.new(rough_noise.outputs['Fac'], rough_ramp.inputs['Value'])
links.new(rough_ramp.outputs['Result'], bsdf.inputs['Roughness'])

# ── Normal: subtle bump from noise ──
bump = nodes.new('ShaderNodeBump')
bump.location = (0, -300)
bump.inputs['Strength'].default_value = 0.15
bump.inputs['Distance'].default_value = 0.002

bump_noise = nodes.new('ShaderNodeTexNoise')
bump_noise.location = (-300, -300)
bump_noise.inputs['Scale'].default_value = 200.0
bump_noise.inputs['Detail'].default_value = 10.0
bump_noise.inputs['Roughness'].default_value = 0.8

links.new(bump_noise.outputs['Fac'], bump.inputs['Height'])
links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])

body.data.materials.clear()
body.data.materials.append(mat)

# ── Bake textures ──
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 32  # lower for bake speed

# Create bake images
albedo_img = bpy.data.images.new('bake_albedo', TEX_SIZE, TEX_SIZE)
normal_img = bpy.data.images.new('bake_normal', TEX_SIZE, TEX_SIZE)
rough_img = bpy.data.images.new('bake_roughness', TEX_SIZE, TEX_SIZE)

def bake_pass(bake_type, image, color_space='sRGB'):
    """Add image texture node, set active, bake, then remove."""
    img_node = nodes.new('ShaderNodeTexImage')
    img_node.image = image
    img_node.location = (800, 0)
    # Must be selected/active for bake target
    for n in nodes:
        n.select = False
    img_node.select = True
    nodes.active = img_node

    print(f"  Baking {bake_type}...")
    if bake_type == 'NORMAL':
        scene.cycles.bake_type = 'NORMAL'
        bpy.ops.object.bake(type='NORMAL')
    elif bake_type == 'ROUGHNESS':
        scene.cycles.bake_type = 'ROUGHNESS'
        bpy.ops.object.bake(type='ROUGHNESS')
    else:
        scene.cycles.bake_type = 'DIFFUSE'
        scene.render.bake.use_pass_direct = False
        scene.render.bake.use_pass_indirect = False
        scene.render.bake.use_pass_color = True
        bpy.ops.object.bake(type='DIFFUSE')

    image.colorspace_settings.name = color_space
    nodes.remove(img_node)

print("Baking textures...")
bake_pass('DIFFUSE', albedo_img, 'sRGB')
bake_pass('NORMAL', normal_img, 'Non-Color')
bake_pass('ROUGHNESS', rough_img, 'Non-Color')

# ── Replace procedural material with baked textures ──
nodes.clear()

output2 = nodes.new('ShaderNodeOutputMaterial')
output2.location = (400, 0)
bsdf2 = nodes.new('ShaderNodeBsdfPrincipled')
bsdf2.location = (0, 0)
links.new(bsdf2.outputs['BSDF'], output2.inputs['Surface'])

# Albedo
albedo_node = nodes.new('ShaderNodeTexImage')
albedo_node.location = (-400, 200)
albedo_node.image = albedo_img
links.new(albedo_node.outputs['Color'], bsdf2.inputs['Base Color'])

# Normal
normal_node = nodes.new('ShaderNodeTexImage')
normal_node.location = (-400, -100)
normal_node.image = normal_img
normal_node.image.colorspace_settings.name = 'Non-Color'
normal_map = nodes.new('ShaderNodeNormalMap')
normal_map.location = (-100, -100)
links.new(normal_node.outputs['Color'], normal_map.inputs['Color'])
links.new(normal_map.outputs['Normal'], bsdf2.inputs['Normal'])

# Roughness
rough_node = nodes.new('ShaderNodeTexImage')
rough_node.location = (-400, -400)
rough_node.image = rough_img
rough_node.image.colorspace_settings.name = 'Non-Color'
links.new(rough_node.outputs['Color'], bsdf2.inputs['Roughness'])

# SSS
bsdf2.inputs['Subsurface Weight'].default_value = 0.2
bsdf2.inputs['Subsurface Radius'].default_value = (1.0, 0.4, 0.25)
bsdf2.inputs['Subsurface Scale'].default_value = 0.008

# ── Export GLB with embedded textures ──
bpy.ops.export_scene.gltf(
    filepath=OUT_GLB,
    export_format='GLB',
    export_image_format='AUTO',
    export_materials='EXPORT',
    export_cameras=False,
    export_lights=False,
)

fsize = os.path.getsize(OUT_GLB)
print(f"SAVED: {OUT_GLB} ({fsize / 1024:.0f} KB)")
