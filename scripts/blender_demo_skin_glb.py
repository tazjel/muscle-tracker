"""Create demo GLB with painted skin texture (no baking needed).
Generates a skin-colored texture image, assigns to UV-mapped MPFB2 mesh, exports GLB.
"""
import bpy
import os
import numpy as np

BASE = r"C:\Users\MiEXCITE\Projects\gtd3d"
TEMPLATE_GLB = os.path.join(BASE, "meshes", "gtd3d_body_template.glb")
OUT_GLB = os.path.join(BASE, "meshes", "demo_pbr.glb")
TEX_SIZE = 2048

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
bpy.ops.object.select_all(action='DESELECT')
body.select_set(True)
bpy.context.view_layer.objects.active = body

# ── Generate skin texture image via numpy ──
# Warm skin base with subtle noise for realism
rng = np.random.RandomState(42)
# Base skin RGB (warm olive/brown)
base_r, base_g, base_b = 0.69, 0.50, 0.39

# Create texture with per-pixel noise for skin pore effect
pixels = np.ones((TEX_SIZE, TEX_SIZE, 4), dtype=np.float32)

def box_blur(arr, radius):
    """Simple cumulative sum box blur (no scipy needed)."""
    from numpy import cumsum
    r = int(radius)
    if r < 1:
        return arr
    # Pad and blur rows
    padded = np.pad(arr, r, mode='reflect')
    cs = cumsum(padded, axis=1)
    blurred = (cs[:, 2*r:] - cs[:, :padded.shape[1]-2*r]) / (2*r)
    # Blur columns
    cs2 = cumsum(blurred, axis=0)
    blurred = (cs2[2*r:, :] - cs2[:blurred.shape[0]-2*r, :]) / (2*r)
    return blurred[:TEX_SIZE, :TEX_SIZE]

# Large-scale color variation (body region shading)
large_noise = rng.randn(TEX_SIZE, TEX_SIZE).astype(np.float32)
large_noise = box_blur(large_noise, 80) * 0.06

# Medium pore-scale noise
med_noise = rng.randn(TEX_SIZE, TEX_SIZE).astype(np.float32)
med_noise = box_blur(med_noise, 3) * 0.03

# Fine detail noise
fine_noise = rng.randn(TEX_SIZE, TEX_SIZE).astype(np.float32) * 0.015

combined = large_noise + med_noise + fine_noise

pixels[:, :, 0] = np.clip(base_r + combined * 1.0, 0.3, 0.85)
pixels[:, :, 1] = np.clip(base_g + combined * 0.8, 0.2, 0.65)
pixels[:, :, 2] = np.clip(base_b + combined * 0.7, 0.15, 0.55)

# Slightly darker in certain UV regions (simulate shadows in creases)
# Darken top and bottom edges (head/feet UV areas)
gradient_v = np.linspace(0, 1, TEX_SIZE).reshape(-1, 1)
edge_dark = 0.03 * (np.exp(-8 * gradient_v) + np.exp(-8 * (1 - gradient_v)))
pixels[:, :, 0] -= edge_dark
pixels[:, :, 1] -= edge_dark
pixels[:, :, 2] -= edge_dark
pixels = np.clip(pixels, 0, 1)

# Create Blender image
skin_img = bpy.data.images.new('skin_albedo', TEX_SIZE, TEX_SIZE, alpha=True)
skin_img.pixels.foreach_set(pixels.ravel())
skin_img.pack()

# ── Generate normal map (subtle bump) ──
normal_pixels = np.ones((TEX_SIZE, TEX_SIZE, 4), dtype=np.float32)
bump = rng.randn(TEX_SIZE, TEX_SIZE).astype(np.float32)
bump = box_blur(bump, 2) * 0.15
# Compute normal from height map via Sobel-like
dy = np.roll(bump, -1, axis=0) - np.roll(bump, 1, axis=0)
dx = np.roll(bump, -1, axis=1) - np.roll(bump, 1, axis=1)
normal_pixels[:, :, 0] = (-dx * 0.5 + 0.5)  # R = X
normal_pixels[:, :, 1] = (-dy * 0.5 + 0.5)  # G = Y
normal_pixels[:, :, 2] = 1.0                  # B = Z (up)
# Normalize
norm = np.sqrt(normal_pixels[:,:,0]**2 + normal_pixels[:,:,1]**2 + normal_pixels[:,:,2]**2)
normal_pixels[:,:,0] /= norm
normal_pixels[:,:,1] /= norm
normal_pixels[:,:,2] /= norm
# Remap to 0-1
normal_pixels[:,:,0] = normal_pixels[:,:,0] * 0.5 + 0.5
normal_pixels[:,:,1] = normal_pixels[:,:,1] * 0.5 + 0.5
normal_pixels[:,:,2] = normal_pixels[:,:,2] * 0.5 + 0.5
normal_pixels = np.clip(normal_pixels, 0, 1)

normal_img = bpy.data.images.new('skin_normal', TEX_SIZE, TEX_SIZE, alpha=True)
normal_img.pixels.foreach_set(normal_pixels.ravel())
normal_img.colorspace_settings.name = 'Non-Color'
normal_img.pack()

# ── Create material with textures ──
mat = bpy.data.materials.new('SkinTextured')
mat.use_nodes = True
nodes = mat.node_tree.nodes
links = mat.node_tree.links
nodes.clear()

output = nodes.new('ShaderNodeOutputMaterial')
output.location = (400, 0)

bsdf = nodes.new('ShaderNodeBsdfPrincipled')
bsdf.location = (0, 0)
links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

# Albedo texture
albedo_node = nodes.new('ShaderNodeTexImage')
albedo_node.location = (-400, 200)
albedo_node.image = skin_img
links.new(albedo_node.outputs['Color'], bsdf.inputs['Base Color'])

# Normal map
normal_tex = nodes.new('ShaderNodeTexImage')
normal_tex.location = (-400, -200)
normal_tex.image = normal_img
normal_map = nodes.new('ShaderNodeNormalMap')
normal_map.location = (-100, -200)
normal_map.inputs['Strength'].default_value = 0.5
links.new(normal_tex.outputs['Color'], normal_map.inputs['Color'])
links.new(normal_map.outputs['Normal'], bsdf.inputs['Normal'])

# Roughness
bsdf.inputs['Roughness'].default_value = 0.45

# SSS (won't export to GLB but looks good in Blender preview)
bsdf.inputs['Subsurface Weight'].default_value = 0.2

body.data.materials.clear()
body.data.materials.append(mat)

# ── Export ──
bpy.ops.export_scene.gltf(
    filepath=OUT_GLB,
    export_format='GLB',
    export_image_format='AUTO',
    export_materials='EXPORT',
    export_cameras=False,
    export_lights=False,
)

fsize = os.path.getsize(OUT_GLB)
print(f"SAVED: {OUT_GLB} ({fsize / 1024 / 1024:.1f} MB)")
