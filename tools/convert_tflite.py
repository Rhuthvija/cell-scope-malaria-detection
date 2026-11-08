"""
tools/convert_tflite.py
Converts malaria_model.keras into a small TensorFlow Lite model for low-end
hardware: a budget Android phone (fully offline screening in a village) or a
Raspberry Pi at a PHC.

Dynamic-range quantization stores weights as 8-bit integers: the file shrinks
roughly 4x (about 10.6 MB -> about 3 MB) and CPU inference gets faster, usually
with a very small accuracy change. Always re-check accuracy afterwards with the
--check flag on held-out images.

Usage:
  python tools/convert_tflite.py                         # writes malaria_model.tflite
  python tools/convert_tflite.py --check cell_images     # also compares Keras vs TFLite on 200 images
"""
import argparse
import os
import random
import sys

import numpy as np
import tensorflow as tf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def convert(keras_path: str, out_path: str) -> None:
    model = tf.keras.models.load_model(keras_path)
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]      # dynamic-range int8 weights
    tflite_model = converter.convert()
    with open(out_path, "wb") as f:
        f.write(tflite_model)
    print(f"Saved {out_path}: {os.path.getsize(out_path) / 1e6:.1f} MB "
          f"(Keras model: {os.path.getsize(keras_path) / 1e6:.1f} MB)")


def check(keras_path: str, tflite_path: str, data_dir: str, n: int = 200) -> None:
    from PIL import Image
    import stain_norm

    files = []
    for cls in ("Parasitized", "Uninfected"):
        folder = os.path.join(data_dir, cls)
        files += [os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(".png")]
    random.seed(0)
    files = random.sample(files, min(n, len(files)))

    model = tf.keras.models.load_model(keras_path)
    interp = tf.lite.Interpreter(model_path=tflite_path)
    interp.allocate_tensors()
    inp, out = interp.get_input_details()[0], interp.get_output_details()[0]

    agree, max_diff = 0, 0.0
    for path in files:
        rgb = np.asarray(Image.open(path).convert("RGB"))
        try:
            rgb = stain_norm.normalize(rgb)
        except Exception:
            pass
        x = np.asarray(Image.fromarray(rgb).resize((128, 128)), dtype=np.float32)[None]
        k = float(model.predict(x, verbose=0)[0][0])
        interp.set_tensor(inp["index"], x)
        interp.invoke()
        l = float(interp.get_tensor(out["index"])[0][0])
        agree += (k >= 0.5) == (l >= 0.5)
        max_diff = max(max_diff, abs(k - l))
    print(f"Keras vs TFLite on {len(files)} images: {agree / len(files) * 100:.1f}% same label, "
          f"max probability difference {max_diff:.3f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="malaria_model.keras")
    ap.add_argument("--out", default="malaria_model.tflite")
    ap.add_argument("--check", metavar="DATA_DIR", help="cell_images folder to compare predictions on")
    args = ap.parse_args()
    convert(args.model, args.out)
    if args.check:
        check(args.model, args.out, args.check)
