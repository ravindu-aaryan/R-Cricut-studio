import numpy as np
import pytest
from PIL import Image, ImageDraw

from app.services import segmentation_service as seg


def synthetic_scene():
    """Coloured disc on a striped background, plus its exact ground-truth mask."""
    img = Image.new("RGB", (400, 400), (70, 130, 200))
    d = ImageDraw.Draw(img)
    for y in range(0, 400, 30):
        d.rectangle((0, y, 400, y + 12), fill=(60, 115, 185))
    d.ellipse((110, 80, 290, 330), fill=(235, 90, 60))
    truth = Image.new("L", (400, 400), 0)
    ImageDraw.Draw(truth).ellipse((110, 80, 290, 330), fill=255)
    return img, np.asarray(truth) > 127


def iou(a, b):
    return (a & b).sum() / max(1, (a | b).sum())


def test_grabcut_finds_subject():
    img, truth = synthetic_scene()
    mask = seg.run_segmentation("grabcut", img, rect=(80, 50, 240, 310))
    assert iou(mask > 127, truth) > 0.9


def test_grabcut_with_hints_only():
    img, truth = synthetic_scene()
    hints = np.zeros((400, 400), np.uint8)
    hints[180:230, 180:220] = seg.HINT_FG
    hints[:20, :] = seg.HINT_BG
    mask = seg.run_segmentation("grabcut", img, hints=hints)
    assert iou(mask > 127, truth) > 0.85


def test_grabcut_cancellation():
    img, _ = synthetic_scene()
    with pytest.raises(seg.SegmentationCancelled):
        seg.grabcut(np.asarray(img), (80, 50, 240, 310), cancelled=lambda: True)


def test_color_key_on_plain_background():
    img = Image.new("RGB", (200, 200), (240, 240, 240))
    ImageDraw.Draw(img).rectangle((60, 60, 140, 140), fill=(20, 80, 200))
    mask = seg.run_segmentation("colorkey", img)
    assert mask[100, 100] > 200 and mask[10, 10] < 30


def test_manual_mask_is_scaled_and_refined():
    img, _ = synthetic_scene()
    manual = np.zeros((100, 100), np.uint8)
    manual[20:80, 30:70] = 255
    mask = seg.run_segmentation("manual", img, manual_mask=manual)
    assert mask.shape == (400, 400)
    assert mask[200, 200] > 200 and mask[10, 10] == 0


def test_refine_removes_specks_and_fills_holes():
    m = np.zeros((300, 300), np.uint8)
    m[50:250, 50:250] = 255
    m[140:150, 140:150] = 0  # small hole
    m[10:13, 10:13] = 255  # speck
    out = seg.refine_mask(m, None, seg.RefineOptions(feather_px=0, remove_holes_area=2000, remove_specks_area=500, edge_refine=False))
    # Areas are specified for a 1000 px image and scale with image size (here 0.3² ×).
    assert out[145, 145] == 255
    assert out[11, 11] == 0


def test_keep_largest_only():
    m = np.zeros((200, 200), np.uint8)
    m[20:120, 20:120] = 255
    m[150:190, 150:190] = 255
    out = seg.refine_mask(m, None, seg.RefineOptions(feather_px=0, keep_largest_only=True, edge_refine=False))
    assert out[170, 170] == 0 and out[60, 60] == 255


def test_hints_decoding():
    hint = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    hint.putpixel((1, 1), (255, 0, 0, 255))
    hint.putpixel((5, 5), (0, 0, 255, 255))
    h = seg.hints_from_rgba(hint, (10, 10))
    assert h[1, 1] == seg.HINT_FG and h[5, 5] == seg.HINT_BG and h[8, 8] == seg.HINT_UNKNOWN


def test_extract_subject_is_transparent_png_and_decontaminated():
    img, truth = synthetic_scene()
    mask = seg.run_segmentation("grabcut", img, rect=(80, 50, 240, 310))
    subject = seg.extract_subject(img, mask)
    assert subject.mode == "RGBA"
    alpha = np.asarray(subject.getchannel("A"))
    assert alpha[5, 5] == 0 and alpha[200, 200] == 255
    # Semi-transparent edge pixels take the subject's red colour, not the blue background.
    rgb = np.asarray(subject.convert("RGB")).astype(int)
    edge = (alpha > 30) & (alpha < 220)
    assert edge.any()
    assert rgb[edge][:, 0].mean() > rgb[edge][:, 2].mean()


def test_alpha_bbox():
    a = np.zeros((50, 50), np.uint8)
    a[10:20, 5:30] = 255
    assert seg.alpha_bbox(a) == (5, 10, 25, 10)
    assert seg.alpha_bbox(np.zeros((5, 5), np.uint8)) is None


def test_model_status_without_model(tmp_path):
    st = seg.model_status(tmp_path)
    assert st["available"] is False and st["modelFile"] is None


def test_model_engine_with_tiny_local_onnx(tmp_path):
    """Exercise the optional ONNX path with a tiny generated model (no download)."""
    onnx = pytest.importorskip("onnx")
    pytest.importorskip("onnxruntime")
    from onnx import TensorProto, helper

    # Output = sigmoid(10 * (mean over channels of input)); shape 1x1x320x320.
    inp = helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, 3, 320, 320])
    out = helper.make_tensor_value_info("out", TensorProto.FLOAT, [1, 1, 320, 320])
    axes = helper.make_tensor("axes", TensorProto.INT64, [1], [1])
    scale = helper.make_tensor("scale", TensorProto.FLOAT, [], [10.0])
    nodes = [helper.make_node("ReduceMean", ["input", "axes"], ["m"], keepdims=1),
             helper.make_node("Constant", [], ["s"], value=scale),
             helper.make_node("Mul", ["m", "s"], ["ms"]), helper.make_node("Sigmoid", ["ms"], ["out"])]
    graph = helper.make_graph(nodes, "tiny", [inp], [out], initializer=[axes])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 18)])
    model.ir_version = 9
    path = tmp_path / "u2netp.onnx"
    path.write_bytes(model.SerializeToString())
    # find_model() ignores tiny placeholder files; point it at this test model directly.
    orig = seg.find_model
    seg.find_model = lambda d: path
    try:
        img = Image.new("RGB", (64, 64), (0, 0, 0))
        ImageDraw.Draw(img).rectangle((16, 16, 48, 48), fill=(255, 255, 255))
        mask = seg.run_segmentation("model", img, models_dir=tmp_path, refine=seg.RefineOptions(edge_refine=False, feather_px=0))
        assert mask[32, 32] > 200 and mask[2, 2] < 50
    finally:
        seg.find_model = orig
