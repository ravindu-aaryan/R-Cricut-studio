"""Generate the bundled, original SVG decoration library, patterns and themes.

All artwork here is drawn from simple geometric primitives written for this
project and released under CC0 1.0 (see LICENSES.md). Re-run with::

    python scripts/build_assets.py
"""
from __future__ import annotations

import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEC = ROOT / "assets" / "decorations"
FRM = ROOT / "assets" / "frames"
PAT = ROOT / "assets" / "patterns"
THM = ROOT / "assets" / "themes"
INK = "#2d2140"
SW = 5
LICENSE = "CC0 1.0 (original artwork for Offline Sticker Studio)"


def svg(w, h, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f'{body}</svg>')


def ink(extra=""):
    """Dark cartoon outline. ``extra`` may override the stroke width."""
    m = re.search(r'stroke-width="([\d.]+)"', extra)
    width = m.group(1) if m else SW
    rest = re.sub(r'stroke-width="[\d.]+"', "", extra).strip()
    return f'stroke="{INK}" stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round" {rest}'


def star_pts(cx, cy, r, inner=0.5, n=5, rot=-90):
    pts = []
    for i in range(2 * n):
        rr = r if i % 2 == 0 else r * inner
        a = math.radians(rot + 180 * i / n)
        pts.append(f"{cx + rr * math.cos(a):.1f},{cy + rr * math.sin(a):.1f}")
    return " ".join(pts)


def heart_path(cx, cy, s):
    return (f"M{cx},{cy + 0.9 * s} C{cx - 1.4 * s},{cy - 0.1 * s} {cx - 0.9 * s},{cy - 1.1 * s} {cx},{cy - 0.45 * s} "
            f"C{cx + 0.9 * s},{cy - 1.1 * s} {cx + 1.4 * s},{cy - 0.1 * s} {cx},{cy + 0.9 * s} Z")


def P(slot, default):
    return f'fill="{default}" data-recolor="{slot}"'


ASSETS: list[dict] = []


def add(id, name, category, tags, w, h, body, recolor=("primary",), defaults=None, frame=False, anchor=None):
    ASSETS.append({"id": id, "name": name, "category": category, "tags": tags, "w": w, "h": h, "body": body,
                   "recolor": list(recolor), "defaults": defaults or {}, "frame": frame, "anchor": anchor})


# ------------------------------------------------------------------ crowns
add("crown_gold", "Gold crown", "crowns", ["crown", "king", "queen", "birthday", "royal"], 200, 130,
    f'<path d="M15,115 L25,30 L65,75 L100,15 L135,75 L175,30 L185,115 Z" {P("primary", "#ffc93c")} {ink()}/>'
    f'<rect x="15" y="100" width="170" height="22" rx="6" {P("secondary", "#ff9f1c")} {ink()}/>'
    f'<circle cx="100" cy="60" r="10" fill="#ff4f8b" {ink("stroke-width=\"3\"")}/>'
    f'<circle cx="25" cy="30" r="8" fill="#ffffff" {ink("stroke-width=\"3\"")}/><circle cx="100" cy="15" r="8" fill="#ffffff" {ink("stroke-width=\"3\"")}/>'
    f'<circle cx="175" cy="30" r="8" fill="#ffffff" {ink("stroke-width=\"3\"")}/>'
    f'<circle cx="60" cy="111" r="5" fill="#4cc9f0"/><circle cx="100" cy="111" r="5" fill="#ff4f8b"/><circle cx="140" cy="111" r="5" fill="#4cc9f0"/>'
    f'<path d="M45,92 L55,80" stroke="#ffffff" stroke-width="5" stroke-linecap="round" opacity="0.7"/>',
    ("primary", "secondary"), anchor="head")
add("crown_royal", "Royal crown", "crowns", ["crown", "king", "prince", "royal", "jewels"], 200, 150,
    f'<path d="M20,130 C10,80 30,50 45,60 C55,30 80,30 100,10 C120,30 145,30 155,60 C170,50 190,80 180,130 Z" {P("primary", "#ffd166")} {ink()}/>'
    f'<rect x="18" y="115" width="164" height="26" rx="8" {P("secondary", "#9b5de5")} {ink()}/>'
    f'<circle cx="55" cy="128" r="6" fill="#00f5d4"/><circle cx="100" cy="128" r="7" fill="#ff4f8b"/><circle cx="145" cy="128" r="6" fill="#00f5d4"/>'
    f'<path d="M100,40 L112,75 L100,95 L88,75 Z" fill="#ff4f8b" {ink("stroke-width=\"3\"")}/>'
    f'<circle cx="100" cy="10" r="9" fill="#ffffff" {ink("stroke-width=\"3\"")}/>', ("primary", "secondary"), anchor="head")
add("crown_paper", "Paper party crown", "crowns", ["crown", "party", "paper", "birthday"], 200, 110,
    f'<path d="M10,100 L10,30 L45,65 L70,20 L100,60 L130,20 L155,65 L190,30 L190,100 Z" {P("primary", "#4cc9f0")} {ink()}/>'
    f'<path d="M10,82 L190,82" stroke="#ffffff" stroke-width="8" opacity="0.6"/>'
    f'<circle cx="70" cy="45" r="6" fill="#ffffff"/><circle cx="130" cy="45" r="6" fill="#ffffff"/>', anchor="head")

# ------------------------------------------------------------------ party hats
add("party_hat_stripes", "Striped party hat", "party-hats", ["party", "hat", "birthday", "cone"], 140, 200,
    f'<path d="M70,15 L125,180 L15,180 Z" {P("primary", "#ff4f8b")} {ink()}/>'
    f'<path d="M48,80 L100,100 M34,122 L112,142 M22,160 L120,178" stroke="#ffffff" stroke-width="12" opacity="0.85"/>'
    f'<path d="M70,15 L125,180 L15,180 Z" fill="none" {ink()}/>'
    f'<ellipse cx="70" cy="182" rx="62" ry="12" {P("secondary", "#ffd166")} {ink()}/>'
    f'<circle cx="70" cy="14" r="13" {P("secondary", "#ffd166")} {ink()}/>', ("primary", "secondary"), anchor="head")
add("party_hat_dots", "Polka-dot party hat", "party-hats", ["party", "hat", "birthday", "dots"], 140, 200,
    f'<path d="M70,15 L125,180 L15,180 Z" {P("primary", "#4cc9f0")} {ink()}/>'
    f'<circle cx="70" cy="70" r="8" fill="#ffffff"/><circle cx="50" cy="120" r="9" fill="#ffffff"/><circle cx="92" cy="128" r="9" fill="#ffffff"/>'
    f'<circle cx="70" cy="160" r="9" fill="#ffffff"/><circle cx="35" cy="165" r="7" fill="#ffffff"/><circle cx="105" cy="165" r="7" fill="#ffffff"/>'
    f'<path d="M15,180 Q30,170 45,180 Q60,190 70,180 Q85,170 100,180 Q115,190 125,180" fill="none" stroke="{INK}" stroke-width="4"/>'
    f'<circle cx="70" cy="14" r="13" {P("secondary", "#ff9f1c")} {ink()}/>', ("primary", "secondary"), anchor="head")

# ------------------------------------------------------------------ hats
add("top_hat", "Top hat", "hats", ["hat", "gentleman", "formal", "magic"], 200, 160,
    f'<rect x="50" y="10" width="100" height="120" rx="8" {P("primary", "#2d2140")} {ink()}/>'
    f'<rect x="50" y="95" width="100" height="20" {P("secondary", "#e63946")} {ink("stroke-width=\"3\"")}/>'
    f'<ellipse cx="100" cy="135" rx="92" ry="18" {P("primary", "#2d2140")} {ink()}/>'
    f'<path d="M62,25 L62,85" stroke="#ffffff" stroke-width="5" opacity="0.25" stroke-linecap="round"/>',
    ("primary", "secondary"), anchor="head")
add("bowler_hat", "Bowler hat", "hats", ["hat", "gentleman", "derby"], 200, 130,
    f'<path d="M45,100 C45,25 155,25 155,100 Z" {P("primary", "#5a3e2b")} {ink()}/>'
    f'<rect x="45" y="80" width="110" height="18" {P("secondary", "#2d2140")}/>'
    f'<path d="M8,108 C40,92 160,92 192,108 C170,124 30,124 8,108 Z" {P("primary", "#5a3e2b")} {ink()}/>'
    f'<path d="M70,45 C80,35 95,32 105,33" stroke="#ffffff" stroke-width="5" fill="none" opacity="0.3" stroke-linecap="round"/>',
    ("primary", "secondary"), anchor="head")
add("cowboy_hat", "Cowboy hat", "hats", ["hat", "western", "adventure"], 200, 120,
    f'<path d="M60,85 C55,20 85,30 100,40 C115,30 145,20 140,85 Z" {P("primary", "#c68642")} {ink()}/>'
    f'<path d="M5,80 C30,110 170,110 195,80 C185,70 170,95 100,95 C30,95 15,70 5,80 Z" {P("primary", "#c68642")} {ink()}/>'
    f'<path d="M60,78 C80,86 120,86 140,78" stroke="{INK}" stroke-width="7" fill="none"/>', anchor="head")
add("witch_hat", "Witch hat", "hats", ["halloween", "hat", "witch", "spooky"], 200, 200,
    f'<path d="M100,10 C120,60 130,110 150,160 L50,160 C70,110 85,60 100,10 Z" {P("primary", "#5a189a")} {ink()}/>'
    f'<path d="M100,10 C90,30 70,35 60,30" stroke="{INK}" stroke-width="5" fill="none"/>'
    f'<rect x="58" y="135" width="84" height="18" {P("secondary", "#ff9f1c")} {ink("stroke-width=\"3\"")}/>'
    f'<ellipse cx="100" cy="165" rx="95" ry="20" {P("primary", "#5a189a")} {ink()}/>', ("primary", "secondary"), anchor="head")
add("santa_hat", "Santa hat", "hats", ["christmas", "hat", "santa", "winter"], 200, 170,
    f'<path d="M30,130 C40,50 110,10 165,40 C175,70 170,100 160,110 C150,80 130,70 120,75 C150,100 160,120 170,130 Z" {P("primary", "#e63946")} {ink()}/>'
    f'<rect x="18" y="118" width="164" height="38" rx="19" fill="#ffffff" {ink()}/>'
    f'<circle cx="165" cy="115" r="20" fill="#ffffff" {ink()}/>', anchor="head")
add("grad_cap", "Graduation cap", "hats", ["school", "graduation", "cap", "teacher"], 200, 140,
    f'<path d="M100,10 L195,50 L100,90 L5,50 Z" {P("primary", "#2d2140")} {ink()}/>'
    f'<path d="M45,68 L45,110 C70,130 130,130 155,110 L155,68 L100,90 Z" {P("primary", "#2d2140")} {ink()}/>'
    f'<path d="M100,50 L170,62 L170,110" stroke="{P("secondary", "#ffc93c").split(chr(34))[1]}" stroke-width="5" fill="none" data-recolor="secondary"/>'
    f'<circle cx="170" cy="118" r="8" {P("secondary", "#ffc93c")}/>', ("primary", "secondary"), anchor="head")
add("baseball_cap", "Sports cap", "hats", ["sports", "cap", "baseball"], 200, 120,
    f'<path d="M30,90 C30,20 150,15 160,85 Z" {P("primary", "#3a86ff")} {ink()}/>'
    f'<path d="M100,90 C140,80 180,82 195,100 C170,108 120,105 100,100 Z" {P("secondary", "#1d3557")} {ink()}/>'
    f'<path d="M95,22 C92,50 92,70 95,88" stroke="{INK}" stroke-width="3" fill="none"/>'
    f'<circle cx="95" cy="22" r="6" {P("secondary", "#1d3557")} {ink("stroke-width=\"3\"")}/>', ("primary", "secondary"), anchor="head")

# ------------------------------------------------------------------ balloons
def balloon(cx, cy, r, slot, color):
    return (f'<path d="M{cx},{cy + r * 1.2} C{cx - 5},{cy + r * 1.6} {cx + 8},{cy + r * 2.0} {cx},{cy + r * 2.6}" '
            f'stroke="{INK}" stroke-width="3" fill="none"/>'
            f'<ellipse cx="{cx}" cy="{cy}" rx="{r}" ry="{r * 1.2}" {P(slot, color)} {ink()}/>'
            f'<path d="M{cx - 6},{cy + r * 1.18} L{cx + 6},{cy + r * 1.18} L{cx},{cy + r * 1.05} Z" fill="{color}" data-recolor="{slot}" {ink("stroke-width=\"3\"")}/>'
            f'<ellipse cx="{cx - r * 0.35}" cy="{cy - r * 0.45}" rx="{r * 0.16}" ry="{r * 0.3}" fill="#ffffff" opacity="0.6" transform="rotate(25 {cx - r * 0.35} {cy - r * 0.45})"/>')


add("balloon_single", "Balloon", "balloons", ["balloon", "party", "birthday"], 120, 220, balloon(60, 60, 45, "primary", "#ff4f8b"))
add("balloon_bunch", "Balloon bunch", "balloons", ["balloons", "party", "birthday", "celebration"], 220, 240,
    balloon(60, 70, 40, "primary", "#ff4f8b") + balloon(160, 70, 40, "secondary", "#4cc9f0") + balloon(110, 50, 44, "accent", "#ffd166"),
    ("primary", "secondary", "accent"))
add("balloon_heart", "Heart balloon", "balloons", ["balloon", "heart", "love", "valentine"], 160, 230,
    f'<path d="M80,140 C75,170 90,190 80,225" stroke="{INK}" stroke-width="3" fill="none"/>'
    f'<path d="{heart_path(80, 75, 60)}" {P("primary", "#ff4f8b")} {ink()}/>'
    f'<ellipse cx="55" cy="55" rx="9" ry="16" fill="#ffffff" opacity="0.55" transform="rotate(-30 55 55)"/>')
add("balloon_star", "Star balloon", "balloons", ["balloon", "star", "party"], 180, 240,
    f'<path d="M90,165 C85,190 100,210 90,238" stroke="{INK}" stroke-width="3" fill="none"/>'
    f'<polygon points="{star_pts(90, 90, 80, 0.5)}" {P("primary", "#ffd166")} {ink()}/>'
    f'<polygon points="{star_pts(90, 90, 40, 0.5)}" fill="#ffffff" opacity="0.35"/>')
add("balloon_number", "Round balloons trio", "balloons", ["balloons", "party", "pastel"], 240, 200,
    balloon(50, 60, 34, "primary", "#cdb4db") + balloon(120, 50, 34, "secondary", "#a2d2ff") + balloon(190, 60, 34, "accent", "#ffafcc"),
    ("primary", "secondary", "accent"))

# ------------------------------------------------------------------ confetti / sparkles
def confetti_body(seed=1, n=26, w=200, h=200):
    import random
    rng = random.Random(seed)
    colors = ["#ff4f8b", "#4cc9f0", "#ffd166", "#06d6a0", "#9b5de5", "#ff9f1c"]
    out = []
    for i in range(n):
        x, y = rng.uniform(10, w - 10), rng.uniform(10, h - 10)
        c = colors[i % len(colors)]
        kind = i % 3
        rot = rng.uniform(0, 180)
        if kind == 0:
            out.append(f'<rect x="{x - 6:.1f}" y="{y - 3:.1f}" width="12" height="6" rx="2" fill="{c}" transform="rotate({rot:.0f} {x:.1f} {y:.1f})"/>')
        elif kind == 1:
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rng.uniform(3, 6):.1f}" fill="{c}"/>')
        else:
            out.append(f'<path d="M{x - 8:.1f},{y:.1f} q4,-8 8,0 t8,0" stroke="{c}" stroke-width="4" fill="none" stroke-linecap="round" transform="rotate({rot:.0f} {x:.1f} {y:.1f})"/>')
    return "".join(out)


add("confetti_scatter", "Confetti", "confetti", ["confetti", "party", "celebration"], 200, 200, confetti_body(3), ())
add("confetti_burst", "Confetti burst", "confetti", ["confetti", "burst", "party", "celebrate"], 200, 200,
    "".join(f'<path d="M100,100 L{100 + 90 * math.cos(math.radians(a)):.1f},{100 + 90 * math.sin(math.radians(a)):.1f}" '
            f'stroke="{["#ff4f8b", "#4cc9f0", "#ffd166", "#06d6a0"][i % 4]}" stroke-width="7" stroke-linecap="round" stroke-dasharray="10 14"/>'
            for i, a in enumerate(range(0, 360, 30))) + confetti_body(7, 12), ())
add("streamers", "Streamers", "confetti", ["streamers", "party", "ribbon"], 240, 120,
    f'<path d="M5,20 C40,80 80,-10 120,50 C160,110 200,10 235,60" stroke="#ff4f8b" stroke-width="10" fill="none" stroke-linecap="round" data-recolor="primary"/>'
    f'<path d="M5,60 C45,110 85,30 125,90 C165,140 200,50 235,100" stroke="#4cc9f0" stroke-width="10" fill="none" stroke-linecap="round" data-recolor="secondary"/>',
    ("primary", "secondary"))
add("sparkles", "Sparkles", "stars", ["sparkle", "shine", "magic", "twinkle"], 200, 200,
    "".join(f'<path d="M{x},{y - s} Q{x + s * 0.18},{y - s * 0.18} {x + s},{y} Q{x + s * 0.18},{y + s * 0.18} {x},{y + s} '
            f'Q{x - s * 0.18},{y + s * 0.18} {x - s},{y} Q{x - s * 0.18},{y - s * 0.18} {x},{y - s} Z" {P("primary", "#ffd166")} {ink("stroke-width=\"4\"")}/>'
            for x, y, s in ((70, 80, 55), (150, 50, 28), (150, 150, 34))))

# ------------------------------------------------------------------ stars
add("star_basic", "Star", "stars", ["star", "shape", "award"], 200, 200,
    f'<polygon points="{star_pts(100, 106, 92, 0.48)}" {P("primary", "#ffd166")} {ink()}/>'
    f'<polygon points="{star_pts(100, 106, 48, 0.48)}" fill="#ffffff" opacity="0.3"/>')
add("star_shooting", "Shooting star", "stars", ["star", "shooting", "space", "wish"], 240, 160,
    f'<path d="M20,140 L120,80 M10,110 L110,62 M40,155 L130,100" stroke="#4cc9f0" stroke-width="9" stroke-linecap="round" data-recolor="secondary"/>'
    f'<polygon points="{star_pts(165, 62, 58, 0.48, rot=-80)}" {P("primary", "#ffd166")} {ink()}/>', ("primary", "secondary"))
add("stars_trio", "Three stars", "stars", ["stars", "rating", "award"], 240, 120,
    f'<polygon points="{star_pts(45, 75, 40, 0.48)}" {P("primary", "#ffd166")} {ink()}/>'
    f'<polygon points="{star_pts(120, 55, 50, 0.48)}" {P("primary", "#ffd166")} {ink()}/>'
    f'<polygon points="{star_pts(195, 75, 40, 0.48)}" {P("primary", "#ffd166")} {ink()}/>')
add("star_face", "Smiling star", "stars", ["star", "cute", "kids"], 200, 200,
    f'<polygon points="{star_pts(100, 108, 92, 0.52)}" {P("primary", "#ffd166")} {ink()}/>'
    f'<circle cx="82" cy="105" r="7" fill="{INK}"/><circle cx="118" cy="105" r="7" fill="{INK}"/>'
    f'<path d="M85,125 Q100,138 115,125" stroke="{INK}" stroke-width="5" fill="none" stroke-linecap="round"/>'
    f'<circle cx="70" cy="122" r="7" fill="#ff8fab" opacity="0.7"/><circle cx="130" cy="122" r="7" fill="#ff8fab" opacity="0.7"/>')

# ------------------------------------------------------------------ hearts
add("heart_basic", "Heart", "hearts", ["heart", "love", "valentine"], 200, 190,
    f'<path d="{heart_path(100, 95, 85)}" {P("primary", "#ff4f8b")} {ink()}/>'
    f'<ellipse cx="62" cy="62" rx="12" ry="20" fill="#ffffff" opacity="0.5" transform="rotate(-35 62 62)"/>')
add("hearts_double", "Two hearts", "hearts", ["hearts", "love", "friendship"], 240, 180,
    f'<path d="{heart_path(85, 95, 70)}" {P("primary", "#ff4f8b")} {ink()}/>'
    f'<path d="{heart_path(165, 85, 55)}" {P("secondary", "#ffafcc")} {ink()}/>', ("primary", "secondary"))
add("heart_outline", "Heart outline", "hearts", ["heart", "outline", "love", "minimal"], 200, 190,
    f'<path d="{heart_path(100, 95, 82)}" fill="none" stroke="#ff4f8b" stroke-width="14" data-recolor="primary"/>')
add("heart_wings", "Winged heart", "hearts", ["heart", "wings", "love", "cute"], 260, 170,
    f'<path d="M95,80 C60,30 20,40 10,70 C30,70 40,80 30,95 C50,95 60,105 55,120 C75,115 90,105 95,80 Z" fill="#ffffff" {ink()}/>'
    f'<path d="M165,80 C200,30 240,40 250,70 C230,70 220,80 230,95 C210,95 200,105 205,120 C185,115 170,105 165,80 Z" fill="#ffffff" {ink()}/>'
    f'<path d="{heart_path(130, 85, 62)}" {P("primary", "#ff4f8b")} {ink()}/>')

# ------------------------------------------------------------------ sunglasses
add("sunglasses_classic", "Cool sunglasses", "sunglasses", ["sunglasses", "cool", "glasses", "summer"], 240, 90,
    f'<path d="M10,25 L230,25" stroke="{INK}" stroke-width="10" stroke-linecap="round"/>'
    f'<path d="M18,25 L105,25 L98,60 C92,80 40,82 28,60 Z" {P("primary", "#2d2140")} {ink()}/>'
    f'<path d="M135,25 L222,25 L212,60 C200,82 148,80 142,60 Z" {P("primary", "#2d2140")} {ink()}/>'
    f'<path d="M40,36 L60,36 M158,36 L178,36" stroke="#ffffff" stroke-width="6" opacity="0.6" stroke-linecap="round"/>', anchor="eyes")
add("sunglasses_star", "Star sunglasses", "sunglasses", ["sunglasses", "star", "party", "fun"], 240, 110,
    f'<path d="M100,50 Q120,35 140,50" stroke="{INK}" stroke-width="7" fill="none"/>'
    f'<polygon points="{star_pts(60, 58, 52, 0.55)}" {P("primary", "#ff4f8b")} {ink()}/>'
    f'<polygon points="{star_pts(180, 58, 52, 0.55)}" {P("primary", "#ff4f8b")} {ink()}/>'
    f'<polygon points="{star_pts(60, 58, 30, 0.55)}" fill="#2d2140" opacity="0.75"/><polygon points="{star_pts(180, 58, 30, 0.55)}" fill="#2d2140" opacity="0.75"/>',
    anchor="eyes")
add("sunglasses_heart", "Heart sunglasses", "sunglasses", ["sunglasses", "heart", "love"], 240, 100,
    f'<path d="M100,40 Q120,28 140,40" stroke="{INK}" stroke-width="7" fill="none"/>'
    f'<path d="{heart_path(60, 50, 42)}" {P("primary", "#e63946")} {ink()}/><path d="{heart_path(180, 50, 42)}" {P("primary", "#e63946")} {ink()}/>', anchor="eyes")
add("glasses_round", "Round glasses", "sunglasses", ["glasses", "school", "smart", "nerd"], 240, 90,
    f'<circle cx="62" cy="45" r="36" fill="#ffffff" fill-opacity="0.25" stroke="{INK}" stroke-width="8" data-recolor="primary"/>'
    f'<circle cx="178" cy="45" r="36" fill="#ffffff" fill-opacity="0.25" stroke="{INK}" stroke-width="8" data-recolor="primary"/>'
    f'<path d="M98,42 Q120,30 142,42" stroke="{INK}" stroke-width="7" fill="none"/>', anchor="eyes")

# ------------------------------------------------------------------ bow ties & gentleman
add("bowtie", "Bow tie", "bowties", ["bow tie", "gentleman", "formal", "party"], 220, 110,
    f'<path d="M110,55 L15,10 C5,40 5,70 15,100 Z" {P("primary", "#e63946")} {ink()}/>'
    f'<path d="M110,55 L205,10 C215,40 215,70 205,100 Z" {P("primary", "#e63946")} {ink()}/>'
    f'<rect x="92" y="35" width="36" height="40" rx="10" {P("secondary", "#b5172f")} {ink()}/>', ("primary", "secondary"), anchor="neck")
add("bowtie_dots", "Polka-dot bow tie", "bowties", ["bow tie", "dots", "gentleman", "cute"], 220, 110,
    f'<path d="M110,55 L15,10 C5,40 5,70 15,100 Z" {P("primary", "#3a86ff")} {ink()}/>'
    f'<path d="M110,55 L205,10 C215,40 215,70 205,100 Z" {P("primary", "#3a86ff")} {ink()}/>'
    + "".join(f'<circle cx="{x}" cy="{y}" r="7" fill="#ffffff"/>' for x, y in ((40, 40), (55, 75), (75, 52), (180, 40), (165, 75), (145, 52)))
    + f'<rect x="92" y="35" width="36" height="40" rx="10" {P("secondary", "#1d3557")} {ink()}/>', ("primary", "secondary"), anchor="neck")
add("necktie", "Necktie", "bowties", ["tie", "gentleman", "office", "formal"], 90, 220,
    f'<path d="M30,10 L60,10 L70,30 L55,45 Z" {P("primary", "#1d3557")} {ink()}/>'
    f'<path d="M35,40 L55,40 L75,170 L45,210 L15,170 Z" {P("primary", "#1d3557")} {ink()}/>'
    f'<path d="M25,100 L65,80 M22,135 L70,112 M22,170 L72,145" stroke="#ffd166" stroke-width="7" data-recolor="secondary"/>',
    ("primary", "secondary"), anchor="neck")
add("mustache_curly", "Curly mustache", "gentleman", ["mustache", "moustache", "gentleman", "funny"], 240, 90,
    f'<path d="M120,30 C100,10 70,20 60,45 C50,65 20,70 10,50 C5,75 35,90 60,75 C80,65 100,55 120,55 '
    f'C140,55 160,65 180,75 C205,90 235,75 230,50 C220,70 190,65 180,45 C170,20 140,10 120,30 Z" {P("primary", "#3d2817")} {ink("stroke-width=\"3\"")}/>',
    anchor="mouth")
add("mustache_classic", "Classic mustache", "gentleman", ["mustache", "moustache", "gentleman"], 220, 80,
    f'<path d="M110,25 C80,5 30,20 10,60 C50,50 80,60 110,45 C140,60 170,50 210,60 C190,20 140,5 110,25 Z" {P("primary", "#2d2140")} {ink("stroke-width=\"3\"")}/>',
    anchor="mouth")
add("monocle", "Monocle", "gentleman", ["monocle", "gentleman", "fancy"], 120, 200,
    f'<circle cx="60" cy="60" r="45" fill="#cfe8ff" fill-opacity="0.35" stroke="#c9a227" stroke-width="9" data-recolor="primary"/>'
    f'<path d="M60,105 C55,140 75,160 60,195" stroke="#c9a227" stroke-width="4" fill="none" data-recolor="primary"/>'
    f'<path d="M35,40 L50,30" stroke="#ffffff" stroke-width="6" stroke-linecap="round" opacity="0.8"/>')
add("cane", "Walking cane", "gentleman", ["cane", "gentleman", "dapper"], 80, 240,
    f'<path d="M60,235 L60,50 C60,10 15,10 15,45" stroke="#5a3e2b" stroke-width="14" fill="none" stroke-linecap="round" data-recolor="primary"/>'
    f'<rect x="50" y="200" width="20" height="10" fill="#c9a227"/>')

# ------------------------------------------------------------------ flowers
def flower(cx, cy, r, petal_slot, petal, center="#ffd166", n=6):
    out = "".join(f'<ellipse cx="{cx + r * 0.62 * math.cos(math.radians(a)):.1f}" cy="{cy + r * 0.62 * math.sin(math.radians(a)):.1f}" '
                  f'rx="{r * 0.42:.1f}" ry="{r * 0.3:.1f}" transform="rotate({a} {cx + r * 0.62 * math.cos(math.radians(a)):.1f} {cy + r * 0.62 * math.sin(math.radians(a)):.1f})" '
                  f'{P(petal_slot, petal)} {ink("stroke-width=\"4\"")}/>' for a in range(0, 360, 360 // n))
    return out + f'<circle cx="{cx}" cy="{cy}" r="{r * 0.32:.1f}" fill="{center}" {ink("stroke-width=\"4\"")}/>'


add("flower_daisy", "Daisy", "flowers", ["flower", "daisy", "spring", "garden"], 200, 200, flower(100, 100, 90, "primary", "#ffffff", n=8))
add("flower_pink", "Pink flower", "flowers", ["flower", "pink", "spring", "cute"], 200, 200, flower(100, 100, 90, "primary", "#ff8fab"))
add("flower_bouquet", "Flower trio", "flowers", ["flowers", "bouquet", "wedding", "garden"], 240, 200,
    f'<path d="M120,190 L70,110 M120,190 L120,90 M120,190 L170,110" stroke="#2a9d8f" stroke-width="7"/>'
    + flower(70, 95, 50, "primary", "#ff8fab") + flower(170, 95, 50, "secondary", "#cdb4db") + flower(120, 70, 55, "accent", "#ffffff"),
    ("primary", "secondary", "accent"))
add("flower_garland", "Flower garland (Diwali)", "festive", ["marigold", "garland", "diwali", "pongal", "festival", "toran"], 260, 120,
    f'<path d="M10,20 Q130,90 250,20" stroke="#2a9d8f" stroke-width="5" fill="none"/>'
    + "".join(f'<circle cx="{10 + i * 30}" cy="{20 + 70 * math.sin(math.pi * i / 8) * 0.8:.1f}" r="15" fill="{["#ff9f1c", "#ffd166"][i % 2]}" {ink("stroke-width=\"3\"")}/>' for i in range(9))
    + "".join(f'<path d="M{40 + i * 60},{70} L{40 + i * 60},{108}" stroke="#ff9f1c" stroke-width="10" stroke-linecap="round" stroke-dasharray="1 13"/>' for i in range(4)), ())

# ------------------------------------------------------------------ cakes & gifts
add("cake_birthday", "Birthday cake", "cakes", ["cake", "birthday", "candles", "party"], 200, 200,
    f'<rect x="96" y="20" width="8" height="40" rx="3" fill="#4cc9f0" {ink("stroke-width=\"3\"")}/>'
    f'<path d="M100,4 C110,16 106,24 100,24 C94,24 90,16 100,4 Z" fill="#ff9f1c"/>'
    f'<rect x="30" y="60" width="140" height="55" rx="10" {P("primary", "#ffafcc")} {ink()}/>'
    f'<path d="M30,75 C45,95 55,70 70,90 C85,108 95,72 110,92 C125,110 135,72 150,90 C160,100 168,85 170,80" stroke="#ffffff" stroke-width="10" fill="none" stroke-linecap="round"/>'
    f'<rect x="15" y="112" width="170" height="70" rx="12" {P("secondary", "#cdb4db")} {ink()}/>'
    f'<path d="M15,135 L185,135" stroke="#ffffff" stroke-width="8"/>'
    + "".join(f'<circle cx="{x}" cy="160" r="6" fill="#ffd166"/>' for x in (45, 80, 115, 150))
    + f'<rect x="5" y="178" width="190" height="14" rx="7" fill="#ffffff" {ink("stroke-width=\"4\"")}/>', ("primary", "secondary"))
add("cupcake", "Cupcake", "cakes", ["cupcake", "sweet", "birthday", "party"], 160, 200,
    f'<path d="M25,110 L45,190 L115,190 L135,110 Z" {P("secondary", "#4cc9f0")} {ink()}/>'
    f'<path d="M60,112 L68,188 M92,112 L90,188" stroke="{INK}" stroke-width="3" opacity="0.5"/>'
    f'<path d="M20,112 C5,80 40,70 45,60 C40,30 80,20 85,40 C100,25 140,45 120,70 C150,80 150,110 140,112 Z" {P("primary", "#ffafcc")} {ink()}/>'
    f'<circle cx="80" cy="25" r="12" fill="#e63946" {ink("stroke-width=\"3\"")}/>'
    + "".join(f'<rect x="{x}" y="{y}" width="10" height="4" rx="2" fill="{c}" transform="rotate({r} {x} {y})"/>' for x, y, c, r in
              ((50, 75, "#ffd166", 30), (90, 65, "#4cc9f0", -20), (110, 90, "#06d6a0", 45), (60, 95, "#9b5de5", -40))), ("primary", "secondary"))
add("gift_box", "Gift box", "gifts", ["gift", "present", "birthday", "christmas"], 200, 200,
    f'<rect x="25" y="85" width="150" height="105" rx="8" {P("primary", "#9b5de5")} {ink()}/>'
    f'<rect x="15" y="60" width="170" height="35" rx="8" {P("primary", "#9b5de5")} {ink()}/>'
    f'<rect x="88" y="60" width="24" height="130" {P("secondary", "#ffd166")} {ink("stroke-width=\"4\"")}/>'
    f'<path d="M100,60 C70,10 30,30 55,55 C65,62 85,62 100,60 C115,62 135,62 145,55 C170,30 130,10 100,60 Z" {P("secondary", "#ffd166")} {ink()}/>',
    ("primary", "secondary"))
add("gift_small", "Small gift", "gifts", ["gift", "present", "thank you"], 160, 170,
    f'<rect x="20" y="70" width="120" height="90" rx="8" {P("primary", "#06d6a0")} {ink()}/>'
    f'<path d="M20,110 L140,110" stroke="#ff4f8b" stroke-width="16" data-recolor="secondary"/>'
    f'<path d="M80,70 L80,160" stroke="#ff4f8b" stroke-width="16" data-recolor="secondary"/>'
    f'<path d="M80,70 C55,30 25,50 45,68 Z M80,70 C105,30 135,50 115,68 Z" {P("secondary", "#ff4f8b")} {ink("stroke-width=\"4\"")}/>', ("primary", "secondary"))

# ------------------------------------------------------------------ ribbons & banners & badges
add("ribbon_bow", "Ribbon bow", "ribbons", ["ribbon", "bow", "gift", "cute"], 200, 160,
    f'<path d="M100,70 L60,150 L45,130 L25,140 L75,70 Z M100,70 L140,150 L155,130 L175,140 L125,70 Z" {P("secondary", "#d00062")} {ink()}/>'
    f'<path d="M100,70 C60,10 5,30 20,70 C30,100 80,90 100,70 C120,90 170,100 180,70 C195,30 140,10 100,70 Z" {P("primary", "#ff4f8b")} {ink()}/>'
    f'<circle cx="100" cy="70" r="16" {P("secondary", "#d00062")} {ink()}/>', ("primary", "secondary"))
add("ribbon_award", "Award rosette", "badges", ["award", "rosette", "winner", "sports", "school"], 180, 240,
    f'<path d="M60,140 L35,230 L60,215 L80,235 L95,150 Z M120,140 L145,230 L120,215 L100,235 L85,150 Z" {P("secondary", "#3a86ff")} {ink()}/>'
    + "".join(f'<circle cx="{90 + 62 * math.cos(math.radians(a)):.1f}" cy="{90 + 62 * math.sin(math.radians(a)):.1f}" r="22" {P("primary", "#ffd166")} {ink("stroke-width=\"4\"")}/>' for a in range(0, 360, 30))
    + f'<circle cx="90" cy="90" r="62" {P("primary", "#ffd166")}/>'
    + f'<circle cx="90" cy="90" r="45" fill="#ffffff" {ink()}/>'
    + f'<polygon points="{star_pts(90, 92, 30, 0.5)}" {P("secondary", "#3a86ff")}/>', ("primary", "secondary"))
add("banner_ribbon", "Ribbon banner", "banners", ["banner", "ribbon", "title", "text"], 300, 110,
    f'<path d="M10,40 L55,40 L55,95 L10,95 L28,68 Z" {P("secondary", "#d00062")} {ink()}/>'
    f'<path d="M290,40 L245,40 L245,95 L290,95 L272,68 Z" {P("secondary", "#d00062")} {ink()}/>'
    f'<rect x="40" y="15" width="220" height="70" rx="6" {P("primary", "#ff4f8b")} {ink()}/>', ("primary", "secondary"))
add("banner_bunting", "Bunting flags", "banners", ["bunting", "flags", "party", "garland"], 300, 120,
    f'<path d="M5,15 Q150,60 295,15" stroke="{INK}" stroke-width="4" fill="none"/>'
    + "".join(f'<path d="M{15 + i * 47},{20 + 30 * math.sin(math.pi * (i + 0.5) / 6) * 0.9:.1f} l40,{3 if i < 3 else -3} l-20,55 Z" '
              f'fill="{["#ff4f8b", "#ffd166", "#4cc9f0", "#06d6a0", "#9b5de5", "#ff9f1c"][i]}" {ink("stroke-width=\"3\"")}/>' for i in range(6)), ())
add("badge_scallop", "Scalloped badge", "badges", ["badge", "label", "seal", "text"], 200, 200,
    "".join(f'<circle cx="{100 + 80 * math.cos(math.radians(a)):.1f}" cy="{100 + 80 * math.sin(math.radians(a)):.1f}" r="20" {P("primary", "#ffd166")}/>' for a in range(0, 360, 20))
    + f'<circle cx="100" cy="100" r="82" {P("primary", "#ffd166")}/>'
    + f'<circle cx="100" cy="100" r="66" fill="#ffffff" stroke="{INK}" stroke-width="4" stroke-dasharray="8 6"/>')
add("badge_label", "Rounded label", "badges", ["label", "tag", "name", "minimal"], 300, 130,
    f'<rect x="8" y="8" width="284" height="114" rx="57" {P("primary", "#ffffff")} {ink()}/>'
    f'<rect x="22" y="22" width="256" height="86" rx="43" fill="none" stroke="{INK}" stroke-width="3" stroke-dasharray="6 6" data-recolor="secondary"/>')
add("badge_tag", "Gift tag", "badges", ["tag", "label", "gift", "name"], 260, 140,
    f'<path d="M60,10 L250,10 L250,130 L60,130 L10,70 Z" {P("primary", "#f1e3c8")} {ink()}/>'
    f'<circle cx="50" cy="70" r="10" fill="#ffffff" {ink("stroke-width=\"4\"")}/>')
add("badge_burst", "Starburst badge", "badges", ["burst", "badge", "sale", "pop", "retro"], 220, 220,
    f'<polygon points="{star_pts(110, 110, 105, 0.82, n=16)}" {P("primary", "#ff4f8b")} {ink()}/>'
    f'<circle cx="110" cy="110" r="68" fill="#ffffff" opacity="0.92"/>')

# ------------------------------------------------------------------ speech bubbles
add("speech_round", "Speech bubble", "speech", ["speech", "bubble", "talk", "comic"], 240, 180,
    f'<path d="M120,10 C185,10 230,40 230,80 C230,120 185,150 120,150 C105,150 95,148 85,145 L45,172 L58,135 C25,122 10,102 10,80 C10,40 55,10 120,10 Z" {P("primary", "#ffffff")} {ink()}/>')
add("speech_cloud", "Thought bubble", "speech", ["thought", "bubble", "cloud", "think"], 240, 190,
    f'<path d="M60,120 C20,125 10,80 40,70 C30,30 80,15 100,35 C115,5 170,10 175,45 C215,40 235,85 205,105 C220,140 170,155 150,135 C130,160 80,155 60,120 Z" {P("primary", "#ffffff")} {ink()}/>'
    f'<circle cx="55" cy="155" r="13" {P("primary", "#ffffff")} {ink()}/><circle cx="32" cy="178" r="8" {P("primary", "#ffffff")} {ink()}/>')
add("speech_shout", "Shout bubble", "speech", ["shout", "comic", "pow", "superhero"], 240, 200,
    f'<polygon points="{star_pts(120, 100, 105, 0.72, n=12, rot=-75)}" {P("primary", "#ffd166")} {ink()}/>')

# ------------------------------------------------------------------ school
add("pencil", "Pencil", "school", ["pencil", "school", "write", "teacher"], 240, 70,
    f'<path d="M20,15 L180,15 L180,55 L20,55 Z" {P("primary", "#ffd166")} {ink()}/>'
    f'<path d="M20,28 L180,28 M20,42 L180,42" stroke="#ff9f1c" stroke-width="3"/>'
    f'<path d="M180,15 L230,35 L180,55 Z" fill="#f1d3a1" {ink()}/><path d="M215,29 L230,35 L215,41 Z" fill="{INK}"/>'
    f'<rect x="5" y="15" width="22" height="40" rx="5" fill="#ff8fab" {ink()}/>')
add("crayons", "Crayons", "school", ["crayon", "drawing", "art", "kids"], 200, 200,
    "".join(f'<g transform="rotate({r} 100 190)"><rect x="88" y="40" width="24" height="140" rx="4" fill="{c}" {ink("stroke-width=\"4\"")}/>'
            f'<path d="M88,40 L100,10 L112,40 Z" fill="{c}" {ink("stroke-width=\"4\"")}/><rect x="88" y="70" width="24" height="12" fill="#ffffff" opacity="0.6"/></g>'
            for r, c in ((-28, "#e63946"), (0, "#3a86ff"), (28, "#06d6a0"))), ())
add("book_open", "Open book", "school", ["book", "reading", "school", "library"], 240, 160,
    f'<path d="M120,30 C90,10 40,10 10,25 L10,145 C40,130 90,130 120,150 Z" {P("primary", "#ffffff")} {ink()}/>'
    f'<path d="M120,30 C150,10 200,10 230,25 L230,145 C200,130 150,130 120,150 Z" {P("primary", "#ffffff")} {ink()}/>'
    f'<path d="M30,50 L100,55 M30,75 L100,80 M30,100 L100,105 M140,55 L210,50 M140,80 L210,75 M140,105 L210,100" stroke="#a2d2ff" stroke-width="5" stroke-linecap="round"/>'
    f'<path d="M120,150 L120,30" stroke="{INK}" stroke-width="4"/>')
add("apple_red", "Apple", "school", ["apple", "teacher", "school", "fruit"], 180, 200,
    f'<path d="M90,55 C60,30 10,45 15,100 C20,160 60,195 90,180 C120,195 160,160 165,100 C170,45 120,30 90,55 Z" {P("primary", "#e63946")} {ink()}/>'
    f'<path d="M90,55 C90,35 95,20 105,10" stroke="#5a3e2b" stroke-width="7" fill="none" stroke-linecap="round"/>'
    f'<path d="M100,35 C120,10 150,15 150,25 C140,45 115,45 100,35 Z" fill="#06d6a0" {ink("stroke-width=\"4\"")}/>'
    f'<ellipse cx="50" cy="90" rx="10" ry="20" fill="#ffffff" opacity="0.45"/>')
add("ruler", "Ruler", "school", ["ruler", "math", "school", "measure"], 260, 70,
    f'<rect x="10" y="10" width="240" height="50" rx="6" {P("primary", "#ffd166")} {ink()}/>'
    + "".join(f'<path d="M{25 + i * 15},10 L{25 + i * 15},{30 if i % 2 == 0 else 22}" stroke="{INK}" stroke-width="3"/>' for i in range(15)))
add("backpack", "School bag", "school", ["backpack", "bag", "school", "kids"], 180, 220,
    f'<path d="M60,40 C60,10 120,10 120,40" stroke="{INK}" stroke-width="10" fill="none"/>'
    f'<rect x="25" y="35" width="130" height="175" rx="35" {P("primary", "#3a86ff")} {ink()}/>'
    f'<rect x="45" y="120" width="90" height="70" rx="15" {P("secondary", "#ffd166")} {ink()}/>'
    f'<path d="M45,145 L135,145" stroke="{INK}" stroke-width="4"/>', ("primary", "secondary"))
add("abc_blocks", "ABC blocks", "school", ["abc", "blocks", "letters", "toddler"], 240, 170,
    f'<rect x="10" y="70" width="90" height="90" rx="10" fill="#ff8fab" {ink()}/><rect x="110" y="70" width="90" height="90" rx="10" fill="#a2d2ff" {ink()}/>'
    f'<rect x="60" y="5" width="80" height="70" rx="10" fill="#ffd166" {ink()}/>'
    f'<path d="M35,140 L55,90 L75,140 M42,123 L68,123" stroke="{INK}" stroke-width="7" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
    f'<path d="M140,90 L140,140 L160,140 C178,140 178,115 160,115 L140,115 M140,90 L157,90 C172,90 172,115 157,115" stroke="{INK}" stroke-width="7" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
    f'<path d="M115,25 C95,15 80,30 82,42 C84,58 100,62 115,55" stroke="{INK}" stroke-width="7" fill="none" stroke-linecap="round"/>', ())

# ------------------------------------------------------------------ sports
add("soccer_ball", "Football", "sports", ["football", "soccer", "ball", "sports"], 200, 200,
    f'<circle cx="100" cy="100" r="88" fill="#ffffff" {ink()}/>'
    f'<polygon points="100,62 136,88 122,130 78,130 64,88" {P("primary", "#2d2140")}/>'
    f'<path d="M100,62 L100,14 M136,88 L180,74 M122,130 L148,170 M78,130 L52,170 M64,88 L20,74" stroke="{INK}" stroke-width="5"/>'
    f'<path d="M70,18 L100,14 L130,18 M180,74 L188,105 L172,140 M148,170 L118,186 L82,186 L52,170 M28,140 L12,105 L20,74" fill="none" stroke="{INK}" stroke-width="5"/>')
add("basketball", "Basketball", "sports", ["basketball", "ball", "sports"], 200, 200,
    f'<circle cx="100" cy="100" r="88" {P("primary", "#ff9f1c")} {ink()}/>'
    f'<path d="M12,100 L188,100 M100,12 L100,188 M40,35 C75,70 75,130 40,165 M160,35 C125,70 125,130 160,165" stroke="{INK}" stroke-width="5" fill="none"/>')
add("cricket_bat", "Cricket bat and ball", "sports", ["cricket", "bat", "ball", "sports"], 220, 240,
    f'<g transform="rotate(-30 110 120)"><rect x="98" y="10" width="24" height="70" rx="8" fill="#3d2817" {ink("stroke-width=\"4\"")}/>'
    f'<path d="M85,80 L135,80 L132,225 C132,235 88,235 88,225 Z" {P("primary", "#f1d3a1")} {ink()}/></g>'
    f'<circle cx="175" cy="200" r="24" fill="#e63946" {ink()}/><path d="M158,185 C170,198 170,210 160,218 M190,183 C180,195 182,210 192,216" stroke="#ffffff" stroke-width="3" fill="none"/>')
add("trophy", "Trophy", "sports", ["trophy", "cup", "winner", "champion", "award"], 200, 220,
    f'<path d="M50,30 C10,30 10,95 60,100 M150,30 C190,30 190,95 140,100" stroke="{INK}" stroke-width="10" fill="none"/>'
    f'<path d="M45,20 L155,20 L150,80 C145,120 120,135 100,135 C80,135 55,120 50,80 Z" {P("primary", "#ffc93c")} {ink()}/>'
    f'<rect x="88" y="132" width="24" height="40" {P("primary", "#ffc93c")} {ink()}/>'
    f'<rect x="55" y="170" width="90" height="38" rx="6" {P("secondary", "#5a3e2b")} {ink()}/>'
    f'<polygon points="{star_pts(100, 70, 26, 0.5)}" fill="#ffffff" opacity="0.65"/>', ("primary", "secondary"))
add("medal", "Medal", "sports", ["medal", "gold", "winner", "first"], 160, 230,
    f'<path d="M40,5 L80,95 L120,5 L95,5 L80,45 L65,5 Z" {P("secondary", "#e63946")} {ink("stroke-width=\"4\"")}/>'
    f'<circle cx="80" cy="155" r="65" {P("primary", "#ffc93c")} {ink()}/>'
    f'<circle cx="80" cy="155" r="45" fill="none" stroke="{INK}" stroke-width="3" opacity="0.5"/>'
    f'<polygon points="{star_pts(80, 157, 30, 0.5)}" fill="#ffffff" opacity="0.7"/>', ("primary", "secondary"))
add("tennis_racket", "Tennis racket", "sports", ["tennis", "racket", "ball", "sports"], 180, 240,
    f'<ellipse cx="90" cy="75" rx="62" ry="70" fill="none" {ink("stroke-width=\"10\"")} data-recolor="primary"/>'
    + "".join(f'<path d="M{40 + i * 17},18 L{40 + i * 17},132" stroke="{INK}" stroke-width="2" opacity="0.6"/>' for i in range(7))
    + "".join(f'<path d="M32,{30 + i * 17} L148,{30 + i * 17}" stroke="{INK}" stroke-width="2" opacity="0.6"/>' for i in range(7))
    + f'<rect x="80" y="145" width="20" height="85" rx="8" fill="#3a86ff" {ink("stroke-width=\"4\"")}/>'
    + f'<circle cx="150" cy="200" r="22" fill="#c7f464" {ink()}/>')

# ------------------------------------------------------------------ seasonal
add("christmas_tree", "Christmas tree", "seasonal", ["christmas", "tree", "winter", "holiday"], 180, 230,
    f'<rect x="78" y="185" width="24" height="35" fill="#5a3e2b" {ink("stroke-width=\"4\"")}/>'
    f'<path d="M90,20 L170,190 L10,190 Z" {P("primary", "#2a9d8f")} {ink()}/>'
    f'<path d="M50,140 C80,150 110,130 140,140 M65,95 C85,105 105,90 120,98" stroke="#ffd166" stroke-width="6" fill="none"/>'
    + "".join(f'<circle cx="{x}" cy="{y}" r="8" fill="{c}" {ink("stroke-width=\"3\"")}/>' for x, y, c in ((60, 165, "#e63946"), (115, 160, "#4cc9f0"), (85, 120, "#e63946"), (100, 75, "#4cc9f0")))
    + f'<polygon points="{star_pts(90, 22, 22, 0.45)}" fill="#ffd166" {ink("stroke-width=\"4\"")}/>')
add("snowflake", "Snowflake", "seasonal", ["snow", "winter", "christmas", "frozen"], 200, 200,
    "".join(f'<g transform="rotate({a} 100 100)"><path d="M100,100 L100,12 M100,40 L82,24 M100,40 L118,24 M100,68 L85,55 M100,68 L115,55" '
            f'stroke="#4cc9f0" stroke-width="9" stroke-linecap="round" fill="none" data-recolor="primary"/></g>' for a in range(0, 360, 60)))
add("candy_cane", "Candy cane", "seasonal", ["candy", "christmas", "sweet"], 120, 220,
    f'<path d="M80,210 L80,60 C80,15 20,15 20,55" stroke="{INK}" stroke-width="30" fill="none" stroke-linecap="round"/>'
    f'<path d="M80,210 L80,60 C80,15 20,15 20,55" stroke="#ffffff" stroke-width="20" fill="none" stroke-linecap="round"/>'
    f'<path d="M80,210 L80,60 C80,15 20,15 20,55" stroke="#e63946" stroke-width="20" fill="none" stroke-dasharray="14 14" data-recolor="primary"/>')
add("gingerbread", "Gingerbread friend", "seasonal", ["gingerbread", "cookie", "christmas"], 180, 220,
    f'<path d="M90,10 C120,10 130,45 115,62 L165,80 C180,90 170,110 155,105 L120,95 L135,180 C140,205 115,210 105,190 L90,155 L75,190 C65,210 40,205 45,180 L60,95 L25,105 C10,110 0,90 15,80 L65,62 C50,45 60,10 90,10 Z" {P("primary", "#c68642")} {ink()}/>'
    f'<circle cx="78" cy="35" r="5" fill="{INK}"/><circle cx="102" cy="35" r="5" fill="{INK}"/><path d="M78,48 Q90,57 102,48" stroke="{INK}" stroke-width="4" fill="none"/>'
    f'<circle cx="90" cy="95" r="7" fill="#e63946"/><circle cx="90" cy="125" r="7" fill="#06d6a0"/>'
    f'<path d="M35,92 L50,88 M130,88 L145,92" stroke="#ffffff" stroke-width="5" stroke-linecap="round"/>')
add("pumpkin", "Pumpkin", "seasonal", ["pumpkin", "halloween", "autumn", "jack-o-lantern"], 220, 200,
    f'<path d="M110,40 C108,25 115,12 128,8" stroke="#2a9d8f" stroke-width="10" fill="none" stroke-linecap="round"/>'
    f'<ellipse cx="65" cy="115" rx="55" ry="75" {P("primary", "#ff9f1c")} {ink()}/><ellipse cx="155" cy="115" rx="55" ry="75" {P("primary", "#ff9f1c")} {ink()}/>'
    f'<ellipse cx="110" cy="115" rx="50" ry="78" {P("primary", "#ff9f1c")} {ink()}/>'
    f'<polygon points="75,95 95,95 85,75" fill="{INK}"/><polygon points="125,95 145,95 135,75" fill="{INK}"/>'
    f'<path d="M65,135 L80,150 L95,135 L110,150 L125,135 L140,150 L155,135 C150,165 70,165 65,135 Z" fill="{INK}"/>')
add("ghost", "Friendly ghost", "seasonal", ["ghost", "halloween", "boo", "cute"], 180, 210,
    f'<path d="M20,190 L20,90 C20,40 55,10 90,10 C125,10 160,40 160,90 L160,190 L135,170 L112,195 L90,172 L68,195 L45,170 Z" {P("primary", "#ffffff")} {ink()}/>'
    f'<ellipse cx="68" cy="85" rx="10" ry="15" fill="{INK}"/><ellipse cx="112" cy="85" rx="10" ry="15" fill="{INK}"/>'
    f'<ellipse cx="90" cy="120" rx="12" ry="15" fill="{INK}"/><circle cx="52" cy="108" r="8" fill="#ff8fab" opacity="0.7"/><circle cx="128" cy="108" r="8" fill="#ff8fab" opacity="0.7"/>')
add("bat", "Bat", "seasonal", ["bat", "halloween", "night", "spooky"], 240, 120,
    f'<path d="M120,40 C110,30 112,20 112,15 L118,25 L122,25 L128,15 C128,20 130,30 120,40 Z M120,40 C90,20 50,5 10,30 C30,40 35,55 30,75 C50,65 65,75 70,95 C85,80 105,80 120,95 C135,80 155,80 170,95 C175,75 190,65 210,75 C205,55 210,40 230,30 C190,5 150,20 120,40 Z" {P("primary", "#2d2140")} {ink("stroke-width=\"3\"")}/>'
    f'<circle cx="113" cy="42" r="3" fill="#ffd166"/><circle cx="127" cy="42" r="3" fill="#ffd166"/>')
add("spider_web", "Spider web", "seasonal", ["web", "spider", "halloween"], 200, 200,
    "".join(f'<path d="M0,0 L{200 * math.cos(math.radians(a)):.1f},{200 * math.sin(math.radians(a)):.1f}" stroke="{INK}" stroke-width="3"/>' for a in (0, 22.5, 45, 67.5, 90))
    + "".join(f'<path d="M{r},0 ' + " ".join(f'Q{r * 0.8 * math.cos(math.radians(a - 11.25)):.1f},{r * 0.8 * math.sin(math.radians(a - 11.25)):.1f} {r * math.cos(math.radians(a)):.1f},{r * math.sin(math.radians(a)):.1f}' for a in (22.5, 45, 67.5, 90)) + f'" stroke="{INK}" stroke-width="3" fill="none"/>' for r in (50, 95, 140, 185)), ())
add("diya_lamp", "Diya lamp", "festive", ["diya", "diwali", "lamp", "festival", "light"], 220, 180,
    f'<path d="M110,20 C130,45 128,70 110,78 C92,70 90,45 110,20 Z" fill="#ffd166" {ink("stroke-width=\"4\"")}/><path d="M110,45 C118,58 116,68 110,72 C104,68 102,58 110,45 Z" fill="#ff9f1c"/>'
    f'<path d="M10,95 C30,95 60,85 110,85 C160,85 190,95 210,95 C200,150 160,170 110,170 C60,170 20,150 10,95 Z" {P("primary", "#e76f51")} {ink()}/>'
    f'<path d="M30,115 C70,130 150,130 190,115" stroke="#ffd166" stroke-width="7" fill="none" data-recolor="secondary"/>'
    + "".join(f'<circle cx="{x}" cy="145" r="6" fill="#ffd166" data-recolor="secondary"/>' for x in (70, 110, 150)), ("primary", "secondary"))
add("rangoli", "Rangoli", "festive", ["rangoli", "kolam", "diwali", "pongal", "pattern", "festival"], 200, 200,
    "".join(f'<ellipse cx="{100 + 55 * math.cos(math.radians(a)):.1f}" cy="{100 + 55 * math.sin(math.radians(a)):.1f}" rx="34" ry="16" '
            f'transform="rotate({a} {100 + 55 * math.cos(math.radians(a)):.1f} {100 + 55 * math.sin(math.radians(a)):.1f})" fill="{["#e63946", "#ffd166", "#9b5de5", "#06d6a0"][i % 4]}" {ink("stroke-width=\"3\"")}/>'
            for i, a in enumerate(range(0, 360, 45)))
    + f'<circle cx="100" cy="100" r="34" {P("primary", "#ff9f1c")} {ink("stroke-width=\"4\"")}/>'
    + f'<polygon points="{star_pts(100, 100, 24, 0.5, n=8)}" fill="#ffffff"/>'
    + "".join(f'<circle cx="{100 + 92 * math.cos(math.radians(a)):.1f}" cy="{100 + 92 * math.sin(math.radians(a)):.1f}" r="5" fill="{INK}"/>' for a in range(0, 360, 30)))
add("pongal_pot", "Pongal pot", "festive", ["pongal", "pot", "harvest", "festival", "rice"], 200, 220,
    "".join(f'<circle cx="{x}" cy="{y}" r="{r}" fill="#ffffff" {ink("stroke-width=\"3\"")}/>' for x, y, r in ((70, 40, 22), (100, 28, 26), (132, 40, 22), (85, 55, 18), (118, 55, 18)))
    + f'<path d="M50,70 L150,70 C155,80 150,85 145,88 C185,110 190,170 160,195 C140,212 60,212 40,195 C10,170 15,110 55,88 C50,85 45,80 50,70 Z" {P("primary", "#c68642")} {ink()}/>'
    f'<path d="M30,125 C70,140 130,140 170,125" stroke="#ffd166" stroke-width="10" fill="none" data-recolor="secondary"/>'
    f'<path d="M35,150 C70,162 130,162 165,150" stroke="#e63946" stroke-width="6" fill="none" stroke-dasharray="2 12" stroke-linecap="round"/>', ("primary", "secondary"))
add("sugarcane", "Sugarcane", "festive", ["sugarcane", "pongal", "harvest", "festival"], 120, 240,
    f'<rect x="40" y="40" width="26" height="195" rx="10" {P("primary", "#7b2cbf")} {ink()}/>'
    + "".join(f'<path d="M40,{y} L66,{y}" stroke="{INK}" stroke-width="4"/>' for y in (80, 120, 160, 200))
    + f'<path d="M53,45 C30,20 10,15 5,10 C30,10 50,20 55,40 C60,10 85,2 110,5 C90,15 70,25 60,45" fill="#06d6a0" {ink("stroke-width=\"4\"")}/>')
add("sun_happy", "Happy sun", "festive", ["sun", "pongal", "summer", "harvest", "happy"], 200, 200,
    "".join(f'<path d="M{100 + 70 * math.cos(math.radians(a)):.1f},{100 + 70 * math.sin(math.radians(a)):.1f} L{100 + 95 * math.cos(math.radians(a)):.1f},{100 + 95 * math.sin(math.radians(a)):.1f}" stroke="#ff9f1c" stroke-width="10" stroke-linecap="round" data-recolor="secondary"/>' for a in range(0, 360, 30))
    + f'<circle cx="100" cy="100" r="58" {P("primary", "#ffd166")} {ink()}/>'
    f'<circle cx="80" cy="92" r="6" fill="{INK}"/><circle cx="120" cy="92" r="6" fill="{INK}"/><path d="M78,115 Q100,135 122,115" stroke="{INK}" stroke-width="5" fill="none" stroke-linecap="round"/>',
    ("primary", "secondary"))
add("lantern_sky", "Sky lantern", "festive", ["lantern", "diwali", "light", "festival"], 140, 220,
    f'<path d="M70,5 L70,25" stroke="{INK}" stroke-width="4"/><rect x="45" y="25" width="50" height="14" rx="4" fill="#ffd166" {ink("stroke-width=\"3\"")}/>'
    f'<path d="M45,39 C10,70 10,140 45,170 L95,170 C130,140 130,70 95,39 Z" {P("primary", "#e63946")} {ink()}/>'
    f'<path d="M70,39 L70,170 M45,39 C35,80 35,130 45,170 M95,39 C105,80 105,130 95,170" stroke="#ffd166" stroke-width="3" fill="none"/>'
    f'<rect x="45" y="170" width="50" height="14" rx="4" fill="#ffd166" {ink("stroke-width=\"3\"")}/><path d="M60,184 L60,215 M70,184 L70,215 M80,184 L80,215" stroke="#ffd166" stroke-width="4"/>')
add("fireworks", "Fireworks", "festive", ["fireworks", "diwali", "celebration", "new year"], 220, 220,
    "".join(f'<path d="M110,110 L{110 + r * math.cos(math.radians(a)):.1f},{110 + r * math.sin(math.radians(a)):.1f}" stroke="{["#ffd166", "#ff4f8b", "#4cc9f0"][i % 3]}" stroke-width="6" stroke-linecap="round" stroke-dasharray="14 8"/>'
            for i, (a, r) in enumerate((a, 95 if a % 30 == 0 else 70) for a in range(0, 360, 15))), ())

# ------------------------------------------------------------------ space
add("rocket", "Rocket", "space", ["rocket", "space", "astronaut", "launch"], 160, 240,
    f'<path d="M50,170 C40,200 55,220 80,235 C105,220 120,200 110,170 Z" fill="#ff9f1c" {ink("stroke-width=\"4\"")}/><path d="M65,170 C62,190 70,205 80,215 C90,205 98,190 95,170 Z" fill="#ffd166"/>'
    f'<path d="M45,120 L10,160 L15,185 L50,165 Z M115,120 L150,160 L145,185 L110,165 Z" {P("secondary", "#e63946")} {ink()}/>'
    f'<path d="M80,5 C130,40 130,130 115,175 L45,175 C30,130 30,40 80,5 Z" {P("primary", "#ffffff")} {ink()}/>'
    f'<circle cx="80" cy="85" r="22" fill="#4cc9f0" {ink()}/><path d="M70,78 L76,72" stroke="#ffffff" stroke-width="5" stroke-linecap="round"/>', ("primary", "secondary"))
add("planet_ring", "Ringed planet", "space", ["planet", "saturn", "space", "galaxy"], 240, 170,
    f'<circle cx="120" cy="85" r="60" {P("primary", "#9b5de5")} {ink()}/>'
    f'<path d="M55,70 C80,60 100,80 130,70 M70,110 C95,100 130,115 170,100" stroke="#ffffff" stroke-width="7" fill="none" opacity="0.4"/>'
    f'<ellipse cx="120" cy="90" rx="112" ry="26" fill="none" stroke="#ffd166" stroke-width="10" transform="rotate(-12 120 90)" data-recolor="secondary"/>'
    f'<path d="M62,63 A60,60 0 0 1 178,63" fill="none" {P("primary", "#9b5de5").replace("fill=", "stroke=")} stroke-width="0"/>', ("primary", "secondary"))
add("moon_cute", "Crescent moon", "space", ["moon", "night", "space", "sleep"], 180, 200,
    f'<path d="M120,10 C50,20 20,90 45,145 C70,195 140,200 170,160 C110,170 70,120 85,70 C95,40 110,25 120,10 Z" {P("primary", "#ffd166")} {ink()}/>'
    f'<circle cx="75" cy="120" r="5" fill="{INK}"/><path d="M85,140 Q95,148 105,140" stroke="{INK}" stroke-width="4" fill="none"/>')
add("ufo", "Flying saucer", "space", ["ufo", "alien", "space", "saucer"], 240, 170,
    f'<path d="M85,70 C85,25 155,25 155,70 Z" fill="#a2d2ff" fill-opacity="0.85" {ink()}/>'
    f'<ellipse cx="120" cy="85" rx="110" ry="30" {P("primary", "#adb5bd")} {ink()}/>'
    + "".join(f'<circle cx="{x}" cy="88" r="8" fill="#ffd166" {ink("stroke-width=\"3\"")}/>' for x in (50, 90, 130, 170, 200))
    + f'<path d="M80,115 L60,165 L180,165 L160,115 Z" fill="#c7f464" opacity="0.35"/>')
add("astronaut_helmet", "Space helmet", "space", ["helmet", "astronaut", "space"], 220, 220,
    f'<circle cx="110" cy="110" r="100" {P("primary", "#f1f3f5")} {ink()}/>'
    f'<ellipse cx="110" cy="105" rx="72" ry="65" fill="#a2d2ff" fill-opacity="0.35" {ink()}/>'
    f'<path d="M60,70 C70,55 85,48 100,46" stroke="#ffffff" stroke-width="9" fill="none" stroke-linecap="round"/>'
    f'<rect x="40" y="185" width="140" height="25" rx="10" fill="#adb5bd" {ink()}/>', frame=False, anchor="head")
add("comet_stars", "Starry sky", "space", ["stars", "night", "space", "galaxy"], 240, 160,
    "".join(f'<polygon points="{star_pts(x, y, r, 0.45)}" fill="{c}" {ink("stroke-width=\"3\"")}/>' for x, y, r, c in
            ((40, 40, 24, "#ffd166"), (120, 90, 34, "#ffffff"), (200, 40, 20, "#ffd166"), (210, 125, 16, "#4cc9f0"), (40, 125, 14, "#ffffff"))), ())

# ------------------------------------------------------------------ jungle & dinosaur & animals
add("palm_leaf", "Jungle leaf", "jungle", ["leaf", "jungle", "tropical", "palm"], 220, 200,
    f'<path d="M20,190 C40,120 90,40 200,15 C180,110 120,170 20,190 Z" {P("primary", "#2a9d8f")} {ink()}/>'
    f'<path d="M20,190 C70,130 120,80 190,25" stroke="#06d6a0" stroke-width="5" fill="none"/>'
    + "".join(f'<path d="M{40 + i * 25},{170 - i * 25} L{70 + i * 25},{185 - i * 30}" stroke="#06d6a0" stroke-width="4"/>' for i in range(5)))
add("monstera", "Monstera leaf", "jungle", ["monstera", "leaf", "jungle", "plant"], 200, 220,
    f'<path d="M100,215 L100,150" stroke="#2a9d8f" stroke-width="8"/>'
    f'<path d="M100,150 C20,160 0,90 30,50 C55,15 145,15 170,50 C200,90 180,160 100,150 Z" {P("primary", "#2a9d8f")} {ink()}/>'
    f'<path d="M100,150 L100,30 M100,120 L45,75 M100,95 L60,45 M100,120 L155,75 M100,95 L140,45" stroke="#06d6a0" stroke-width="5"/>'
    f'<ellipse cx="65" cy="110" rx="9" ry="5" fill="#ffffff" opacity="0.9"/><ellipse cx="135" cy="110" rx="9" ry="5" fill="#ffffff" opacity="0.9"/>')
add("binoculars", "Binoculars", "jungle", ["binoculars", "explorer", "safari", "adventure"], 220, 140,
    f'<rect x="85" y="35" width="50" height="30" rx="6" fill="#5a3e2b" {ink()}/>'
    f'<circle cx="55" cy="85" r="45" {P("primary", "#2d6a4f")} {ink()}/><circle cx="165" cy="85" r="45" {P("primary", "#2d6a4f")} {ink()}/>'
    f'<circle cx="55" cy="85" r="26" fill="#a2d2ff" {ink("stroke-width=\"4\"")}/><circle cx="165" cy="85" r="26" fill="#a2d2ff" {ink("stroke-width=\"4\"")}/>')
add("explorer_hat", "Safari hat", "jungle", ["safari", "explorer", "hat", "adventure"], 220, 130,
    f'<path d="M55,90 C55,20 165,20 165,90 Z" {P("primary", "#e9c46a")} {ink()}/>'
    f'<rect x="55" y="72" width="110" height="16" {P("secondary", "#5a3e2b")}/>'
    f'<path d="M5,100 C40,80 180,80 215,100 C190,125 30,125 5,100 Z" {P("primary", "#e9c46a")} {ink()}/>', ("primary", "secondary"), anchor="head")
add("dino_green", "Friendly dinosaur", "dinosaur", ["dinosaur", "dino", "rex", "kids"], 240, 200,
    f'<path d="M30,180 L45,140 C20,130 5,110 10,90 C30,100 45,100 60,95 C70,60 100,40 135,45 C150,20 200,15 220,40 C235,60 225,85 200,88 C185,90 175,95 170,110 C175,140 165,165 150,180 L130,180 L128,160 C110,165 90,165 75,160 L72,180 Z" {P("primary", "#06d6a0")} {ink()}/>'
    f'<circle cx="195" cy="45" r="7" fill="{INK}"/><path d="M200,70 C205,72 212,72 215,68" stroke="{INK}" stroke-width="4" fill="none"/>'
    + "".join(f'<path d="M{x},{y} l10,-18 l10,18 Z" {P("secondary", "#ffd166")} {ink("stroke-width=\"3\"")}/>' for x, y in ((80, 75), (100, 60), (122, 52)))
    + f'<circle cx="110" cy="120" r="10" fill="#ffffff" opacity="0.35"/><circle cx="140" cy="100" r="7" fill="#ffffff" opacity="0.35"/>', ("primary", "secondary"))
add("dino_egg", "Dinosaur egg", "dinosaur", ["egg", "dinosaur", "hatch"], 160, 200,
    f'<path d="M80,10 C130,10 150,110 145,140 C140,180 110,195 80,195 C50,195 20,180 15,140 C10,110 30,10 80,10 Z" {P("primary", "#f1e3c8")} {ink()}/>'
    f'<path d="M15,110 L40,95 L60,115 L80,92 L100,115 L120,95 L145,110" stroke="{INK}" stroke-width="5" fill="none"/>'
    + "".join(f'<circle cx="{x}" cy="{y}" r="{r}" {P("secondary", "#06d6a0")}/>' for x, y, r in ((60, 50, 10), (100, 65, 8), (55, 155, 12), (110, 150, 9))), ("primary", "secondary"))
add("dino_footprint", "Dino footprint", "dinosaur", ["footprint", "dinosaur", "track"], 180, 200,
    f'<path d="M90,190 C40,190 35,130 60,110 C75,100 105,100 120,110 C145,130 140,190 90,190 Z" {P("primary", "#2a9d8f")} {ink()}/>'
    f'<path d="M50,95 C30,60 40,20 55,25 C70,30 70,70 65,95 Z M90,85 C85,45 85,10 95,10 C105,10 108,45 100,85 Z M125,95 C125,60 135,25 148,30 C160,35 150,75 135,98 Z" {P("primary", "#2a9d8f")} {ink()}/>')
add("volcano", "Volcano", "dinosaur", ["volcano", "dinosaur", "prehistoric"], 240, 200,
    f'<path d="M95,40 C90,20 100,10 110,15 C115,0 135,0 140,15 C150,10 162,20 155,40 Z" fill="#adb5bd" {ink("stroke-width=\"4\"")}/>'
    f'<path d="M10,190 L90,55 L150,55 L230,190 Z" {P("primary", "#8d6e63")} {ink()}/>'
    f'<path d="M90,55 L150,55 L140,75 C135,95 125,80 120,100 C115,80 105,95 100,75 Z" fill="#ff6b35" {ink("stroke-width=\"4\"")}/>')
add("cat_face", "Cat face", "animals", ["cat", "kitty", "animal", "cute", "ears"], 220, 200,
    f'<path d="M30,90 L35,15 L90,50 C100,48 120,48 130,50 L185,15 L190,90 C200,150 160,190 110,190 C60,190 20,150 30,90 Z" {P("primary", "#ffb703")} {ink()}/>'
    f'<path d="M45,40 L50,75 L75,58 Z M175,40 L170,75 L145,58 Z" fill="#ff8fab"/>'
    f'<ellipse cx="80" cy="110" rx="9" ry="13" fill="{INK}"/><ellipse cx="140" cy="110" rx="9" ry="13" fill="{INK}"/>'
    f'<path d="M102,135 L118,135 L110,145 Z" fill="#ff8fab" {ink("stroke-width=\"3\"")}/><path d="M110,145 C105,160 92,160 88,152 M110,145 C115,160 128,160 132,152" stroke="{INK}" stroke-width="4" fill="none"/>'
    f'<path d="M20,125 L70,130 M20,145 L70,140 M200,125 L150,130 M200,145 L150,140" stroke="{INK}" stroke-width="3"/>')
add("bear_face", "Teddy bear face", "animals", ["bear", "teddy", "animal", "cute"], 220, 200,
    f'<circle cx="45" cy="45" r="35" {P("primary", "#b07d62")} {ink()}/><circle cx="175" cy="45" r="35" {P("primary", "#b07d62")} {ink()}/>'
    f'<circle cx="45" cy="45" r="17" fill="#f1d3a1"/><circle cx="175" cy="45" r="17" fill="#f1d3a1"/>'
    f'<circle cx="110" cy="110" r="85" {P("primary", "#b07d62")} {ink()}/>'
    f'<ellipse cx="110" cy="140" rx="42" ry="32" fill="#f1d3a1" {ink("stroke-width=\"4\"")}/>'
    f'<circle cx="78" cy="100" r="9" fill="{INK}"/><circle cx="142" cy="100" r="9" fill="{INK}"/><ellipse cx="110" cy="128" rx="14" ry="10" fill="{INK}"/>'
    f'<path d="M110,138 L110,150 M95,155 Q110,165 125,155" stroke="{INK}" stroke-width="4" fill="none"/>')
add("bunny_ears", "Bunny ears", "animals", ["bunny", "rabbit", "ears", "easter", "cute"], 200, 170,
    f'<path d="M50,165 C20,110 25,20 55,10 C85,0 85,110 75,165 Z" {P("primary", "#ffffff")} {ink()}/>'
    f'<path d="M125,165 C115,110 115,0 145,10 C175,20 180,110 150,165 Z" {P("primary", "#ffffff")} {ink()}/>'
    f'<path d="M55,150 C40,110 42,40 56,30 C70,30 70,110 66,150 Z M135,150 C130,110 130,30 144,30 C158,40 160,110 145,150 Z" fill="#ffafcc"/>'
    f'<rect x="20" y="150" width="160" height="18" rx="9" {P("secondary", "#cdb4db")} {ink("stroke-width=\"4\"")}/>', ("primary", "secondary"), anchor="head")
add("cat_ears", "Cat ears headband", "animals", ["cat", "ears", "headband", "cute"], 220, 110,
    f'<path d="M20,95 C60,60 160,60 200,95" stroke="{INK}" stroke-width="12" fill="none" stroke-linecap="round"/>'
    f'<path d="M40,85 L55,10 L105,65 Z M180,85 L165,10 L115,65 Z" {P("primary", "#2d2140")} {ink()}/>'
    f'<path d="M55,65 L60,32 L85,60 Z M165,65 L160,32 L135,60 Z" fill="#ff8fab"/>', anchor="head")
add("paw_print", "Paw print", "animals", ["paw", "dog", "cat", "pet"], 180, 180,
    f'<ellipse cx="90" cy="120" rx="45" ry="38" {P("primary", "#9b5de5")} {ink()}/>'
    + "".join(f'<ellipse cx="{x}" cy="{y}" rx="16" ry="21" {P("primary", "#9b5de5")} {ink()}/>' for x, y in ((35, 75), (70, 40), (110, 40), (145, 75))))
add("fish_cute", "Little fish", "animals", ["fish", "ocean", "sea", "cute"], 220, 140,
    f'<path d="M150,70 L210,20 L205,70 L210,120 Z" {P("secondary", "#ff9f1c")} {ink()}/>'
    f'<ellipse cx="95" cy="70" rx="80" ry="55" {P("primary", "#4cc9f0")} {ink()}/>'
    f'<circle cx="55" cy="58" r="12" fill="#ffffff" {ink("stroke-width=\"3\"")}/><circle cx="58" cy="58" r="6" fill="{INK}"/>'
    f'<path d="M30,90 Q40,98 50,92" stroke="{INK}" stroke-width="4" fill="none"/>'
    f'<path d="M100,30 C115,50 115,90 100,110 M125,35 C140,55 140,85 125,105" stroke="#ffffff" stroke-width="5" fill="none" opacity="0.6"/>', ("primary", "secondary"))
add("elephant", "Little elephant", "animals", ["elephant", "jungle", "animal", "cute"], 220, 190,
    f'<ellipse cx="120" cy="105" rx="85" ry="65" {P("primary", "#a2a9c8")} {ink()}/>'
    f'<path d="M60,85 C25,90 15,130 30,165 C35,175 50,170 48,160 C40,135 45,115 65,112" {P("primary", "#a2a9c8")} {ink()}/>'
    f'<ellipse cx="100" cy="80" rx="38" ry="48" fill="#ffafcc" {ink()}/>'
    f'<circle cx="68" cy="75" r="7" fill="{INK}"/><rect x="70" y="150" width="28" height="35" rx="10" {P("primary", "#a2a9c8")} {ink()}/><rect x="150" y="150" width="28" height="35" rx="10" {P("primary", "#a2a9c8")} {ink()}/>')

# ------------------------------------------------------------------ fantasy / princess
add("tiara", "Tiara", "fantasy", ["tiara", "princess", "crown", "fairytale"], 220, 110,
    f'<path d="M10,100 C40,75 70,65 110,15 C150,65 180,75 210,100 C180,90 140,85 110,85 C80,85 40,90 10,100 Z" {P("primary", "#e5e5e5")} {ink()}/>'
    f'<path d="M110,30 L122,55 L110,75 L98,55 Z" {P("secondary", "#ff4f8b")} {ink("stroke-width=\"3\"")}/>'
    + "".join(f'<circle cx="{x}" cy="{y}" r="7" fill="#a2d2ff" {ink("stroke-width=\"3\"")}/>' for x, y in ((55, 78), (165, 78), (80, 62), (140, 62))), ("primary", "secondary"), anchor="head")
add("magic_wand", "Magic wand", "fantasy", ["wand", "magic", "fairy", "princess"], 200, 220,
    f'<path d="M30,205 L120,95" stroke="{INK}" stroke-width="14" stroke-linecap="round"/><path d="M30,205 L120,95" stroke="#cdb4db" stroke-width="7" stroke-linecap="round"/>'
    f'<polygon points="{star_pts(135, 70, 60, 0.48)}" {P("primary", "#ffd166")} {ink()}/>'
    f'<path d="M175,140 l4,10 l10,4 l-10,4 l-4,10 l-4,-10 l-10,-4 l10,-4 Z M60,60 l3,8 l8,3 l-8,3 l-3,8 l-3,-8 l-8,-3 l8,-3 Z" fill="#ff8fab"/>')
add("castle", "Fairytale castle", "fantasy", ["castle", "princess", "fairytale", "kingdom"], 220, 220,
    f'<rect x="40" y="100" width="140" height="110" {P("primary", "#ffd6e7")} {ink()}/>'
    f'<rect x="10" y="80" width="45" height="130" {P("primary", "#ffd6e7")} {ink()}/><rect x="165" y="80" width="45" height="130" {P("primary", "#ffd6e7")} {ink()}/>'
    f'<path d="M5,82 L32,20 L60,82 Z M160,82 L187,20 L215,82 Z" {P("secondary", "#9b5de5")} {ink()}/>'
    f'<rect x="80" y="60" width="60" height="50" {P("primary", "#ffd6e7")} {ink()}/><path d="M75,62 L110,5 L145,62 Z" {P("secondary", "#9b5de5")} {ink()}/>'
    f'<path d="M90,210 L90,170 C90,145 130,145 130,170 L130,210 Z" fill="#5a3e2b" {ink()}/>'
    f'<rect x="25" y="110" width="15" height="22" rx="7" fill="#a2d2ff"/><rect x="180" y="110" width="15" height="22" rx="7" fill="#a2d2ff"/>', ("primary", "secondary"))
add("unicorn_horn", "Unicorn horn", "fantasy", ["unicorn", "horn", "magic", "rainbow"], 120, 200,
    f'<path d="M60,5 L95,170 L25,170 Z" {P("primary", "#ffd166")} {ink()}/>'
    f'<path d="M48,60 L75,52 M40,100 L84,88 M32,140 L90,125" stroke="#ffffff" stroke-width="7" opacity="0.8"/>'
    f'<path d="M5,190 C20,160 40,165 45,175 C55,155 75,155 80,175 C85,165 105,160 115,190 Z" fill="#ffafcc" {ink("stroke-width=\"4\"")}/>', anchor="head")
add("rainbow", "Rainbow", "fantasy", ["rainbow", "pastel", "happy", "weather"], 240, 140,
    "".join(f'<path d="M{20 + i * 16},130 A{100 - i * 16},{100 - i * 16} 0 0 1 {220 - i * 16},130" stroke="{c}" stroke-width="16" fill="none"/>'
            for i, c in enumerate(("#ff595e", "#ff9f1c", "#ffd166", "#06d6a0", "#4cc9f0", "#9b5de5")))
    + f'<path d="M5,128 C5,100 45,98 50,115 C60,95 90,105 80,130 Z" fill="#ffffff" {ink("stroke-width=\"4\"")}/>'
      f'<path d="M160,130 C150,105 180,95 190,115 C195,98 235,100 235,128 Z" fill="#ffffff" {ink("stroke-width=\"4\"")}/>', ())
add("cloud_cute", "Cloud", "fantasy", ["cloud", "sky", "pastel", "weather"], 220, 140,
    f'<path d="M45,125 C10,125 5,80 40,75 C35,35 85,20 105,45 C120,15 180,20 180,65 C215,65 220,125 180,125 Z" {P("primary", "#ffffff")} {ink()}/>'
    f'<circle cx="90" cy="90" r="6" fill="{INK}"/><circle cx="130" cy="90" r="6" fill="{INK}"/><path d="M100,105 Q110,114 120,105" stroke="{INK}" stroke-width="4" fill="none"/>')

# ------------------------------------------------------------------ superhero (generic, no franchises)
add("hero_mask", "Hero eye mask", "superhero", ["mask", "superhero", "hero", "costume"], 240, 100,
    f'<path d="M120,30 C150,10 215,5 232,35 C238,70 200,90 160,80 C140,75 130,65 120,65 C110,65 100,75 80,80 C40,90 2,70 8,35 C25,5 90,10 120,30 Z" {P("primary", "#e63946")} {ink()}/>'
    f'<path d="M45,45 C55,35 80,35 92,50 C80,60 55,60 45,45 Z M195,45 C185,35 160,35 148,50 C160,60 185,60 195,45 Z" fill="#ffffff" {ink("stroke-width=\"4\"")}/>', anchor="eyes")
add("hero_cape", "Hero cape", "superhero", ["cape", "superhero", "hero", "costume"], 220, 240,
    f'<path d="M60,15 C90,30 130,30 160,15 L210,225 C150,240 70,240 10,225 Z" {P("primary", "#e63946")} {ink()}/>'
    f'<path d="M60,15 C90,30 130,30 160,15 C150,45 70,45 60,15 Z" {P("secondary", "#b5172f")} {ink()}/>'
    f'<path d="M85,60 L60,220 M135,60 L160,220" stroke="#b5172f" stroke-width="5" opacity="0.5"/>', ("primary", "secondary"))
add("lightning", "Lightning bolt", "superhero", ["lightning", "bolt", "power", "energy", "hero"], 140, 220,
    f'<path d="M85,5 L15,125 L65,125 L45,215 L125,85 L75,85 L105,5 Z" {P("primary", "#ffd166")} {ink()}/>')
add("hero_emblem", "Hero shield emblem", "superhero", ["shield", "emblem", "hero", "badge"], 200, 220,
    f'<path d="M100,10 L185,40 C185,120 150,180 100,210 C50,180 15,120 15,40 Z" {P("primary", "#3a86ff")} {ink()}/>'
    f'<path d="M100,30 L165,52 C165,115 140,160 100,185 C60,160 35,115 35,52 Z" {P("secondary", "#ffd166")}/>'
    f'<polygon points="{star_pts(100, 102, 48, 0.45)}" {P("primary", "#3a86ff")}/>', ("primary", "secondary"))
add("pow_burst", "Comic burst", "superhero", ["pow", "comic", "burst", "boom", "hero"], 240, 200,
    f'<polygon points="{star_pts(120, 100, 105, 0.6, n=11, rot=-80)}" {P("primary", "#ff4f8b")} {ink()}/>'
    f'<polygon points="{star_pts(120, 100, 75, 0.62, n=11, rot=-80)}" {P("secondary", "#ffd166")}/>', ("primary", "secondary"))

# ------------------------------------------------------------------ wedding
add("rings", "Wedding rings", "wedding", ["rings", "wedding", "engagement", "love"], 240, 170,
    f'<circle cx="90" cy="100" r="58" fill="none" stroke="{INK}" stroke-width="22"/><circle cx="90" cy="100" r="58" fill="none" stroke="#ffc93c" stroke-width="13" data-recolor="primary"/>'
    f'<circle cx="155" cy="100" r="58" fill="none" stroke="{INK}" stroke-width="22"/><circle cx="155" cy="100" r="58" fill="none" stroke="#e5e5e5" stroke-width="13" data-recolor="secondary"/>'
    f'<path d="M135,42 L148,20 L162,20 L175,42 L155,58 Z" fill="#a2d2ff" {ink("stroke-width=\"4\"")}/>', ("primary", "secondary"))
add("dove", "Dove", "wedding", ["dove", "bird", "peace", "wedding"], 220, 170,
    f'<path d="M30,110 C50,80 90,80 110,95 C120,50 160,20 200,15 C190,60 170,90 140,105 C170,105 190,120 195,135 C160,140 120,150 80,140 C60,150 30,150 10,140 C25,135 30,125 30,110 Z" {P("primary", "#ffffff")} {ink()}/>'
    f'<circle cx="45" cy="108" r="5" fill="{INK}"/><path d="M28,112 L12,118 L28,120 Z" fill="#ff9f1c"/>')
add("champagne", "Celebration glasses", "wedding", ["champagne", "toast", "cheers", "celebration", "new year"], 220, 220,
    f'<g transform="rotate(-15 80 120)"><path d="M50,20 L110,20 L100,110 C95,125 65,125 60,110 Z" fill="#ffe8a3" {ink()}/><path d="M80,122 L80,195 M55,200 L105,200" stroke="{INK}" stroke-width="7" stroke-linecap="round"/></g>'
    f'<g transform="rotate(15 140 120)"><path d="M110,20 L170,20 L160,110 C155,125 125,125 120,110 Z" fill="#ffe8a3" {ink()}/><path d="M140,122 L140,195 M115,200 L165,200" stroke="{INK}" stroke-width="7" stroke-linecap="round"/></g>'
    f'<circle cx="110" cy="15" r="6" fill="#ffd166"/><circle cx="95" cy="35" r="4" fill="#ffd166"/><circle cx="125" cy="40" r="4" fill="#ffd166"/>')
add("wedding_cake", "Tiered cake", "wedding", ["cake", "wedding", "tiered", "celebration"], 200, 220,
    f'<rect x="65" y="40" width="70" height="50" rx="6" {P("primary", "#ffffff")} {ink()}/>'
    f'<rect x="40" y="88" width="120" height="55" rx="6" {P("primary", "#ffffff")} {ink()}/>'
    f'<rect x="15" y="141" width="170" height="65" rx="6" {P("primary", "#ffffff")} {ink()}/>'
    f'<path d="M65,75 Q100,90 135,75 M40,125 Q100,145 160,125 M15,180 Q100,200 185,180" stroke="#ffafcc" stroke-width="6" fill="none" data-recolor="secondary"/>'
    f'<path d="{heart_path(100, 25, 15)}" fill="#ff4f8b"/>', ("primary", "secondary"))

# ------------------------------------------------------------------ decorative shapes
add("shape_circle", "Circle", "shapes", ["circle", "dot", "shape", "basic"], 200, 200, f'<circle cx="100" cy="100" r="95" {P("primary", "#4cc9f0")}/>')
add("shape_blob", "Blob", "shapes", ["blob", "organic", "shape", "background"], 220, 200,
    f'<path d="M110,10 C170,5 215,50 210,105 C205,160 160,195 105,190 C45,185 5,150 10,95 C15,45 55,15 110,10 Z" {P("primary", "#ffd6e7")}/>')
add("shape_squiggle", "Squiggle", "shapes", ["squiggle", "line", "retro", "memphis"], 240, 80,
    f'<path d="M10,40 C30,0 50,0 70,40 C90,80 110,80 130,40 C150,0 170,0 190,40 C210,80 225,70 232,50" stroke="#9b5de5" stroke-width="14" fill="none" stroke-linecap="round" data-recolor="primary"/>')
add("shape_zigzag", "Zigzag", "shapes", ["zigzag", "retro", "pop", "memphis"], 240, 80,
    f'<path d="M10,60 L40,20 L70,60 L100,20 L130,60 L160,20 L190,60 L220,20" stroke="#ff4f8b" stroke-width="14" fill="none" stroke-linejoin="round" stroke-linecap="round" data-recolor="primary"/>')
add("shape_dots", "Dot cluster", "shapes", ["dots", "spots", "pattern", "retro"], 200, 200,
    "".join(f'<circle cx="{x}" cy="{y}" r="{r}" {P("primary", "#ffd166")}/>' for x, y, r in ((40, 40, 18), (110, 60, 26), (170, 40, 14), (60, 130, 22), (150, 140, 30), (100, 185, 12))))
add("shape_triangle", "Rounded triangle", "shapes", ["triangle", "shape", "geometric"], 200, 180,
    f'<path d="M100,15 C110,15 115,22 120,30 L185,145 C192,160 185,170 170,170 L30,170 C15,170 8,160 15,145 L80,30 C85,22 90,15 100,15 Z" {P("primary", "#06d6a0")}/>')
add("shape_flower_frame", "Flower shape", "shapes", ["flower", "scallop", "shape"], 200, 200,
    "".join(f'<circle cx="{100 + 60 * math.cos(math.radians(a)):.1f}" cy="{100 + 60 * math.sin(math.radians(a)):.1f}" r="40" {P("primary", "#ffafcc")}/>' for a in range(0, 360, 45))
    + f'<circle cx="100" cy="100" r="62" {P("primary", "#ffafcc")}/>')

# ------------------------------------------------------------------ frames (drawn over the whole artboard)
def ring_frame(color_slot, color, inner_deco):
    return (f'<circle cx="200" cy="200" r="188" fill="none" stroke="{color}" stroke-width="18" data-recolor="{color_slot}"/>'
            f'<circle cx="200" cy="200" r="174" fill="none" stroke="#ffffff" stroke-width="4" stroke-dasharray="4 10" opacity="0.9"/>'
            + inner_deco)


add("frame_ring_stars", "Star ring frame", "frames", ["frame", "circle", "stars", "badge"], 400, 400,
    ring_frame("primary", "#ffd166", "".join(f'<polygon points="{star_pts(200 + 188 * math.cos(math.radians(a)), 200 + 188 * math.sin(math.radians(a)), 16, 0.45)}" fill="#ffffff" {ink("stroke-width=\"3\"")}/>' for a in range(0, 360, 45))),
    frame=True)
add("frame_ring_hearts", "Heart ring frame", "frames", ["frame", "circle", "hearts", "love"], 400, 400,
    ring_frame("primary", "#ff8fab", "".join(f'<path d="{heart_path(200 + 188 * math.cos(math.radians(a)), 200 + 188 * math.sin(math.radians(a)), 14)}" fill="#ffffff" {ink("stroke-width=\"3\"")}/>' for a in range(0, 360, 40))),
    frame=True)
add("frame_scallop", "Scalloped frame", "frames", ["frame", "scallop", "vintage", "label"], 400, 400,
    "".join(f'<circle cx="{200 + 182 * math.cos(math.radians(a)):.1f}" cy="{200 + 182 * math.sin(math.radians(a)):.1f}" r="16" fill="none" stroke="#9b5de5" stroke-width="8" data-recolor="primary"/>' for a in range(0, 360, 12))
    + f'<circle cx="200" cy="200" r="165" fill="none" stroke="#9b5de5" stroke-width="5" data-recolor="primary"/>', frame=True)
add("frame_square_dots", "Dotted square frame", "frames", ["frame", "square", "dots", "polaroid"], 400, 400,
    f'<rect x="12" y="12" width="376" height="376" rx="30" fill="none" stroke="#4cc9f0" stroke-width="18" data-recolor="primary"/>'
    + "".join(f'<circle cx="{x}" cy="{y}" r="6" fill="#ffffff"/>' for x in range(40, 380, 40) for y in (12, 388))
    + "".join(f'<circle cx="{x}" cy="{y}" r="6" fill="#ffffff"/>' for y in range(40, 380, 40) for x in (12, 388)), frame=True)
add("frame_laurel", "Laurel wreath", "frames", ["frame", "laurel", "wreath", "award", "wedding"], 400, 400,
    "".join(f'<ellipse cx="{200 + 175 * math.cos(math.radians(a)):.1f}" cy="{200 + 175 * math.sin(math.radians(a)):.1f}" rx="22" ry="10" '
            f'transform="rotate({a + 60} {200 + 175 * math.cos(math.radians(a)):.1f} {200 + 175 * math.sin(math.radians(a)):.1f})" {P("primary", "#2a9d8f")} {ink("stroke-width=\"3\"")}/>'
            for a in list(range(110, 250, 14)) + list(range(-70, 70, 14))), frame=True)
add("frame_film", "Photo frame", "frames", ["frame", "photo", "polaroid", "picture"], 400, 460,
    f'<path fill-rule="evenodd" d="M10,10 L390,10 L390,450 L10,450 Z M35,35 L35,365 L365,365 L365,35 Z" {P("primary", "#ffffff")} {ink()}/>', frame=True)
add("frame_confetti", "Confetti frame", "frames", ["frame", "confetti", "party", "border"], 400, 400,
    confetti_body(11, 40, 400, 60) + f'<g transform="translate(0,340)">{confetti_body(12, 40, 400, 60)}</g>'
    + f'<g transform="translate(0,60)">{confetti_body(13, 14, 60, 280)}</g><g transform="translate(340,60)">{confetti_body(14, 14, 60, 280)}</g>',
    (), frame=True)
add("frame_kolam", "Kolam border", "frames", ["frame", "kolam", "pongal", "diwali", "festival"], 400, 400,
    f'<rect x="20" y="20" width="360" height="360" rx="20" fill="none" stroke="#e76f51" stroke-width="10" data-recolor="primary"/>'
    + "".join(f'<circle cx="{x}" cy="{y}" r="5" fill="#ffd166"/>' for x in range(50, 360, 30) for y in (20, 380))
    + "".join(f'<path d="M{c[0]},{c[1]} m-28,0 a28,28 0 1,0 56,0 a28,28 0 1,0 -56,0" fill="none" stroke="#9b5de5" stroke-width="6"/>' for c in ((20, 20), (380, 20), (20, 380), (380, 380))), frame=True)


# ------------------------------------------------------------------ patterns (tiles)
PATTERNS = [
    ("dots", "Polka dots", '<circle cx="25" cy="25" r="9" {f}/><circle cx="75" cy="75" r="9" {f}/>'),
    ("stripes", "Stripes", '<path d="M-10,60 L60,-10 M40,110 L110,40 M-10,110 L110,-10" stroke="{c}" stroke-width="14" data-recolor="pattern"/>'),
    ("stars", "Stars", '<polygon points="' + star_pts(25, 27, 14, 0.45) + '" {f}/><polygon points="' + star_pts(75, 77, 10, 0.45) + '" {f}/>'),
    ("hearts", "Hearts", '<path d="' + heart_path(25, 27, 13) + '" {f}/><path d="' + heart_path(75, 77, 11) + '" {f}/>'),
    ("checks", "Checks", '<rect x="0" y="0" width="50" height="50" {f} opacity="0.55"/><rect x="50" y="50" width="50" height="50" {f} opacity="0.55"/>'),
    ("confetti", "Confetti", '<rect x="10" y="12" width="14" height="6" rx="2" {f} transform="rotate(30 17 15)"/><circle cx="70" cy="22" r="5" {f}/>'
                             '<rect x="58" y="68" width="14" height="6" rx="2" {f} transform="rotate(-40 65 71)"/><circle cx="22" cy="74" r="4" {f}/>'),
    ("waves", "Waves", '<path d="M0,25 Q25,5 50,25 T100,25 M0,75 Q25,55 50,75 T100,75" stroke="{c}" stroke-width="7" fill="none" data-recolor="pattern"/>'),
    ("zigzag", "Zigzag", '<path d="M0,40 L25,15 L50,40 L75,15 L100,40 M0,90 L25,65 L50,90 L75,65 L100,90" stroke="{c}" stroke-width="7" fill="none" data-recolor="pattern"/>'),
    ("leaves", "Leaves", '<path d="M15,45 C15,20 35,10 45,10 C45,35 30,45 15,45 Z" {f}/><path d="M60,95 C60,70 80,60 90,60 C90,85 75,95 60,95 Z" {f}/>'),
    ("snowflakes", "Snowflakes", '<path d="M25,10 L25,40 M12,17 L38,33 M12,33 L38,17 M75,60 L75,90 M62,67 L88,83 M62,83 L88,67" stroke="{c}" stroke-width="4" stroke-linecap="round" data-recolor="pattern"/>'),
    ("grid", "Grid", '<path d="M0,0 L100,0 L100,100 M50,0 L50,100 M0,50 L100,50" stroke="{c}" stroke-width="3" fill="none" data-recolor="pattern"/>'),
    ("sparkle", "Sparkles", '<path d="M25,8 Q28,22 42,25 Q28,28 25,42 Q22,28 8,25 Q22,22 25,8 Z" {f}/><path d="M75,62 Q77,72 87,75 Q77,78 75,88 Q73,78 63,75 Q73,72 75,62 Z" {f}/>'),
]


def pattern_svg(body):
    fill = 'fill="#ffffff" data-recolor="pattern"'
    return svg(100, 100, '<rect width="100" height="100" fill="none" data-recolor="background"/>' + body.replace("{f}", fill).replace("{c}", "#ffffff"))


# ------------------------------------------------------------------ themes
def theme(id, order, name, description, palette, heading, decorations, accessories, frames, texts, backgrounds,
          shapes=("silhouette", "circle", "rounded"), border=None, shadow=None, sizes=(50, 60, 75), text_color=None, body_font="Poppins"):
    return {
        "id": id, "order": order, "name": name, "description": description, "palette": list(palette),
        "colors": {"primary": palette[0], "secondary": palette[1], "accent": palette[2], "text": text_color or INK,
                   "background": palette[3] if len(palette) > 3 else "#ffffff"},
        "typography": {"heading": heading, "body": body_font},
        "decorations": decorations, "accessorySets": accessories, "frames": frames,
        "border": border or {"widthMm": 3.0, "color": "#ffffff", "outlines": [], "smoothing": 0.5},
        "shadow": shadow or {"enabled": False, "blurMm": 1.0, "opacity": 0.3},
        "layoutPresets": [
            {"id": "grid-60", "name": "Grid of 60 mm stickers", "mode": "grid", "sizeMm": 60},
            {"id": "pack-mixed", "name": "Mixed sizes, packed", "mode": "pack", "sizesMm": [75, 50, 40]},
            {"id": "fill-50", "name": "Fill page with 50 mm", "mode": "fill", "sizeMm": 50},
        ],
        "suggestedSizesMm": list(sizes), "textPresets": texts, "backgrounds": backgrounds, "shapes": list(shapes),
        "license": {"assets": LICENSE, "fonts": "See assets/fonts/licenses"},
    }


def bg_solid(c):
    return {"type": "solid", "color": c}


def bg_grad(a, b, angle=135):
    return {"type": "gradient", "color": a, "color2": b, "angle": angle}


def bg_pat(pid, base, fg="#ffffff"):
    return {"type": "pattern", "patternId": pid, "color": base, "patternColor": fg}


THEMES = [
    theme("birthday", 1, "Birthday", "Balloons, cake and confetti for a bright birthday party.", ["#ff4f8b", "#4cc9f0", "#ffd166", "#fff5f9"], "Luckiest Guy",
          ["balloon_bunch", "balloon_single", "confetti_scatter", "cake_birthday", "cupcake", "gift_box", "banner_bunting", "sparkles", "streamers", "star_basic"],
          {"Party hats": ["party_hat_stripes", "party_hat_dots", "crown_paper"], "Crowns": ["crown_gold"], "Fun glasses": ["sunglasses_star"]},
          ["frame_ring_stars", "frame_confetti"], ["Happy Birthday", "Birthday Boy", "Birthday Girl", "Make a Wish", "Party Time", "Let's Celebrate"],
          [bg_pat("dots", "#ff8fab"), bg_grad("#ffd166", "#ff8fab"), bg_pat("confetti", "#4cc9f0"), bg_solid("#ffffff")],
          border={"widthMm": 3.0, "color": "#ffffff", "outlines": [{"widthMm": 0.8, "color": "#ff4f8b", "gapMm": 0}], "smoothing": 0.6}),
    theme("gentleman", 2, "Mr. Gentleman", "Bow ties, top hats and mustaches with a dapper navy-and-gold palette.", ["#1d3557", "#c9a227", "#e63946", "#f1faee"], "Lobster",
          ["cane", "stars_trio", "badge_scallop", "banner_ribbon"], {"Hats": ["top_hat", "bowler_hat"], "Neckwear": ["bowtie", "bowtie_dots", "necktie"],
                                                                    "Mustaches": ["mustache_curly", "mustache_classic"], "Monocle": ["monocle"]},
          ["frame_laurel", "frame_scallop"], ["Little Gentleman", "Dapper Dude", "Mr. Cool", "Thank You", "Happy Birthday"],
          [bg_pat("stripes", "#1d3557", "#2b4a75"), bg_solid("#f1faee"), bg_grad("#1d3557", "#457b9d")], body_font="Poppins",
          border={"widthMm": 3.0, "color": "#ffffff", "outlines": [{"widthMm": 0.9, "color": "#c9a227", "gapMm": 0}], "smoothing": 0.5}),
    theme("superhero", 3, "Superhero", "Comic bursts, capes and lightning in primary colours (original designs, no franchise characters).", ["#e63946", "#3a86ff", "#ffd166", "#fff3b0"], "Bangers",
          ["pow_burst", "lightning", "hero_emblem", "speech_shout", "star_basic", "hero_cape"], {"Masks": ["hero_mask"], "Capes": ["hero_cape"]},
          ["frame_ring_stars"], ["Super Kid", "Hero Mode", "Power Up!", "Kapow!", "Birthday Hero"],
          [bg_pat("dots", "#ffd166", "#ff9f1c"), bg_grad("#3a86ff", "#e63946", 160), bg_solid("#fff3b0")], text_color="#1d3557",
          border={"widthMm": 3.0, "color": "#ffffff", "outlines": [{"widthMm": 1.2, "color": "#1d3557", "gapMm": 0}], "smoothing": 0.5}),
    theme("space", 4, "Space", "Rockets, planets and stars on deep-space colours.", ["#3a0ca3", "#4cc9f0", "#ffd166", "#10002b"], "Luckiest Guy",
          ["rocket", "planet_ring", "moon_cute", "ufo", "comet_stars", "star_shooting", "sparkles"], {"Helmets": ["astronaut_helmet"]},
          ["frame_ring_stars"], ["Space Explorer", "To the Moon", "Blast Off!", "Out of this World"],
          [bg_pat("stars", "#240046", "#ffd166"), bg_grad("#10002b", "#3a0ca3", 180), bg_pat("sparkle", "#3a0ca3", "#4cc9f0")], text_color="#3a0ca3"),
    theme("jungle", 5, "Jungle Adventure", "Leaves, binoculars and safari hats for explorers.", ["#2a9d8f", "#e9c46a", "#f4a261", "#e9f5db"], "Chewy",
          ["palm_leaf", "monstera", "binoculars", "elephant", "sun_happy"], {"Safari hats": ["explorer_hat"]},
          ["frame_laurel"], ["Jungle Explorer", "Wild One", "Adventure Awaits", "Roar!"],
          [bg_pat("leaves", "#95d5b2", "#2d6a4f"), bg_grad("#e9f5db", "#95d5b2"), bg_solid("#e9c46a")], text_color="#1b4332"),
    theme("dinosaur", 6, "Dinosaur", "Friendly dinos, eggs, footprints and volcanoes.", ["#06d6a0", "#ff9f1c", "#8d6e63", "#f1faee"], "Chewy",
          ["dino_green", "dino_egg", "dino_footprint", "volcano", "palm_leaf"], {"Party hats": ["party_hat_dots"]},
          ["frame_ring_stars"], ["Dino-mite!", "Roar!", "Three-Rex", "Birthday-saurus"],
          [bg_pat("dots", "#b7e4c7", "#52b788"), bg_grad("#f1faee", "#b7e4c7"), bg_solid("#ffd8a8")], text_color="#1b4332"),
    theme("princess", 7, "Princess and Fairytale", "Tiaras, castles, wands and sparkles in soft pinks and lilacs.", ["#ff8fab", "#cdb4db", "#ffd166", "#fff0f6"], "Great Vibes",
          ["castle", "magic_wand", "sparkles", "heart_basic", "cloud_cute", "flower_pink"], {"Tiaras": ["tiara", "crown_royal"], "Unicorn": ["unicorn_horn"]},
          ["frame_scallop", "frame_ring_hearts"], ["Little Princess", "Once Upon a Time", "Make a Wish", "Magical Day"],
          [bg_pat("sparkle", "#ffd6e7", "#ffffff"), bg_grad("#fff0f6", "#cdb4db"), bg_pat("hearts", "#ffafcc", "#ffffff")], text_color="#9d4edd"),
    theme("animals", 8, "Cute Animals", "Cats, bears, bunnies and paw prints.", ["#ffb703", "#ff8fab", "#9b5de5", "#fff8e7"], "Chewy",
          ["cat_face", "bear_face", "paw_print", "fish_cute", "elephant", "heart_basic"], {"Animal ears": ["bunny_ears", "cat_ears"]},
          ["frame_ring_hearts"], ["Purr-fect", "Wild About You", "Beary Cute", "Hello Friend"],
          [bg_pat("dots", "#ffe5b4", "#ffffff"), bg_grad("#fff8e7", "#ffd6e7"), bg_solid("#e0f2fe")]),
    theme("school", 9, "School", "Pencils, books, apples and backpacks for labels and rewards.", ["#3a86ff", "#ffd166", "#e63946", "#f8f9fa"], "Permanent Marker",
          ["pencil", "crayons", "book_open", "apple_red", "ruler", "backpack", "abc_blocks", "star_face", "ribbon_award"], {"Graduation": ["grad_cap"], "Glasses": ["glasses_round"]},
          ["frame_square_dots"], ["Great Job!", "Star Student", "Back to School", "Super Reader", "First Day"],
          [bg_pat("grid", "#ffffff", "#a2d2ff"), bg_solid("#fff3b0"), bg_grad("#e0f2fe", "#fff3b0")], text_color="#1d3557", shapes=("silhouette", "rounded", "rect", "circle")),
    theme("sports", 10, "Sports", "Balls, trophies and medals for champions.", ["#3a86ff", "#06d6a0", "#ffc93c", "#f1faee"], "Bangers",
          ["soccer_ball", "basketball", "cricket_bat", "trophy", "medal", "tennis_racket", "stars_trio"], {"Caps": ["baseball_cap"]},
          ["frame_laurel"], ["Champion", "MVP", "Game Day", "Team Player", "Goal!"],
          [bg_pat("stripes", "#2a9d8f", "#40c9a2"), bg_grad("#3a86ff", "#06d6a0"), bg_solid("#f1faee")], text_color="#1d3557"),
    theme("christmas", 11, "Christmas", "Trees, snowflakes, candy canes and Santa hats.", ["#e63946", "#2a9d8f", "#ffd166", "#f1faee"], "Lobster",
          ["christmas_tree", "snowflake", "candy_cane", "gingerbread", "gift_box", "star_basic"], {"Santa hats": ["santa_hat"]},
          ["frame_laurel", "frame_ring_stars"], ["Merry Christmas", "Ho Ho Ho", "Season's Greetings", "Happy Holidays"],
          [bg_pat("snowflakes", "#e63946", "#ffffff"), bg_pat("checks", "#ffffff", "#2a9d8f"), bg_grad("#2a9d8f", "#1b4332")], text_color="#9d0208"),
    theme("halloween", 12, "Halloween", "Friendly ghosts, pumpkins, bats and witch hats.", ["#ff9f1c", "#5a189a", "#2d2140", "#fff1e6"], "Creepster",
          ["pumpkin", "ghost", "bat", "spider_web", "moon_cute"], {"Witch hats": ["witch_hat"], "Cat ears": ["cat_ears"]},
          ["frame_ring_stars"], ["Happy Halloween", "Boo!", "Trick or Treat", "Spooky Cute"],
          [bg_pat("dots", "#5a189a", "#ff9f1c"), bg_grad("#ff9f1c", "#5a189a", 180), bg_solid("#2d2140")], text_color="#5a189a"),
    theme("diwali", 13, "Diwali", "Diyas, rangoli, lanterns and marigold garlands in warm festive colours.", ["#e76f51", "#ffd166", "#9b5de5", "#fff3e0"], "Lobster",
          ["diya_lamp", "rangoli", "lantern_sky", "fireworks", "flower_garland", "sparkles"], {}, ["frame_kolam"],
          ["Happy Diwali", "Festival of Lights", "Shubh Deepavali", "Light and Joy"],
          [bg_pat("sparkle", "#7b2cbf", "#ffd166"), bg_grad("#ff9f1c", "#e63946"), bg_solid("#fff3e0")], text_color="#7b2cbf"),
    theme("pongal", 14, "Pongal", "Harvest pots, sugarcane, kolam and the happy sun.", ["#ff9f1c", "#2a9d8f", "#ffd166", "#fffbea"], "Chewy",
          ["pongal_pot", "sugarcane", "sun_happy", "rangoli", "flower_garland"], {}, ["frame_kolam"],
          ["Happy Pongal", "Harvest Joy", "Pongalo Pongal", "Thai Pongal"],
          [bg_pat("dots", "#ffd166", "#ffffff"), bg_grad("#fffbea", "#ffd166"), bg_solid("#e9f5db")], text_color="#9c4a1a"),
    theme("wedding", 15, "Wedding and Celebration", "Rings, doves, flowers and tiered cakes in elegant neutrals.", ["#c9a227", "#ffafcc", "#e5e5e5", "#fffaf5"], "Great Vibes",
          ["rings", "dove", "champagne", "wedding_cake", "flower_bouquet", "hearts_double"], {"Bow ties": ["bowtie"], "Tiaras": ["tiara"]},
          ["frame_laurel", "frame_scallop"], ["Just Married", "Mr & Mrs", "Happily Ever After", "Thank You", "Let's Celebrate"],
          [bg_solid("#fffaf5"), bg_grad("#fffaf5", "#ffd6e7"), bg_pat("hearts", "#fffaf5", "#ffd6e7")], text_color="#8a6d1d",
          border={"widthMm": 2.5, "color": "#ffffff", "outlines": [{"widthMm": 0.6, "color": "#c9a227", "gapMm": 0.6}], "smoothing": 0.6}),
    theme("minimal", 16, "Minimalist Labels", "Clean labels and badges for names, jars and school supplies.", ["#2d2140", "#adb5bd", "#f8f9fa", "#ffffff"], "Poppins",
          ["badge_label", "badge_tag", "shape_circle", "badge_scallop"], {}, ["frame_square_dots"],
          ["Name", "Thank You", "Handmade", "Property of", "Custom text"],
          [bg_solid("#ffffff"), bg_solid("#f1f3f5"), bg_pat("grid", "#ffffff", "#e9ecef")], shapes=("rounded", "rect", "circle", "oval", "silhouette"),
          border={"widthMm": 1.5, "color": "#ffffff", "outlines": [{"widthMm": 0.5, "color": "#2d2140", "gapMm": 0}], "smoothing": 0.3}, sizes=(30, 45, 60)),
    theme("hearts", 17, "Hearts and Friendship", "Hearts, wings and sweet sayings for friends and family.", ["#ff4f8b", "#ffafcc", "#cdb4db", "#fff0f6"], "Pacifico",
          ["heart_basic", "hearts_double", "heart_outline", "heart_wings", "balloon_heart", "flower_pink"], {"Heart glasses": ["sunglasses_heart"]},
          ["frame_ring_hearts"], ["Best Friends", "Love You", "Besties", "Thank You", "XOXO"],
          [bg_pat("hearts", "#ffd6e7", "#ffffff"), bg_grad("#fff0f6", "#ffafcc"), bg_solid("#ffffff")], text_color="#c9184a"),
    theme("rainbow", 18, "Rainbow and Pastel", "Rainbows, clouds and stars in soft pastels.", ["#a2d2ff", "#ffafcc", "#cdb4db", "#fdfcdc"], "Chewy",
          ["rainbow", "cloud_cute", "star_face", "balloon_number", "sparkles", "shape_blob"], {"Unicorn": ["unicorn_horn"]},
          ["frame_scallop"], ["Dream Big", "Hello Sunshine", "Be Kind", "Happy Day"],
          [bg_grad("#ffafcc", "#a2d2ff", 120), bg_pat("dots", "#fdfcdc", "#cdb4db"), bg_solid("#fdfcdc")], text_color="#7209b7"),
    theme("retro", 19, "Retro Pop", "Bold Memphis shapes, zigzags and starbursts.", ["#ff4f8b", "#ffd166", "#06d6a0", "#fff8e1"], "Bangers",
          ["shape_squiggle", "shape_zigzag", "shape_dots", "shape_triangle", "badge_burst", "lightning", "pow_burst"], {"Cool shades": ["sunglasses_classic"]},
          ["frame_square_dots"], ["Groovy", "Rad!", "Totally Awesome", "Far Out"],
          [bg_pat("zigzag", "#ffd166", "#ff4f8b"), bg_pat("checks", "#fff8e1", "#06d6a0"), bg_grad("#ff4f8b", "#ffd166")], text_color="#2d2140",
          border={"widthMm": 3.0, "color": "#ffffff", "outlines": [{"widthMm": 1.2, "color": "#2d2140", "gapMm": 0}], "smoothing": 0.4}),
    theme("custom", 20, "Custom Theme", "Start from scratch: pick your own colours, fonts and decorations.", ["#6c63ff", "#ff6584", "#ffd166", "#ffffff"], "Poppins",
          ["star_basic", "heart_basic", "sparkles", "shape_circle", "badge_scallop"], {}, ["frame_ring_stars"], ["Custom text"],
          [bg_solid("#ffffff"), bg_grad("#6c63ff", "#ff6584")]),
]


def main():
    for d in (DEC, FRM, PAT):
        d.mkdir(parents=True, exist_ok=True)
        for old in d.glob("*.svg"):
            old.unlink()
    dec_index, frame_index = [], []
    ids = set()
    for a in ASSETS:
        assert a["id"] not in ids, a["id"]
        ids.add(a["id"])
        target_dir = FRM if a["frame"] else DEC
        fname = f"{a['id']}.svg"
        text = svg(a["w"], a["h"], a["body"])
        ET.fromstring(text)  # fail the build on malformed XML
        (target_dir / fname).write_text(text, encoding="utf-8")
        defaults = {}
        for slot in a["recolor"]:
            m = re.search(rf'fill="(#[0-9a-fA-F]{{6}})" data-recolor="{slot}"', a["body"]) or re.search(
                rf'stroke="(#[0-9a-fA-F]{{6}})"[^>]*data-recolor="{slot}"', a["body"])
            if m:
                defaults[slot] = m.group(1)
        entry = {"id": a["id"], "name": a["name"], "category": a["category"], "tags": a["tags"], "kind": "svg",
                 "file": fname, "aspect": round(a["w"] / a["h"], 4), "recolor": a["recolor"], "defaultColors": {},
                 "paletteDefaults": defaults, "anchor": a["anchor"], "license": LICENSE, "author": "Offline Sticker Studio"}
        (frame_index if a["frame"] else dec_index).append(entry)
    (DEC / "index.json").write_text(json.dumps(dec_index, indent=1), encoding="utf-8")
    (FRM / "index.json").write_text(json.dumps(frame_index, indent=1), encoding="utf-8")
    pat_index = []
    for pid, name, body in PATTERNS:
        (PAT / f"{pid}.svg").write_text(pattern_svg(body), encoding="utf-8")
        pat_index.append({"id": pid, "name": name, "file": f"{pid}.svg", "license": LICENSE})
    (PAT / "index.json").write_text(json.dumps(pat_index, indent=1), encoding="utf-8")
    for t in THEMES:
        for ref in t["decorations"] + t["frames"] + [x for v in t["accessorySets"].values() for x in v]:
            assert ref in ids, f"theme {t['id']} references missing asset {ref}"
        d = THM / t["id"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "theme.json").write_text(json.dumps(t, indent=1), encoding="utf-8")
    print(f"{len(dec_index)} decorations, {len(frame_index)} frames, {len(pat_index)} patterns, {len(THEMES)} themes")


if __name__ == "__main__":
    main()
