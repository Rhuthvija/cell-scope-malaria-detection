"""
quality_check.py
Fast, pre-classification checks on an uploaded image: is it too blurry, too
dark, or too bright to trust a prediction on? Catches the most common
real-world failure mode -- bad phone photos through a cheap microscope
adapter -- before they reach the model and produce a confident-sounding
but meaningless result.
"""

import cv2
import numpy as np

BLUR_THRESHOLD = 60.0       # below this Laplacian variance, call it "too blurry"
DARK_THRESHOLD = 40.0        # mean brightness (0-255) below this = too dark
BRIGHT_THRESHOLD = 235.0     # mean brightness above this = blown out / overexposed


def check_image_quality(rgb_image: np.ndarray) -> dict:
    """
    rgb_image: (H, W, 3) uint8 array.
    Returns {"ok": bool, "issues": [...], "metrics": {...}} -- issues is a
    list of short human-readable problems found, empty if the image passes.
    """
    gray = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2GRAY)

    blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
    brightness = float(gray.mean())

    issues = []
    if blur_score < BLUR_THRESHOLD:
        issues.append(f"Image looks blurry (sharpness score {blur_score:.1f}, expected >{BLUR_THRESHOLD:.0f}). Try retaking with better focus.")
    if brightness < DARK_THRESHOLD:
        issues.append(f"Image looks too dark (brightness {brightness:.0f}/255). Check the microscope's light source.")
    if brightness > BRIGHT_THRESHOLD:
        issues.append(f"Image looks overexposed (brightness {brightness:.0f}/255). Reduce the light source or exposure.")

    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "metrics": {"blur_score": round(blur_score, 1), "brightness": round(brightness, 1)},
    }
