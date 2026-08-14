"""
stain_norm.py
Macenko stain normalization for H&E/Giemsa-style stained microscopy images.

Different labs/slides/scanners produce images with the same biological content
but different color casts. This corrects for that by estimating each image's
actual stain vectors (via SVD on the optical density of the image) and
remapping them to match a fixed reference image's stain vectors -- so a
purple-heavy slide and a pink-heavy slide of the same cell type end up with
comparable color statistics before they're fed to the classifier.

Reference:
  Macenko et al., "A method for normalizing histology slides for
  quantitative analysis", ISBI 2009.

This is a from-scratch implementation (the commonly used `staintools`
package pulls in a `spams` dependency that's awkward to build in a lot of
environments -- this avoids that entirely with just numpy).
"""

import numpy as np

# A reference cell image's stain vectors, precomputed once from a
# representative NIH dataset image. Every image gets normalized toward this
# so all training/inference happens in a consistent color space.
# (Regenerate this from your own reference image with `fit_reference()` below
# if your dataset's typical staining looks meaningfully different.)
DEFAULT_STAIN_VECTORS = np.array([
    [0.65, 0.70, 0.29],   # stain 1 (roughly the "purple" hematoxylin-like component)
    [0.27, 0.90, 0.34],   # stain 2 (roughly the "pink" eosin-like component)
])
DEFAULT_MAX_CONCENTRATIONS = np.array([1.5, 1.0])


def _rgb_to_od(image: np.ndarray) -> np.ndarray:
    """RGB -> optical density. OD = -log10(I / I0), I0=255 (white light)."""
    image = image.astype(np.float64)
    image = np.maximum(image, 1.0)  # avoid log(0)
    od = -np.log10(image / 255.0)
    return np.nan_to_num(od, nan=0.0, posinf=5.0, neginf=0.0)


def _od_to_rgb(od: np.ndarray) -> np.ndarray:
    rgb = 255.0 * np.power(10.0, -np.clip(od, 0.0, 5.0))
    return np.clip(np.nan_to_num(rgb, nan=255.0, posinf=255.0, neginf=0.0), 0, 255).astype(np.uint8)


def _estimate_stain_vectors(od: np.ndarray, beta: float = 0.15, alpha_percentile: float = 1.0):
    """Estimate the two dominant stain vectors from an image's optical density
    via SVD, following Macenko's method."""
    od_flat = od.reshape(-1, 3)
    od_flat = od_flat[np.all(od_flat > beta, axis=1)]  # drop near-white/background pixels

    if od_flat.shape[0] < 10:
        # Not enough tissue/cell signal (e.g. a mostly-blank image) -- fall back
        # to the default vectors rather than fitting noise.
        return DEFAULT_STAIN_VECTORS, DEFAULT_MAX_CONCENTRATIONS

    # Project onto the plane of the two largest principal components
    od_flat = np.nan_to_num(od_flat.astype(np.float64), nan=0.0, posinf=5.0, neginf=0.0)
    cov = np.cov(od_flat.T)
    if np.any(np.isnan(cov)) or np.any(np.isinf(cov)):
        return DEFAULT_STAIN_VECTORS, DEFAULT_MAX_CONCENTRATIONS
    eigvals, eigvecs = np.linalg.eigh(cov)
    top2 = eigvecs[:, [-1, -2]].astype(np.float64)
    top2 = np.nan_to_num(top2, nan=0.0, posinf=1.0, neginf=-1.0)
    projected = np.matmul(od_flat, top2)

    angles = np.arctan2(projected[:, 1], projected[:, 0])
    min_angle = np.percentile(angles, alpha_percentile)
    max_angle = np.percentile(angles, 100 - alpha_percentile)

    v_min = top2 @ np.array([np.cos(min_angle), np.sin(min_angle)])
    v_max = top2 @ np.array([np.cos(max_angle), np.sin(max_angle)])

    if v_min[0] > v_max[0]:
        stain1, stain2 = v_min, v_max
    else:
        stain1, stain2 = v_max, v_min

    stain_vectors = np.array([stain1, stain2])
    norms = np.linalg.norm(stain_vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1
    stain_vectors = stain_vectors / norms

    # Concentrations = how much of each stain vector is needed to reconstruct
    # the image's OD (least-squares solve), then take the 99th percentile as
    # this image's "max" concentration for scaling.
    concentrations = np.linalg.lstsq(stain_vectors.T, od_flat.T, rcond=None)[0]
    max_concentrations = np.percentile(concentrations, 99, axis=1)
    max_concentrations[max_concentrations == 0] = 1

    return stain_vectors, max_concentrations


def normalize(image: np.ndarray, beta: float = 0.15) -> np.ndarray:
    """
    Normalize a single RGB image (H, W, 3 uint8 array) toward the reference
    stain vectors. Returns an RGB uint8 array of the same shape.
    """
    if np.max(np.std(image.astype(np.float64), axis=(0, 1))) < 5.0:
        return image
    try:
        od = _rgb_to_od(image)
        h, w, _ = image.shape
        od_flat = np.nan_to_num(od.reshape(-1, 3).astype(np.float64), nan=0.0, posinf=5.0, neginf=0.0)

        src_vectors, src_max_conc = _estimate_stain_vectors(od, beta=beta)
        if src_vectors is None or np.any(np.isnan(src_vectors)):
            return image

        src_max_conc = np.where(src_max_conc <= 0, 1.0, src_max_conc)

        # Concentrations of this image under its own estimated stain vectors
        concentrations = np.linalg.lstsq(src_vectors.T, od_flat.T, rcond=None)[0]
        concentrations = np.nan_to_num(concentrations, nan=0.0, posinf=0.0, neginf=0.0)
        concentrations = (concentrations / src_max_conc[:, None]) * DEFAULT_MAX_CONCENTRATIONS[:, None]
        concentrations = np.clip(np.nan_to_num(concentrations, nan=0.0, posinf=5.0, neginf=0.0), 0.0, 5.0).astype(np.float64)

        # Reconstruct using the reference stain vectors instead of this image's own
        od_normalized = np.matmul(DEFAULT_STAIN_VECTORS.T.astype(np.float64), concentrations)
        od_normalized = np.clip(np.nan_to_num(od_normalized, nan=0.0, posinf=5.0, neginf=0.0), 0.0, 5.0)
        normalized = _od_to_rgb(od_normalized.T.reshape(h, w, 3))
        return normalized
    except Exception:
        return image


def fit_reference(reference_image: np.ndarray):
    """
    Call this once on a representative, well-stained image from your dataset
    to replace DEFAULT_STAIN_VECTORS / DEFAULT_MAX_CONCENTRATIONS with values
    tuned to your data, instead of the generic defaults baked into this file.
    Prints the values to paste back in above.
    """
    od = _rgb_to_od(reference_image)
    vectors, max_conc = _estimate_stain_vectors(od)
    print("DEFAULT_STAIN_VECTORS = np.array(", vectors.tolist(), ")")
    print("DEFAULT_MAX_CONCENTRATIONS = np.array(", max_conc.tolist(), ")")
    return vectors, max_conc
