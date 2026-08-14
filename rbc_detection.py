"""
rbc_detection.py
Detects and crops individual red blood cells from a full microscope
field-of-view photo (as opposed to a single pre-cropped cell), so users can
upload a real smear image the way a microscopist actually works with one.

Pipeline (classical CV, mirrors the segmentation approach used in the
original NIH malaria paper this project is built on):
  1. Grayscale + blur to reduce staining noise
  2. Otsu threshold to separate cells from background
  3. Distance transform + watershed to split touching/overlapping cells
  4. Filter detected regions by size/circularity to reject artifacts
  5. Crop a fixed-size square around each detected cell's centroid

This needs real tuning against real smear photos (thresholds below are
reasonable starting points, not final values) -- see the README for
calibration notes.
"""

from dataclasses import dataclass

import cv2
import numpy as np

MIN_CELL_AREA = 150        # pixels; rejects tiny specks/artifacts
MAX_CELL_AREA = 20000       # pixels; rejects large merged blobs that watershed failed to split
MIN_CIRCULARITY = 0.55      # 1.0 = perfect circle; RBCs are fairly round, debris often isn't
CROP_SIZE = 128             # matches the classifier's expected input size


@dataclass
class DetectedCell:
    centroid: tuple          # (x, y) in the original image
    bbox: tuple               # (x, y, w, h)
    crop: np.ndarray          # CROP_SIZE x CROP_SIZE x 3 uint8, ready for the classifier


def _circularity(contour) -> float:
    area = cv2.contourArea(contour)
    perimeter = cv2.arcLength(contour, True)
    if perimeter == 0:
        return 0.0
    return 4 * np.pi * area / (perimeter ** 2)


def detect_cells(rgb_image: np.ndarray) -> list:
    """
    rgb_image: (H, W, 3) uint8 array of a full smear field-of-view.
    Returns a list of DetectedCell, one per detected RBC.
    """
    h, w = rgb_image.shape[:2]
    gray = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # Cells are usually darker/more saturated than the pale background in
    # Giemsa-stained smears -- Otsu's method picks a good global threshold
    # automatically rather than needing a hand-tuned constant.
    _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Clean up small noise, then close small gaps within cells
    kernel = np.ones((3, 3), np.uint8)
    opened = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=2)
    sure_bg = cv2.dilate(opened, kernel, iterations=3)

    # Distance transform: pixels deep inside a cell have high values, pixels
    # near a cell's edge (including where two cells touch) have low values --
    # this is what lets watershed separate touching cells instead of merging them.
    dist_transform = cv2.distanceTransform(opened, cv2.DIST_L2, 5)
    _, sure_fg = cv2.threshold(dist_transform, 0.4 * dist_transform.max(), 255, 0)
    sure_fg = np.uint8(sure_fg)

    unknown = cv2.subtract(sure_bg, sure_fg)

    _, markers = cv2.connectedComponents(sure_fg)
    markers = markers + 1
    markers[unknown == 255] = 0

    color_for_watershed = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2BGR).copy()
    markers = cv2.watershed(color_for_watershed, markers)

    detected = []
    for label in range(2, markers.max() + 1):  # label 1 = background, -1 = watershed boundary
        mask = np.uint8(markers == label) * 255
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue
        contour = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(contour)

        if area < MIN_CELL_AREA or area > MAX_CELL_AREA:
            continue
        if _circularity(contour) < MIN_CIRCULARITY:
            continue

        x, y, cw, ch = cv2.boundingRect(contour)
        cx, cy = x + cw // 2, y + ch // 2

        crop = _crop_square(rgb_image, cx, cy, CROP_SIZE)
        if crop is None:
            continue

        detected.append(DetectedCell(centroid=(cx, cy), bbox=(x, y, cw, ch), crop=crop))

    return detected


def _crop_square(rgb_image: np.ndarray, cx: int, cy: int, size: int):
    """Crops a `size x size` square centered on (cx, cy), padding with edge
    pixels if the crop would run off the image boundary. Returns None only
    if the image itself is smaller than `size` in either dimension."""
    h, w = rgb_image.shape[:2]
    half = size // 2

    x0, x1 = cx - half, cx + half
    y0, y1 = cy - half, cy + half

    pad_left = max(0, -x0)
    pad_top = max(0, -y0)
    pad_right = max(0, x1 - w)
    pad_bottom = max(0, y1 - h)

    x0c, x1c = max(0, x0), min(w, x1)
    y0c, y1c = max(0, y0), min(h, y1)

    if x1c <= x0c or y1c <= y0c:
        return None

    crop = rgb_image[y0c:y1c, x0c:x1c]
    if any([pad_left, pad_top, pad_right, pad_bottom]):
        crop = cv2.copyMakeBorder(crop, pad_top, pad_bottom, pad_left, pad_right, cv2.BORDER_REPLICATE)

    if crop.shape[0] != size or crop.shape[1] != size:
        crop = cv2.resize(crop, (size, size))
    return crop


def draw_annotations(rgb_image: np.ndarray, cells: list, labels: list = None) -> np.ndarray:
    """
    Returns a copy of rgb_image with a circle drawn around each detected
    cell. If `labels` (list of bool, True=parasitized) is given, circles are
    color-coded: red for parasitized, green for uninfected.
    """
    annotated = rgb_image.copy()
    for i, cell in enumerate(cells):
        x, y, w, h = cell.bbox
        radius = max(w, h) // 2
        if labels is not None:
            color = (194, 72, 61) if labels[i] else (62, 142, 90)  # coral / green, matches UI palette
        else:
            color = (31, 111, 107)  # teal, "detected, not yet classified"
        cv2.circle(annotated, cell.centroid, radius, color, 2)
    return annotated
