import numpy as np
import pytest
import os
import tempfile
from core.body_map import generate_body_map, generate_body_map_data


class TestGenerateBodyMapData:
    def test_aggregates_by_muscle_group(self):
        records = [
            {'muscle_group': 'bicep', 'side': 'left', 'volume_cm3': 120, 'shape_score': 75, 'growth_pct': 5.0, 'scan_date': '2026-03-01'},
            {'muscle_group': 'bicep', 'side': 'left', 'volume_cm3': 125, 'shape_score': 78, 'growth_pct': 4.2, 'scan_date': '2026-03-10'},
            {'muscle_group': 'quad', 'side': 'right', 'volume_cm3': 800, 'shape_score': 60, 'growth_pct': 2.0, 'scan_date': '2026-03-05'},
        ]
        data = generate_body_map_data(records)
        assert 'bicep' in data or 'bicep_left' in data
        # Should use latest scan
        bicep_key = [k for k in data if 'bicep' in k][0]
        assert data[bicep_key]['volume_cm3'] == 125  # latest

    def test_empty_records(self):
        data = generate_body_map_data([])
        assert isinstance(data, dict)
        assert len(data) == 0


class TestGenerateBodyMap:
    def test_generates_image_file(self):
        records = [
            {'muscle_group': 'bicep', 'side': 'left', 'volume_cm3': 120, 'shape_score': 75, 'growth_pct': 5.0, 'scan_date': '2026-03-01'},
            {'muscle_group': 'quad', 'side': 'right', 'volume_cm3': 800, 'shape_score': 40, 'growth_pct': -1.0, 'scan_date': '2026-03-05'},
        ]
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            path = f.name
        try:
            result = generate_body_map(records, output_path=path)
            assert os.path.exists(result)
            assert os.path.getsize(result) > 0
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_empty_records_still_draws(self):
        """Should draw body outline with all regions gray."""
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            path = f.name
        try:
            result = generate_body_map([], output_path=path)
            assert os.path.exists(result)
        finally:
            if os.path.exists(path):
                os.unlink(path)
