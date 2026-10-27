import io

import numpy as np
from PIL import Image

from app.services import photo_service
from tests.fixtures.synthetic import figure_image, jpeg_bytes, png_bytes, transparent_subject

LIMITS = photo_service.Limits(20_000_000, 50_000_000, 10000, 600, 200)


def test_exif_orientation_is_applied(tmp_path):
    # Orientation 6 = rotate 90° clockwise for display: an 800x1000 sensor image shows as 1000x800.
    img = figure_image((800, 1000))
    photo = photo_service.import_photo(jpeg_bytes(img, orientation=6), "rotated.jpg", tmp_path, LIMITS)
    assert (photo["originalWidth"], photo["originalHeight"]) == (800, 1000)
    assert (photo["width"], photo["height"]) == (1000, 800)
    working = photo_service.load_working(tmp_path, photo)
    assert working.size == (1000, 800)


def test_original_bytes_preserved(tmp_path):
    data = jpeg_bytes(figure_image((400, 500)))
    photo = photo_service.import_photo(data, "x.jpg", tmp_path, LIMITS)
    assert (tmp_path / photo["original"]).read_bytes() == data


def test_transparency_preserved(tmp_path):
    photo = photo_service.import_photo(png_bytes(transparent_subject()), "subject.png", tmp_path, LIMITS)
    working = photo_service.load_working(tmp_path, photo)
    assert working.mode == "RGBA"
    alpha = np.asarray(working.getchannel("A"))
    assert alpha.min() == 0 and alpha.max() == 255
    assert photo["hasAlpha"]


def test_previews_and_thumbnails(tmp_path):
    photo = photo_service.import_photo(jpeg_bytes(figure_image((1200, 1500))), "big.jpg", tmp_path, LIMITS)
    paths = photo_service.photo_paths(tmp_path, photo)
    assert max(Image.open(paths["preview"]).size) == 600
    assert max(Image.open(paths["thumb"]).size) == 200


def test_geometric_edits():
    img = Image.new("RGB", (400, 200), (255, 0, 0))
    img.paste((0, 0, 255), (0, 0, 100, 200))  # blue left quarter
    out = photo_service.apply_geometric_edits(img, {"rotate": 90})
    assert out.size == (200, 400)
    flipped = photo_service.apply_geometric_edits(img, {"flipH": True})
    assert flipped.getpixel((399, 10)) == (0, 0, 255)
    cropped = photo_service.apply_geometric_edits(img, {"crop": {"x": 0, "y": 0, "w": 0.25, "h": 1}})
    assert cropped.size == (100, 200) and cropped.getpixel((50, 100)) == (0, 0, 255)


def test_resize_never_upscales():
    img = Image.new("RGB", (400, 200))
    assert photo_service.apply_geometric_edits(img, {"resizeMaxSide": 200}).size == (200, 100)
    assert photo_service.apply_geometric_edits(img, {"resizeMaxSide": 4000}).size == (400, 200)


def test_rebuild_from_original_does_not_degrade(tmp_path):
    photo = photo_service.import_photo(jpeg_bytes(figure_image((400, 500))), "x.jpg", tmp_path, LIMITS)
    first = np.asarray(photo_service.load_working(tmp_path, photo)).copy()
    for _ in range(3):
        photo["edits"] = {"rotate": 90}
        photo_service.rebuild_working(tmp_path, photo, LIMITS)
        photo["edits"] = {"rotate": 0}
        photo_service.rebuild_working(tmp_path, photo, LIMITS)
    again = np.asarray(photo_service.load_working(tmp_path, photo))
    assert np.array_equal(first, again)


def test_face_mask():
    m = photo_service.face_mask((100, 100), [{"x": 20, "y": 20, "w": 40, "h": 40}])
    arr = np.asarray(m)
    assert arr[40, 40] > 200 and arr[2, 2] == 0
