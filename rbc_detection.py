"""
rbc_detection.py
Finds individual red blood cells (RBCs) in a full thin-smear field-of-view
photo and turns each one into a crop that looks like the NIH training data,
so the single-cell classifier can be applied to a whole smear.

Why the crops matter: the model was trained on NIH crops in which ONE cell
fills the frame on a black background. The old pipeline cut a fixed 128 px
square around each centroid, so at low magnification a crop contained several
cells, and at high magnification only part of one. That is a different
distribution from training and the main source of full-smear errors. Each
crop is now sized to the cell itself, with the background masked to black.

Pipeline (classical CV, no extra training data needed):
  1. Green channel + blur (best RBC contrast in Giemsa stains), Otsu threshold.
     Works for pale backgrounds (normal smears) and dark ones (NIH-style).
  2. Fill holes, so the pale centre of an RBC doesn't split it into a ring.
  3. Estimate the typical cell radius from the image itself, so the pipeline
     adapts to any magnification or phone camera.
  4. Distance transform + local maxima as seeds; each foreground pixel is
     assigned to its nearest seed, splitting touching and overlapping cells.
  5. Reject what is not a single RBC: specks/platelets (too small), white blood
     cells and unsplit clumps (too large), irregular debris (not round), and
     cells cut off by the image border (they would skew parasitemia).
  6. Crop each cell to its own bounding box, mask outside the cell to black,
     resize to the classifier's input size.

Thresholds are relative to the median cell size in each image, not fixed pixel
counts, which is what makes this robust across microscopes and phone adapters.
Validate on labelled full smears with evaluate_smears.py (BBBC041).
"""

from dataclasses import dataclass

import cv2
import numpy as np

CROP_SIZE = 128               # matches the classifier's expected input size
MIN_AREA_FRAC = 0.30          # < 30% of median cell area  -> speck / platelet
MAX_AREA_FRAC = 2.20          # > 220% of median cell area -> WBC or unsplit clump
MIN_CIRCULARITY = 0.50        # 1.0 = perfect circle; debris is usually irregular
CROP_PAD_FRAC = 0.08          # margin around each cell inside its crop
MAX_CELLS = 800               # safety cap for very dense / mis-segmented images
ABS_MIN_AREA = 60             # pixels; ignore noise in tiny images


@dataclass
class DetectedCell:
    centroid: tuple           # (x, y) in the original image
    bbox: tuple               # (x, y, w, h)
    crop: np.ndarray          # CROP_SIZE x CROP_SIZE x 3 uint8, ready for the classifier
    area: float = 0.0


def _circularity(contour) -> float:
    area = cv2.contourArea(contour)
    perimeter = cv2.arcLength(contour, True)
    if perimeter == 0:
        return 0.0
    return 4 * np.pi * area / (perimeter ** 2)


def _foreground_mask(rgb_image: np.ndarray) -> np.ndarray:
    """Binary mask (255 = cell) that works for light or dark backgrounds."""
    green = rgb_image[:, :, 1]
    blurred = cv2.GaussianBlur(green, (5, 5), 0)

    # Decide polarity from the image border, which is mostly background.
    border = np.concatenate([blurred[0, :], blurred[-1, :], blurred[:, 0], blurred[:, -1]])
    dark_background = np.median(border) < np.median(blurred)
    mode = cv2.THRESH_BINARY if dark_background else cv2.THRESH_BINARY_INV
    _, mask = cv2.threshold(blurred, 0, 255, mode + cv2.THRESH_OTSU)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=2)

    # Fill holes (RBC central pallor) by filling every external contour.
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filled = np.zeros_like(mask)
    cv2.drawContours(filled, contours, -1, 255, thickness=cv2.FILLED)
    return filled


def _estimate_radius(mask: np.ndarray, dist: np.ndarray) -> float:
    """Typical cell radius = median of the deepest distance-transform value in
    each connected blob. Clumps inflate a few values but not the median."""
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    peaks = []
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] < ABS_MIN_AREA:
            continue
        peaks.append(dist[labels == i].max())
    if not peaks:
        return 0.0
    return float(np.median(peaks))


def _watershed_regions(rgb_image: np.ndarray, mask: np.ndarray):
    dist = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
    r_est = _estimate_radius(mask, dist)
    if r_est < 2:
        return None, r_est

    # Seeds: local maxima of the distance map that are deep enough to be a cell
    # centre. The neighbourhood scales with the estimated radius.
    k = max(3, int(r_est * 0.9) | 1)
    local_max = cv2.dilate(dist, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    seeds = np.uint8((dist >= local_max - 1e-6) & (dist >= 0.55 * r_est)) * 255
    seeds = cv2.dilate(seeds, np.ones((3, 3), np.uint8))   # merge plateau pixels

    # Split each blob between its seeds: every foreground pixel goes to the
    # nearest seed (distance-transform labels). For touching, roughly round
    # RBCs this cuts along the neck between them, like a watershed on the
    # distance map, but it can't leak into the background.
    n_seeds, seed_ids = cv2.connectedComponents(seeds)
    if n_seeds <= 1:
        return None, r_est
    _, nearest = cv2.distanceTransformWithLabels(
        255 - seeds, cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_CCOMP)
    # Map distance-transform labels (one per seed blob) to seed component ids.
    lut = np.zeros(nearest.max() + 1, np.int32)
    on_seed = seeds > 0
    lut[nearest[on_seed]] = seed_ids[on_seed]
    markers = lut[nearest] + 1            # seeds -> 2..n, so 1 stays background
    markers[mask == 0] = 1
    return markers, r_est


def _cell_crop(rgb_image: np.ndarray, contour, size: int) -> np.ndarray:
    """Square crop around one cell, background masked to black (NIH style)."""
    h, w = rgb_image.shape[:2]
    x, y, cw, ch = cv2.boundingRect(contour)
    side = int(max(cw, ch) * (1 + 2 * CROP_PAD_FRAC))
    cx, cy = x + cw / 2.0, y + ch / 2.0
    x0, y0 = int(round(cx - side / 2.0)), int(round(cy - side / 2.0))

    cell_mask = np.zeros((h, w), np.uint8)
    cv2.drawContours(cell_mask, [contour], -1, 255, thickness=cv2.FILLED)
    masked = cv2.bitwise_and(rgb_image, rgb_image, mask=cell_mask)

    canvas = np.zeros((side, side, 3), np.uint8)
    sx0, sy0 = max(0, x0), max(0, y0)
    sx1, sy1 = min(w, x0 + side), min(h, y0 + side)
    canvas[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = masked[sy0:sy1, sx0:sx1]
    return cv2.resize(canvas, (size, size), interpolation=cv2.INTER_AREA)


def detect_cells(rgb_image: np.ndarray, crop_size: int = CROP_SIZE, return_stats: bool = False):
    """
    rgb_image: (H, W, 3) uint8 array of a full smear field-of-view.
    Returns a list of DetectedCell (one per accepted RBC). With
    return_stats=True, returns (cells, stats) where stats explains what was
    rejected and why -- useful for the evaluation script and for debugging.
    """
    stats = {"estimated_radius_px": 0.0, "candidates": 0, "accepted": 0,
             "rejected_small": 0, "rejected_large": 0, "rejected_shape": 0, "rejected_border": 0}
    h, w = rgb_image.shape[:2]
    mask = _foreground_mask(rgb_image)
    markers, r_est = _watershed_regions(rgb_image, mask)
    stats["estimated_radius_px"] = round(r_est, 1)
    if markers is None:
        return ([], stats) if return_stats else []

    regions = []
    for label in range(2, markers.max() + 1):
        region = np.uint8(markers == label) * 255
        contours, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue
        contour = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(contour)
        if area >= ABS_MIN_AREA:
            regions.append((contour, area))
    stats["candidates"] = len(regions)
    if not regions:
        return ([], stats) if return_stats else []

    median_area = float(np.median([a for _, a in regions]))
    cells = []
    for contour, area in regions:
        if area < MIN_AREA_FRAC * median_area:
            stats["rejected_small"] += 1
            continue
        if area > MAX_AREA_FRAC * median_area:
            stats["rejected_large"] += 1
            continue
        if _circularity(contour) < MIN_CIRCULARITY:
            stats["rejected_shape"] += 1
            continue
        x, y, cw, ch = cv2.boundingRect(contour)
        if x <= 1 or y <= 1 or x + cw >= w - 1 or y + ch >= h - 1:
            stats["rejected_border"] += 1
            continue
        crop = _cell_crop(rgb_image, contour, crop_size)
        cells.append(DetectedCell(centroid=(x + cw // 2, y + ch // 2), bbox=(x, y, cw, ch),
                                  crop=crop, area=area))
        if len(cells) >= MAX_CELLS:
            break

    stats["accepted"] = len(cells)
    return (cells, stats) if return_stats else cells


def _crop_square(rgb_image: np.ndarray, cx: int, cy: int, size: int):
    """Fixed-size square crop centred on (cx, cy) with edge padding. Kept for
    backwards compatibility; detect_cells now uses per-cell crops."""
    h, w = rgb_image.shape[:2]
    half = size // 2
    x0, x1, y0, y1 = cx - half, cx + half, cy - half, cy + half
    pads = (max(0, -y0), max(0, y1 - h), max(0, -x0), max(0, x1 - w))
    x0c, x1c, y0c, y1c = max(0, x0), min(w, x1), max(0, y0), min(h, y1)
    if x1c <= x0c or y1c <= y0c:
        return None
    crop = rgb_image[y0c:y1c, x0c:x1c]
    if any(pads):
        crop = cv2.copyMakeBorder(crop, *pads, cv2.BORDER_REPLICATE)
    if crop.shape[:2] != (size, size):
        crop = cv2.resize(crop, (size, size))
    return crop


def draw_annotations(rgb_image: np.ndarray, cells: list, labels: list = None, probs: list = None) -> np.ndarray:
    """
    Copy of rgb_image with each detected cell outlined.
    labels (list of bool, True = parasitized): red box for infected, thin green
    circle for uninfected. probs (optional) prints the infection probability
    above each infected cell so a health worker can check them by eye.
    """
    annotated = rgb_image.copy()
    h, w = annotated.shape[:2]
    thick = max(2, int(round(min(h, w) / 400)))
    font_scale = max(0.4, min(h, w) / 1500)
    for i, cell in enumerate(cells):
        x, y, cw, ch = cell.bbox
        if labels is None:
            cv2.circle(annotated, cell.centroid, max(cw, ch) // 2, (31, 111, 107), thick)
            continue
        if labels[i]:
            pad = max(3, cw // 10)
            cv2.rectangle(annotated, (x - pad, y - pad), (x + cw + pad, y + ch + pad), (239, 68, 68), thick + 1)
            if probs is not None:
                cv2.putText(annotated, f"{probs[i] * 100:.0f}%", (x - pad, max(12, y - pad - 4)),
                            cv2.FONT_HERSHEY_SIMPLEX, font_scale, (239, 68, 68), thick, cv2.LINE_AA)
        else:
            cv2.circle(annotated, cell.centroid, max(cw, ch) // 2, (16, 185, 129), max(1, thick - 1))
    return annotated
