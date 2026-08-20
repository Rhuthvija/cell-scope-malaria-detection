# Cell Scope

**AI-powered malaria detection from a single blood smear.**
Bringing lab-grade malaria screening to every clinic.

---

## 🚧 Deployment Status

This project was deployed as a working prototype during development. The
live demo link is currently down and being fixed.

The multi-tenant account system (separate clinic/NGO/researcher logins,
with each organization's patient data kept isolated, plus an anonymized
cross-org view for researchers) has been **designed and built**, but is
**not yet integrated into the deployment**. The updated backend
(`app.py`, `db.py`) and new auth/signup/researcher-portal templates are
included in this repo, ready for the next deployment pass.

---

## Features

- **Single-cell classification** — upload a cropped blood cell image, get a Parasitized / Uninfected prediction with confidence score
- **Full smear analysis** — upload an uncropped microscope field photo; automatically detects and classifies every red blood cell in it
- **Grad-CAM explainability** — visual heatmap showing which part of the cell drove the model's prediction
- **Risk gauge** — maps prediction confidence and parasitemia % to a clinical risk band (Clear / Low / Moderate / High / Critical)
- **Patient tracking** — log visits over time per patient, view parasitemia trend charts
- **PDF reports** — downloadable diagnostic report per visit or per patient, including images and treatment guidance
- **Stain normalization** — corrects for Giemsa stain color variation across different slides/scanners before classification

---

## Tech stack

| Layer | Tech |
|---|---|
| Backend | Flask |
| Model | MobileNetV2 (transfer learning), TensorFlow/Keras |
| Cell detection | OpenCV (watershed segmentation) |
| Explainability | Grad-CAM |
| Reports | ReportLab, Matplotlib |
| Database | SQLite |
| Deployment | Render |

---

## Project structure

```
app.py                 # Flask routes, inference pipeline, risk scoring
db.py                  # SQLite data layer (patients, visits)
train_model.py          # Trains the MobileNetV2 classifier
gradcam.py                # Grad-CAM heatmap generation
rbc_detection.py           # Full-smear cell detection (watershed + fallback)
stain_norm.py                # Macenko stain normalization
quality_check.py               # Blur/brightness checks on uploaded images
report.py                        # PDF report generation
templates/                         # HTML pages
static/                              # CSS/JS/assets
malaria_model.keras                    # Trained model (produced by train_model.py)
class_indices.json                       # Class label mapping
```

---

## Getting started (local setup)

**Requirements:** Python 3.11 (TensorFlow 2.15/2.16 does not yet support 3.12+)

```bash
# Clone the repo
git clone https://github.com/Rhuthvija/cell-scope-malaria-detection.git
cd cell-scope-malaria-detection

# Create and activate a virtual environment
python3.11 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the app
python app.py
```

Then open **http://localhost:5050**.

---

## Training the model

The trained model (`malaria_model.keras`) is already included, but to retrain it from scratch:

1. Download the [NIH/NLM Malaria Cell Images dataset](https://lhncbc.nlm.nih.gov/LHC-downloads/downloads.html#malaria-datasets) (27,558 labeled cell images)
2. Unzip it so you have a `cell_images/Parasitized/` and `cell_images/Uninfected/` folder
3. Run:
   ```bash
   python train_model.py --data_dir cell_images --epochs 10
   ```
4. This produces a new `malaria_model.keras` and `class_indices.json`

---

## ⚠️ Disclaimer

This is a research/hackathon prototype, **not a diagnostic device**.
Model predictions are screening-level estimates from an AI classifier and
have not been clinically validated. A confirmed malaria diagnosis should
always come from a trained microscopist or an approved rapid diagnostic
test.
