"""
train_model.py
Trains a malaria cell classifier (Parasitized vs Uninfected) using transfer
learning on top of MobileNetV2. Designed to run in Google Colab (free GPU)
or any machine with a decent CPU/GPU in under ~20 minutes.

Dataset (NIH / NLM Malaria Cell Images, 27,558 images):
  https://lhncbc.nlm.nih.gov/LHC-downloads/downloads.html#malaria-datasets
  (Look for "cell_images.zip")

Expected folder structure after unzipping:
  cell_images/
    Parasitized/
      C33P1thinF_IMG_20150619_114756a_cell_179.png
      ...
    Uninfected/
      C1_thinF_IMG_20150604_104722_cell_9.png
      ...

Usage:
  python train_model.py --data_dir cell_images --epochs 10
  (add --no_stain_norm to train on raw colours; app.py normalizes stains at inference,
   so keep normalization on for a model that matches the app)

Output:
  malaria_model.keras   <- the trained model, used by app.py
  training_history.png  <- accuracy/loss curves, nice to drop into your slides
  metrics.json          <- held-out TEST metrics (accuracy, sensitivity, specificity, F1, AUC)
"""

import argparse
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import tensorflow as tf
from tensorflow.keras import layers, models
from tensorflow.keras.applications import MobileNetV2
from tensorflow.keras.preprocessing.image import ImageDataGenerator

IMG_SIZE = 128  # small enough to train fast, large enough to keep parasite detail


def _stain_normalize(image):
    """ImageDataGenerator hook: Macenko-normalize one image (float 0-255 in, float out).
    Falls back to the original image if normalization fails (e.g. a nearly blank crop)."""
    import numpy as np
    import stain_norm
    try:
        return stain_norm.normalize(np.clip(image, 0, 255).astype("uint8")).astype("float32")
    except Exception:
        return image


def build_model(img_size: int) -> tf.keras.Model:
    """MobileNetV2 backbone (ImageNet weights, frozen) + a small classification head."""
    base = MobileNetV2(
        input_shape=(img_size, img_size, 3),
        include_top=False,
        weights="imagenet",
    )
    base.trainable = False  # freeze for fast, stable training on a small dataset

    inputs = tf.keras.Input(shape=(img_size, img_size, 3))
    x = tf.keras.applications.mobilenet_v2.preprocess_input(inputs)
    x = base(x, training=False)
    x = layers.GlobalAveragePooling2D()(x)
    x = layers.Dropout(0.3)(x)
    x = layers.Dense(64, activation="relu")(x)
    x = layers.Dropout(0.3)(x)
    outputs = layers.Dense(1, activation="sigmoid")(x)  # 1 = uninfected, 0 = parasitized (see class_indices)

    model = models.Model(inputs, outputs)
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=1e-3),
        loss="binary_crossentropy",
        metrics=["accuracy", tf.keras.metrics.AUC(name="auc")],
    )
    return model


def build_split_dataframe(data_dir: str, val_frac: float, test_frac: float, seed: int = 42):
    """List every image with its class, then assign train/val/test by slide photo.
    NIH file names look like C33P1thinF_IMG_20150619_114756a_cell_179.png; everything
    before '_cell' identifies the source photo."""
    import numpy as np
    import pandas as pd

    rows = []
    for cls in ("Parasitized", "Uninfected"):
        folder = os.path.join(data_dir, cls)
        for fname in os.listdir(folder):
            if not fname.lower().endswith((".png", ".jpg", ".jpeg")):
                continue
            group = fname.split("_cell")[0]
            rows.append({"filepath": os.path.join(folder, fname), "class": cls, "group": group})
    df = pd.DataFrame(rows)

    rng = np.random.default_rng(seed)
    groups = np.array(sorted(df["group"].unique()), dtype=object)
    rng.shuffle(groups)
    n_test = int(len(groups) * test_frac)
    n_val = int(len(groups) * val_frac)
    test_g = set(groups[:n_test])
    val_g = set(groups[n_test:n_test + n_val])
    df["split"] = ["test" if g in test_g else "val" if g in val_g else "train" for g in df["group"]]
    return df


def evaluate_on_test(model, test_gen, class_indices: dict) -> dict:
    """Screening metrics with Parasitized as the positive class.
    Sensitivity (recall on Parasitized) matters most: a missed infection is worse
    than a false alarm that gets re-checked."""
    import numpy as np

    probs = model.predict(test_gen, verbose=0).ravel()          # P(class index 1)
    y_idx = test_gen.classes                                     # true class indices
    para = class_indices["Parasitized"]
    p_para = probs if para == 1 else 1.0 - probs
    y_true = (np.asarray(y_idx) == para).astype(int)             # 1 = parasitized
    y_pred = (p_para >= 0.5).astype(int)

    tp = int(((y_pred == 1) & (y_true == 1)).sum())
    tn = int(((y_pred == 0) & (y_true == 0)).sum())
    fp = int(((y_pred == 1) & (y_true == 0)).sum())
    fn = int(((y_pred == 0) & (y_true == 1)).sum())
    sens = tp / (tp + fn) if tp + fn else 0.0
    spec = tn / (tn + fp) if tn + fp else 0.0
    prec = tp / (tp + fp) if tp + fp else 0.0
    f1 = 2 * prec * sens / (prec + sens) if prec + sens else 0.0
    auc = tf.keras.metrics.AUC()
    auc.update_state(y_true, p_para)

    return {
        "n_test": int(len(y_true)),
        "accuracy": (tp + tn) / len(y_true),
        "sensitivity": sens,
        "specificity": spec,
        "precision": prec,
        "f1": f1,
        "auc": float(auc.result().numpy()),
        # rows = true (Parasitized, Uninfected), cols = predicted
        "confusion_matrix": [[tp, fn], [fp, tn]],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir", default="cell_images", help="Path to the cell_images folder")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch_size", type=int, default=32)
    parser.add_argument("--val_split", type=float, default=0.15)
    parser.add_argument("--test_split", type=float, default=0.15,
                        help="Fraction of slide photos held out for the final test score")
    parser.add_argument("--out", default="malaria_model.keras")
    parser.add_argument("--no_stain_norm", dest="stain_norm", action="store_false",
                        help="Skip Macenko stain normalization (app.py applies it at inference)")
    args = parser.parse_args()

    if not os.path.isdir(args.data_dir):
        raise SystemExit(
            f"Couldn't find '{args.data_dir}'. Download and unzip the NIH dataset first "
            f"(see the docstring at the top of this file for the link)."
        )

    # Stain normalization is applied at inference time in app.py, so training must
    # see the same normalized colours -- otherwise the model is evaluated on a
    # colour distribution it never trained on (train/serve skew).
    preprocess = _stain_normalize if args.stain_norm else None

    # ---- Train / validation / test split, grouped by slide image ----------------
    # Each NIH image is one cell cropped from a larger slide photo, and one photo
    # contributes many cells. A random per-cell split puts near-identical cells from
    # the same photo into both train and test, which inflates the scores. So we
    # split by slide photo, and keep a TEST set that is never used for early stopping
    # or checkpointing -- that is the number to report.
    df = build_split_dataframe(args.data_dir, args.val_split, args.test_split, seed=42)
    for name in ("train", "val", "test"):
        part = df[df.split == name]
        print(f"{name:>5}: {len(part):6d} cells | " +
              " | ".join(f"{c}={n}" for c, n in part["class"].value_counts().sort_index().items()))

    train_datagen = ImageDataGenerator(
        rotation_range=20,
        horizontal_flip=True,
        vertical_flip=True,
        zoom_range=0.1,
        preprocessing_function=preprocess,
    )
    # Augmentation is for training only; val/test images stay untouched.
    eval_datagen = ImageDataGenerator(preprocessing_function=preprocess)

    common = dict(x_col="filepath", y_col="class", target_size=(IMG_SIZE, IMG_SIZE),
                  batch_size=args.batch_size, class_mode="binary",
                  classes=["Parasitized", "Uninfected"])
    train_gen = train_datagen.flow_from_dataframe(df[df.split == "train"], shuffle=True, seed=42, **common)
    val_gen = eval_datagen.flow_from_dataframe(df[df.split == "val"], shuffle=False, **common)
    test_gen = eval_datagen.flow_from_dataframe(df[df.split == "test"], shuffle=False, **common)

    print("Class indices (important -- app.py needs to match this):", train_gen.class_indices)
    with open("class_indices.json", "w") as f:
        json.dump(train_gen.class_indices, f, indent=2)
    print("Saved class_indices.json")

    model = build_model(IMG_SIZE)
    model.summary()

    callbacks = [
        tf.keras.callbacks.EarlyStopping(monitor="val_auc", mode="max", patience=3, restore_best_weights=True),
        tf.keras.callbacks.ModelCheckpoint(args.out, monitor="val_auc", mode="max", save_best_only=True),
    ]

    history = model.fit(
        train_gen,
        validation_data=val_gen,
        epochs=args.epochs,
        callbacks=callbacks,
    )

    model.save(args.out)
    print(f"\nSaved model to {args.out}")

    # ---- Held-out test evaluation ------------------------------------------------
    metrics = evaluate_on_test(model, test_gen, train_gen.class_indices)
    with open("metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)
    print("\n=== HELD-OUT TEST SET (report these numbers) ===")
    for k in ("accuracy", "sensitivity", "specificity", "precision", "f1", "auc"):
        print(f"  {k:<12} {metrics[k]:.4f}")
    cm = metrics["confusion_matrix"]
    print(f"  confusion matrix (rows=true, cols=pred, order Parasitized/Uninfected): {cm}")
    print("Saved metrics.json")

    # plot curves for the slide deck
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    axes[0].plot(history.history["accuracy"], label="train")
    axes[0].plot(history.history["val_accuracy"], label="val")
    axes[0].set_title("Accuracy")
    axes[0].legend()
    axes[1].plot(history.history["loss"], label="train")
    axes[1].plot(history.history["val_loss"], label="val")
    axes[1].set_title("Loss")
    axes[1].legend()
    fig.tight_layout()
    fig.savefig("training_history.png", dpi=150)
    print("Saved training_history.png")


if __name__ == "__main__":
    main()
