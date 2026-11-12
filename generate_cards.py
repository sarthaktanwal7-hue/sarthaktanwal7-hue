#!/usr/bin/env python3
"""
generate_cards.py — Sarthak Tanwal's GitHub Profile SVG Card Generator
=======================================================================
Generates animated SVG cards for the GitHub profile README.

Usage:
    python3 generate_cards.py          # animated mode
    STATIC=1 python3 generate_cards.py # static/final-frame mode (for screenshots)

Cards produced in cards/:
    hero.svg          — name + tagline + real GitHub avatar
    links.svg         — three linked tiles (GitHub / LinkedIn / Email)
    stats.svg         — contributions chart + streak / active days / busiest day
    repo_<name>.svg   — one card per featured repo
    contrib_graph.svg — contribution bar graph in brand colour

Requirements:
    pip install fonttools brotli
    Avatar at: data/avatar.jpg  (fetched by CI or fetch_avatar.py)
    Data at:   data/contributions.json
"""

import base64, json, math, os, pathlib, sys, textwrap, xml.etree.ElementTree as ET

# ── Config ──────────────────────────────────────────────────────────────────
STATIC    = os.environ.get("STATIC", "0") == "1"
ROOT      = pathlib.Path(__file__).parent
CARDS_DIR = ROOT / "cards"
DATA_FILE = ROOT / "data" / "contributions.json"
AVATAR_FILE     = ROOT / "data" / "avatar.jpg"
AVATAR_WEBP     = ROOT / "data" / "avatar.webp"   # pre-processed circular portrait


def prepare_avatar(src: pathlib.Path, size: int = 460) -> pathlib.Path:
    """
    Convert any source avatar into a crisp circular WebP using Pillow:
      - Lanczos upscale to `size`×`size`
      - Unsharp-mask sharpening to remove JPEG softness
      - 4× super-sampled circular alpha mask (anti-aliased edge)
    Returns path to the WebP, caching if already fresh.
    """
    out = AVATAR_WEBP
    # Return cached version if it's newer than the source
    if out.exists() and src.exists() and out.stat().st_mtime >= src.stat().st_mtime:
        return out

    try:
        from PIL import Image, ImageFilter, ImageDraw as ID
        import io
    except ImportError:
        return src  # Pillow not installed — fall back to raw JPEG

    img = Image.open(src).convert("RGBA")
    img = img.resize((size, size), Image.LANCZOS)
    img = img.filter(ImageFilter.UnsharpMask(radius=1.0, percent=110, threshold=2))

    # 4× super-sampled circle mask for smooth anti-aliased edge
    ms = size * 4
    mask = Image.new("L", (ms, ms), 0)
    ID.Draw(mask).ellipse((0, 0, ms, ms), fill=255)
    mask = mask.resize((size, size), Image.LANCZOS)

    result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    result.paste(img, (0, 0), mask)

    buf = io.BytesIO()
    result.save(buf, format="WEBP", quality=92, method=4)
    buf.seek(0)
    out.write_bytes(buf.read())
    return out

CARDS_DIR.mkdir(exist_ok=True)

# ── Brand colours ────────────────────────────────────────────────────────────
BG       = "#05060f"
PURPLE   = "#8b7bff"
CYAN     = "#4fd1ff"
TEXT     = "#eef1ff"
MUTED    = "#9ea8c8"
CARD_BG  = "#0d0e1f"
BORDER   = "#2a2650"

# ── Helpers ──────────────────────────────────────────────────────────────────
def b64_file(path: pathlib.Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()

def encode_font(ttf_path: str, text: str) -> str:
    """Subset a TTF to only the glyphs in `text`, return base64 WOFF2 data URI."""
    import tempfile, subprocess
    chars = "".join(sorted(set(text)))
    uni_list = ",".join(f"U+{ord(c):04X}" for c in chars if ord(c) > 31)
    if not uni_list:
        return ""
    with tempfile.NamedTemporaryFile(suffix=".woff2", delete=False) as tf:
        out = tf.name

    pyftsubset = pathlib.Path.home() / "Library/Python/3.9/bin/pyftsubset"
    if not pyftsubset.exists():
        # Fallback: try system path
        import shutil
        pyftsubset_path = shutil.which("pyftsubset")
        if pyftsubset_path:
            pyftsubset = pathlib.Path(pyftsubset_path)
        else:
            return ""  # font embedding skipped

    result = subprocess.run(
        [str(pyftsubset), ttf_path,
         f"--unicodes={uni_list}",
         "--flavor=woff2",
         f"--output-file={out}"],
        capture_output=True
    )
    if result.returncode != 0 or not pathlib.Path(out).exists():
        return ""
    data = pathlib.Path(out).read_bytes()
    pathlib.Path(out).unlink(missing_ok=True)
    return f"data:font/woff2;base64,{base64.b64encode(data).decode()}"

# ── Shared text corpus for font subsetting ───────────────────────────────────
ALL_TEXT = (
    "Sarthak Tanwal CS & AI Student Aspiring Software Developer "
    "Always curious always experimenting always building "
    "GitHub LinkedIn Email stars forks "
    "Contributions Streak Active Days Busiest Day "
    "SPAR Smart Personal AI Robotic Companion "
    "Robo Sumo autonomous competitive "
    "smart services backend Python C++ SVG "
    "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec "
    "0123456789 "
)

# Try to subset fonts; fall back to system-safe generic stack
FONT_REGULAR_URI = ""
FONT_BOLD_URI    = ""
FONT_STACK = "'Space Grotesk', 'Segoe UI', system-ui, sans-serif"

REGULAR_TTF = "/tmp/SpaceGrotesk-VF.ttf"
BOLD_TTF    = "/tmp/SpaceGrotesk-Bold.ttf"

if pathlib.Path(REGULAR_TTF).exists() and pathlib.Path(REGULAR_TTF).stat().st_size > 10000:
    FONT_REGULAR_URI = encode_font(REGULAR_TTF, ALL_TEXT)
if pathlib.Path(BOLD_TTF).exists() and pathlib.Path(BOLD_TTF).stat().st_size > 10000:
    FONT_BOLD_URI    = encode_font(BOLD_TTF, ALL_TEXT)

def font_style_block() -> str:
    """Return <style> content with @font-face declarations if URIs available."""
    parts = []
    if FONT_REGULAR_URI:
        parts.append(f"""@font-face {{
  font-family: 'Space Grotesk';
  font-weight: 400;
  src: url('{FONT_REGULAR_URI}') format('woff2');
}}""")
    if FONT_BOLD_URI:
        parts.append(f"""@font-face {{
  font-family: 'Space Grotesk';
  font-weight: 700;
  src: url('{FONT_BOLD_URI}') format('woff2');
}}""")
    return "\n".join(parts)

# ── Animation helpers ─────────────────────────────────────────────────────────
def anim_css(delay: float = 0.0, reduced_motion: bool = False) -> str:
    """Return CSS keyframe animations. STATIC=1 skips all animations."""
    if STATIC:
        return ""
    rm_rule = """
@media (prefers-reduced-motion: reduce) {
  * { animation: none !important; transition: none !important; }
}"""
    return f"""
@keyframes fadeUp {{
  from {{ opacity: 0; transform: translateY(16px); }}
  to   {{ opacity: 1; transform: translateY(0); }}
}}
@keyframes glow {{
  0%, 100% {{ opacity: 0.7; }}
  50%       {{ opacity: 1.0; }}
}}
@keyframes shimmer {{
  0%   {{ stop-color: {PURPLE}; }}
  50%  {{ stop-color: {CYAN};   }}
  100% {{ stop-color: {PURPLE}; }}
}}
@keyframes barGrow {{
  from {{ transform: scaleY(0); transform-origin: bottom; }}
  to   {{ transform: scaleY(1); transform-origin: bottom; }}
}}
{rm_rule}
"""

def smil_fade(el: ET.Element, delay: float, duration: float = 0.6) -> None:
    """Attach SMIL animate to fade-in an element (works in GitHub's SVG renderer)."""
    if STATIC:
        return
    anim = ET.SubElement(el, "animate",
        attributeName="opacity",
        from_="0", to="1",
        begin=f"{delay:.2f}s", dur=f"{duration:.2f}s",
        fill="freeze",
        calcMode="spline",
        keySplines="0.16 1 0.3 1",
        keyTimes="0;1"
    )
    # Set initial opacity low so it starts invisible
    el.set("opacity", "0" if not STATIC else "1")

def smil_slide_up(el: ET.Element, delay: float, dy: float = 16, duration: float = 0.6) -> None:
    if STATIC:
        return
    el.set("opacity", "0")
    anim_op = ET.SubElement(el, "animate",
        attributeName="opacity",
        from_="0", to="1",
        begin=f"{delay:.2f}s", dur=f"{duration:.2f}s",
        fill="freeze"
    )
    anim_tr = ET.SubElement(el, "animateTransform",
        attributeName="transform",
        type="translate",
        from_=f"0,{dy}", to="0,0",
        begin=f"{delay:.2f}s", dur=f"{duration:.2f}s",
        fill="freeze",
        additive="sum"
    )

# ── SVG root factory ──────────────────────────────────────────────────────────
def make_svg(w: int, h: int) -> ET.Element:
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
    svg = ET.Element("svg",
        xmlns="http://www.w3.org/2000/svg",
        width=str(w), height=str(h),
        viewBox=f"0 0 {w} {h}",
        fill="none"
    )
    return svg

def add_defs_gradient(svg: ET.Element, grad_id: str = "headGrad") -> None:
    defs = ET.SubElement(svg, "defs")
    lg = ET.SubElement(defs, "linearGradient", id=grad_id,
        x1="0", y1="0", x2="1", y2="0")
    s1 = ET.SubElement(lg, "stop", offset="0%")
    s1.set("stop-color", "#ffffff")
    s2 = ET.SubElement(lg, "stop", offset="100%")
    s2.set("stop-color", CYAN)
    if not STATIC:
        ET.SubElement(s2, "animate",
            attributeName="stop-color",
            values=f"{CYAN};{PURPLE};{CYAN}",
            dur="4s", repeatCount="indefinite")
    return defs

def card_bg(svg: ET.Element, w: int, h: int, rx: int = 18) -> None:
    """Draw the card background rect + border."""
    ET.SubElement(svg, "rect",
        width=str(w), height=str(h), rx=str(rx),
        fill=CARD_BG, stroke=BORDER, **{"stroke-width": "1.5"})

def add_style(svg: ET.Element, extra: str = "") -> None:
    style = ET.SubElement(svg, "style")
    style.text = font_style_block() + anim_css() + extra

def save(svg: ET.Element, path: pathlib.Path) -> None:
    tree = ET.ElementTree(svg)
    ET.indent(tree, space="  ")
    with open(path, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        tree.write(f, encoding="unicode", xml_declaration=False)
    print(f"  ✓  {path.name}")

# ════════════════════════════════════════════════════════════════════════════════
# CARD 1 — HERO  (high-quality circular portrait)
# ════════════════════════════════════════════════════════════════════════════════
def card_hero() -> None:
    W, H    = 820, 220
    AV_SIZE = 170          # avatar diameter in SVG units
    AV_CX   = 24 + AV_SIZE // 2
    AV_CY   = H // 2

    svg = make_svg(W, H)

    # ── defs ─────────────────────────────────────────────────────────────────
    defs = ET.SubElement(svg, "defs")

    # Name gradient
    lg_name = ET.SubElement(defs, "linearGradient", id="nameGrad",
        x1="0", y1="0", x2="1", y2="0")
    ET.SubElement(lg_name, "stop", offset="0%").set("stop-color", "#ffffff")
    s2 = ET.SubElement(lg_name, "stop", offset="100%")
    s2.set("stop-color", CYAN)
    if not STATIC:
        ET.SubElement(s2, "animate",
            attributeName="stop-color",
            values=f"{CYAN};{PURPLE};{CYAN}",
            dur="4s", repeatCount="indefinite")

    # Ring gradient
    lg_ring = ET.SubElement(defs, "linearGradient", id="ringGrad",
        x1="0", y1="0", x2="1", y2="1")
    ET.SubElement(lg_ring, "stop", offset="0%").set("stop-color", PURPLE)
    ET.SubElement(lg_ring, "stop", offset="100%").set("stop-color", CYAN)

    # Radial glow behind avatar
    rg = ET.SubElement(defs, "radialGradient", id="avGlow",
        cx=str(AV_CX), cy=str(AV_CY),
        r=str(AV_SIZE // 2 + 40),
        gradientUnits="userSpaceOnUse")
    ET.SubElement(rg, "stop", offset="0%").set("stop-color", PURPLE)
    ET.SubElement(rg, "stop", offset="100%").set("stop-color", BG)

    # Clip path (SVG clip as safety net — the WebP itself is already circular)
    clip = ET.SubElement(defs, "clipPath", id="avatarClip")
    ET.SubElement(clip, "circle",
        cx=str(AV_CX), cy=str(AV_CY), r=str(AV_SIZE // 2))

    # Inline styles
    style = ET.SubElement(svg, "style")
    style.text = anim_css() + """
@media (prefers-reduced-motion:reduce) {
  * { animation:none!important; }
}"""

    card_bg(svg, W, H)

    # Soft glow halo behind avatar
    ET.SubElement(svg, "circle",
        cx=str(AV_CX), cy=str(AV_CY),
        r=str(AV_SIZE // 2 + 40),
        fill="url(#avGlow)", opacity="0.22")

    # Gradient ring
    ring = ET.SubElement(svg, "circle",
        cx=str(AV_CX), cy=str(AV_CY),
        r=str(AV_SIZE // 2 + 4),
        fill="none", stroke="url(#ringGrad)", **{"stroke-width": "3.5"})
    if not STATIC:
        ET.SubElement(ring, "animate",
            attributeName="stroke-opacity",
            values="0.5;1;0.5", dur="2.8s", repeatCount="indefinite")

    # ── Avatar — prefer pre-processed circular WebP, fall back to raw JPEG ───
    av_src = prepare_avatar(AVATAR_FILE) if AVATAR_FILE.exists() else AVATAR_WEBP
    if av_src.exists():
        mime = "image/webp" if av_src.suffix == ".webp" else "image/jpeg"
        ET.SubElement(svg, "image",
            x=str(AV_CX - AV_SIZE // 2),
            y=str(AV_CY - AV_SIZE // 2),
            width=str(AV_SIZE), height=str(AV_SIZE),
            **{
                "clip-path": "url(#avatarClip)",
                "href": f"data:{mime};base64,{b64_file(av_src)}",
                "preserveAspectRatio": "xMidYMid slice",
                "image-rendering": "auto",
            })
    else:
        # Initials fallback
        ET.SubElement(svg, "circle",
            cx=str(AV_CX), cy=str(AV_CY),
            r=str(AV_SIZE // 2), fill="#1a1b2e")
        ET.SubElement(svg, "text",
            x=str(AV_CX), y=str(AV_CY + 14),
            **{"text-anchor": "middle", "font-size": "52",
               "fill": PURPLE, "font-family": FONT_STACK}).text = "ST"

    # ── Text group (slide-up on load) ────────────────────────────────────────
    tg = ET.SubElement(svg, "g")
    smil_slide_up(tg, delay=0.1)

    tx = AV_CX + AV_SIZE // 2 + 28   # text starts right of avatar

    # Name
    ET.SubElement(tg, "text",
        x=str(tx), y="82",
        **{"font-family": FONT_STACK, "font-size": "38",
           "font-weight": "700", "fill": "url(#nameGrad)"}).text = "Sarthak Tanwal"

    # Cyan rule
    ET.SubElement(tg, "rect",
        x=str(tx), y="92", width="265", height="1.5",
        fill=CYAN, opacity="0.4", rx="1")

    # Title
    ET.SubElement(tg, "text",
        x=str(tx), y="118",
        **{"font-family": FONT_STACK, "font-size": "15",
           "font-weight": "500", "fill": CYAN}).text = \
        "CS & AI Student  ·  Aspiring Software Developer"

    # Tagline
    ET.SubElement(tg, "text",
        x=str(tx), y="150",
        **{"font-family": FONT_STACK, "font-size": "13.5",
           "font-weight": "400", "fill": MUTED,
           "font-style": "italic"}).text = \
        "Always curious, always experimenting, always building. 🚀"

    # Sparkle dots
    if not STATIC:
        for i, (sx, sy) in enumerate([(730,22),(762,44),(745,70),(775,92),(755,118),(785,142),(740,162)]):
            dot = ET.SubElement(svg, "circle",
                cx=str(sx), cy=str(sy), r="2",
                fill=PURPLE if i % 2 == 0 else CYAN, opacity="0")
            ET.SubElement(dot, "animate",
                attributeName="opacity", values="0;1;0",
                begin=f"{0.3 + i*0.22:.2f}s",
                dur=f"{1.4 + i*0.1:.1f}s",
                repeatCount="indefinite")
            ET.SubElement(dot, "animate",
                attributeName="r", values="1.5;2.8;1.5",
                begin=f"{0.3 + i*0.22:.2f}s",
                dur=f"{1.4 + i*0.1:.1f}s",
                repeatCount="indefinite")

    save(svg, CARDS_DIR / "hero.svg")

# ════════════════════════════════════════════════════════════════════════════════
# CARD 2 — LINKS (three tiles)
# ════════════════════════════════════════════════════════════════════════════════
def card_links() -> None:
    W, H = 800, 80
    svg = make_svg(W, H)
    add_defs_gradient(svg, "linkGrad")
    add_style(svg)
    card_bg(svg, W, H)

    tiles = [
        ("⌥  GitHub",   "https://github.com/sarthaktanwal7-hue",                       PURPLE),
        ("◈  LinkedIn", "https://www.linkedin.com/in/sarthak-t-855243423",              CYAN),
        ("✉  Email",    "mailto:sarthaktanwal7@gmail.com",                              "#ff9ff3"),
    ]

    tile_w = (W - 48) // 3
    for i, (label, href, col) in enumerate(tiles):
        x = 16 + i * (tile_w + 8)
        g = ET.SubElement(svg, "g")
        smil_slide_up(g, delay=0.3 + i * 0.15)

        # Tile background
        ET.SubElement(g, "rect",
            x=str(x), y="8", width=str(tile_w), height="64",
            rx="12", fill="rgba(255,255,255,0.04)",
            stroke=BORDER, **{"stroke-width": "1"})

        # Label
        a = ET.SubElement(g, "a", href=href, target="_blank")
        txt = ET.SubElement(a, "text",
            x=str(x + tile_w // 2), y="48",
            **{"text-anchor": "middle",
               "font-family": FONT_STACK,
               "font-size": "15", "font-weight": "600",
               "fill": col})
        txt.text = label

    save(svg, CARDS_DIR / "links.svg")

# ════════════════════════════════════════════════════════════════════════════════
# CARD 3 — STATS (chart + streak badges)
# ════════════════════════════════════════════════════════════════════════════════
def card_stats(data: dict) -> None:
    W, H = 800, 240
    svg = make_svg(W, H)
    defs = ET.SubElement(svg, "defs")
    
    # Bar gradient
    bg_grad = ET.SubElement(defs, "linearGradient", id="barGrad",
        x1="0", y1="0", x2="0", y2="1")
    ET.SubElement(bg_grad, "stop", offset="0%").set("stop-color", PURPLE)
    ET.SubElement(bg_grad, "stop", offset="100%").set("stop-color", CYAN)

    add_style(svg)
    card_bg(svg, W, H)

    monthly = data.get("monthly", [])
    max_val  = max((m["count"] for m in monthly), default=1) or 1
    
    chart_x  = 32
    chart_y  = 60
    chart_w  = 490
    chart_h  = 150
    n        = len(monthly)
    bar_gap  = 4
    bar_w    = (chart_w - bar_gap * (n - 1)) // n

    # Section title
    tg = ET.SubElement(svg, "g")
    smil_slide_up(tg, delay=0.2)
    t = ET.SubElement(tg, "text",
        x=str(chart_x), y="35",
        **{"font-family": FONT_STACK, "font-size": "14",
           "font-weight": "700", "fill": TEXT,
           "letter-spacing": "1"})
    t.text = "CONTRIBUTIONS"

    # Bars
    for i, m in enumerate(monthly):
        bx    = chart_x + i * (bar_w + bar_gap)
        count = m["count"]
        bh    = int((count / max_val) * chart_h) if count else 3
        by    = chart_y + chart_h - bh

        bar_g = ET.SubElement(svg, "g")
        smil_slide_up(bar_g, delay=0.4 + i * 0.04)

        bar = ET.SubElement(bar_g, "rect",
            x=str(bx), y=str(by),
            width=str(bar_w), height=str(bh),
            rx="3", fill=f"url(#barGrad)" if count else BORDER)
        if not STATIC and count:
            ET.SubElement(bar, "animate",
                attributeName="height",
                from_="0", to=str(bh),
                begin=f"{0.5 + i*0.04:.2f}s", dur="0.6s",
                fill="freeze")
            ET.SubElement(bar, "animate",
                attributeName="y",
                from_=str(chart_y + chart_h), to=str(by),
                begin=f"{0.5 + i*0.04:.2f}s", dur="0.6s",
                fill="freeze")

        # Month label
        lbl = ET.SubElement(bar_g, "text",
            x=str(bx + bar_w // 2),
            y=str(chart_y + chart_h + 16),
            **{"text-anchor": "middle",
               "font-family": FONT_STACK,
               "font-size": "10", "fill": MUTED})
        lbl.text = m["month"][:3]

    # ── Stat badges (right side) ─────────────────────────────────────────
    badges = [
        ("🔥", "Current Streak", f"{data.get('streak', 0)} days",          0.6),
        ("📅", "Active Days",    f"{data.get('active_days', 0)} days",      0.75),
        ("⚡", "Busiest Day",    data.get('busiest_day', '—'),              0.9),
    ]
    bx0 = chart_x + chart_w + 24
    for j, (icon, label, val, delay) in enumerate(badges):
        by0 = 60 + j * 65
        bg = ET.SubElement(svg, "g")
        smil_slide_up(bg, delay=delay)

        ET.SubElement(bg, "rect",
            x=str(bx0), y=str(by0),
            width="230", height="52",
            rx="10", fill="rgba(139,123,255,0.08)",
            stroke=BORDER, **{"stroke-width": "1"})

        # Icon + label
        ET.SubElement(bg, "text",
            x=str(bx0 + 14), y=str(by0 + 20),
            **{"font-family": FONT_STACK, "font-size": "11",
               "fill": MUTED}).text = f"{icon}  {label}"
        # Value
        ET.SubElement(bg, "text",
            x=str(bx0 + 14), y=str(by0 + 40),
            **{"font-family": FONT_STACK, "font-size": "18",
               "font-weight": "700", "fill": CYAN}).text = val

    save(svg, CARDS_DIR / "stats.svg")

# ════════════════════════════════════════════════════════════════════════════════
# CARD 4 — REPO CARDS
# ════════════════════════════════════════════════════════════════════════════════
LANG_COLORS = {
    "Python": "#3572A5", "C++": "#f34b7d", "JavaScript": "#f1e05a",
    "TypeScript": "#3178c6", "SVG": "#8b7bff", "HTML": "#e34c26",
    "Shell": "#89e051", "C": "#555555",
}

def card_repo(repo: dict, index: int) -> None:
    W, H = 800, 120
    svg = make_svg(W, H)
    add_defs_gradient(svg, f"rGrad{index}")
    add_style(svg)
    card_bg(svg, W, H)

    delay = 0.2 + index * 0.15
    g = ET.SubElement(svg, "g")
    smil_slide_up(g, delay=delay)

    # Repo icon
    ET.SubElement(g, "rect",
        x="20", y="20", width="52", height="52",
        rx="12", fill="rgba(139,123,255,0.12)",
        stroke=PURPLE, **{"stroke-width": "1"})
    t_icon = ET.SubElement(g, "text",
        x="46", y="52",
        **{"text-anchor": "middle", "font-size": "26",
           "font-family": FONT_STACK})
    # Pick emoji by language
    icon_map = {"Python":"🐍","C++":"⚡","JavaScript":"🌐","TypeScript":"🔷","SVG":"✨","HTML":"🌐"}
    t_icon.text = icon_map.get(repo.get("language",""),"📁")

    # Title as link
    a = ET.SubElement(g, "a",
        href=repo.get("url","#"), target="_blank")
    ET.SubElement(a, "text",
        x="88", y="44",
        **{"font-family": FONT_STACK, "font-size": "17",
           "font-weight": "700", "fill": TEXT}).text = repo["name"]

    # Description
    desc = repo.get("description","") or ""
    # Wrap to ~80 chars
    lines = textwrap.wrap(desc, 75) or [""]
    for li, line in enumerate(lines[:2]):
        ET.SubElement(g, "text",
            x="88", y=str(66 + li * 17),
            **{"font-family": FONT_STACK, "font-size": "13",
               "fill": MUTED}).text = line

    # Language pill
    lang = repo.get("language","")
    lang_col = LANG_COLORS.get(lang, MUTED)
    if lang:
        ET.SubElement(g, "circle",
            cx="88", cy="97", r="5", fill=lang_col)
        ET.SubElement(g, "text",
            x="98", y="102",
            **{"font-family": FONT_STACK, "font-size": "12",
               "fill": MUTED}).text = lang

    # Stars & forks
    stars = repo.get("stars", 0)
    forks = repo.get("forks", 0)
    ET.SubElement(g, "text",
        x="680", y="102",
        **{"font-family": FONT_STACK, "font-size": "12",
           "fill": MUTED, "text-anchor": "end"}).text = f"★ {stars}  ⑂ {forks}"

    name_safe = repo["name"].replace("/","-").replace(" ","-")
    save(svg, CARDS_DIR / f"repo_{name_safe}.svg")

# ════════════════════════════════════════════════════════════════════════════════
# CARD 5 — CONTRIBUTION GRAPH (full-year grid)
# ════════════════════════════════════════════════════════════════════════════════
def card_contrib_graph(data: dict) -> None:
    """
    Renders a simplified contribution grid — 12 months × up to 5 rows of weeks.
    Uses brand purple palette.
    """
    W, H = 800, 140
    svg = make_svg(W, H)
    defs = ET.SubElement(svg, "defs")

    add_style(svg)
    card_bg(svg, W, H)

    monthly = data.get("monthly", [])

    # Title
    tg = ET.SubElement(svg, "g")
    smil_slide_up(tg, delay=0.3)
    ET.SubElement(tg, "text",
        x="20", y="28",
        **{"font-family": FONT_STACK, "font-size": "11",
           "fill": MUTED, "letter-spacing": "1.5"}).text = "CONTRIBUTION GRAPH"

    cell = 11
    gap  = 3
    months_per_row = 12
    start_x = 20
    start_y = 42

    for mi, m in enumerate(monthly):
        count = m["count"]
        # For each month simulate ~4 weeks of activity
        for week in range(4):
            for day in range(7):
                cx = start_x + mi * (cell * 4 + gap * 4 + 6) + week * (cell + gap)
                cy = start_y + day * (cell + gap)

                # Determine fill intensity
                # Distribute month count across 28 days roughly
                day_count = count / 28
                intensity = min(day_count * 3, 1.0)
                # Add slight randomness for realism
                import random
                random.seed(mi * 100 + week * 10 + day)
                intensity = max(0, min(1.0, intensity + (random.random() - 0.5) * 0.4))

                if intensity < 0.05:
                    fill = "#161b22"  # GitHub empty cell color
                else:
                    # Interpolate between border-dark and purple
                    r1, g1, b1 = 0x2a, 0x26, 0x50  # BORDER dark
                    r2, g2, b2 = 0x8b, 0x7b, 0xff  # PURPLE
                    r = int(r1 + (r2 - r1) * intensity)
                    g_ = int(g1 + (g2 - g1) * intensity)
                    b = int(b1 + (b2 - b1) * intensity)
                    fill = f"#{r:02x}{g_:02x}{b:02x}"

                rect = ET.SubElement(svg, "rect",
                    x=str(cx), y=str(cy),
                    width=str(cell), height=str(cell),
                    rx="2", fill=fill)
                if not STATIC and intensity > 0.1:
                    ET.SubElement(rect, "animate",
                        attributeName="opacity",
                        from_="0", to="1",
                        begin=f"{0.4 + mi*0.05:.2f}s",
                        dur="0.4s", fill="freeze")
                    rect.set("opacity", "0")

        # Month label
        lbl_x = start_x + mi * (cell * 4 + gap * 4 + 6)
        ET.SubElement(svg, "text",
            x=str(lbl_x), y=str(start_y + 7 * (cell + gap) + 12),
            **{"font-family": FONT_STACK, "font-size": "9",
               "fill": MUTED}).text = m["month"][:1]

    save(svg, CARDS_DIR / "contrib_graph.svg")

# ════════════════════════════════════════════════════════════════════════════════
# README builder
# ════════════════════════════════════════════════════════════════════════════════
def build_readme(data: dict) -> str:
    repos = data.get("repos", [])
    repo_imgs = "\n".join(
        f'<img src="cards/repo_{r["name"].replace("/","-").replace(" ","-")}.svg" width="100%" alt="{r["name"]} repo card"/>'
        for r in repos
    )

    return f"""\
<!-- AUTO-GENERATED by generate_cards.py — do not edit directly -->
<div align="center">

<img src="cards/hero.svg" width="100%" alt="Sarthak Tanwal — hero card"/>

<img src="cards/links.svg" width="100%" alt="Links — GitHub · LinkedIn · Email"/>

<img src="cards/stats.svg" width="100%" alt="Contribution statistics"/>

{repo_imgs}

<img src="cards/contrib_graph.svg" width="100%" alt="Contribution graph"/>

---

<sub>Cards refresh daily via GitHub Actions · Built with Python + SVG</sub>

</div>
"""

# ════════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════════
def main() -> None:
    print(f"{'[STATIC]' if STATIC else '[ANIMATED]'} Generating SVG cards...")

    # Copy avatar to data/ if it was downloaded to /tmp
    if not AVATAR_FILE.exists() and pathlib.Path("/tmp/avatar.png").exists():
        import shutil
        shutil.copy("/tmp/avatar.png", AVATAR_FILE)
        print("  ↳ Copied avatar from /tmp/avatar.png")

    # Load data
    data = json.loads(DATA_FILE.read_text()) if DATA_FILE.exists() else {}

    card_hero()
    card_links()
    card_stats(data)

    for i, repo in enumerate(data.get("repos", [])):
        card_repo(repo, i)

    card_contrib_graph(data)

    # Write README
    readme_path = ROOT / "README.md"
    readme_path.write_text(build_readme(data))
    print(f"  ✓  README.md")

    print("\nDone! ✅")
    print(f"Cards in: {CARDS_DIR}/")

if __name__ == "__main__":
    main()
