"""Deterministic sticker-collection generation from templates.

Variants are built by combining crops, framing, scale, shapes, borders,
backgrounds, colour treatments, local accessories and user-supplied text.
A seeded random generator drives any "random" choices, so the same seed
and options always reproduce the same collection.

Nothing here invents new photographic content: poses, faces and clothing
all come from the user's own photos. Accessories are separate graphic
layers placed relative to a face region the user can see and edit.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from ..models.base import new_id
from ..models.layer import Layer
from ..models.sticker import Background, Border, Outline, Shadow, ShapeSpec, StickerDoc
from ..utils.image_dimensions import mm_to_px

COMPOSITIONS = ("hero", "closeup", "title-top", "framed", "scatter", "badge", "wordart-under", "prop", "emphasis")
NAVY = "#1d2b6a"
PROP_ASSETS = ("gift_stack", "teddy_bear", "cake_chocolate", "balloon_cluster", "gift_box", "slipper_cushion", "pumpkin_carriage",
               "vintage_car", "books_stack", "castle_blue", "rose_pink", "rose_blue")
BORDER_STYLES = ("classic", "bold", "double", "thin", "kiss")
TREATMENTS = ("none", "grayscale", "sepia", "posterize", "duotone", "cartoon", "warm", "vivid")

ANCHOR_BY_CATEGORY = {
    "crowns": "head", "party-hats": "head", "hats": "head", "sunglasses": "eyes", "bowties": "neck",
    "gentleman": "mouth",
}


def wordart_layers(template: dict, cx: float, cy: float, box_w: float, assets: dict[str, dict] | None = None) -> list[Layer]:
    """Build the layers of a word-art template centred at (cx, cy), ``box_w`` px wide.

    Large decorations (banners, balloon clusters) go behind the text; small
    ones (sparkles, hearts) go in front.
    """
    assets = assets or {}
    lines = template.get("lines") or []
    sizes = [float(l.get("size") or 0.15) * box_w for l in lines]
    heights = [sz * (1.25 if (l.get("font") or "") in ("Great Vibes", "Pacifico", "Lobster") else 1.05) for sz, l in zip(sizes, lines)]
    total = sum(heights)
    y = cy - total / 2
    text_layers = []
    for l, sz, hh in zip(lines, sizes, heights):
        colors = [c for c in (l.get("colors") or []) if isinstance(c, str)]
        stroke_rel = float(template.get("strokeRel", 0.07))
        text_layers.append(Layer(
            type="text", name=l.get("text") or "Text", text=l.get("text") or "", font_family=l.get("font") or "Luckiest Guy",
            font_size=sz, fill=l.get("fill") or NAVY, letter_colors=colors,
            stroke=NAVY if colors else template.get("stroke", "#ffffff"), stroke_width=sz * (0.07 if colors else stroke_rel),
            curve=float(l.get("curve") or 0), align="center", x=cx, y=y + hh / 2, width=box_w, height=hh,
            shadow={"color": "#1d2b6a40", "blur": 0, "offsetX": sz * 0.03, "offsetY": sz * 0.04} if colors else None))
        y += hh
    behind, front = [], []
    top = cy - total / 2
    for d in template.get("decor") or []:
        a = assets.get(d.get("asset"))
        aspect = float(a.get("aspect") or 1) if a else 1.0
        w = float(d.get("w") or 0.15) * box_w
        h = w / aspect
        fy = float(d.get("y", 0.5))
        y_px = top + fy * total
        if float(d.get("w") or 0) < 0.6:
            # Keep top/bottom ornaments (crowns, bows, hearts) clear of the lettering.
            if fy <= 0.15:
                y_px = top - h * 0.45
            elif fy >= 0.85 and abs(float(d.get("x", 0.5)) - 0.5) < 0.2:
                y_px = top + total + h * 0.45
        layer = Layer(type="asset", asset_id=d.get("asset"), name=(a or {}).get("name", d.get("asset")),
                      x=cx - box_w / 2 + float(d.get("x", 0.5)) * box_w, y=y_px,
                      width=w, height=h, rotation=float(d.get("rotation") or 0))
        (behind if float(d.get("w") or 0) >= 0.6 else front).append(layer)
    return behind + text_layers + front


def _match_wordart(text: str | None, theme: dict) -> dict | None:
    def norm(v):
        return "".join(ch for ch in (v or "").lower() if ch.isalnum())
    for t in theme.get("wordArt") or []:
        if norm(t.get("name", "").split("(")[0]) == norm(text) or norm(" ".join(l.get("text", "") for l in t.get("lines", []))) == norm(text):
            return t
    return None


@dataclass
class CollectionOptions:
    photo_ids: list[str]
    theme_id: str
    shapes: list[str] = field(default_factory=lambda: ["silhouette"])
    border_styles: list[str] = field(default_factory=lambda: ["classic"])
    count: int = 6
    accessory_ids: list[str] = field(default_factory=list)
    decoration_ids: list[str] = field(default_factory=list)
    backgrounds: list[dict] = field(default_factory=list)
    texts: list[str] = field(default_factory=list)
    treatments: list[str] = field(default_factory=lambda: ["none"])
    compositions: list[str] = field(default_factory=lambda: list(COMPOSITIONS))
    size_mm: float = 60.0
    seed: int = 1
    randomize: bool = False
    use_face_anchors: bool = True
    word_art: bool = True  # style matching text as theme word art
    text_stickers: int = 0  # extra word-art-only stickers
    decor_stickers: int = 0  # extra decoration-only stickers
    number: str | None = None  # optional number balloon chosen by the user (never inferred)


def _treatment_params(name: str, theme: dict) -> dict:
    pal = theme.get("palette") or ["#2b1055", "#ffd36e"]
    return {
        "none": {},
        "grayscale": {"filter": "grayscale"},
        "sepia": {"filter": "sepia"},
        "posterize": {"filter": "posterize", "posterizeLevels": 5},
        "cartoon": {"filter": "cartoon", "posterizeLevels": 7},
        "duotone": {"filter": "duotone", "duotoneDark": pal[-1] if len(pal) > 2 else "#2b1055", "duotoneLight": pal[0]},
        "warm": {"temperature": 0.45, "saturation": 0.15},
        "vivid": {"saturation": 0.35, "contrast": 0.12},
    }.get(name, {})


def border_for(style: str, theme: dict) -> Border:
    tb = theme.get("border") or {}
    pal = theme.get("palette") or ["#ff4f8b", "#ffd36e"]
    base_w = float(tb.get("widthMm", 3.0))
    color = tb.get("color", "#ffffff")
    if style == "bold":
        return Border(width_mm=base_w, color=color, outlines=[Outline(1.0, pal[0], 0.0)], smoothing=0.6)
    if style == "double":
        return Border(width_mm=base_w * 0.8, color=color,
                      outlines=[Outline(0.8, pal[0], 0.0), Outline(0.9, pal[1 % len(pal)], 0.8)], smoothing=0.6)
    if style == "thin":
        return Border(width_mm=max(1.0, base_w * 0.5), color=color, smoothing=0.5)
    if style == "kiss":
        return Border(width_mm=0.6, color=color, smoothing=0.3)
    outlines = [Outline(**{"width_mm": o.get("widthMm", 1), "color": o.get("color", pal[0]), "gap_mm": o.get("gapMm", 0)})
                for o in tb.get("outlines", [])]
    return Border(width_mm=base_w, color=color, outlines=outlines, smoothing=float(tb.get("smoothing", 0.5)))


def _face_box(photo: dict, crop: dict) -> tuple[float, float, float, float] | None:
    """Largest face region in normalised crop coordinates (x, y, w, h)."""
    faces = photo.get("faceRegions") or []
    W, H = photo.get("width", 1), photo.get("height", 1)
    if not faces:
        return None
    f = max(faces, key=lambda r: r["w"] * r["h"])
    fx, fy, fw, fh = f["x"] / W, f["y"] / H, f["w"] / W, f["h"] / H
    return ((fx - crop["x"]) / crop["w"], (fy - crop["y"]) / crop["h"], fw / crop["w"], fh / crop["h"])


def face_safe_crop(photo: dict, mode: str) -> dict:
    """Crop in normalised coordinates that never cuts through a face region."""
    box = photo.get("subjectBox") or {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}
    x0, y0, x1, y1 = box["x"], box["y"], box["x"] + box["w"], box["y"] + box["h"]
    faces = photo.get("faceRegions") or []
    W, H = photo.get("width", 1), photo.get("height", 1)
    if mode == "closeup" and faces:
        f = max(faces, key=lambda r: r["w"] * r["h"])
        fx0, fy0, fx1, fy1 = f["x"] / W, f["y"] / H, (f["x"] + f["w"]) / W, (f["y"] + f["h"]) / H
        fw, fh = fx1 - fx0, fy1 - fy0
        # Head-and-shoulders: generous margin around the face, more below it.
        cx0, cy0 = fx0 - fw * 0.6, fy0 - fh * 0.35
        cx1, cy1 = fx1 + fw * 0.6, fy1 + fh * 1.1
        x0, y0, x1, y1 = max(x0, cx0), max(y0, cy0), min(x1, cx1), min(y1, cy1)
    # Always include every face completely.
    for f in faces:
        x0, y0 = min(x0, f["x"] / W), min(y0, f["y"] / H)
        x1, y1 = max(x1, (f["x"] + f["w"]) / W), max(y1, (f["y"] + f["h"]) / H)
    x0, y0, x1, y1 = max(0.0, x0), max(0.0, y0), min(1.0, x1), min(1.0, y1)
    return {"x": round(x0, 5), "y": round(y0, 5), "w": round(max(0.01, x1 - x0), 5), "h": round(max(0.01, y1 - y0), 5)}


def _image_layer(photo: dict, crop: dict, box: tuple[float, float, float, float], source: str, treatment: dict) -> Layer:
    """Fit the cropped photo uniformly into box (cx, cy, max_w, max_h)."""
    cw = crop["w"] * photo.get("width", 1000)
    ch = crop["h"] * photo.get("height", 1000)
    cx, cy, mw, mh = box
    s = min(mw / cw, mh / ch)
    return Layer(type="image", name=photo.get("name", "Photo"), photo_id=photo["id"], source=source, crop=crop,
                 x=cx, y=cy, width=cw * s, height=ch * s, treatment=treatment)


def _anchor_layer(asset: dict, anchor: str, img: Layer, face: tuple[float, float, float, float]) -> Layer | None:
    fx, fy, fw, fh = face
    left = img.x - img.width / 2
    top = img.y - img.height / 2
    fpx, fpy, fpw, fph = left + fx * img.width, top + fy * img.height, fw * img.width, fh * img.height
    aspect = float(asset.get("aspect") or 1.0)
    if anchor == "head":
        w = fpw * 1.05
        h = w / aspect
        return Layer(type="asset", asset_id=asset["id"], name=asset["name"], x=fpx + fpw / 2, y=fpy + fph * 0.12 - h * 0.42, width=w, height=h)
    if anchor == "eyes":
        w = fpw * 0.86
        h = w / aspect
        return Layer(type="asset", asset_id=asset["id"], name=asset["name"], x=fpx + fpw / 2, y=fpy + fph * 0.46, width=w, height=h)
    if anchor == "mouth":
        w = fpw * 0.5
        h = w / aspect
        return Layer(type="asset", asset_id=asset["id"], name=asset["name"], x=fpx + fpw / 2, y=fpy + fph * 0.7, width=w, height=h)
    if anchor == "neck":
        w = fpw * 0.55
        h = w / aspect
        return Layer(type="asset", asset_id=asset["id"], name=asset["name"], x=fpx + fpw / 2, y=fpy + fph * 1.02 + h / 2, width=w, height=h)
    return None


def _text_layer(text: str, theme: dict, W: float, H: float, y: float, size: float, curve: float = 0.0) -> Layer:
    typo = theme.get("typography") or {}
    colors = theme.get("colors") or {}
    return Layer(type="text", name="Text", text=text, font_family=typo.get("heading", "Luckiest Guy"),
                 font_size=size, fill=colors.get("text", "#2d2140"), stroke="#ffffff", stroke_width=size * 0.12,
                 align="center", x=W / 2, y=y, width=W * 0.9, height=size * 1.2, curve=curve,
                 shadow={"color": "#00000040", "blur": 0, "offsetX": size * 0.04, "offsetY": size * 0.05})


def _scatter(rng: random.Random, assets: list[dict], n: int, W: float, H: float, avoid: Layer | None) -> list[Layer]:
    out = []
    spots = [(0.12, 0.14), (0.88, 0.14), (0.1, 0.62), (0.9, 0.6), (0.2, 0.9), (0.82, 0.88), (0.5, 0.06)]
    rng.shuffle(spots)
    for i in range(min(n, len(spots), max(1, len(assets) * 2))):
        a = assets[i % len(assets)]
        sx, sy = spots[i]
        size = min(W, H) * rng.uniform(0.14, 0.22)
        aspect = float(a.get("aspect") or 1)
        out.append(Layer(type="asset", asset_id=a["id"], name=a["name"], x=W * sx, y=H * sy,
                         width=size * (aspect if aspect < 1 else 1), height=size / (aspect if aspect > 1 else 1),
                         rotation=rng.uniform(-22, 22)))
    return out


def generate_collection(opts: CollectionOptions, theme: dict, photos: list[dict], assets: dict[str, dict]) -> list[dict]:
    """Return ``opts.count`` sticker documents (dicts) for the given options."""
    rng = random.Random(int(opts.seed))
    if not photos:
        if opts.text_stickers or opts.decor_stickers:
            return extra_stickers(opts, theme, assets, rng, 0)
        raise ValueError("Select at least one photo.")
    count = max(1, min(48, int(opts.count)))
    W = H = mm_to_px(opts.size_mm, 300)
    shapes = opts.shapes or ["silhouette"]
    borders = [b for b in opts.border_styles if b in BORDER_STYLES] or ["classic"]
    comps = [c for c in opts.compositions if c in COMPOSITIONS] or list(COMPOSITIONS)
    treatments = [t for t in opts.treatments if t in TREATMENTS] or ["none"]
    backgrounds = opts.backgrounds or theme.get("backgrounds") or [{"type": "solid", "color": "#ffffff"}]
    accessories = [assets[a] for a in opts.accessory_ids if a in assets]
    decorations = [assets[a] for a in opts.decoration_ids if a in assets and (not a.startswith("balloon_number_") or a == f"balloon_number_{opts.number}")]
    head = [a for a in accessories if ANCHOR_BY_CATEGORY.get(a.get("category", "")) == "head"]
    other_anchor = [a for a in accessories if ANCHOR_BY_CATEGORY.get(a.get("category", "")) in ("eyes", "neck", "mouth")]
    loose = [a for a in accessories if a not in head and a not in other_anchor] + decorations
    texts = [t for t in opts.texts if t.strip()]
    docs = []
    for i in range(count):
        pick = (lambda seq, k=i: rng.choice(seq)) if opts.randomize else (lambda seq, k=i: seq[k % len(seq)])
        photo = photos[i % len(photos)]
        comp = pick(comps)
        shape = pick(shapes)
        if comp in ("framed", "badge") and shape == "silhouette" and len(shapes) == 1:
            shape = "circle"
        border_style = pick(borders)
        treatment_name = treatments[(i // max(1, len(comps))) % len(treatments)] if not opts.randomize else rng.choice(treatments)
        treatment = _treatment_params(treatment_name, theme)
        has_subject = bool(photo.get("mask"))
        source = "subject" if has_subject and (shape == "silhouette" or comp not in ("framed",)) else "working"
        if shape == "silhouette" and not has_subject:
            source = "working"  # whole photo; the die-cut then follows the rectangle
        crop = face_safe_crop(photo, "closeup" if comp in ("closeup", "badge") else "full")
        if source == "working" and not has_subject:
            crop = face_safe_crop({**photo, "subjectBox": None}, "closeup" if comp in ("closeup", "badge") else "full")
        layers: list[Layer] = []
        text = texts[i % len(texts)] if texts else None
        margin = 0.06 if shape == "silhouette" else 0.16
        if comp == "hero":
            img = _image_layer(photo, crop, (W / 2, H * 0.47, W * (1 - 2 * margin), H * (0.78 if text else 0.88)), source, treatment)
        elif comp == "closeup":
            img = _image_layer(photo, crop, (W / 2, H * 0.47, W * (1 - 2 * margin), H * (0.74 if text else 0.86)), source, treatment)
        elif comp == "title-top":
            img = _image_layer(photo, crop, (W / 2, H * 0.6, W * 0.8, H * 0.7), source, treatment)
        elif comp == "scatter":
            img = _image_layer(photo, crop, (W / 2, H * 0.52, W * 0.62, H * 0.66), source, treatment)
        elif comp == "badge":
            img = _image_layer(photo, crop, (W / 2, H * 0.5, W * 0.6, H * 0.6), source, treatment)
        elif comp == "wordart-under":
            img = _image_layer(photo, crop, (W / 2, H * 0.36, W * 0.84, H * 0.66), source, treatment)
        elif comp == "prop":
            img = _image_layer(photo, crop, (W * 0.44, H * 0.45, W * 0.76, H * 0.86), source, treatment)
        elif comp == "emphasis":
            img = _image_layer(photo, crop, (W / 2, H * 0.5, W * 0.78, H * 0.88), source, treatment)
        else:  # framed
            img = _image_layer(photo, crop, (W / 2, H * 0.53, W * 0.72, H * 0.72), source, treatment)
        layers.append(img)
        face = _face_box(photo, crop) if opts.use_face_anchors else None
        if face is not None:
            if head and comp != "badge":
                hat = _anchor_layer(head[i % len(head)], "head", img, face)
                if hat:
                    layers.append(hat)
            if other_anchor and (i % 2 == 1 or not head):
                a = other_anchor[i % len(other_anchor)]
                acc = _anchor_layer(a, ANCHOR_BY_CATEGORY[a["category"]], img, face)
                if acc:
                    layers.append(acc)
        elif head:
            # No face region: place the hat on top of the subject's bounding box.
            a = head[i % len(head)]
            w = img.width * 0.45
            h = w / float(a.get("aspect") or 1)
            layers.append(Layer(type="asset", asset_id=a["id"], name=a["name"], x=img.x, y=img.y - img.height / 2 + h * 0.15, width=w, height=h,
                                rotation=-8))
        if loose and comp in ("scatter", "hero", "framed", "title-top"):
            n = 4 if comp == "scatter" else 2
            layers += _scatter(rng, loose, n, W, H, img)
        if comp == "prop":
            # Number balloons only ever come from the user's explicit choice (never a guessed age).
            props = [assets[a] for a in dict.fromkeys(opts.decoration_ids + list(theme.get("decorations") or [])) if a in assets and a in PROP_ASSETS]
            if opts.number and f"balloon_number_{opts.number}" in assets:
                props.insert(0, assets[f"balloon_number_{opts.number}"])
            if props:
                a = props[i % len(props)]
                aspect = float(a.get("aspect") or 1)
                h = H * (0.62 if aspect < 0.8 else 0.42)
                w = h * aspect
                tall = aspect < 0.8
                layers.append(Layer(type="asset", asset_id=a["id"], name=a["name"], x=W - w / 2 - W * 0.04,
                                    y=H * (0.5 if tall else 0.72), width=w, height=h))
        if comp in ("emphasis", "prop", "wordart-under"):
            lines = assets.get("action_lines_color") or assets.get("action_lines")
            if lines:
                fx = _face_box(photo, crop)
                top_y = img.y - img.height / 2 + (fx[1] * img.height if fx else img.height * 0.05)
                left_x = img.x - img.width / 2 + (fx[0] * img.width if fx else img.width * 0.15)
                right_x = img.x - img.width / 2 + ((fx[0] + fx[2]) * img.width if fx else img.width * 0.85)
                s_ = min(W, H) * 0.17
                layers.append(Layer(type="asset", asset_id=lines["id"], name="Emphasis lines", x=max(s_ / 2, left_x - s_ * 0.1), y=max(s_ / 2, top_y), width=s_, height=s_))
                if comp == "emphasis":
                    layers.append(Layer(type="asset", asset_id=lines["id"], name="Emphasis lines", x=min(W - s_ / 2, right_x + s_ * 0.1), y=max(s_ / 2, top_y),
                                        width=s_, height=s_, flip_x=True))
        template = _match_wordart(text, theme) if (text and opts.word_art) else None
        if comp == "wordart-under" and text:
            template = template or {"lines": [{"text": text, "font": (theme.get("typography") or {}).get("heading", "Luckiest Guy"),
                                               "size": 0.15, "colors": (theme.get("palette") or [])[:3]}], "decor": []}
        if template:
            # Inside shaped stickers the art is clipped by the shape, so keep word art smaller and higher.
            shaped = shape != "silhouette"
            layers += wordart_layers(template, W / 2, H * (0.72 if shaped else 0.8), W * (0.62 if shaped else 0.92), assets)
        elif text:
            if comp == "title-top":
                layers.append(_text_layer(text, theme, W, H, H * 0.17, H * 0.12, curve=60))
            elif comp == "badge":
                layers.append(_text_layer(text, theme, W, H, H * 0.86, H * 0.1, curve=-70))
            else:
                layers.append(_text_layer(text, theme, W, H, H * 0.86, H * 0.11))
        bg = backgrounds[i % len(backgrounds)] if not opts.randomize else rng.choice(backgrounds)
        tshadow = theme.get("shadow") or {}
        doc = StickerDoc(
            name=f"{theme.get('name', 'Sticker')} {i + 1}",
            width_mm=opts.size_mm, height_mm=opts.size_mm,
            shape=ShapeSpec(type=shape if shape in ("silhouette", "circle", "oval", "rounded", "rect", "square", "heart", "star", "speech") else "silhouette",
                            corner_radius_mm=opts.size_mm * 0.12),
            border=border_for(border_style, theme),
            shadow=Shadow(enabled=bool(tshadow.get("enabled", False)), target="art", blur_mm=tshadow.get("blurMm", 1.0),
                          opacity=tshadow.get("opacity", 0.3)),
            background=Background(type=bg.get("type", "solid"), color=bg.get("color", "#ffffff"), color2=bg.get("color2", "#ffffff"),
                                  angle=bg.get("angle", 90), pattern_id=bg.get("patternId"), pattern_color=bg.get("patternColor", "#ffffff")),
            layers=layers,
            theme_id=theme.get("id"),
            variant={"index": i, "composition": comp, "shape": shape, "border": border_style, "treatment": treatment_name,
                     "photoId": photo["id"], "seed": opts.seed,
                     "note": "Composited from your photo and local graphics; no new photographic content was generated."},
        )
        for layer in doc.layers:
            layer.id = new_id("ly_")
        docs.append(doc.to_dict())
    docs += extra_stickers(opts, theme, assets, rng, len(docs))
    return docs


def _plain_doc(name: str, opts: CollectionOptions, theme: dict, layers: list[Layer], index: int, kind: str) -> dict:
    doc = StickerDoc(name=name, width_mm=opts.size_mm, height_mm=opts.size_mm, shape=ShapeSpec(type="silhouette"),
                     border=border_for((opts.border_styles or ["classic"])[0], theme), layers=layers, theme_id=theme.get("id"),
                     variant={"index": index, "composition": kind, "shape": "silhouette", "seed": opts.seed,
                              "note": "Made from local graphics and text only."})
    return doc.to_dict()


def extra_stickers(opts: CollectionOptions, theme: dict, assets: dict[str, dict], rng: random.Random, start: int) -> list[dict]:
    """Word-art-only and decoration-only stickers that complete a themed sheet."""
    W = mm_to_px(opts.size_mm, 300)
    out = []
    templates = list(theme.get("wordArt") or [])
    wanted = [t for t in templates if any(_match_wordart(x, theme) is t for x in opts.texts)] or templates
    for k in range(max(0, min(24, int(opts.text_stickers)))):
        if not wanted:
            break
        t = wanted[k % len(wanted)]
        out.append(_plain_doc(t["name"], opts, theme, wordart_layers(t, W / 2, W / 2, W * 0.9, assets), start + len(out), "wordart"))
    skip = {"confetti", "banners", "frames", "shapes", "badges"}
    decor = [a for a in (opts.decoration_ids or theme.get("decorations") or []) if a in assets and assets[a].get("category") not in skip
             and not a.startswith("balloon_number_")]
    picks = [decor[(k * 3 + int(opts.seed)) % len(decor)] for k in range(max(0, min(24, int(opts.decor_stickers))))] if decor else []
    if opts.number and f"balloon_number_{opts.number}" in assets and opts.decor_stickers:
        picks = [f"balloon_number_{opts.number}"] + picks[:-1]  # the chosen number comes first
    for k, aid in enumerate(picks):
        a = assets[aid]
        aspect = float(a.get("aspect") or 1)
        w, h = (W * 0.86, W * 0.86 / aspect) if aspect >= 1 else (W * 0.86 * aspect, W * 0.86)
        layers = [Layer(type="asset", asset_id=a["id"], name=a["name"], x=W / 2, y=W / 2, width=w, height=h)]
        sparkle = assets.get("sparkles")
        if sparkle and 0.6 <= aspect <= 1.4:
            layers.append(Layer(type="asset", asset_id="sparkles", name="Sparkles", x=W / 2 + w * 0.42, y=W / 2 - h * 0.38, width=W * 0.18, height=W * 0.18, rotation=rng.uniform(-10, 10)))
        out.append(_plain_doc(a["name"], opts, theme, layers, start + len(out), "decoration"))
    return out
