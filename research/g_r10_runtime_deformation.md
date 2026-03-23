# G-R10: Runtime Body Deformation Without Blender

### 1. Shape Key Replication (NumPy)
MPFB2 .target files are sparse vertex deltas. They can be applied in pure Python:
```python
# new_verts = base_verts + (deltas * intensity)
deformed_verts[indices] += target_deltas * factor
```

### 2. Local Body Part Scaling
To match circumferences (biceps, thighs):
1. **Radial Scaling:** Define a bone axis for the vertex group. Move vertices away from the axis radially.
2. **Soft Weights:** Import the full (N, 15) vertex group weight matrix from Blender to ensure smooth falloff at boundaries.

### 3. Smoothing & Blending
- **Trimesh Laplacian:** Use `trimesh.smoothing.filter_laplacian(mesh, iterations=5)` after local scaling to remove pressure artifacts.
- **Libigl:** Alternative for high-precision Bi-harmonic deformation if simple scaling looks unnatural.

### 4. Verdict
Pure Python deformation is highly feasible using NumPy + Trimesh. The compound body shape is a linear sum of target del`tas.