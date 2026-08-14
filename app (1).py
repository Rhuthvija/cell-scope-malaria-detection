"""
app.py
Flask backend for Cell Scope: single-cell classification, full-smear RBC
detection + batch classification, patient/visit tracking, and PDF reports.

Run:
  python app.py
Then open http://localhost:5000

Requires malaria_model.keras to exist in this folder (produced by train_model.py).
"""

import base64
import io
import os
import tempfile

import numpy as np
from flask import Flask, jsonify, render_template, request, send_file
from PIL import Image

import db
import quality_check
import rbc_detection
import report
import stain_norm

IMG_SIZE = 128
MODEL_PATH = "malaria_model.keras"

# ImageDataGenerator.flow_from_directory sorts class folders alphabetically:
# "Parasitized" < "Uninfected", so index 0 = Parasitized, index 1 = Uninfected.
# The model's sigmoid output is P(Uninfected).
CLASS_NAMES = ["Parasitized", "Uninfected"]

# Predictions with P(parasitized) inside this band are too close to call
# confidently and get flagged for manual review instead of a forced label.
UNCERTAIN_LOW, UNCERTAIN_HIGH = 0.40, 0.60

app = Flask(__name__)
db.init_db()

_model = None  # lazy-loaded so the app starts instantly even before training is done


def get_model():
    global _model
    if _model is None:
        import tensorflow as tf

        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(
                f"'{MODEL_PATH}' not found. Run train_model.py first to produce it."
            )
        _model = tf.keras.models.load_model(MODEL_PATH)
    return _model


def load_rgb(image_bytes: bytes) -> np.ndarray:
    """Bytes -> (H, W, 3) uint8 RGB array, the common starting point for
    quality checks, stain normalization, detection, and Grad-CAM."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    return np.asarray(img)


def preprocess_for_model(rgb_image: np.ndarray, normalize_stain: bool = True) -> np.ndarray:
    """RGB array -> (1, IMG_SIZE, IMG_SIZE, 3) float32 batch ready for the
    model (which applies its own preprocess_input internally, matching
    train_model.py)."""
    if normalize_stain:
        try:
            rgb_image = stain_norm.normalize(rgb_image)
        except Exception:
            pass  # if normalization fails on a weird image, fall back to the raw crop rather than erroring out

    img = Image.fromarray(rgb_image).resize((IMG_SIZE, IMG_SIZE))
    arr = np.asarray(img, dtype=np.float32)
    return np.expand_dims(arr, axis=0)


def classify_rgb(rgb_image: np.ndarray) -> float:
    """Returns P(parasitized) for a single cell image (as an RGB array)."""
    batch = preprocess_for_model(rgb_image)
    model = get_model()
    prob_uninfected = float(model.predict(batch, verbose=0)[0][0])
    return 1.0 - prob_uninfected


def classify_image_bytes(image_bytes: bytes) -> float:
    return classify_rgb(load_rgb(image_bytes))


def build_result(prob_parasitized: float) -> dict:
    prob_uninfected = 1.0 - prob_parasitized
    is_uncertain = UNCERTAIN_LOW <= prob_parasitized <= UNCERTAIN_HIGH
    label = CLASS_NAMES[1] if prob_uninfected >= 0.5 else CLASS_NAMES[0]
    confidence = max(prob_uninfected, prob_parasitized)
    return {
        "label": "Uncertain" if is_uncertain else label,
        "uncertain": is_uncertain,
        "confidence": round(confidence * 100, 1),
        "prob_parasitized": round(prob_parasitized * 100, 1),
        "prob_uninfected": round(prob_uninfected * 100, 1),
    }


def image_to_base64(rgb_image: np.ndarray) -> str:
    buf = io.BytesIO()
    Image.fromarray(rgb_image).save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/track")
def track():
    return render_template("track.html")


@app.route("/smear")
def smear():
    return render_template("smear.html")


@app.route("/predict", methods=["POST"])
def predict():
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded."}), 400

    file = request.files["image"]
    if file.filename == "":
        return jsonify({"error": "No image selected."}), 400

    try:
        image_bytes = file.read()
        rgb_image = load_rgb(image_bytes)
    except Exception:
        return jsonify({"error": "Couldn't read that as an image. Try a .png or .jpg cell photo."}), 400

    quality = quality_check.check_image_quality(rgb_image)

    try:
        prob_parasitized = classify_rgb(rgb_image)
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 503
    except Exception:
        return jsonify({"error": "Couldn't classify that image."}), 400

    result = build_result(prob_parasitized)
    result["quality"] = quality

    # Grad-CAM heatmap: shows which part of the cell drove the prediction.
    # Best-effort -- if it fails for any reason we still return the
    # classification rather than blocking the whole response on it.
    try:
        import gradcam
        batch = preprocess_for_model(rgb_image)
        model = get_model()
        heatmap_png = gradcam.gradcam_overlay_png_bytes(rgb_image, model, batch)
        result["heatmap"] = "data:image/png;base64," + base64.b64encode(heatmap_png).decode()
    except Exception:
        result["heatmap"] = None

    return jsonify(result)


@app.route("/health")
def health():
    return jsonify({"model_loaded": os.path.exists(MODEL_PATH)})


# ---------------------------------------------------------------------------
# Full smear analysis: detect individual RBCs in an uncropped microscope
# photo, classify each one, return an annotated image + aggregate stats.
# ---------------------------------------------------------------------------

@app.route("/api/analyze-smear", methods=["POST"])
def analyze_smear():
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded."}), 400

    file = request.files["image"]
    if file.filename == "":
        return jsonify({"error": "No image selected."}), 400

    try:
        image_bytes = file.read()
        rgb_image = load_rgb(image_bytes)
    except Exception:
        return jsonify({"error": "Couldn't read that as an image."}), 400

    quality = quality_check.check_image_quality(rgb_image)

    try:
        cells = rbc_detection.detect_cells(rgb_image)
    except Exception:
        return jsonify({"error": "Cell detection failed on this image."}), 400

    if not cells:
        return jsonify({
            "error": "No cells detected in this image. Try a clearer, well-lit smear photo.",
            "quality": quality,
        }), 200

    labels = []
    cell_results = []
    try:
        for cell in cells:
            prob_parasitized = classify_rgb(cell.crop)
            result = build_result(prob_parasitized)
            labels.append(result["label"] == "Parasitized")
            cell_results.append({
                "centroid": cell.centroid,
                "bbox": cell.bbox,
                **result,
            })
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 503

    annotated = rbc_detection.draw_annotations(rgb_image, cells, labels)

    confident_results = [r for r in cell_results if not r["uncertain"]]
    parasitized_count = sum(1 for r in confident_results if r["label"] == "Parasitized")
    total_confident = len(confident_results)
    ci_low, ci_high = db.wilson_confidence_interval(parasitized_count, total_confident) if total_confident else (0, 0)
    pct = round((parasitized_count / total_confident) * 100, 2) if total_confident else 0.0

    return jsonify({
        "quality": quality,
        "annotated_image": image_to_base64(annotated),
        "cells_detected": len(cells),
        "cells_confident": total_confident,
        "cells_uncertain": len(cells) - total_confident,
        "cells_parasitized": parasitized_count,
        "parasitemia_pct": pct,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "tier": db.parasitemia_tier(pct),
        "per_cell": cell_results,
    })


# ---------------------------------------------------------------------------
# Patient tracking: batch-classify a set of cell images into one "visit"
# with an aggregate parasitemia %, then chart that across visits over time.
# ---------------------------------------------------------------------------

@app.route("/api/patients", methods=["GET", "POST"])
def api_patients():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Patient name is required."}), 400
        patient_id = db.create_patient(name)
        return jsonify(db.get_patient(patient_id)), 201

    return jsonify(db.list_patients())


@app.route("/api/patients/<int:patient_id>/visits", methods=["GET", "POST"])
def api_visits(patient_id):
    patient = db.get_patient(patient_id)
    if not patient:
        return jsonify({"error": "Patient not found."}), 404

    if request.method == "GET":
        visits = db.list_visits(patient_id)
        return jsonify(
            {
                "patient": patient,
                "visits": visits,
                "trend": db.treatment_response(visits),
            }
        )

    # POST: a new visit = a batch of cell images taken on visit_date.
    # Only confidently-classified cells count toward the parasitemia % --
    # uncertain ones are recorded but excluded from the denominator, which
    # is more honest than silently forcing them into a bucket.
    visit_date = request.form.get("visit_date", "").strip()
    if not visit_date:
        return jsonify({"error": "visit_date is required."}), 400

    files = request.files.getlist("images")
    if not files:
        return jsonify({"error": "Upload at least one cell image."}), 400

    per_image = []
    try:
        for f in files:
            image_bytes = f.read()
            rgb_image = load_rgb(image_bytes)
            quality = quality_check.check_image_quality(rgb_image)
            prob_parasitized = classify_rgb(rgb_image)
            result = build_result(prob_parasitized)
            per_image.append({"filename": f.filename, "quality": quality, **result})
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 503
    except Exception:
        return jsonify({"error": "One or more files couldn't be read as images."}), 400

    confident = [r for r in per_image if not r["uncertain"]]
    parasitized_count = sum(1 for r in confident if r["label"] == "Parasitized")

    visit_id = db.add_visit(patient_id, visit_date, len(confident), parasitized_count)
    visits = db.list_visits(patient_id)

    return jsonify(
        {
            "visit_id": visit_id,
            "per_image": per_image,
            "cells_uncertain": len(per_image) - len(confident),
            "visits": visits,
            "trend": db.treatment_response(visits),
        }
    ), 201


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


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
