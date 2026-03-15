import numpy as np
import pytest
import cv2
import os
from core.timelapse import generate_progress_timelapse, generate_comparison_slider_image

def test_generate_timelapse():
    # Create dummy images
    paths = ['f1.png', 'f2.png']
    for p in paths:
        cv2.imwrite(p, np.zeros((100, 100, 3), dtype=np.uint8))
    
    metrics = [{'scan_date': '2021-01-01', 'volume_cm3': 100}, {'scan_date': '2021-02-01', 'volume_cm3': 110}]
    out = 'test_progress.gif'
    res = generate_progress_timelapse(paths, [None, None], metrics, out)
    
    assert res == out
    assert os.path.exists(out)
    
    for p in paths + [out]:
        if os.path.exists(p): os.remove(p)

def test_generate_slider():
    im1 = np.zeros((100, 100, 3), dtype=np.uint8)
    im2 = np.ones((100, 100, 3), dtype=np.uint8) * 255
    out = 'test_slider.png'
    res = generate_comparison_slider_image(im1, im2, None, None, 0.5, out)
    assert res == out
    assert os.path.exists(out)
    os.remove(out)
