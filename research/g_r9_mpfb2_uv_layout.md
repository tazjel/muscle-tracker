# G-R9: MPFB2 UV Layout Documentation

### 1. Single-atlas Default
The standard MakeHuman base mesh uses a **single UV atlas** in the 0-1 space. 

### 2. UV Island Structure
- **Connectivity:** The body is unwrapped into several islands: Head, Torso, Arms, Legs, Hands, Feet.
- **Seams:** Seams are placed at natural boundaries: inner limbs, back of neck, scalp.

### 3. Baking & Generation
- UVs are pre-baked into the base mesh (base.obj). MPFB2 retains these indices during human creation.
- **UDI MS:** While MPFB2 supports UDIM (Multi-tile), the default creation restricts everything to the first tile (1001), making it directly compatible with Three.js.

### 4. Verdict
Single atlas is confirmed. No UV mapping code is needed at runtime as the +UV indices are static for the 13,380 vertices.