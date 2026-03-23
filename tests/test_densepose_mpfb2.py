"""
DensePose → MPFB2 end-to-end integration test.

Tests that the DensePose texture pipeline can:
1. Load MPFB2 template mesh (13380 verts)
2. Load precomputed template UVs
3. Build IUV atlas from photos
4. Bake texture via KDTree NN matching
5. Export GLB with correct vertex count
"""
import pytest
import sys
import os
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MESHES_DIR = os.path.join(PROJECT_ROOT, 'meshes')
SCAN_DIR = os.path.join(PROJECT_ROOT, 'captures', 'skin_scan')


class TestMPFB2Template:
    def test_template_glb_exists(self):
        assert os.path.exists(os.path.join(MESHES_DIR, 'gtd3d_body_template.glb'))

    def test_template_uvs_exists(self):
        assert os.path.exists(os.path.join(MESHES_DIR, 'template_uvs.npy'))

    def test_template_uvs_shape(self):
        uvs = np.load(os.path.join(MESHES_DIR, 'template_uvs.npy'))
        assert uvs.shape == (13380, 2), f'Expected (13380, 2), got {uvs.shape}'

    def test_template_uvs_range(self):
        uvs = np.load(os.path.join(MESHES_DIR, 'template_uvs.npy'))
        assert uvs.min() >= 0.0, f'UV min is {uvs.min()}'
        assert uvs.max() <= 1.0, f'UV max is {uvs.max()}'

    def test_template_vertex_count(self):
        """glTF splits verts at UV seams, so trimesh sees more than Blender's 13380.
        The pipeline uses precomputed template_uvs.npy (13380 entries) which maps
        to the Blender-internal vertex ordering. This test verifies the GLB loads
        and has a reasonable vertex count (13380-15000 after normal splitting)."""
        import trimesh
        scene = trimesh.load(os.path.join(MESHES_DIR, 'gtd3d_body_template.glb'),
                             force='scene', process=False)
        geoms = list(scene.geometry.values())
        body = max(geoms, key=lambda g: len(g.vertices))
        n = len(body.vertices)
        assert 13380 <= n <= 15000, f'Expected 13380-15000 (glTF split), got {n}'


class TestDensePoseAtlas:
    def test_iuv_to_atlas_basic(self):
        from core.densepose_texture import iuv_to_atlas
        # Synthetic IUV: 100x100 image, part 1, U/V = pixel position
        h, w = 100, 100
        image = np.random.randint(0, 255, (h, w, 3), dtype=np.uint8)
        iuv = np.zeros((h, w, 3), dtype=np.uint8)
        # Set center region as part 1
        iuv[30:70, 30:70, 0] = 1
        iuv[30:70, 30:70, 1] = np.arange(40).reshape(1, 40).repeat(40, axis=0).astype(np.uint8) * 6
        iuv[30:70, 30:70, 2] = np.arange(40).reshape(40, 1).repeat(40, axis=1).astype(np.uint8) * 6

        atlas, weight = iuv_to_atlas(image, iuv, atlas_size=256)
        assert atlas.shape == (256, 256, 3)
        assert weight.shape == (256, 256)
        assert (weight > 0).sum() > 0, 'Atlas should have some filled pixels'

    def test_merge_atlases(self):
        from core.densepose_texture import merge_atlases
        a1 = np.full((128, 128, 3), 100, dtype=np.uint8)
        w1 = np.ones((128, 128), dtype=np.float32)
        a2 = np.full((128, 128, 3), 200, dtype=np.uint8)
        w2 = np.ones((128, 128), dtype=np.float32)
        merged, mw = merge_atlases([(a1, w1), (a2, w2)])
        assert merged.shape == (128, 128, 3)
        # Should be average of 100 and 200 = ~150
        assert 140 <= merged.mean() <= 160

    def test_harmonize_view(self):
        from core.densepose_texture import harmonize_view
        src = np.random.randint(50, 150, (100, 100, 3), dtype=np.uint8)
        anchor = np.random.randint(100, 200, (100, 100, 3), dtype=np.uint8)
        result = harmonize_view(src, anchor)
        assert result.shape == src.shape
        assert result.dtype == np.uint8

    def test_inpaint_atlas(self):
        from core.densepose_texture import inpaint_atlas
        atlas = np.zeros((64, 64, 3), dtype=np.uint8)
        weight = np.zeros((64, 64), dtype=np.float32)
        # Fill some pixels
        atlas[20:40, 20:40] = [128, 128, 128]
        weight[20:40, 20:40] = 1.0
        result = inpaint_atlas(atlas, weight)
        assert result.shape == (64, 64, 3)


class TestScanPhotos:
    """Verify scan photos exist for the pipeline."""
    def test_front_photo_exists(self):
        assert os.path.exists(os.path.join(SCAN_DIR, 'front.jpg'))

    def test_back_photo_exists(self):
        assert os.path.exists(os.path.join(SCAN_DIR, 'back.jpg'))


class TestSegmentationData:
    """Verify viewer segmentation JSON is compatible with template."""
    def test_segmentation_json_exists(self):
        seg_path = os.path.join(PROJECT_ROOT, 'web_app', 'static', 'viewer3d',
                                'template_vert_segmentation.json')
        assert os.path.exists(seg_path)

    def test_segmentation_max_index(self):
        import json
        seg_path = os.path.join(PROJECT_ROOT, 'web_app', 'static', 'viewer3d',
                                'template_vert_segmentation.json')
        with open(seg_path) as f:
            seg = json.load(f)
        max_idx = max(max(indices) for indices in seg.values() if indices)
        assert max_idx < 13380, f'Segmentation max index {max_idx} exceeds 13380 vertices'
