# Task 23: A2B Regressor Training Guide — Phase 5

## Part 1: Verified Paper/Repo Reference
- **Verified Paper:** *"Leveraging Anthropometric Measurements to Improve Human Mesh Estimation"* — **arXiv:2412.14742** (December 2024).
- **Verified Repo:** [kaulquappe23/a2b_human_mesh](https://github.com/kaulquappe23/a2b_human_mesh)
- **Clarification:** The previous citation `arXiv:2412.03556` was a fabrication (referring to a jailbreaking paper); the correct A2B citation is `arXiv:2412.14742`.

## Part 2: Data Access Guide (ANSUR/CAESAR)

### **ANSUR-II (U.S. Army Anthropometric Survey)**
- **Access:** Available via the [DTIC (Defense Technical Information Center)](https://discover.dtic.mil/) or public mirrors on Kaggle/GitHub.
- **Format:** CSV (Male and Female datasets).
- **Size:** 6,068 subjects (4,082 male, 1,986 female).
- **Measurements:** 93 manual measurements (waist, hip, chest, stature, etc.) + 20 demographic fields.
- **License:** Public domain (U.S. Government data).
- **Type:** Tape measurements and 1D anthropometry; no 3D meshes included.

### **CAESAR (Civilian American and European Surface Anthropometry Resource)**
- **Access:** Requires purchase/license from the [SAE International](https://www.sae.org/standards/content/caesar/) or a DUA from the Air Force Research Lab (AFRL).
- **Format:** `.ply` / `.obj` 3D scans + `.csv` measurements.
- **Size:** ~4,400 individuals.
- **License:** Commercial/Academic restricted.
- **SMPL Registrations:** High-quality SMPL fittings for CAESAR are available in the **MPI Meshcapade** datasets.

## Part 3: Synthetic Data Generation Approach
Instead of restricted datasets, we can generate a **synthetic dataset** directly from our pipeline:
1. **Sample:** Draw 10,000 random samples from the SMPL shape space ($\beta \sim \mathcal{N}(0, 1)$).
2. **Mesh:** Run `build_smpl_mesh(betas)` for each sample.
3. **Measure:** Use `core/measurement_extraction.py` (Sonnet T7) to extract the 36 anthropometric measurements from each synthetic mesh.
4. **Train:** Train a 3-layer MLP to map `(measurements) → (betas)`.

**Analysis:**
- **Pros:** Zero license issues; perfectly paired ground truth; can be tuned to our specific landmark definitions.
- **Cons:** **Domain Gap.** Synthetic measurements may not perfectly match how a user (or HMR2.0) measures a real human body. The distribution of synthetic shapes might over-represent biologically impossible proportions.

## Part 4: Training Script (MLP Regressor)

```python
import torch
import torch.nn as nn
import torch.optim as optim

class A2BRegressor(nn.Module):
    def __init__(self, input_dim=36, output_dim=10):
        super(A2BRegressor, self).__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.ReLU(),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Linear(64, output_dim)
        )

    def forward(self, x):
        return self.net(x)

def train_model(data_loader, epochs=100):
    model = A2BRegressor()
    criterion = nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    
    for epoch in range(epochs):
        for measurements, target_betas in data_loader:
            optimizer.zero_grad()
            preds = model(measurements)
            loss = criterion(preds, target_betas)
            loss.backward()
            optimizer.step()
    return model
```

## Part 5: ONNX Export Guide
1. **Convert:** Use `torch.onnx.export` to save the trained model.
2. **Optimize:** Use `onnxruntime` to quantize the model to `int8` (reducing size to ~20KB).
3. **Frontend:** Load in Flutter/React via `onnxruntime-web`.
4. **Performance:** Expect **< 1ms** inference time on modern smartphones.

## Part 6: Validation Protocol
- **Split:** 80% train / 20% hold-out test set.
- **Metric A (Parameter Error):** Euclidean distance between predicted and true $\beta$ vectors.
- **Metric B (Reconstruction Error):** Compute vertex-to-vertex (V2V) error in mm between the mesh generated from predicted betas vs. ground truth betas.
- **Metric C (Circumference Error):** Verify that extracting measurements from the *predicted* mesh returns the *input* measurements within a tolerance of < 0.5 cm.
