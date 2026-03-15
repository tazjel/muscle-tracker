import cv2
import numpy as np
import logging

logger = logging.getLogger(__name__)

MIN_MATCH_COUNT = 10
GOOD_MATCH_RATIO = 0.75  # Lowe's ratio test threshold


def align_images(img_ref, img_to_align, method="orb"):
    """
    Aligns img_to_align to img_ref using feature-based registration.

    Returns (aligned_image, homography_matrix, confidence).
    On failure, returns (original_image, None, 0.0) so the pipeline continues.
    """
    gray_ref = cv2.cvtColor(img_ref, cv2.COLOR_BGR2GRAY)
    gray_align = cv2.cvtColor(img_to_align, cv2.COLOR_BGR2GRAY)

    if method == "orb":
        aligned, h, confidence = _align_orb(img_ref, img_to_align, gray_ref, gray_align)
    elif method == "sift":
        aligned, h, confidence = _align_sift(img_ref, img_to_align, gray_ref, gray_align)
    else:
        logger.error("Unknown alignment method: %s", method)
        return img_to_align, None, 0.0

    if aligned is None:
        logger.warning("Alignment failed — using original image")
        return img_to_align, None, 0.0

    return aligned, h, confidence


def _align_orb(img_ref, img_to_align, gray_ref, gray_align):
    """ORB-based alignment with quality gating."""
    orb = cv2.ORB_create(2000)
    kp1, des1 = orb.detectAndCompute(gray_ref, None)
    kp2, des2 = orb.detectAndCompute(gray_align, None)

    if des1 is None or des2 is None:
        logger.warning("ORB: No descriptors found")
        return None, None, 0.0

    bf = cv2.BFMatcher(cv2.NORM_HAMMING)
    matches = bf.knnMatch(des1, des2, k=2)

    # Lowe's ratio test for quality filtering
    good_matches = []
    for pair in matches:
        if len(pair) == 2:
            m, n = pair
            if m.distance < GOOD_MATCH_RATIO * n.distance:
                good_matches.append(m)

    if len(good_matches) < MIN_MATCH_COUNT:
        logger.warning("ORB: Only %d good matches (need %d)", len(good_matches), MIN_MATCH_COUNT)
        return None, None, 0.0

    pts1 = np.float32([kp1[m.queryIdx].pt for m in good_matches])
    pts2 = np.float32([kp2[m.trainIdx].pt for m in good_matches])

    h, mask = cv2.findHomography(pts2, pts1, cv2.RANSAC, 5.0)
    if h is None:
        return None, None, 0.0

    inlier_ratio = np.sum(mask) / len(mask) if mask is not None else 0.0
    confidence = inlier_ratio * 100

    if confidence < 30.0:
        logger.warning("ORB: Low inlier ratio %.1f%% — alignment unreliable", confidence)
        return None, None, confidence

    height, width = img_ref.shape[:2]
    aligned = cv2.warpPerspective(img_to_align, h, (width, height))

    logger.info("ORB alignment: %d matches, %.1f%% inliers", len(good_matches), confidence)
    return aligned, h, confidence


def _align_sift(img_ref, img_to_align, gray_ref, gray_align):
    """SIFT-based alignment (higher precision, slower)."""
    sift = cv2.SIFT_create(2000)
    kp1, des1 = sift.detectAndCompute(gray_ref, None)
    kp2, des2 = sift.detectAndCompute(gray_align, None)

    if des1 is None or des2 is None:
        return None, None, 0.0

    bf = cv2.BFMatcher(cv2.NORM_L2)
    matches = bf.knnMatch(des1, des2, k=2)

    good_matches = []
    for pair in matches:
        if len(pair) == 2:
            m, n = pair
            if m.distance < GOOD_MATCH_RATIO * n.distance:
                good_matches.append(m)

    if len(good_matches) < MIN_MATCH_COUNT:
        return None, None, 0.0

    pts1 = np.float32([kp1[m.queryIdx].pt for m in good_matches])
    pts2 = np.float32([kp2[m.trainIdx].pt for m in good_matches])

    h, mask = cv2.findHomography(pts2, pts1, cv2.RANSAC, 5.0)
    if h is None:
        return None, None, 0.0

    inlier_ratio = np.sum(mask) / len(mask) if mask is not None else 0.0
    confidence = inlier_ratio * 100

    if confidence < 30.0:
        return None, None, confidence

    height, width = img_ref.shape[:2]
    aligned = cv2.warpPerspective(img_to_align, h, (width, height))

    logger.info("SIFT alignment: %d matches, %.1f%% inliers", len(good_matches), confidence)
    return aligned, h, confidence
