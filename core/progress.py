import numpy as np
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def analyze_trend(scan_history):
    """
    Analyzes muscle growth trends from a series of scan records.

    Args:
        scan_history: List of dicts, each with at minimum:
            - scan_date: date or ISO string
            - volume_cm3: float
            - area_mm2: float (optional)
            - shape_score: float (optional)

    Returns dict with trend analysis, statistics, and projections.
    """
    if not scan_history or len(scan_history) < 2:
        return {
            "status": "Insufficient Data",
            "message": "At least 2 scans are required for trend analysis",
            "scan_count": len(scan_history) if scan_history else 0,
        }

    # Sort by date
    records = sorted(scan_history, key=lambda r: _parse_date(r.get("scan_date")))
    n = len(records)

    # Extract volume series
    volumes = [r.get("volume_cm3", 0.0) for r in records]
    dates = [_parse_date(r.get("scan_date")) for r in records]

    # Days since first scan (for regression)
    day_offsets = [(d - dates[0]).days for d in dates]

    # Linear regression for volume trend
    slope, intercept = _linear_regression(day_offsets, volumes)

    # Statistics
    vol_latest = volumes[-1]
    vol_first = volumes[0]
    total_change = vol_latest - vol_first
    total_pct = (total_change / vol_first * 100) if vol_first > 0 else 0.0
    total_days = day_offsets[-1] if day_offsets[-1] > 0 else 1

    # Per-period changes
    period_changes = []
    for i in range(1, n):
        delta = volumes[i] - volumes[i - 1]
        days = (dates[i] - dates[i - 1]).days or 1
        period_changes.append({
            "from_date": dates[i - 1].isoformat(),
            "to_date": dates[i].isoformat(),
            "days": days,
            "volume_change_cm3": round(delta, 2),
            "daily_rate_cm3": round(delta / days, 4),
        })

    # Best and worst periods
    best = max(period_changes, key=lambda p: p["volume_change_cm3"])
    worst = min(period_changes, key=lambda p: p["volume_change_cm3"])

    # Weekly rate (slope * 7)
    weekly_rate = slope * 7

    # Projection: next 30 days at current rate
    projected_30d = vol_latest + slope * 30

    # Consistency score: how linear is the growth?
    # R² of the linear fit
    r_squared = _r_squared(day_offsets, volumes, slope, intercept)

    # Streak analysis
    streak = _calculate_streak(period_changes)

    return {
        "status": "Success",
        "scan_count": n,
        "date_range": {
            "first": dates[0].isoformat(),
            "latest": dates[-1].isoformat(),
            "total_days": total_days,
        },
        "volume_summary": {
            "first_cm3": round(vol_first, 2),
            "latest_cm3": round(vol_latest, 2),
            "total_change_cm3": round(total_change, 2),
            "total_change_pct": round(total_pct, 2),
            "min_cm3": round(min(volumes), 2),
            "max_cm3": round(max(volumes), 2),
            "mean_cm3": round(np.mean(volumes), 2),
            "std_cm3": round(np.std(volumes), 2),
        },
        "trend": {
            "direction": "gaining" if slope > 0.001 else "losing" if slope < -0.001 else "maintaining",
            "daily_rate_cm3": round(slope, 4),
            "weekly_rate_cm3": round(weekly_rate, 3),
            "consistency_r2": round(r_squared, 3),
            "projected_30d_cm3": round(projected_30d, 2),
        },
        "periods": period_changes,
        "best_period": best,
        "worst_period": worst,
        "growth_streak": streak,
    }


def calculate_correlation(scan_history, health_logs):
    """
    Correlates muscle gains with diet/activity data.

    Returns which factors (protein, calories, activity) most closely
    correlate with volume gains.
    """
    if len(scan_history) < 3 or len(health_logs) < 3:
        return {"status": "Insufficient Data",
                "message": "Need at least 3 scans and 3 health logs"}

    scans = sorted(scan_history, key=lambda r: _parse_date(r.get("scan_date")))
    logs = sorted(health_logs, key=lambda r: _parse_date(r.get("log_date")))

    # Match health logs to scan periods
    volumes = [s.get("volume_cm3", 0.0) for s in scans]
    vol_changes = [volumes[i] - volumes[i - 1] for i in range(1, len(volumes))]

    # Average health metrics per scan period
    scan_dates = [_parse_date(s.get("scan_date")) for s in scans]
    period_metrics = []

    for i in range(1, len(scan_dates)):
        start = scan_dates[i - 1]
        end = scan_dates[i]
        period_logs = [l for l in logs
                       if start <= _parse_date(l.get("log_date", "2000-01-01")) <= end]

        if not period_logs:
            period_metrics.append({"protein_g": 0, "calories_in": 0})
            continue

        avg_protein = np.mean([l.get("protein_g", 0) for l in period_logs])
        avg_calories = np.mean([l.get("calories_in", 0) for l in period_logs])
        period_metrics.append({
            "protein_g": avg_protein,
            "calories_in": avg_calories,
        })

    # Correlations
    correlations = {}
    if len(vol_changes) >= 3:
        proteins = [p.get("protein_g", 0) for p in period_metrics]
        calories = [p.get("calories_in", 0) for p in period_metrics]

        if np.std(proteins) > 0 and np.std(vol_changes) > 0:
            correlations["protein_vs_growth"] = round(
                float(np.corrcoef(proteins, vol_changes)[0, 1]), 3)

        if np.std(calories) > 0 and np.std(vol_changes) > 0:
            correlations["calories_vs_growth"] = round(
                float(np.corrcoef(calories, vol_changes)[0, 1]), 3)

    return {
        "status": "Success",
        "correlations": correlations,
        "interpretation": _interpret_correlations(correlations),
    }


def _parse_date(d):
    """Parse a date from various formats."""
    if isinstance(d, datetime):
        return d
    if hasattr(d, 'isoformat'):
        return datetime.combine(d, datetime.min.time())
    if isinstance(d, str):
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(d, fmt)
            except ValueError:
                continue
    return datetime(2000, 1, 1)


def _linear_regression(x, y):
    """Simple linear regression returning (slope, intercept)."""
    x = np.array(x, dtype=float)
    y = np.array(y, dtype=float)
    n = len(x)
    if n < 2:
        return 0.0, y[0] if n > 0 else 0.0
    x_mean = np.mean(x)
    y_mean = np.mean(y)
    ss_xy = np.sum((x - x_mean) * (y - y_mean))
    ss_xx = np.sum((x - x_mean) ** 2)
    if ss_xx == 0:
        return 0.0, y_mean
    slope = ss_xy / ss_xx
    intercept = y_mean - slope * x_mean
    return float(slope), float(intercept)


def _r_squared(x, y, slope, intercept):
    """Calculate R² for a linear fit."""
    x = np.array(x, dtype=float)
    y = np.array(y, dtype=float)
    y_pred = slope * x + intercept
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    if ss_tot == 0:
        return 1.0
    return max(0.0, 1.0 - ss_res / ss_tot)


def _calculate_streak(period_changes):
    """Calculate the current consecutive growth streak."""
    streak = 0
    for p in reversed(period_changes):
        if p["volume_change_cm3"] > 0:
            streak += 1
        else:
            break
    return {"consecutive_gains": streak, "total_periods": len(period_changes)}


def _interpret_correlations(correlations):
    """Human-readable interpretation of correlation coefficients."""
    interp = []
    for key, val in correlations.items():
        label = key.replace("_vs_", " vs ").replace("_", " ").title()
        if abs(val) > 0.7:
            strength = "strong"
        elif abs(val) > 0.4:
            strength = "moderate"
        else:
            strength = "weak"
        direction = "positive" if val > 0 else "negative"
        interp.append(f"{label}: {strength} {direction} correlation ({val})")
    return interp
