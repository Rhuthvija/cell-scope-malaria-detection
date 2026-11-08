"""
app.py
Flask backend for CELL SCOPE: AI Hematology & Malaria Diagnostics Suite.
Includes MobileNetV2 classification, Grad-CAM explainability maps, risk gauge mapping,
patient database persistence, per-patient analytics, and PDF report downloads.
"""

import base64
import hmac
import time
from collections import defaultdict, deque
import io
import json
import logging
import os
import tempfile
import traceback
from datetime import datetime, timezone
os.environ['MPLCONFIGDIR'] = tempfile.mkdtemp()

import numpy as np
from flask import Flask, Response, jsonify, render_template, request, send_file
from PIL import Image

import db
import quality_check
import rbc_detection
import report
import stain_norm
from crypto_util import encryption_enabled

IMG_SIZE = 128
MODEL_PATH = "malaria_model.keras"
CLASS_INDICES_PATH = "class_indices.json"

CLASS_INDICES = {"Parasitized": 0, "Uninfected": 1}
if os.path.exists(CLASS_INDICES_PATH):
    try:
        with open(CLASS_INDICES_PATH, "r") as f:
            CLASS_INDICES = json.load(f)
    except Exception as e:
        print(f"Warning: Failed to read {CLASS_INDICES_PATH}: {e}")

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
# Uploads: cap request size and pixel count (guards against huge files and
# "decompression bomb" images that expand to gigabytes in memory).
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("CELLSCOPE_MAX_UPLOAD_MB", "10")) * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 40_000_000
ALLOWED_IMAGE_FORMATS = {"PNG", "JPEG", "BMP", "TIFF", "WEBP"}

# Optional access lock: set CELLSCOPE_PASSWORD (and optionally CELLSCOPE_USERNAME,
# default "cellscope") to require a login for every page and API call. Uses the
# browser's built-in login prompt, so the app's own UI is unchanged. /health stays
# open for Render's health checks.
AUTH_USER = os.environ.get("CELLSCOPE_USERNAME", "cellscope")
AUTH_PASSWORD = os.environ.get("CELLSCOPE_PASSWORD", "")
AUTH_EXEMPT = {"/health"}

# Simple per-IP rate limit on diagnosis (expensive: runs the model and writes to
# the DB). In-memory, which is fine for the single-worker deployment.
RATE_LIMIT_PER_MIN = int(os.environ.get("CELLSCOPE_RATE_LIMIT_PER_MIN", "30"))
_rate_hits = defaultdict(deque)


def _client_ip() -> str:
    fwd = request.headers.get("X-Forwarded-For", "")
    return fwd.split(",")[0].strip() if fwd else (request.remote_addr or "unknown")


@app.before_request
def _require_auth():
    if not AUTH_PASSWORD or request.path in AUTH_EXEMPT:
        return None
    auth = request.authorization
    if auth and auth.type == "basic" \
            and hmac.compare_digest(auth.username or "", AUTH_USER) \
            and hmac.compare_digest(auth.password or "", AUTH_PASSWORD):
        return None
    return Response("Login required", 401, {"WWW-Authenticate": 'Basic realm="CELL SCOPE", charset="UTF-8"'})


@app.before_request
def _rate_limit():
    if request.path != "/api/diagnose" or request.method != "POST" or RATE_LIMIT_PER_MIN <= 0:
        return None
    now = time.time()
    hits = _rate_hits[_client_ip()]
    while hits and now - hits[0] > 60:
        hits.popleft()
    if len(hits) >= RATE_LIMIT_PER_MIN:
        return jsonify({"success": False, "error": "Too many requests. Please wait a minute and try again."}), 429
    hits.append(now)
    return None


@app.after_request
def _security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("Permissions-Policy", "camera=(self), geolocation=(self), microphone=()")
    # Allows only this site plus the CDN/fonts the existing UI already uses.
    resp.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data: blob:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
    )
    if request.headers.get("X-Forwarded-Proto", request.scheme) == "https":
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    # Patient data must not be cached by browsers or proxies.
    if request.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.errorhandler(413)
def _too_large(_err):
    mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
    return jsonify({"success": False, "error": f"Image is too large (max {mb} MB)."}), 413


db.init_db()

_model = None

# ---------------------------------------------------------------------------
# MobileNetV2 Classifier & Grad-CAM Pipeline
# ---------------------------------------------------------------------------
# TODO: load trained MobileNetV2 weights if custom .h5, .pt, or .keras weights file provided
def get_model():
    global _model
    if _model is None:
        import tensorflow as tf
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(
                f"'{MODEL_PATH}' not found. Run train_model.py first to produce MobileNetV2 model."
            )
        _model = tf.keras.models.load_model(MODEL_PATH)
        print(f"[DEBUG MODEL] MobileNetV2 model loaded successfully from {MODEL_PATH}")
    return _model

def load_rgb(image_bytes: bytes) -> np.ndarray:
    """Decode an upload, accepting only real image formats (content is checked,
    not the file extension). Raises ValueError for anything else."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        if img.format not in ALLOWED_IMAGE_FORMATS:
            raise ValueError(f"unsupported format {img.format}")
        img = img.convert("RGB")
    except Image.DecompressionBombError as err:
        raise ValueError("image has too many pixels") from err
    except ValueError:
        raise
    except Exception as err:
        raise ValueError("not a valid image") from err
    return np.asarray(img)

def preprocess_for_model(rgb_image: np.ndarray, normalize_stain: bool = True) -> np.ndarray:
    if normalize_stain:
        try:
            rgb_image = stain_norm.normalize(rgb_image)
        except Exception:
            pass
    img = Image.fromarray(rgb_image).resize((IMG_SIZE, IMG_SIZE))
    arr = np.asarray(img, dtype=np.float32)
    return np.expand_dims(arr, axis=0)

def classify_rgb(rgb_image: np.ndarray, filename: str = "sample") -> float:
    """
    Runs binary classification inference (Parasitized vs Uninfected).
    Attempts to load trained MobileNetV2 Keras model if TensorFlow runtime is active,
    or runs biological Giemsa chromatin/ring-form morphological analysis.
    Returns: probability of parasitized in [0.0, 1.0].
    """
    # 1. Attempt Trained MobileNetV2 Neural Network Inference
    # TODO: load trained MobileNetV2 weights
    try:
        batch = preprocess_for_model(rgb_image)
        model = get_model()
        raw_pred = model.predict(batch, verbose=0)
        
        # Determine class index dynamically from class_indices.json
        if raw_pred.shape[-1] == 1:
            raw_val = float(raw_pred[0][0])
            # Index 1 = Uninfected (alphabetical order), Index 0 = Parasitized
            if CLASS_INDICES.get("Uninfected") == 1:
                prob_parasitized = 1.0 - raw_val
            else:
                prob_parasitized = raw_val
        else:
            para_idx = CLASS_INDICES.get("Parasitized", 0)
            prob_parasitized = float(raw_pred[0][para_idx])
            
        prob_parasitized = float(np.clip(prob_parasitized, 0.01, 0.99))
        print(f"[DEBUG INFERENCE] Model='MobileNetV2' file='{filename}' raw_pred={raw_pred.tolist()} -> prob_parasitized={prob_parasitized:.4f}")
        return prob_parasitized

    except Exception as model_err:
        # The colour heuristic below is NOT the trained model. Using it silently would
        # show confident-looking results that no model produced, so it only runs when
        # explicitly enabled (e.g. for UI demos without TensorFlow installed).
        if os.environ.get("CELLSCOPE_ALLOW_HEURISTIC") != "1":
            raise RuntimeError(
                "Trained model could not be loaded; refusing to fall back to the colour "
                "heuristic. Set CELLSCOPE_ALLOW_HEURISTIC=1 to allow it for demos."
            ) from model_err
        print("[WARNING] Using colour heuristic instead of the trained model.")
        # 2. Robust Biological Giemsa Stain & Chromatin Inclusion Analyzer
        import cv2
        gray = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2GRAY)
        
        # Segment erythrocyte from dark optical background
        cell_mask = gray > 25
        cell_pixels = int(np.sum(cell_mask))
        if cell_pixels < 40:
            print(f"[DEBUG INFERENCE] file='{filename}' -> Empty background -> prob=0.02")
            return 0.02

        r = rgb_image[:, :, 0].astype(float)
        g = rgb_image[:, :, 1].astype(float)
        b = rgb_image[:, :, 2].astype(float)

        mean_r = np.median(r[cell_mask]) if cell_pixels > 0 else 128
        mean_g = np.median(g[cell_mask]) if cell_pixels > 0 else 128
        mean_b = np.median(b[cell_mask]) if cell_pixels > 0 else 128
        mean_gray = np.median(gray[cell_mask]) if cell_pixels > 0 else 128

        is_pink_rbc = (mean_r > mean_b + 15)
        is_green_rbc = (mean_g > mean_r + 15) and (mean_g > mean_b)

        if is_pink_rbc:
            parasite_ring = cell_mask & (b > 90) & (b > g + 20) & (b > r - 30) & (b > mean_b + 20)
            cell_gray = gray.copy()
            cell_gray[~cell_mask] = int(mean_gray)
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
            blackhat = cv2.morphologyEx(cell_gray, cv2.MORPH_BLACKHAT, kernel)
            chromatin_dot = cell_mask & (blackhat > 15) & (parasite_ring | (r > g + 40) | (b > g + 15))
            parasite_signals = cell_mask & (parasite_ring | chromatin_dot)
        elif is_green_rbc:
            parasite_signals = cell_mask & ((b > g + 20) | (r > g + 20))
        else:
            color_dist = np.sqrt((r - mean_r)**2 + (g - mean_g)**2 + (b - mean_b)**2)
            cell_gray = gray.copy()
            cell_gray[~cell_mask] = int(mean_gray)
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
            blackhat = cv2.morphologyEx(cell_gray, cv2.MORPH_BLACKHAT, kernel)
            parasite_signals = cell_mask & (color_dist > 35) & ((b > g + 15) | (blackhat > 15))

        signal_pixels = int(np.sum(parasite_signals))
        signal_ratio = signal_pixels / float(cell_pixels)
        
        if signal_ratio > 0.010:
            prob = 0.88 + min(0.10, signal_ratio * 3.0)
        elif signal_ratio > 0.002:
            prob = 0.65 + min(0.20, signal_ratio * 15.0)
        else:
            prob = max(0.01, min(0.12, signal_ratio * 8.0))
            
        prob_parasitized = float(np.clip(prob, 0.01, 0.99))
        print(f"[DEBUG INFERENCE] Fallback='GiemsaMorphology' file='{filename}' signal_ratio={signal_ratio:.5f} -> prob_parasitized={prob_parasitized:.4f}")
        return prob_parasitized

def run_self_test():
    """Runs automated inference self-test on known parasitized and uninfected sample images."""
    import cv2
    # Create test uninfected cell
    uninfected_img = np.zeros((128, 128, 3), dtype=np.uint8)
    cv2.circle(uninfected_img, (64, 64), 45, (16, 185, 129), -1)
    cv2.circle(uninfected_img, (64, 64), 20, (160, 240, 200), -1)
    
    # Create test parasitized cell (ring trophozoite + chromatin nucleus)
    parasitized_img = np.zeros((128, 128, 3), dtype=np.uint8)
    cv2.circle(parasitized_img, (64, 64), 45, (236, 72, 153), -1)
    cv2.circle(parasitized_img, (55, 55), 10, (124, 58, 237), 2)
    cv2.circle(parasitized_img, (62, 50), 3, (244, 63, 94), -1)

    prob_uninfected = classify_rgb(uninfected_img, "selftest_uninfected.png")
    prob_parasitized = classify_rgb(parasitized_img, "selftest_parasitized.png")

    uninfected_ok = (prob_uninfected < 0.5)
    parasitized_ok = (prob_parasitized >= 0.5)
    all_passed = uninfected_ok and parasitized_ok

    return {
        "all_passed": all_passed,
        "class_indices": CLASS_INDICES,
        "uninfected_test": {
            "expected": "Uninfected",
            "prob_parasitized": round(prob_uninfected, 4),
            "predicted": "Uninfected" if prob_uninfected < 0.5 else "Parasitized",
            "passed": uninfected_ok
        },
        "parasitized_test": {
            "expected": "Parasitized",
            "prob_parasitized": round(prob_parasitized, 4),
            "predicted": "Parasitized" if prob_parasitized >= 0.5 else "Uninfected",
            "passed": parasitized_ok
        }
    }

# Warm up at startup: load the model and run one dummy prediction so the first
# real request isn't slowed by TensorFlow initialisation. (The synthetic-shape
# self-test is still available at /api/diagnose/selftest, but drawn circles are
# not real cells, so it is a smoke test, not a measure of accuracy.)
try:
    get_model().predict(np.zeros((1, IMG_SIZE, IMG_SIZE, 3), dtype=np.float32), verbose=0)
    print("[STARTUP] Model loaded and warmed up.")
except Exception as _e:
    print(f"[STARTUP] Model warm-up failed: {_e}")

def generate_gradcam_overlay(rgb_image: np.ndarray, prob_parasitized: float = None) -> str:
    """
    Generates Grad-CAM explainability heatmap.
    Uses MobileNetV2 last conv layer if TensorFlow runtime is active,
    or morphological parasite inclusion localization.
    
    Uses green (low) -> yellow -> red (high) activation intensity, a smooth
    per-image normalization, and a 40% overlay so cell morphology remains visible.
    """
    # 1. Attempt Neural Grad-CAM if TensorFlow is active
    try:
        import gradcam
        batch = preprocess_for_model(rgb_image)
        model = get_model()
        heatmap_png = gradcam.gradcam_overlay_png_bytes(
            rgb_image, model, batch, prob_parasitized=prob_parasitized
        )
        return "data:image/png;base64," + base64.b64encode(heatmap_png).decode()
    except Exception:
        # 2. Robust Biological Feature Localization & JET Colormap Compositing
        import cv2
        h, w = rgb_image.shape[:2]
        gray = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2GRAY)
        
        cell_mask = gray > 25
        if np.sum(cell_mask) < 40:
            cell_mask = (gray > 15) & (gray < 245)
            
        r = rgb_image[:, :, 0].astype(np.float32)
        g = rgb_image[:, :, 1].astype(np.float32)
        b = rgb_image[:, :, 2].astype(np.float32)
        
        is_pos = (prob_parasitized is not None and prob_parasitized >= 0.5)
        
        if is_pos or np.sum(cell_mask) > 50:
            mean_r = np.median(r[cell_mask]) if np.sum(cell_mask) > 0 else 128
            mean_g = np.median(g[cell_mask]) if np.sum(cell_mask) > 0 else 128
            mean_b = np.median(b[cell_mask]) if np.sum(cell_mask) > 0 else 128
            mean_gray = np.median(gray[cell_mask]) if np.sum(cell_mask) > 0 else 128

            is_pink_rbc = (mean_r > mean_b + 15)
            is_green_rbc = (mean_g > mean_r + 15) and (mean_g > mean_b)

            if is_pink_rbc:
                parasite_ring = cell_mask & (b > 90) & (b > g + 20) & (b > r - 30) & (b > mean_b + 20)
                cell_gray = gray.copy()
                cell_gray[~cell_mask] = int(mean_gray)
                kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
                blackhat = cv2.morphologyEx(cell_gray, cv2.MORPH_BLACKHAT, kernel)
                chromatin_dot = cell_mask & (blackhat > 15) & (parasite_ring | (r > g + 40) | (b > g + 15))
                raw_act = (parasite_ring.astype(np.float32) * 180.0) + (chromatin_dot.astype(np.float32) * 255.0)
            elif is_green_rbc:
                raw_act = ((b > g + 20) | (r > g + 20)).astype(np.float32) * 255.0 * cell_mask
            else:
                color_dist = np.sqrt((r - mean_r)**2 + (g - mean_g)**2 + (b - mean_b)**2)
                cell_gray = gray.copy()
                cell_gray[~cell_mask] = int(mean_gray)
                kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
                blackhat = cv2.morphologyEx(cell_gray, cv2.MORPH_BLACKHAT, kernel)
                raw_act = (color_dist * 1.5) + (blackhat.astype(np.float32) * 2.0)
                raw_act[~cell_mask] = 0.0

            has_strong_signal = (np.max(raw_act) > 15.0)
            
            if is_pos or has_strong_signal:
                smooth_act = cv2.GaussianBlur(raw_act, (25, 25), 0)
                norm_heatmap = cv2.normalize(smooth_act, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
            else:
                # Clean cell: baseline low activation (no high-activation red spots)
                grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
                grad_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
                mag = cv2.magnitude(grad_x, grad_y)
                mag[~cell_mask] = 0
                norm_heatmap = cv2.normalize(mag, None, 0, 40, cv2.NORM_MINMAX).astype(np.uint8)
                norm_heatmap = cv2.GaussianBlur(norm_heatmap, (15, 15), 0)
        else:
            norm_heatmap = np.zeros((h, w), dtype=np.uint8)

        # Use the same smooth, clinical presentation pipeline as neural Grad-CAM.
        # This keeps fallback maps sharp on small images and cool for negatives.
        from gradcam import overlay_heatmap
        blended = overlay_heatmap(
            rgb_image,
            norm_heatmap.astype(np.float32) / 255.0,
            suppress_hotspots=not is_pos,
        )
        return image_to_base64(blended)

def image_to_base64(rgb_image: np.ndarray) -> str:
    buf = io.BytesIO()
    Image.fromarray(rgb_image).save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

def get_risk_band(predicted_class: str, confidence: float, parasitemia_pct: float = 0.0,
                  mode: str = "single", cells_parasitized: int = 0) -> dict:
    """
    Deterministic risk evaluation.

    Severity is driven by PARASITEMIA (share of infected red cells), which is what
    clinicians use; model confidence only expresses how sure the model is.
    Earlier versions mapped "confidence >= 85%" straight to Critical, so a single
    clearly-infected cell was labelled an emergency. Now:
      * Full smear:  >=5% parasitemia -> Critical, >=2% -> High, otherwise Moderate
                     (a single, low-confidence positive cell stays Moderate).
      * Single cell: parasitemia can't be measured from one cell, so a positive is
                     High (confident) or Moderate (uncertain), never Critical.
    """
    conf = float(np.clip(confidence, 50.0, 100.0))

    if predicted_class == "Uninfected":
        if conf >= 90.0:
            band_key, band = "clear", "Negative / Clear"
            angle = -85.0 + (100.0 - conf) * 2.5            # -85 .. -60
            tagline = "No parasites detected. Re-test if fever continues."
        else:
            band_key, band = "low", "Low risk"
            angle = -60.0 + (90.0 - conf) * 1.0             # -60 .. -20
            tagline = "Likely clear, but uncertain. Confirm with RDT if fever is present."
    elif mode == "smear":
        weak_single = cells_parasitized <= 1 and conf < 90.0
        if parasitemia_pct >= 5.0 and not weak_single:
            band_key, band = "critical", "Critical risk"
            angle = 60.0 + min(parasitemia_pct - 5.0, 13.0) * 2.0   # 60 .. 86
            tagline = "High parasite load. Refer to a doctor / PHC immediately."
        elif parasitemia_pct >= 2.0 and not weak_single:
            band_key, band = "high", "High risk"
            angle = 20.0 + (parasitemia_pct - 2.0) * 12.0           # 20 .. 56
            tagline = "Malaria parasites detected. Confirm with RDT and start treatment today."
        else:
            band_key, band = "moderate", "Moderate risk"
            angle = -15.0 + (conf - 50.0) * 0.6                     # -15 .. 15
            tagline = "Few infected cells seen. Confirm with RDT or a trained microscopist."
    else:  # single cell, Parasitized
        if conf >= 85.0:
            band_key, band = "high", "High risk"
            angle = 20.0 + (conf - 85.0) * 2.0                      # 20 .. 50
            tagline = "Infected cell detected. Test a full smear or RDT today."
        else:
            band_key, band = "moderate", "Moderate risk"
            angle = -15.0 + (conf - 50.0) * 0.85                    # -15 .. 15
            tagline = "Possible infection. Confirm with RDT or a full smear."

    angle = round(float(np.clip(angle, -88.0, 88.0)), 1)
    risk_val = round((angle + 90.0) / 180.0 * 100.0, 1)
    refer = band_key in ("high", "critical")

    return {
        "band": band_key,
        "risk_band": band,
        "class": predicted_class,
        "confidence": conf,
        "risk_value": risk_val,
        "needle_angle": angle,
        "tagline": tagline,
        "refer": refer,
    }

compute_risk_assessment = get_risk_band


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/track")
def track():
    return render_template("index.html")

@app.route("/smear")
def smear():
    return render_template("index.html")

# ---------------------------------------------------------------------------
# Atomic MobileNet Diagnosis & Persistence Pipeline
# ---------------------------------------------------------------------------
@app.route("/api/diagnose/selftest", methods=["GET"])
def api_diagnose_selftest():
    """Self-test endpoint validating inference on known parasitized and uninfected samples."""
    test_results = run_self_test()
    status_code = 200 if test_results["all_passed"] else 500
    return jsonify(test_results), status_code

@app.route("/api/diagnose", methods=["POST"])
def api_diagnose():
    name = (request.form.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Patient name is required."}), 400

    patient_code = (request.form.get("patient_code") or "").strip()
    age = request.form.get("age") or 30
    gender = request.form.get("gender") or "Male"
    phone = (request.form.get("phone") or "").strip()
    mode = request.form.get("mode") or "single"

    # Rural surveillance fields (all optional)
    village = (request.form.get("village") or "").strip()[:80]
    district = (request.form.get("district") or "").strip()[:80]
    health_worker = (request.form.get("health_worker") or "").strip()[:80]

    def _coord(key, lo, hi):
        try:
            v = float(request.form.get(key, ""))
            return v if lo <= v <= hi else None
        except (TypeError, ValueError):
            return None

    latitude = _coord("latitude", -90.0, 90.0)
    longitude = _coord("longitude", -180.0, 180.0)

    # Image upload check
    filename = "unknown"
    
    if "image" in request.files and request.files["image"].filename != "":
        file = request.files["image"]
        filename = file.filename
        image_bytes = file.read()
        try:
            rgb_image = load_rgb(image_bytes)
        except ValueError as err:
            return jsonify({"success": False,
                            "error": f"Please upload a PNG or JPEG blood smear image ({err})."}), 400
    else:
        # Never diagnose a made-up image and save it to a patient record.
        return jsonify({"success": False, "error": "Please upload a blood smear image."}), 400

    # 0. Image quality check (blur / too dark / overexposed). Reported as a
    # warning rather than a hard block, because NIH-style single-cell crops have
    # dark backgrounds that can trip the brightness threshold.
    try:
        quality = quality_check.check_image_quality(rgb_image)
    except Exception as err:
        quality = {"ok": True, "issues": [], "metrics": {}, "error": str(err)}

    # 1. Model Inference
    try:
        if mode == "smear":
            cells = rbc_detection.detect_cells(rgb_image)
            if not cells:
                # Never invent a result: if segmentation finds no cells, say so.
                return jsonify({
                    "success": False,
                    "error": "No red blood cells were detected in this image. Check focus and "
                             "magnification, or use single-cell mode with a cropped cell image."
                }), 422
            cell_probs = [classify_rgb(c.crop, filename=f"crop_{c.centroid}") for c in cells]
            cells_analyzed = len(cells)
            cells_parasitized = sum(1 for p in cell_probs if p >= 0.5)
            parasitemia_pct = round((cells_parasitized / cells_analyzed) * 100, 2)
            # A smear is positive if ANY cell is parasitized, not only when most cells are.
            # The most suspicious cell's probability drives the smear-level label and confidence;
            # parasitemia_pct (share of infected cells) still drives the risk band.
            prob_parasitized = max(cell_probs)
        else:
            prob_parasitized = classify_rgb(rgb_image, filename=filename)
            cells_analyzed = 1
            cells_parasitized = 1 if prob_parasitized >= 0.5 else 0
            # Parasitemia (% of infected red cells) can't be measured from one cell.
            parasitemia_pct = None
    except RuntimeError as err:
        return jsonify({"success": False, "error": str(err)}), 503

    is_parasitized = (prob_parasitized >= 0.5)
    label = "Parasitized" if is_parasitized else "Uninfected"
    confidence_score = round((prob_parasitized if is_parasitized else (1.0 - prob_parasitized)) * 100, 1)

    # 2. Generate Explainability Heatmap & Base64 Images
    image_b64 = image_to_base64(rgb_image)
    heatmap_b64 = generate_gradcam_overlay(rgb_image, prob_parasitized=prob_parasitized)

    print(f"[DIAGNOSIS COMPLETE] Mode='{mode}' Result='{label}' Conf={confidence_score}% Parasitemia={parasitemia_pct}")

    # 3. Deterministic Risk Band, Needle Angle & Dynamic Tagline
    risk_info = compute_risk_assessment(label, confidence_score, parasitemia_pct or 0.0,
                                        mode=mode, cells_parasitized=cells_parasitized)

    # 4. Create or Get Patient & Append Visit Record in DB
    patient_id = db.create_or_get_patient(name, patient_code, age, gender, phone)
    patient = db.get_patient(patient_id)

    visit_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    visit_id = db.add_visit(
        patient_id=patient_id,
        visit_date=visit_date,
        cells_analyzed=cells_analyzed,
        cells_parasitized=cells_parasitized,
        diagnosis_result=label,
        confidence_score=confidence_score,
        risk_band=risk_info["risk_band"],
        risk_tagline=risk_info["tagline"],
        image_data=image_b64,
        heatmap_data=heatmap_b64,
        village=village,
        district=district,
        health_worker=health_worker,
        latitude=latitude,
        longitude=longitude,
        referred=risk_info["refer"],
    )

    records = db.get_all_records_with_latest_visit()

    return jsonify({
        "success": True,
        "message": "Diagnosis evaluated and saved to patient record.",
        "quality": quality,
        "patient": patient,
        "diagnosis": {
            "visit_id": visit_id,
            "date": visit_date,
            "label": label,
            "confidence_score": confidence_score,
            "parasitemia_pct": parasitemia_pct,
            "band": risk_info.get("band", "clear"),
            "risk_band": risk_info["risk_band"],
            "risk_value": risk_info["risk_value"],
            "needle_angle": risk_info["needle_angle"],
            "risk_tagline": risk_info["tagline"],
            "refer": risk_info["refer"],
            "mode": mode,
            "cells_analyzed": cells_analyzed,
            "cells_parasitized": cells_parasitized,
            "village": village,
            "district": district,
            "health_worker": health_worker,
            "image_data": image_b64,
            "heatmap_data": heatmap_b64
        },
        "records": records
    }), 201

# ---------------------------------------------------------------------------
# Patient Records API Endpoint
# ---------------------------------------------------------------------------
@app.route("/api/patient-records", methods=["GET"])
def api_patient_records():
    records = db.get_all_records_with_latest_visit()
    return jsonify(records)

# ---------------------------------------------------------------------------
# Per-Patient Analytics API Endpoint
# ---------------------------------------------------------------------------
@app.route("/api/patients/<int:patient_id>/analytics", methods=["GET"])
def api_patient_analytics(patient_id):
    patient = db.get_patient(patient_id)
    if not patient:
        return jsonify({"error": "Patient not found."}), 404

    visits = db.list_visits(patient_id)
    total_tests = len(visits)
    positive_count = sum(1 for v in visits if v["diagnosis_result"] in ["Parasitized", "Malaria Detected"])
    latest = visits[-1] if visits else {}

    trend = db.treatment_response(visits)

    timeline = [
        {
            "visit_id": v["id"],
            "date": v["visit_date"],
            "parasitemia_pct": v["parasitemia_pct"],
            "confidence": v["confidence_score"],
            "label": v["diagnosis_result"],
            "risk_band": v["risk_band"],
            "risk_tagline": v["risk_tagline"]
        }
        for v in visits
    ]

    return jsonify({
        "patient": patient,
        "total_tests": total_tests,
        "positive_count": positive_count,
        "negative_count": total_tests - positive_count,
        "latest_result": latest.get("diagnosis_result", "Uninfected"),
        "latest_confidence": latest.get("confidence_score", 0),
        "trend_indicator": trend,
        "timeline": timeline
    })

# ---------------------------------------------------------------------------
# Data Science Analytics Endpoint (All Patients Overview)
# ---------------------------------------------------------------------------
@app.route("/api/analytics-data", methods=["GET"])
def api_analytics_data():
    analytics = db.get_analytics_dataset()
    patients = db.list_patients()
    analytics["patients_list"] = patients
    return jsonify(analytics)

@app.route("/api/patients", methods=["GET", "POST"], strict_slashes=False)
@app.route("/api/patients/save", methods=["POST"], strict_slashes=False)
def api_patients():
    if request.method == "POST":
        try:
            data = request.get_json(silent=True) or request.form or {}
            app.logger.info("[PATIENT SAVE] Payload received: %s", data)

            name = (data.get("name") or "").strip()
            if not name:
                return jsonify({"success": False, "error": "Patient name is required."}), 400

            age_raw = data.get("age")
            try:
                age = int(age_raw) if age_raw is not None and str(age_raw).strip() != "" else 30
                if age < 1 or age > 120:
                    return jsonify({"success": False, "error": "Age must be between 1 and 120."}), 400
            except (ValueError, TypeError):
                return jsonify({"success": False, "error": "Age must be a valid integer between 1 and 120."}), 400

            patient_code = (data.get("patient_code") or "").strip()
            gender = (data.get("gender") or "Male").strip()
            phone = (data.get("phone") or "").strip()

            # Check if record already existed prior to save
            existing = db.get_patient_by_code(patient_code)
            
            patient_id = db.create_or_get_patient(
                name=name,
                patient_code=patient_code,
                age=age,
                gender=gender,
                phone=phone
            )
            patient = db.get_patient(patient_id)
            if not patient:
                return jsonify({"success": False, "error": "Failed to retrieve saved patient record from database."}), 500

            visits = db.list_visits(patient_id)
            app.logger.info("[PATIENT SAVE] Successfully saved: %s (ID: %s, Code: %s, Visits: %d)", patient["name"], patient["id"], patient["patient_code"], len(visits))

            return jsonify({
                "success": True,
                "message": "Patient profile saved to database.",
                "patient": patient,
                "visit_count": len(visits),
                "is_new": (existing is None)
            }), 200

        except Exception as ex:
            app.logger.exception("[PATIENT SAVE] Unexpected server error: %s", ex)
            traceback.print_exc()
            return jsonify({
                "success": False,
                "error": f"Server database error: {str(ex)}"
            }), 500

    return jsonify(db.list_patients())

@app.route("/api/patients/<int:patient_id>/visits", methods=["GET", "POST"])
def api_visits(patient_id):
    patient = db.get_patient(patient_id)
    if not patient:
        return jsonify({"error": "Patient not found."}), 404

    if request.method == "GET":
        visits = db.list_visits(patient_id)
        return jsonify({
            "patient": patient,
            "visits": visits,
            "trend": db.treatment_response(visits),
        })

    visit_date = request.form.get("visit_date", "").strip() or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cell_count = int(request.form.get("cell_count", 100))
    parasite_count = int(request.form.get("parasite_count", 0))
    label = "Parasitized" if parasite_count > 0 else "Uninfected"

    visit_id = db.add_visit(patient_id, visit_date, cell_count, parasite_count, label)
    visits = db.list_visits(patient_id)

    return jsonify({
        "visit_id": visit_id,
        "visits": visits,
        "trend": db.treatment_response(visits),
    }), 201

@app.route("/api/visits/<int:visit_id>/details", methods=["GET"])
def api_visit_details(visit_id):
    visit = db.get_visit_by_id(visit_id)
    if not visit:
        return jsonify({"error": "Visit record not found."}), 404
    return jsonify(visit)

@app.route("/api/visits/<int:visit_id>/report", methods=["GET"])
def api_visit_report(visit_id):
    visit = db.get_visit_by_id(visit_id)
    if not visit:
        return jsonify({"error": "Visit record not found."}), 404

    tmp_path = os.path.join(tempfile.gettempdir(), f"cellscope_visit_report_{visit_id}.pdf")
    report.generate_visit_report(visit, tmp_path)

    patient_name = visit.get("patient_name") or visit.get("name") or "patient"
    safe_name = "".join(c for c in patient_name if c.isalnum() or c in " _-").strip() or "patient"
    return send_file(
        tmp_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"cellscope_diagnostic_report_{safe_name}_v{visit_id}.pdf",
    )

@app.route("/api/patients/<int:patient_id>/report", methods=["GET"])
def api_patient_report(patient_id):
    patient = db.get_patient(patient_id)
    if not patient:
        return jsonify({"error": "Patient not found."}), 404

    visits = db.list_visits(patient_id)
    trend = db.treatment_response(visits)

    tmp_path = os.path.join(tempfile.gettempdir(), f"cellscope_report_patient_{patient_id}.pdf")
    report.generate_patient_report(patient, visits, trend, tmp_path)

    safe_name = "".join(c for c in patient["name"] if c.isalnum() or c in " _-").strip() or "patient"
    return send_file(
        tmp_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"cellscope_report_{safe_name}.pdf",
    )

@app.route("/api/outbreaks", methods=["GET"])
def api_outbreaks():
    """Village-level case clusters for the outbreak map."""
    try:
        days = max(1, min(int(request.args.get("days", 14)), 90))
        min_pos = max(1, min(int(request.args.get("min_positive", 3)), 50))
    except ValueError:
        return jsonify({"error": "days and min_positive must be integers"}), 400
    return jsonify(db.get_outbreak_summary(days=days, hotspot_min_positive=min_pos))


@app.route("/api/referrals", methods=["GET"])
def api_referrals():
    """Patients flagged High / Critical risk who should be seen by a doctor."""
    try:
        days = max(1, min(int(request.args.get("days", 30)), 365))
    except ValueError:
        return jsonify({"error": "days must be an integer"}), 400
    return jsonify(db.get_referrals(days=days))


@app.route("/health")
def health():
    return jsonify({"model_loaded": os.path.exists(MODEL_PATH), "status": "active",
                    "encryption_at_rest": encryption_enabled(), "auth_enabled": bool(AUTH_PASSWORD)})

if __name__ == "__main__":
    # Render (and most hosts) assign the port through $PORT; 5050 is the local default.
    port = int(os.environ.get("PORT", 5050))
    debug = os.environ.get("FLASK_DEBUG") == "1"
    print(f"CELL SCOPE Server running on http://0.0.0.0:{port}")
    app.run(debug=debug, host="0.0.0.0", port=port)
