import unittest
import numpy as np
import cv2
import sys
import os

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.alignment import align_images, _align_orb

class TestAlignment(unittest.TestCase):
    def setUp(self):
        # Create a synthetic image with a shape for feature detection
        self.img1 = np.zeros((300, 300, 3), dtype=np.uint8)
        cv2.rectangle(self.img1, (50, 50), (200, 200), (255, 255, 255), -1)
        cv2.circle(self.img1, (100, 100), 20, (0, 0, 255), -1)
        
        self.img2 = self.img1.copy()
        
        # Create a blank image
        self.blank = np.zeros((300, 300, 3), dtype=np.uint8)
        
        # Create a completely different noise image
        np.random.seed(42)
        self.noise = np.random.randint(0, 256, (300, 300, 3), dtype=np.uint8)

    def test_align_images_identical(self):
        aligned, h, conf = align_images(self.img1, self.img2, method="orb")
        self.assertIsNotNone(h)
        self.assertGreater(conf, 0.0)
        self.assertEqual(aligned.shape, self.img1.shape)
        
        # SIFT should also work
        aligned_sift, h_sift, conf_sift = align_images(self.img1, self.img2, method="sift")
        self.assertIsNotNone(h_sift)
        self.assertGreater(conf_sift, 0.0)

    def test_align_images_different(self):
        aligned, h, conf = align_images(self.img1, self.noise, method="orb")
        self.assertIsNone(h)
        self.assertEqual(conf, 0.0)
        # Returns the original image if alignment fails
        np.testing.assert_array_equal(aligned, self.noise)

    def test_align_images_unknown_method(self):
        aligned, h, conf = align_images(self.img1, self.img2, method="unknown")
        self.assertIsNone(h)
        self.assertEqual(conf, 0.0)
        np.testing.assert_array_equal(aligned, self.img2)

    def test_align_orb_no_features(self):
        gray_blank = cv2.cvtColor(self.blank, cv2.COLOR_BGR2GRAY)
        aligned, h, conf = _align_orb(self.blank, self.blank, gray_blank, gray_blank)
        self.assertIsNone(aligned)
        self.assertIsNone(h)
        self.assertEqual(conf, 0.0)

if __name__ == '__main__':
    unittest.main()
