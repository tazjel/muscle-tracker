#!/usr/bin/env python3
"""
render_body.py — CLI entry point for photorealistic body rendering.

Composes: uv_canonical → texture_factory → asset_cache → blender_renderer

Usage:
    # Quick draft render
    python scripts/render_body.py --mesh meshes/body_1.glb --room home --quality draft

    # Production 4-angle render
    python scripts/render_body.py --mesh meshes/body_1.glb --room gym --angles 4 --quality production

    # Just generate textures (no render)
    python scripts/render_body.py --mesh meshes/body_1.glb --textures-only

    # Full pipeline with custom output
    python scripts/render_body.py --mesh meshes/body_1.glb --room home --quality preview --output renders/
"""
import argparse
import os
import sys
import logging
import time

# Ensure project root is on path
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logger = logging.getLogger('render_body')


def parse_args():
    parser = argparse.ArgumentParser(
        description='Render photorealistic body mesh with Blender Cycles')

    parser.add_argument('--mesh', required=True,
                        help='Path to GLB/OBJ body mesh')
    parser.add_argument('--room', default='studio',
                        choices=['studio', 'home', 'gym', 'outdoor'],
                        help='Room environment (default: studio)')
    parser.add_argument('--quality', default='draft',
                        choices=['draft', 'preview', 'production', 'ultra'],
                        help='Render quality preset (default: draft)')
    parser.add_argument('--angles', type=int, default=1,
                        help='Number of camera angles (default: 1)')
    parser.add_argument('--angle-names', nargs='+',
                        help='Specific camera angle names (overrides --angles)')
    parser.add_argument('--output', '-o',
                        help='Output directory (default: auto)')
    parser.add_argument('--textures-only', action='store_true',
                        help='Generate PBR textures without rendering')
    parser.add_argument('--no-upscale', action='store_true',
                        help='Skip texture upscaling')
    parser.add_argument('--lens', type=int, default=85,
                        help='Camera focal length in mm (default: 85)')
    parser.add_argument('--dof', action='store_true',
                        help='Enable depth of field')
    parser.add_argument('--fstop', type=float, default=2.8,
                        help='Aperture for DOF (default: 2.8)')
    parser.add_argument('--open', action='store_true',
                        help='Open output directory when done')
    parser.add_argument('--serve', action='store_true',
                        help='Start HTTP server to preview renders in browser (port 9090)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Verbose logging')

    return parser.parse_args()


def generate_textures(mesh_path, upscale=True, output_dir=None):
    """
    Generate PBR texture set from a GLB mesh.

    Returns dict of texture file paths.
    """
    from core.texture_factory import generate_pbr_textures, save_pbr_textures

    # Try to extract textures from the GLB
    try:
        import pygltflib
        import numpy as np
        import cv2

        gltf = pygltflib.GLTF2().load(mesh_path)
        blob = gltf.binary_blob()

        # Extract vertices
        accessor = gltf.accessors[gltf.meshes[0].primitives[0].attributes.POSITION]
        bv = gltf.bufferViews[accessor.bufferView]
        verts_data = blob[bv.byteOffset: bv.byteOffset + bv.byteLength]
        import struct
        n_verts = accessor.count
        verts = np.array(struct.unpack(f'<{n_verts * 3}f', verts_data)).reshape(n_verts, 3).astype(np.float32)

        # Extract faces
        idx_acc = gltf.accessors[gltf.meshes[0].primitives[0].indices]
        idx_bv = gltf.bufferViews[idx_acc.bufferView]
        idx_data = blob[idx_bv.byteOffset: idx_bv.byteOffset + idx_bv.byteLength]
        if idx_acc.componentType == 5125:  # UNSIGNED_INT
            faces = np.array(struct.unpack(f'<{idx_acc.count}I', idx_data)).reshape(-1, 3).astype(np.uint32)
        else:  # UNSIGNED_SHORT
            faces = np.array(struct.unpack(f'<{idx_acc.count}H', idx_data)).reshape(-1, 3).astype(np.uint32)

        # Extract UVs
        uvs = None
        prim = gltf.meshes[0].primitives[0]
        if hasattr(prim.attributes, 'TEXCOORD_0') and prim.attributes.TEXCOORD_0 is not None:
            uv_acc = gltf.accessors[prim.attributes.TEXCOORD_0]
            uv_bv = gltf.bufferViews[uv_acc.bufferView]
            uv_data = blob[uv_bv.byteOffset: uv_bv.byteOffset + uv_bv.byteLength]
            uvs = np.array(struct.unpack(f'<{uv_acc.count * 2}f', uv_data)).reshape(-1, 2).astype(np.float32)

        # Extract existing albedo texture
        albedo = None
        normal_map = None
        if gltf.images:
            for i, img in enumerate(gltf.images):
                if img.bufferView is not None:
                    ibv = gltf.bufferViews[img.bufferView]
                    img_bytes = blob[ibv.byteOffset: ibv.byteOffset + ibv.byteLength]
                    arr = np.frombuffer(img_bytes, dtype=np.uint8)
                    decoded = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    if decoded is not None:
                        if i == 0:
                            albedo = decoded
                        elif i == 1:
                            normal_map = decoded

        if uvs is None:
            # Load canonical UVs
            from core.uv_canonical import get_canonical_uvs
            uvs = get_canonical_uvs()
            if uvs is None or len(uvs) != len(verts):
                from core.smpl_direct import cylindrical_uvs
                uvs = cylindrical_uvs(verts)

        if albedo is None:
            # Create a default skin-tone albedo
            atlas_size = 2048
            albedo = np.full((atlas_size, atlas_size, 3), [140, 160, 190], dtype=np.uint8)

        # Generate PBR set
        pbr = generate_pbr_textures(
            albedo, uvs, verts, faces,
            normal_map=normal_map,
            upscale=upscale,
            target_size=4096,
        )

        # Save
        if output_dir is None:
            output_dir = os.path.join(os.path.dirname(mesh_path), 'textures')
        prefix = os.path.splitext(os.path.basename(mesh_path))[0]
        paths = save_pbr_textures(pbr, output_dir, prefix=prefix)

        logger.info("PBR textures saved to %s", output_dir)
        return paths

    except Exception as e:
        logger.error("Texture generation failed: %s", e)
        import traceback
        traceback.print_exc()
        return {}


def main():
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s %(name)s %(levelname)s %(message)s',
        datefmt='%H:%M:%S',
    )

    mesh_path = os.path.abspath(args.mesh)
    if not os.path.exists(mesh_path):
        logger.error("Mesh not found: %s", mesh_path)
        sys.exit(1)

    output_dir = args.output
    if output_dir is None:
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        output_dir = os.path.join(_PROJECT_ROOT, 'renders', timestamp)

    output_dir = os.path.abspath(output_dir)

    # Step 1: Generate PBR textures
    logger.info("Generating PBR textures...")
    t0 = time.time()
    texture_paths = generate_textures(
        mesh_path,
        upscale=not args.no_upscale,
        output_dir=os.path.join(output_dir, 'textures'),
    )
    logger.info("Textures generated in %.1fs", time.time() - t0)

    if args.textures_only:
        logger.info("Textures saved to: %s", output_dir)
        if texture_paths:
            for name, path in texture_paths.items():
                logger.info("  %s: %s", name, path)
        if args.open:
            os.startfile(output_dir)
        return

    # Step 2: Render with Blender
    from core.blender_renderer import render_body, find_blender

    blender = find_blender()
    if blender is None:
        logger.error("Blender not found. Install Blender or add to PATH.")
        logger.info("Textures are still available in: %s", output_dir)
        sys.exit(1)

    angles = args.angle_names if args.angle_names else args.angles

    logger.info("Rendering with Blender Cycles (%s quality)...", args.quality)
    t0 = time.time()
    result = render_body(
        mesh_path,
        room=args.room,
        quality=args.quality,
        angles=angles,
        textures=texture_paths,
        output_dir=output_dir,
        lens_mm=args.lens,
        dof=args.dof,
        fstop=args.fstop,
    )
    elapsed = time.time() - t0

    if result['status'] == 'success':
        logger.info("Render complete in %.1fs", elapsed)
        for p in result['renders']:
            logger.info("  %s", p)
        if args.open and result['renders']:
            os.startfile(result['output_dir'])
        if args.serve and result['renders']:
            import http.server, functools
            handler = functools.partial(
                http.server.SimpleHTTPRequestHandler, directory=output_dir)
            server = http.server.HTTPServer(('localhost', 9090), handler)
            logger.info("Preview at http://localhost:9090/")
            for p in result['renders']:
                logger.info("  http://localhost:9090/%s", os.path.basename(p))
            server.serve_forever()
    else:
        logger.error("Render failed: %s", result.get('message', 'unknown error'))
        if result.get('stderr'):
            logger.error("Blender stderr:\n%s", result['stderr'][-500:])
        sys.exit(1)


if __name__ == '__main__':
    main()
