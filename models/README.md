# Optional offline segmentation model

Offline Sticker Studio works without any model: GrabCut, manual painting and
the plain-background colour key are always available.

To enable the optional **local model** engine:

1. `pip install onnxruntime` (CPU build, no GPU or CUDA needed).
2. Put a U²-Net-family ONNX file in this folder with one of these names:
   `u2netp.onnx`, `u2net.onnx`, `silueta.onnx`, `u2net_human_seg.onnx`.

The app never downloads models. No model is bundled, because redistribution
terms vary. Use a model only if its licence allows your use (for example,
the original U²-Net weights are published under the Apache-2.0 licence by
their authors). The Status page shows whether a model was found.
