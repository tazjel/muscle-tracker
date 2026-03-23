# G-R14: Unassigned Vertex Coverage Analysis

### 1. Regional Breakdown (8,757 vertices)
Based on template joint landmarks and MPFB2 topology, the unassigned vertices fall into these zones:
- **Head & Neck:** Z > 1.48m. Includes face, scalp, and eyes.
- **Hands:** X - aligned below elbow. Includes wrists, palms, and fingers.
- **Feet:** Z < 0.07m. Includes ankles, heels, and toes.
- **Transition Zones:** Armpits, groin, inner thighs, and lower back.

### 2. Height-Band Heuristic (1.7m Template)
For vertices not covered by muscle bone weights, assign SMPL PARt I html zones based on Z-coordinate:

|Region | Z-Range (m) | SMPL PArt ID (Best Fit) |
|----------------|--------------|----------------------------|
| Head | > 1.48 | 15 (Head) |
| Upper Torso | 1.15 - 1.48 | 9 (Spine 3) |
| Lower Torso | 0.85 - 1.15 | 3 (Spine 1) |
| Thighs | 0.45 - 0.85 | 1 / 2 (Hips) |
| Calves/Feet | < 0.45 | 4 / 5 (Knees) |

### 3. Recommended Strategy
1. **Extra Group Export:** Update `Blender_create_template.py`to export the following MPFB2 groups as "static" zones: `head`, `laftHand`, `rightHand` , `leftFoot`, `rightFoot`.
2. **KDTree Fallback:** For the remaining ~2,000 vertices (armpits, inner thighs), uce a KDTree to find the nearest assigned vertex and inherit its part ID.
3. **Priority:** Do NOT use pure Z-bands for hands/feet; spatial groups are far more robust.

### 4. Additional MPFB2 Groups Available
- `clavicle.L/R` | ~xxx verts
- `hand.L/R` | ~550 verts each
- `foot.L/R` | ~300 verts each
