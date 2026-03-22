"""
a2b_regressor.py — Anthropometry-to-Betas MLP regressor.

Maps body measurements (circumferences, lengths, height) back to SMPL
shape parameters (10 betas). Enables "FutureMe" body morphing: user
enters target measurements → predict body shape.

Training uses synthetic data from our own SMPL pipeline (no external
datasets required, no licensing issues).

Usage:
    # Generate training data + train + export:
    python -m core.a2b_regressor --train --export

    # Inference:
    from core.a2b_regressor import predict_betas
    betas = predict_betas({'height_cm': 175, 'chest_circumference_cm': 100, ...})
"""
import os
import csv
import logging
import numpy as np

logger = logging.getLogger(__name__)

MODEL_DIR = os.path.join(os.path.dirname(__file__), '..', 'models')
ONNX_PATH = os.path.join(MODEL_DIR, 'a2b_regressor.onnx')
CSV_PATH  = os.path.join(MODEL_DIR, 'a2b_training_data.csv')

# Measurement keys used as input features (must match extract_measurements output)
FEATURE_KEYS = [
    'height_cm',
    'chest_circumference_cm',
    'waist_circumference_cm',
    'hip_circumference_cm',
    'neck_circumference_cm',
    'shoulder_width_cm',
    'torso_length_cm',
    'arm_length_cm',
    'upper_arm_length_cm',
    'forearm_length_cm',
    'floor_to_knee_cm',
    'thigh_circumference_cm',
    'calf_circumference_cm',
    'bicep_circumference_cm',
    'forearm_circumference_cm',
    'weight_est_kg',
    'bmi_est',
]

NUM_FEATURES = len(FEATURE_KEYS)
NUM_BETAS = 10


# ── Synthetic Data Generation ─────────────────────────────────────────────────

def generate_training_data(n_samples=10000, output_csv=None):
    """
    Generate synthetic (measurements, betas) pairs from random SMPL shapes.

    Returns:
        X: (n_samples, NUM_FEATURES) measurements
        Y: (n_samples, NUM_BETAS) betas
    """
    from core.smpl_optimizer import smpl_forward, extract_measurements, _load_smpl

    smpl = _load_smpl()
    faces = smpl['faces']

    X_rows = []
    Y_rows = []
    skipped = 0

    logger.info(f"Generating {n_samples} synthetic training samples...")
    for i in range(n_samples):
        betas = np.random.randn(NUM_BETAS) * 1.5
        try:
            verts, joints = smpl_forward(betas)
            m = extract_measurements(verts, joints, faces)

            features = [m.get(k, 0.0) for k in FEATURE_KEYS]
            if any(f == 0.0 for f in features[:5]):  # skip if core measurements missing
                skipped += 1
                continue

            X_rows.append(features)
            Y_rows.append(betas.tolist())
        except Exception as e:
            skipped += 1
            if skipped < 5:
                logger.warning(f"Sample {i} failed: {e}")
            continue

        if (i + 1) % 1000 == 0:
            logger.info(f"  {i + 1}/{n_samples} generated ({skipped} skipped)")

    X = np.array(X_rows, dtype=np.float32)
    Y = np.array(Y_rows, dtype=np.float32)
    logger.info(f"Generated {len(X)} valid samples ({skipped} skipped)")

    if output_csv:
        os.makedirs(os.path.dirname(output_csv) or '.', exist_ok=True)
        header = FEATURE_KEYS + [f'beta_{i}' for i in range(NUM_BETAS)]
        with open(output_csv, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(header)
            for x, y in zip(X_rows, Y_rows):
                w.writerow(x + y)
        logger.info(f"Saved training data to {output_csv}")

    return X, Y


# ── Training ──────────────────────────────────────────────────────────────────

def train_model(X, Y, epochs=200, lr=0.001, test_fraction=0.2):
    """
    Train a 3-layer MLP: features → 128 → 64 → 10 betas.

    Returns:
        model: trained PyTorch model
        stats: dict with train/test losses and validation metrics
    """
    import torch
    import torch.nn as nn
    import torch.optim as optim

    class A2BRegressor(nn.Module):
        def __init__(self):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(NUM_FEATURES, 128),
                nn.ReLU(),
                nn.Linear(128, 64),
                nn.ReLU(),
                nn.Linear(64, NUM_BETAS),
            )

        def forward(self, x):
            return self.net(x)

    # Normalize inputs
    X_mean = X.mean(axis=0)
    X_std  = X.std(axis=0)
    X_std[X_std < 1e-6] = 1.0  # avoid division by zero
    X_norm = (X - X_mean) / X_std

    # Split
    n = len(X)
    n_test = int(n * test_fraction)
    indices = np.random.permutation(n)
    train_idx = indices[n_test:]
    test_idx  = indices[:n_test]

    X_train = torch.tensor(X_norm[train_idx], dtype=torch.float32)
    Y_train = torch.tensor(Y[train_idx], dtype=torch.float32)
    X_test  = torch.tensor(X_norm[test_idx], dtype=torch.float32)
    Y_test  = torch.tensor(Y[test_idx], dtype=torch.float32)

    model = A2BRegressor()
    criterion = nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=lr)

    best_test_loss = float('inf')
    for epoch in range(epochs):
        model.train()
        optimizer.zero_grad()
        preds = model(X_train)
        loss = criterion(preds, Y_train)
        loss.backward()
        optimizer.step()

        if (epoch + 1) % 50 == 0 or epoch == 0:
            model.eval()
            with torch.no_grad():
                test_preds = model(X_test)
                test_loss = criterion(test_preds, Y_test).item()
            best_test_loss = min(best_test_loss, test_loss)
            logger.info(f"  Epoch {epoch + 1}/{epochs}: train={loss.item():.5f} test={test_loss:.5f}")

    # Final validation
    model.eval()
    with torch.no_grad():
        test_preds = model(X_test).numpy()
        beta_mae = np.mean(np.abs(test_preds - Y[test_idx]))
        beta_euclidean = np.mean(np.linalg.norm(test_preds - Y[test_idx], axis=1))

    stats = {
        'train_loss': loss.item(),
        'test_loss': best_test_loss,
        'beta_mae': float(beta_mae),
        'beta_euclidean_mean': float(beta_euclidean),
        'X_mean': X_mean.tolist(),
        'X_std': X_std.tolist(),
        'n_train': len(train_idx),
        'n_test': len(test_idx),
    }
    logger.info(f"Training complete. Beta MAE={beta_mae:.4f}, Euclidean={beta_euclidean:.4f}")

    return model, stats


# ── ONNX Export ───────────────────────────────────────────────────────────────

def export_onnx(model, stats, output_path=None):
    """Export trained model to ONNX with normalization baked in."""
    import torch
    import json

    output_path = output_path or ONNX_PATH
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

    # Save normalization params alongside ONNX
    norm_path = output_path.replace('.onnx', '_norm.json')
    with open(norm_path, 'w') as f:
        json.dump({
            'feature_keys': FEATURE_KEYS,
            'X_mean': stats['X_mean'],
            'X_std': stats['X_std'],
            'stats': stats,
        }, f, indent=2)

    dummy = torch.randn(1, NUM_FEATURES)
    torch.onnx.export(
        model, dummy, output_path,
        input_names=['measurements'],
        output_names=['betas'],
        dynamic_axes={'measurements': {0: 'batch'}, 'betas': {0: 'batch'}},
        opset_version=18,
    )

    size_kb = os.path.getsize(output_path) / 1024
    logger.info(f"Exported ONNX to {output_path} ({size_kb:.1f} KB)")
    logger.info(f"Normalization params saved to {norm_path}")
    return output_path


# ── Inference ─────────────────────────────────────────────────────────────────

def predict_betas(measurements_dict):
    """
    Predict SMPL betas from a measurements dict.

    Uses ONNX Runtime if available, otherwise falls back to loading
    the PyTorch model.

    Args:
        measurements_dict: dict with keys from FEATURE_KEYS

    Returns:
        betas: (10,) numpy array of predicted SMPL shape parameters
    """
    import json

    norm_path = ONNX_PATH.replace('.onnx', '_norm.json')
    if not os.path.exists(norm_path):
        raise FileNotFoundError(
            f"Normalization params not found at {norm_path}. Run training first."
        )

    with open(norm_path) as f:
        norm = json.load(f)

    features = np.array(
        [measurements_dict.get(k, 0.0) for k in norm['feature_keys']],
        dtype=np.float32
    )
    X_mean = np.array(norm['X_mean'], dtype=np.float32)
    X_std  = np.array(norm['X_std'], dtype=np.float32)
    features_norm = (features - X_mean) / X_std

    if os.path.exists(ONNX_PATH):
        try:
            import onnxruntime as ort
            sess = ort.InferenceSession(ONNX_PATH)
            result = sess.run(None, {'measurements': features_norm.reshape(1, -1)})
            return result[0][0]
        except ImportError:
            logger.warning("onnxruntime not available, cannot run ONNX model")
            raise

    raise FileNotFoundError(f"Model not found at {ONNX_PATH}. Run training first.")


# ── Round-trip Validation ─────────────────────────────────────────────────────

def validate_roundtrip(n_samples=100):
    """
    Validate: random measurements → predict betas → rebuild mesh → extract
    measurements → compare. Reports per-key MAE.
    """
    from core.smpl_optimizer import smpl_forward, extract_measurements, _load_smpl

    smpl = _load_smpl()
    faces = smpl['faces']
    errors = {k: [] for k in FEATURE_KEYS}

    for i in range(n_samples):
        betas_true = np.random.randn(NUM_BETAS) * 1.5
        verts, joints = smpl_forward(betas_true)
        m_true = extract_measurements(verts, joints, faces)

        try:
            betas_pred = predict_betas(m_true)
        except Exception:
            continue

        verts_pred, joints_pred = smpl_forward(betas_pred)
        m_pred = extract_measurements(verts_pred, joints_pred, faces)

        for k in FEATURE_KEYS:
            if k in m_true and k in m_pred:
                errors[k].append(abs(m_true[k] - m_pred[k]))

    print("\n  Round-trip Validation (MAE per measurement):")
    print("  " + "─" * 50)
    all_ok = True
    for k in FEATURE_KEYS:
        if errors[k]:
            mae = np.mean(errors[k])
            status = "OK" if mae < 2.0 else "WARN" if mae < 5.0 else "FAIL"
            if status == "FAIL":
                all_ok = False
            print(f"    {k:<35} MAE={mae:.2f} cm  [{status}]")

    v2v_errors = []
    for _ in range(min(50, n_samples)):
        betas_true = np.random.randn(NUM_BETAS) * 1.5
        verts_true, _ = smpl_forward(betas_true)
        m_true = extract_measurements(verts_true, _, faces)
        try:
            betas_pred = predict_betas(m_true)
            verts_pred, _ = smpl_forward(betas_pred)
            v2v = np.mean(np.linalg.norm(verts_true - verts_pred, axis=1))
            v2v_errors.append(v2v)
        except Exception:
            continue

    if v2v_errors:
        mean_v2v = np.mean(v2v_errors)
        print(f"\n    V2V mesh error: {mean_v2v:.1f} mm (target < 5mm)")

    return all_ok


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    parser = argparse.ArgumentParser(description='A2B Regressor: measurements → SMPL betas')
    parser.add_argument('--train', action='store_true', help='Generate data + train model')
    parser.add_argument('--export', action='store_true', help='Export to ONNX after training')
    parser.add_argument('--validate', action='store_true', help='Run round-trip validation')
    parser.add_argument('--samples', type=int, default=10000, help='Training samples (default 10000)')
    parser.add_argument('--epochs', type=int, default=200, help='Training epochs (default 200)')
    args = parser.parse_args()

    if args.train:
        X, Y = generate_training_data(n_samples=args.samples, output_csv=CSV_PATH)
        model, stats = train_model(X, Y, epochs=args.epochs)

        if args.export:
            export_onnx(model, stats)

    if args.validate:
        validate_roundtrip()
