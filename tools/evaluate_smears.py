"""
tools/evaluate_smears.py
Measures how well Cell Scope works on WHOLE thin-smear images (not single
cells), using expert-labelled full-field images.

Dataset: BBBC041 (Broad Bioimage Benchmark Collection) -- 1,364 Giemsa-stained
thin-smear images with ~80,000 cells boxed and labelled by experts as
uninfected RBC, ring, trophozoite, schizont, gametocyte or leukocyte.
  https://bbbc.broadinstitute.org/BBBC041
Download "malaria.zip" and unzip; it contains images/, training.json, test.json.

Note: BBBC041 is P. vivax, while the model was trained on NIH P. falciparum
crops from a different lab, so this is a genuine out-of-distribution test.
Report the numbers honestly whatever they are -- they show where to improve.

What it reports
  Detection   - did we find the red blood cells? (recall / precision vs expert boxes)
                and how many white blood cells were wrongly counted as RBCs
  Cell level  - of the cells we found, were infected ones flagged? (sensitivity /
                specificity, infected = ring/trophozoite/schizont/gametocyte)
  Parasitemia - mean absolute error of the % infected cells per image
  Image level - would a positive smear be called positive? (sensitivity / specificity)
  Speed       - seconds per image on this machine

Usage
  python tools/evaluate_smears.py --data malaria --split test
  python tools/evaluate_smears.py --data malaria --split test --detection-only   # no TensorFlow needed
  python tools/evaluate_smears.py --data malaria --limit 50 --threshold 0.6
Writes smear_metrics.json next to where it is run.
"""
import argparse
import json
import os
import sys
import time

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rbc_detection  # noqa: E402

INFECTED = {"ring", "trophozoite", "schizont", "gametocyte"}
RBC_CLASSES = INFECTED | {"red blood cell"}
WBC = "leukocyte"


def load_annotations(data_dir: str, split: str):
    name = "training.json" if split == "train" else "test.json"
    with open(os.path.join(data_dir, name)) as f:
        entries = json.load(f)
    out = []
    for e in entries:
        path = os.path.join(data_dir, e["image"]["pathname"].lstrip("/"))
        boxes = []
        for o in e["objects"]:
            bb = o["bounding_box"]
            x0, y0 = bb["minimum"]["c"], bb["minimum"]["r"]
            x1, y1 = bb["maximum"]["c"], bb["maximum"]["r"]
            boxes.append({"box": (x0, y0, x1, y1), "category": o["category"]})
        out.append((path, boxes))
    return out


def iou(a, b):
    ix0, iy0, ix1, iy1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def match(dets, gts, thr=0.3):
    """Greedy one-to-one matching by IoU. Returns list of (det_idx, gt_idx)."""
    pairs = sorted(((iou(d, g["box"]), i, j) for i, d in enumerate(dets) for j, g in enumerate(gts)), reverse=True)
    used_d, used_g, out = set(), set(), []
    for score, i, j in pairs:
        if score < thr:
            break
        if i in used_d or j in used_g:
            continue
        used_d.add(i); used_g.add(j); out.append((i, j))
    return out


class Classifier:
    """Same preprocessing as app.py: stain normalisation, resize to 128, model has preprocess built in."""

    def __init__(self, model_path, class_indices_path):
        import tensorflow as tf
        import stain_norm
        self.stain_norm = stain_norm
        self.model = tf.keras.models.load_model(model_path)
        ci = {"Parasitized": 0, "Uninfected": 1}
        if os.path.exists(class_indices_path):
            with open(class_indices_path) as f:
                ci = json.load(f)
        self.uninfected_is_one = ci.get("Uninfected") == 1

    def __call__(self, crops):
        batch = []
        for c in crops:
            try:
                c = self.stain_norm.normalize(c)
            except Exception:
                pass
            batch.append(np.asarray(Image.fromarray(c).resize((128, 128)), dtype=np.float32))
        raw = self.model.predict(np.stack(batch), batch_size=64, verbose=0)[:, 0]
        return (1.0 - raw) if self.uninfected_is_one else raw


def safe_div(a, b):
    return round(a / b, 4) if b else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="Unzipped BBBC041 'malaria' folder")
    ap.add_argument("--split", choices=["train", "test"], default="test")
    ap.add_argument("--model", default="malaria_model.keras")
    ap.add_argument("--class-indices", default="class_indices.json")
    ap.add_argument("--threshold", type=float, default=0.5, help="Per-cell infected threshold")
    ap.add_argument("--limit", type=int, default=0, help="Only evaluate the first N images")
    ap.add_argument("--detection-only", action="store_true", help="Skip the classifier (no TensorFlow)")
    ap.add_argument("--out", default="smear_metrics.json")
    args = ap.parse_args()

    items = load_annotations(args.data, args.split)
    if args.limit:
        items = items[:args.limit]
    clf = None if args.detection_only else Classifier(args.model, args.class_indices)

    det = {"gt_rbc": 0, "detected": 0, "matched_rbc": 0, "wbc_counted_as_rbc": 0}
    cell = {"tp": 0, "fn": 0, "fp": 0, "tn": 0}
    img = {"tp": 0, "fn": 0, "fp": 0, "tn": 0}
    para_err, seconds = [], []

    for n, (path, gts) in enumerate(items, 1):
        rgb = np.asarray(Image.open(path).convert("RGB"))
        rbc_gts = [g for g in gts if g["category"] in RBC_CLASSES]
        wbc_gts = [g for g in gts if g["category"] == WBC]

        t0 = time.time()
        cells = rbc_detection.detect_cells(rgb)
        dets = [(c.bbox[0], c.bbox[1], c.bbox[0] + c.bbox[2], c.bbox[1] + c.bbox[3]) for c in cells]
        probs = clf([c.crop for c in cells]) if (clf and cells) else None
        seconds.append(time.time() - t0)

        det["gt_rbc"] += len(rbc_gts)
        det["detected"] += len(dets)
        pairs = match(dets, rbc_gts)
        det["matched_rbc"] += len(pairs)
        det["wbc_counted_as_rbc"] += len(match(dets, wbc_gts))

        gt_infected_img = any(g["category"] in INFECTED for g in rbc_gts)
        if probs is not None:
            for i, j in pairs:
                truth = rbc_gts[j]["category"] in INFECTED
                pred = probs[i] >= args.threshold
                key = ("tp" if pred else "fn") if truth else ("fp" if pred else "tn")
                cell[key] += 1
            pred_pos = int(np.sum(probs >= args.threshold))
            pred_pct = 100.0 * pred_pos / len(cells) if cells else 0.0
            gt_pct = 100.0 * sum(g["category"] in INFECTED for g in rbc_gts) / len(rbc_gts) if rbc_gts else 0.0
            para_err.append(abs(pred_pct - gt_pct))
            pred_img = pred_pos > 0
            key = ("tp" if pred_img else "fn") if gt_infected_img else ("fp" if pred_img else "tn")
            img[key] += 1

        if n % 25 == 0 or n == len(items):
            print(f"  {n}/{len(items)} images", flush=True)

    results = {
        "dataset": "BBBC041", "split": args.split, "images": len(items), "cell_threshold": args.threshold,
        "detection": {
            "rbc_recall": safe_div(det["matched_rbc"], det["gt_rbc"]),
            "rbc_precision": safe_div(det["matched_rbc"], det["detected"]),
            "wbc_counted_as_rbc": det["wbc_counted_as_rbc"],
            **det,
        },
        "seconds_per_image": round(float(np.mean(seconds)), 3) if seconds else None,
    }
    if clf:
        results["cell_level"] = {
            "sensitivity": safe_div(cell["tp"], cell["tp"] + cell["fn"]),
            "specificity": safe_div(cell["tn"], cell["tn"] + cell["fp"]),
            "precision": safe_div(cell["tp"], cell["tp"] + cell["fp"]),
            **cell,
        }
        results["parasitemia_mae_pct_points"] = round(float(np.mean(para_err)), 3) if para_err else None
        results["image_level"] = {
            "sensitivity": safe_div(img["tp"], img["tp"] + img["fn"]),
            "specificity": safe_div(img["tn"], img["tn"] + img["fp"]),
            **img,
        }

    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)
    print(json.dumps(results, indent=2))
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
