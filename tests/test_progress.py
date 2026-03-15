"""Tests for core/progress.py — trend analysis, regression, correlation, streaks."""
import unittest
import numpy as np
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.progress import (
    analyze_trend, calculate_correlation,
    _parse_date, _linear_regression, _r_squared, _calculate_streak,
    _interpret_correlations,
)


class TestParseDate(unittest.TestCase):

    def test_iso_string(self):
        result = _parse_date("2026-01-15")
        self.assertEqual(result.year, 2026)
        self.assertEqual(result.month, 1)
        self.assertEqual(result.day, 15)

    def test_datetime_passthrough(self):
        dt = datetime(2026, 3, 10, 14, 30)
        self.assertEqual(_parse_date(dt), dt)

    def test_date_object(self):
        from datetime import date
        d = date(2026, 6, 1)
        result = _parse_date(d)
        self.assertEqual(result.year, 2026)
        self.assertEqual(result.month, 6)

    def test_invalid_returns_default(self):
        result = _parse_date("not-a-date")
        self.assertEqual(result, datetime(2000, 1, 1))

    def test_none_returns_default(self):
        result = _parse_date(None)
        self.assertEqual(result, datetime(2000, 1, 1))


class TestLinearRegression(unittest.TestCase):

    def test_perfect_positive_slope(self):
        x = [0, 1, 2, 3]
        y = [10, 12, 14, 16]
        slope, intercept = _linear_regression(x, y)
        self.assertAlmostEqual(slope, 2.0, places=5)
        self.assertAlmostEqual(intercept, 10.0, places=5)

    def test_flat_line(self):
        x = [0, 1, 2, 3]
        y = [5.0, 5.0, 5.0, 5.0]
        slope, intercept = _linear_regression(x, y)
        self.assertAlmostEqual(slope, 0.0, places=5)
        self.assertAlmostEqual(intercept, 5.0, places=5)

    def test_single_point(self):
        slope, intercept = _linear_regression([0], [42.0])
        self.assertEqual(slope, 0.0)
        self.assertEqual(intercept, 42.0)

    def test_negative_slope(self):
        x = [0, 1, 2]
        y = [20, 15, 10]
        slope, _ = _linear_regression(x, y)
        self.assertAlmostEqual(slope, -5.0, places=5)


class TestRSquared(unittest.TestCase):

    def test_perfect_fit(self):
        x = [0, 1, 2, 3]
        y = [2, 4, 6, 8]
        r2 = _r_squared(x, y, 2.0, 2.0)
        self.assertAlmostEqual(r2, 1.0, places=5)

    def test_constant_y(self):
        x = [0, 1, 2]
        y = [5, 5, 5]
        r2 = _r_squared(x, y, 0.0, 5.0)
        self.assertEqual(r2, 1.0)

    def test_poor_fit(self):
        x = [0, 1, 2, 3]
        y = [1, 100, 2, 99]
        slope, intercept = _linear_regression(x, y)
        r2 = _r_squared(x, y, slope, intercept)
        self.assertLess(r2, 0.5)


class TestCalculateStreak(unittest.TestCase):

    def test_all_gains(self):
        periods = [
            {"volume_change_cm3": 1.0},
            {"volume_change_cm3": 2.0},
            {"volume_change_cm3": 0.5},
        ]
        result = _calculate_streak(periods)
        self.assertEqual(result["consecutive_gains"], 3)
        self.assertEqual(result["total_periods"], 3)

    def test_broken_streak(self):
        periods = [
            {"volume_change_cm3": 1.0},
            {"volume_change_cm3": -0.5},
            {"volume_change_cm3": 2.0},
        ]
        result = _calculate_streak(periods)
        self.assertEqual(result["consecutive_gains"], 1)

    def test_no_gains(self):
        periods = [
            {"volume_change_cm3": -1.0},
            {"volume_change_cm3": -2.0},
        ]
        result = _calculate_streak(periods)
        self.assertEqual(result["consecutive_gains"], 0)

    def test_empty(self):
        result = _calculate_streak([])
        self.assertEqual(result["consecutive_gains"], 0)


class TestAnalyzeTrend(unittest.TestCase):

    def _make_scans(self, volumes, start_date="2026-01-01", interval_days=7):
        start = datetime.strptime(start_date, "%Y-%m-%d")
        scans = []
        for i, vol in enumerate(volumes):
            scans.append({
                "scan_date": (start + timedelta(days=i * interval_days)).isoformat(),
                "volume_cm3": vol,
            })
        return scans

    def test_insufficient_data_empty(self):
        result = analyze_trend([])
        self.assertEqual(result["status"], "Insufficient Data")
        self.assertEqual(result["scan_count"], 0)

    def test_insufficient_data_one_scan(self):
        result = analyze_trend([{"scan_date": "2026-01-01", "volume_cm3": 100}])
        self.assertEqual(result["status"], "Insufficient Data")

    def test_basic_gaining_trend(self):
        scans = self._make_scans([100, 105, 110, 115])
        result = analyze_trend(scans)
        self.assertEqual(result["status"], "Success")
        self.assertEqual(result["scan_count"], 4)
        self.assertEqual(result["trend"]["direction"], "gaining")
        self.assertGreater(result["trend"]["daily_rate_cm3"], 0)
        self.assertAlmostEqual(result["volume_summary"]["total_change_cm3"], 15.0, places=1)

    def test_losing_trend(self):
        scans = self._make_scans([120, 115, 110])
        result = analyze_trend(scans)
        self.assertEqual(result["trend"]["direction"], "losing")
        self.assertLess(result["trend"]["daily_rate_cm3"], 0)

    def test_maintaining_trend(self):
        scans = self._make_scans([100, 100, 100])
        result = analyze_trend(scans)
        self.assertEqual(result["trend"]["direction"], "maintaining")

    def test_projection_30d(self):
        scans = self._make_scans([100, 107], interval_days=7)
        result = analyze_trend(scans)
        self.assertGreater(result["trend"]["projected_30d_cm3"], 107)

    def test_r_squared_perfect_linear(self):
        scans = self._make_scans([100, 110, 120, 130])
        result = analyze_trend(scans)
        self.assertGreater(result["trend"]["consistency_r2"], 0.99)

    def test_best_worst_periods(self):
        scans = self._make_scans([100, 110, 105, 120])
        result = analyze_trend(scans)
        self.assertEqual(result["best_period"]["volume_change_cm3"], 15.0)
        self.assertEqual(result["worst_period"]["volume_change_cm3"], -5.0)

    def test_growth_streak(self):
        scans = self._make_scans([100, 95, 100, 105, 110])
        result = analyze_trend(scans)
        self.assertEqual(result["growth_streak"]["consecutive_gains"], 3)

    def test_date_range(self):
        scans = self._make_scans([100, 110, 120], start_date="2026-02-01", interval_days=14)
        result = analyze_trend(scans)
        self.assertEqual(result["date_range"]["total_days"], 28)

    def test_volume_summary_stats(self):
        scans = self._make_scans([100, 120, 110])
        result = analyze_trend(scans)
        self.assertEqual(result["volume_summary"]["min_cm3"], 100.0)
        self.assertEqual(result["volume_summary"]["max_cm3"], 120.0)
        self.assertAlmostEqual(result["volume_summary"]["mean_cm3"], 110.0, places=1)


class TestCalculateCorrelation(unittest.TestCase):

    def _make_data(self):
        start = datetime(2026, 1, 1)
        scans = [
            {"scan_date": (start + timedelta(days=0)).isoformat(), "volume_cm3": 100},
            {"scan_date": (start + timedelta(days=7)).isoformat(), "volume_cm3": 105},
            {"scan_date": (start + timedelta(days=14)).isoformat(), "volume_cm3": 112},
            {"scan_date": (start + timedelta(days=21)).isoformat(), "volume_cm3": 115},
        ]
        logs = [
            {"log_date": (start + timedelta(days=1)).isoformat(), "protein_g": 150, "calories_in": 2500},
            {"log_date": (start + timedelta(days=3)).isoformat(), "protein_g": 160, "calories_in": 2600},
            {"log_date": (start + timedelta(days=8)).isoformat(), "protein_g": 180, "calories_in": 2800},
            {"log_date": (start + timedelta(days=10)).isoformat(), "protein_g": 170, "calories_in": 2700},
            {"log_date": (start + timedelta(days=15)).isoformat(), "protein_g": 190, "calories_in": 3000},
            {"log_date": (start + timedelta(days=18)).isoformat(), "protein_g": 200, "calories_in": 3100},
        ]
        return scans, logs

    def test_insufficient_scans(self):
        result = calculate_correlation(
            [{"scan_date": "2026-01-01", "volume_cm3": 100}],
            [{"log_date": "2026-01-01"}, {"log_date": "2026-01-02"}, {"log_date": "2026-01-03"}],
        )
        self.assertEqual(result["status"], "Insufficient Data")

    def test_insufficient_logs(self):
        scans = [
            {"scan_date": "2026-01-01", "volume_cm3": 100},
            {"scan_date": "2026-01-08", "volume_cm3": 105},
            {"scan_date": "2026-01-15", "volume_cm3": 110},
        ]
        result = calculate_correlation(scans, [{"log_date": "2026-01-02"}])
        self.assertEqual(result["status"], "Insufficient Data")

    def test_returns_correlations(self):
        scans, logs = self._make_data()
        result = calculate_correlation(scans, logs)
        self.assertEqual(result["status"], "Success")
        self.assertIn("correlations", result)
        self.assertIn("interpretation", result)

    def test_correlation_values_in_range(self):
        scans, logs = self._make_data()
        result = calculate_correlation(scans, logs)
        for key, val in result.get("correlations", {}).items():
            self.assertGreaterEqual(val, -1.0)
            self.assertLessEqual(val, 1.0)


class TestInterpretCorrelations(unittest.TestCase):

    def test_strong_positive(self):
        result = _interpret_correlations({"protein_vs_growth": 0.85})
        self.assertEqual(len(result), 1)
        self.assertIn("strong", result[0])
        self.assertIn("positive", result[0])

    def test_moderate_negative(self):
        result = _interpret_correlations({"calories_vs_growth": -0.5})
        self.assertIn("moderate", result[0])
        self.assertIn("negative", result[0])

    def test_weak(self):
        result = _interpret_correlations({"protein_vs_growth": 0.2})
        self.assertIn("weak", result[0])

    def test_empty(self):
        result = _interpret_correlations({})
        self.assertEqual(result, [])


if __name__ == '__main__':
    unittest.main()
