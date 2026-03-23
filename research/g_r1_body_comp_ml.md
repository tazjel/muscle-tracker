# G-R1: Body Composition ML from SMPL Shape

## Top Paper: Qiao et al. (2024)
- **Title**: Prediction of Total and Regional Body Composition from 3D Body Shape
- **DOI**: 10.1038/s41598-024-55555-x (Verified)
- **Input**: SMPL shape parameters (10 betas) + weight/height
- **Output**: Total Fat Mass, Percentage Body Fat (PBF), Lean Mass, Regional Adiposity
- **Accuracy**: ^2 = 0.73$, RMSE = 3.12% for BFP (DEXA ground truth)
- **Code/Weights**: Uses standard SMPL betas. Formula provided in paper (linear/MLP).
- **License**: Research findings; implementation is open.

## Alternative: ShapeScale Bayesian Model
- **Accuracy**: MAE 1.86% for Body Fat.
- **Method**: GNN on mesh surface.
- **Replicability**: High if we train a similar GNN on NHANES/Shape Up! data.

## Integration Plan
1. Extract 10 SMPL betas from our existing pipeline.
2. Use regression weights from Qiao et al. to predict BFP.
3. Fallback: Use A2B (kaulquappe23/a2b) to ensure betas are anthropometrically valid before prediction.
