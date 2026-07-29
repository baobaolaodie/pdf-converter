"""preview.py — 缩略图加载与渲染"""

from PIL import Image, ImageTk, ImageDraw, ImageFont
import fitz  # PyMuPDF

from constants import (
    Page, CELL_W, THUMB_MAX,
    ORIENT_NAMES, ORIENT_COLORS,
)


def _load_base_image(pg: Page) -> Image.Image | None:
    """加载页面原始图像（不做旋转/缩放），用于后续合成预览。"""
    try:
        if pg.is_pdf:
            doc = fitz.open(pg.source_path)
            page = doc[pg.page_idx]
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            doc.close()
            return img
        else:
            img = Image.open(pg.source_path)
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
            return img
    except Exception:
        return None


# 预览缓存：避免重复渲染相同参数的缩略图
_preview_cache: dict[tuple, Image.Image] = {}
_font_small = ImageFont.load_default(size=11)
_font_tiny = ImageFont.load_default(size=9)


def render_preview(pg: Page, base_img: Image.Image | None,
                   paper_w_mm: float, paper_h_mm: float) -> Image.Image | None:
    if base_img is None:
        return None

    cache_key = (id(base_img), pg.orientation, pg.scale)
    if cache_key in _preview_cache:
        return _preview_cache[cache_key]

    pw, ph = paper_w_mm, paper_h_mm
    img_w, img_h = base_img.size

    if pg.orientation == "auto":
        use_landscape = (pg.orig_w > pg.orig_h) if pg.is_pdf else (img_w > img_h)
        rotate = False
    else:
        use_landscape = (pg.orientation == "landscape")
        page_is_land = (pg.orig_w > pg.orig_h) if pg.is_pdf else (img_w > img_h)
        rotate = (use_landscape != page_is_land)

    if use_landscape:
        frame_w_mm, frame_h_mm = max(pw, ph), min(pw, ph)
    else:
        frame_w_mm, frame_h_mm = min(pw, ph), max(pw, ph)

    img = base_img.rotate(-90, expand=True) if rotate else base_img
    img_w, img_h = img.size

    canvas = Image.new("RGBA", (CELL_W, THUMB_MAX + 30), (240, 240, 240, 255))
    draw = ImageDraw.Draw(canvas)

    frame_ratio = frame_w_mm / frame_h_mm
    avail_w, avail_h = CELL_W - 16, THUMB_MAX - 10
    if frame_ratio > avail_w / avail_h:
        fw = avail_w
        fh = int(fw / frame_ratio)
    else:
        fh = avail_h
        fw = int(fh * frame_ratio)

    fx0 = (CELL_W - fw) // 2
    fy0 = (THUMB_MAX - fh) // 2 + 2
    draw.rectangle([fx0, fy0, fx0 + fw, fy0 + fh], fill="white", outline="#888", width=1)

    scale_factor = pg.scale / 100.0
    inner_w = max(1, int((fw - 6) * scale_factor))
    inner_h = max(1, int((fh - 6) * scale_factor))

    img_ratio = img_w / img_h
    if img_ratio > inner_w / inner_h:
        iw = inner_w
        ih = max(1, int(iw / img_ratio))
    else:
        ih = inner_h
        iw = max(1, int(ih * img_ratio))

    img_thumb = img.resize((iw, ih), Image.LANCZOS)
    ix = fx0 + (fw - iw) // 2
    iy = fy0 + (fh - ih) // 2
    canvas.paste(img_thumb, (ix, iy))

    tag_text = ORIENT_NAMES[pg.orientation]
    tag_color = ORIENT_COLORS[pg.orientation]
    draw.rounded_rectangle([fx0 + 2, fy0 + 2, fx0 + 38, fy0 + 16], radius=3, fill=tag_color)
    draw.text((fx0 + 4, fy0 + 3), tag_text, fill="white", font=_font_tiny)

    if pg.scale != 100:
        draw.rounded_rectangle([fx0 + 2, fy0 + fh - 18, fx0 + 38, fy0 + fh - 2],
                               radius=3, fill="#555")
        draw.text((fx0 + 4, fy0 + fh - 17), f"{pg.scale}%", fill="white", font=_font_tiny)

    if not pg.enabled:
        overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ImageDraw.Draw(overlay).rectangle([0, 0, canvas.width, canvas.height], fill=(200, 200, 200, 140))
        canvas = Image.alpha_composite(canvas, overlay)

    _preview_cache[cache_key] = canvas
    return canvas
