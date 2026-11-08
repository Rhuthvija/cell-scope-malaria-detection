# Cell Scope — AI Malaria Screening for Rural Health Centres

> AI-powered malaria screening from a single blood smear image, built for primary health centres (PHCs) and community health workers who have no on-site lab technician.

**Live demo:** https://cell-scope-malaria-detection.onrender.com/ (free tier — the first load can take ~1 minute while it wakes up)  ·  **Status:** Research / hackathon prototype, being extended as a rural development project

> ⚠️ **Not a diagnostic device.** Cell Scope gives screening-level estimates that have not been clinically validated. A confirmed diagnosis must come from a trained microscopist or an approved rapid diagnostic test (RDT).

---

## The problem

Malaria is concentrated in tribal and rural districts, where many PHCs have no trained microscopist. Blood smears often have to be sent to a town lab, so results take days, treatment starts late, and outbreaks are noticed only after they have spread.

## What Cell Scope does

A health worker uploads a microscope image of a Giemsa-stained blood smear. Cell Scope then:

| Feature | What it does |
|---|---|
| **Single-cell classification** | Labels a cropped red blood cell as *Parasitized* or *Uninfected*, with a confidence score |
| **Full smear analysis** | Detects every red blood cell in an uncropped smear image and classifies each one |
| **Parasitemia + risk gauge** | Risk band (Clear, Low, Moderate, High, Critical) driven by parasitemia, the share of infected red cells. A single infected cell is never marked Critical |
| **Grad-CAM explainability** | Shows a heatmap of the region of each cell that drove the prediction, so a clinician can check it |
| **Stain normalisation** | Corrects Giemsa colour variation between slides, microscopes and cameras |
| **Image quality check** | Warns when an image is blurry, too dark or overexposed, so the result can be treated with caution |
| **Patient tracking** | Logs each visit and charts parasitemia over time during treatment |
| **PDF reports** | Per-visit or per-patient reports with images, results, village and health worker, and confirm-and-refer next steps (no drug doses: species can't be identified from this screen) |
| **Referral flagging** | High and Critical results are flagged for referral to a doctor or PHC |
| **Outbreak surveillance API** | Groups recent tests by village and flags hotspots (≥3 positives in 14 days) for district health officers |

## How it works

```
Upload image
   │
   ▼
Quality check ──► warn if blurry / too dark
   │
   ▼
Stain normalisation
   │
   ├── single cell ──────────────► MobileNetV2 classifier
   │                                      │
   └── full smear ──► watershed RBC ──────┘
                      detection (OpenCV)  │
                                          ▼
                         Grad-CAM heatmap + confidence
                                          │
                                          ▼
                     Parasitemia % → risk band → patient record → PDF report
```

## Model

- **Architecture:** MobileNetV2 (ImageNet weights) fine-tuned with transfer learning in TensorFlow/Keras. It was chosen because it is small enough to run on low-cost hardware.
- **Dataset:** [NIH/NLM Malaria Cell Images](https://lhncbc.nlm.nih.gov/LHC-research/LHC-projects/image-processing/malaria-datasheet.html), 27,558 labelled single-cell images (Parasitized / Uninfected).
- **Evaluation:** `train_model.py` splits the data **by slide photo** into train / validation / test (70 / 15 / 15), so cells from the same photo never appear in both training and test. The test set is never used for early stopping or checkpointing. Results are saved to `metrics.json`.
- **Results (held-out test set):**

| Metric | Value |
|---|---|
| Accuracy | `<ACCURACY>` |
| Sensitivity (recall, Parasitized) | `<RECALL>` |
| Specificity | `<SPECIFICITY>` |
| F1 score | `<F1>` |

> For screening, **sensitivity matters most**: a missed infection is worse than a false alarm that is later checked by RDT.

## Risk bands

| Result | Band | Rule |
|---|---|---|
| Uninfected | Clear / Low | Model confidence ≥90% / below 90% |
| Parasitized, full smear | Critical | Parasitemia ≥5% |
| Parasitized, full smear | High | Parasitemia ≥2% |
| Parasitized, full smear | Moderate | Below 2%, or only one low-confidence infected cell |
| Parasitized, single cell | High / Moderate | Confidence ≥85% / below. Parasitemia can't be measured from one cell |

High and Critical results are saved with `referred = 1`.

## Rural surveillance API

| Endpoint | Returns |
|---|---|
| `POST /api/diagnose` | Also accepts optional `village`, `district`, `health_worker`, `latitude` and `longitude` form fields |
| `GET /api/outbreaks?days=14&min_positive=3` | Tests, positives and positivity per village, with hotspot flags |
| `GET /api/referrals?days=30` | Patients flagged High or Critical, with village and health worker |

## Security

| Protection | How |
|---|---|
| **Encryption at rest** | Phone numbers, blood-smear images and Grad-CAM images are encrypted in SQLite with Fernet (AES-128 + HMAC-SHA256) when `CELLSCOPE_ENCRYPTION_KEY` is set |
| **Access lock** | Set `CELLSCOPE_PASSWORD` to require a login for every page and API call (browser login prompt, so the UI is unchanged). `/health` stays open |
| **HTTPS** | Provided by Render. HSTS header sent on HTTPS requests |
| **Upload validation** | 10 MB size limit, image content checked (not just the file extension), pixel limit against decompression-bomb images |
| **Rate limiting** | 30 diagnoses per minute per IP |
| **Security headers** | Content-Security-Policy, X-Frame-Options, nosniff, Referrer-Policy, and `no-store` on API responses so patient data isn't cached |
| **No patient data in logs** | Diagnosis logs record the result only, not the name or file name |

Generate an encryption key once and keep it secret. If you lose it, encrypted records can't be read:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Environment variables

| Variable | Purpose |
|---|---|
| `CELLSCOPE_ENCRYPTION_KEY` | Fernet key for encryption at rest (recommended) |
| `CELLSCOPE_PASSWORD` / `CELLSCOPE_USERNAME` | Optional login lock (username defaults to `cellscope`) |
| `CELLSCOPE_DEMO_DATA=1` | Load the demo Telangana village records on Render (for presentations) |
| `CELLSCOPE_MAX_UPLOAD_MB`, `CELLSCOPE_RATE_LIMIT_PER_MIN` | Override the upload and rate limits |

## Tech stack

| Layer | Tools |
|---|---|
| Backend | Flask |
| Model | TensorFlow / Keras, MobileNetV2 |
| Image processing | OpenCV (watershed segmentation), stain normalisation |
| Explainability | Grad-CAM |
| Reports | ReportLab, Matplotlib |
| Database | SQLite, with Fernet field encryption (`cryptography`) |
| Deployment | Render |

## Project structure

```
app.py               Flask routes, inference, risk scoring
db.py                SQLite data layer, outbreak and referral queries
crypto_util.py       Field-level encryption at rest
train_model.py       Training script (retrains malaria_model.keras)
malaria_model.keras  Pretrained model
class_indices.json   Label mapping
rbc_detection.py     Watershed red-blood-cell detection
stain_norm.py        Giemsa stain normalisation
quality_check.py     Image quality checks
gradcam.py           Grad-CAM heatmaps
report.py            PDF report generation
templates/, static/  Frontend
```

## Run locally

Requires **Python 3.11** (pinned in `.python-version`).

```bash
git clone https://github.com/Rhuthvija/cell-scope-malaria-detection.git
cd cell-scope-malaria-detection
python3.11 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Then open http://localhost:5050.

### Retrain the model

1. Download `cell_images.zip` from the [NIH malaria dataset page](https://lhncbc.nlm.nih.gov/LHC-downloads/downloads.html#malaria-datasets) and unzip it.
2. Run (Google Colab with a GPU is easiest; training also needs `pandas`):

```bash
python train_model.py --data_dir cell_images --epochs 10
```

This writes `malaria_model.keras`, `class_indices.json`, `training_history.png` and `metrics.json` (held-out test accuracy, sensitivity, specificity, F1, AUC and the confusion matrix).

## Deploy (Render)

The repo includes `render.yaml`, `.python-version` and pinned `requirements.txt`:

- **Python 3.11.9.** Newer Python versions break the TensorFlow install.
- **`tensorflow-cpu` + Keras 3.13.** The bundled model was saved with Keras 3, so TensorFlow 2.15 (Keras 2) cannot load it.
- **Start command:** `gunicorn app:app --workers 1 --threads 2 --timeout 180 --bind 0.0.0.0:$PORT`. One worker fits the free tier's 512 MB. The long timeout covers model loading when the worker starts.
- **Health check:** `/health`

> The free tier's disk is wiped on every redeploy and restart, so the SQLite patient records are demo data only.

## Roadmap — rural extension

| Planned feature | Why it matters in rural settings |
|---|---|
| **Phone capture** with a low-cost clip-on microscope lens | Removes the need for a lab microscope and camera setup |
| **On-device inference** (TFLite) and offline mode | Works where internet access is patchy or unavailable |
| **Telugu and Hindi interface and reports** | Usable by ASHA workers and readable by patients |
| **GPS-tagged cases and an outbreak map** | Lets district health officials see village-level case clusters early |
| **Doctor referral** for high-risk results | Remote confirmation and treatment advice from a doctor |
| **Multi-tenant accounts** (PHC / NGO / district) | Keeps each organisation's patient data separate (built, not yet deployed) |

## Limitations

- Trained on curated single-cell images. Accuracy on real-world phone photos still needs to be checked.
- Detects whether a cell is infected, but does not identify the *Plasmodium* species.
- Not clinically validated. Use for screening support only.

## Author

**Rhuthvija Allavala** — [GitHub](https://github.com/Rhuthvija) · [LinkedIn](https://linkedin.com/in/rhuthvija-allavala)
