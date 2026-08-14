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

Output:
  malaria_model.keras   <- the trained model, used by app.py
  training_history.png  <- accuracy/loss curves, nice to drop into your slides
"""

import argparse
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import tensorflow as tf
from tensorflow.keras import layers, models
from tensorflow.keras.applications import MobileNetV2
from tensorflow.keras.preprocessing.image import ImageDataGenerator

IMG_SIZE = 128  # small enough to train fast, large enough to keep parasite detail


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir", default="cell_images", help="Path to the cell_images folder")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch_size", type=int, default=32)
    parser.add_argument("--val_split", type=float, default=0.2)
    parser.add_argument("--out", default="malaria_model.keras")
    args = parser.parse_args()

    if not os.path.isdir(args.data_dir):
        raise SystemExit(
            f"Couldn't find '{args.data_dir}'. Download and unzip the NIH dataset first "
            f"(see the docstring at the top of this file for the link)."
        )

    datagen = ImageDataGenerator(
        validation_split=args.val_split,
        rotation_range=20,
        horizontal_flip=True,
        vertical_flip=True,
        zoom_range=0.1,
    )

    train_gen = datagen.flow_from_directory(
        args.data_dir,
        target_size=(IMG_SIZE, IMG_SIZE),
        batch_size=args.batch_size,
        class_mode="binary",
        subset="training",
        shuffle=True,
        seed=42,
    )
    val_gen = datagen.flow_from_directory(
        args.data_dir,
        target_size=(IMG_SIZE, IMG_SIZE),
        batch_size=args.batch_size,
        class_mode="binary",
        subset="validation",
        shuffle=False,
        seed=42,
    )

    print("Class indices (important -- app.py needs to match this):", train_gen.class_indices)
    with open("class_indices.json", "w") as f:
        import json
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

    # quick eval summary
    val_loss, val_acc, val_auc = model.evaluate(val_gen)
    print(f"Validation accuracy: {val_acc:.3f} | AUC: {val_auc:.3f}")

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
