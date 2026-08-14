"""
gradcam.py
Grad-CAM (Selvaraju et al., 2017): shows which pixels of an input image
most influenced the model's prediction, as a heatmap overlay.

For the MobileNetV2-based model in train_model.py, the target layer is the
last convolutional layer of the backbone -- by default we auto-detect it
(the last layer in the model with a 4D output), but you can pass a specific
layer name if your architecture changes.

NOTE: this module isn't exercised by the test suite in this sandbox (no
TensorFlow available in this environment to run it against), but it follows
the standard, widely-used Grad-CAM implementation pattern. Sanity-check it
against your actual trained model once you have one -- e.g. run it on a
clearly-parasitized training image and confirm the hot region lands on the
visible parasite rather than the image border or background.
"""

import io

import cv2
import numpy as np
try:
    import tensorflow as tf
except ImportError:
    tf = None
from PIL import Image


def find_last_conv_layer(model) -> str:
    """Return the final spatial feature map before the classifier head.

    Here the MobileNetV2 backbone is a nested model. Its 4D output is the
    final Conv_1/out_relu feature map, immediately before global pooling.
    """
    if tf is None:
        raise ImportError("TensorFlow is required to inspect Keras model layers.")
    for layer in reversed(model.layers):
        output_shape = getattr(layer, "output_shape", None)
        if output_shape is None:
            output_shape = tuple(layer.output.shape)
        if len(output_shape) == 4:
            return layer.name
    raise ValueError("Could not find a 4D conv-style layer in this model.")


def make_gradcam_heatmap(preprocessed_batch: np.ndarray, model, layer_name: str = None) -> np.ndarray:
    """
    preprocessed_batch: (1, H, W, 3) array, already resized (raw pixel values --
        the model applies its own preprocess_input internally, matching train_model.py).
    Returns a (h, w) float32 heatmap in [0, 1], at the target conv layer's resolution.
    """
    if tf is None:
        raise ImportError("TensorFlow is required for neural Grad-CAM heatmap generation.")
    if layer_name is None:
        layer_name = find_last_conv_layer(model)

    grad_model = tf.keras.models.Model(
        inputs=model.inputs,
        outputs=[model.get_layer(layer_name).output, model.output],
    )

    with tf.GradientTape() as tape:
        conv_output, predictions = grad_model(preprocessed_batch)
        # predictions is a sigmoid P(uninfected); to explain "parasitized" we
        # want the gradient of P(parasitized) = 1 - P(uninfected), which has
        # the same magnitude gradient with a sign flip. We use -predictions so
        # positive gradients correspond to evidence *for* "parasitized".
        target = -predictions[:, 0]

    grads = tape.gradient(target, conv_output)
    pooled_grads = tf.reduce_mean(grads, axis=(0, 1, 2))  # importance weight per channel

    conv_output = conv_output[0]
    heatmap = conv_output @ pooled_grads[..., tf.newaxis]
    heatmap = tf.squeeze(heatmap)
    heatmap = tf.maximum(heatmap, 0)  # ReLU: keep only positive (supporting) evidence
    max_val = tf.reduce_max(heatmap)
    if max_val > 0:
        heatmap = heatmap / max_val
    return heatmap.numpy()


def _activation_colormap(activation: np.ndarray) -> np.ndarray:
    """Map [0, 255] activation values from green through yellow to red."""
    ramp = np.array(
        [[22, 163, 74], [132, 204, 22], [250, 204, 21], [249, 115, 22], [220, 38, 38]],
        dtype=np.float32,
    )
    positions = np.linspace(0.0, 1.0, len(ramp))
    values = activation.astype(np.float32) / 255.0
    rgb = np.empty((*activation.shape, 3), dtype=np.uint8)
    for channel in range(3):
        rgb[..., channel] = np.interp(values, positions, ramp[:, channel]).astype(np.uint8)
    return rgb


def overlay_heatmap(
    original_rgb: np.ndarray,
    heatmap: np.ndarray,
    alpha: float = 0.40,
    suppress_hotspots: bool = False,
) -> np.ndarray:
    """Smooth, normalize, color, and blend a Grad-CAM over an RGB image."""
    if original_rgb.dtype != np.uint8:
        original_rgb = np.clip(original_rgb, 0, 255).astype(np.uint8)

    h, w = original_rgb.shape[:2]
    if min(h, w) < 320:
        scale = 320.0 / min(h, w)
        w, h = round(w * scale), round(h * scale)
        original_rgb = cv2.resize(original_rgb, (w, h), interpolation=cv2.INTER_LANCZOS4)

    # MobileNet CAMs are only a few pixels across. Smooth interpolation and a
    # light blur remove blocky activation bands while preserving localization.
    heatmap_resized = cv2.resize(heatmap.astype(np.float32), (w, h), interpolation=cv2.INTER_LANCZOS4)
    heatmap_resized = cv2.GaussianBlur(heatmap_resized, (0, 0), sigmaX=1.2, sigmaY=1.2)
    cam_min, cam_max = float(heatmap_resized.min()), float(heatmap_resized.max())
    if cam_max > cam_min:
        activation = (heatmap_resized - cam_min) / (cam_max - cam_min)
    else:
        activation = np.zeros_like(heatmap_resized)

    # Fade low-value noise below 18% to the cool end of the scale.
    activation = np.clip((activation - 0.18) / 0.82, 0.0, 1.0)
    if suppress_hotspots:
        # A negative parasite result should not show an artificial red lesion
        # simply because per-image normalization maps its tiny maximum to red.
        activation *= 0.22

    colored_rgb = _activation_colormap((activation * 255).astype(np.uint8))
    return cv2.addWeighted(colored_rgb, alpha, original_rgb, 1.0 - alpha, 0)


def gradcam_overlay_png_bytes(
    original_rgb: np.ndarray, model, preprocessed_batch: np.ndarray, prob_parasitized: float = None
) -> bytes:
    """Convenience wrapper: runs Grad-CAM and returns a ready-to-serve PNG
    (as bytes) of the original image with the heatmap overlaid."""
    heatmap = make_gradcam_heatmap(preprocessed_batch, model)
    overlaid = overlay_heatmap(
        original_rgb, heatmap, suppress_hotspots=prob_parasitized is not None and prob_parasitized < 0.5
    )

    buf = io.BytesIO()
    Image.fromarray(overlaid).save(buf, format="PNG")
    return buf.getvalue()
