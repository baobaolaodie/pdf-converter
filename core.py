"""core.py — 文件收集、页面构建、PDF 合并"""

import os
import re
from io import BytesIO

from PIL import Image
from pypdf import PdfWriter, PdfReader

from constants import IMAGE_EXTS, Page
from editor import composite_layers


def collect_files(folder_path: str, exclude_name: str = "") -> list[tuple[int, str, str]]:
    """收集文件夹中所有图片和 PDF 文件，按文件名排序。
    优先提取 -N 后缀中的数字，否则提取文件名中的首个数字。
    exclude_name: 排除的输出文件名（如 "1110.pdf"）。"""
    ALL_EXTS = IMAGE_EXTS | {".pdf"}
    folder_name = os.path.basename(folder_path)
    entries = []
    for fname in os.listdir(folder_path):
        ext = os.path.splitext(fname)[1].lower()
        if ext not in ALL_EXTS:
            continue
        if fname == f"{folder_name}.pdf" or (exclude_name and fname == exclude_name):
            continue
        stem = os.path.splitext(fname)[0]
        m = re.search(r'-(\d+)$', stem)
        if not m:
            m = re.search(r'(\d+)', stem)
        sort_key = int(m.group(1)) if m else -1
        entries.append((sort_key, ext, fname))

    entries.sort(key=lambda x: (0 if x[0] >= 0 else 1, x[0], x[2]))
    return entries


def build_page_list(folder_path: str, folder_name: str,
                    entries: list, default_orient: str = "auto") -> list[Page]:
    pages: list[Page] = []
    for file_idx, (num, ext, fname) in enumerate(entries):
        fpath = os.path.join(folder_path, fname)
        if ext == ".pdf":
            try:
                reader = PdfReader(fpath)
                for pi, page in enumerate(reader.pages):
                    mb = page.mediabox
                    pages.append(Page(fpath, file_idx, pi, True,
                                      orientation=default_orient,
                                      orig_w=float(mb.width), orig_h=float(mb.height)))
            except Exception:
                pass
        elif ext in IMAGE_EXTS:
            try:
                img = Image.open(fpath)
                pages.append(Page(fpath, file_idx, 0, False,
                                  orientation=default_orient,
                                  orig_w=img.width, orig_h=img.height))
                img.close()
            except Exception:
                pass
    return pages


def merge_folder(
    folder_path: str,
    folder_name: str,
    pages: list[Page],
    paper_w_mm: float,
    paper_h_mm: float,
    dpi: int,
    output_path: str | None = None,
    log_func=None,
):
    def log(msg):
        if log_func:
            log_func(msg)

    if output_path is None:
        output_path = os.path.join(folder_path, f"{folder_name}.pdf")

    portrait_w_px = int(paper_w_mm / 25.4 * dpi)
    portrait_h_px = int(paper_h_mm / 25.4 * dpi)
    writer = PdfWriter()

    # 编辑器渲染基准：1.5x (≈108 DPI)
    EDITOR_RENDER_SCALE = 1.5

    for pg in pages:
        fname = os.path.basename(pg.source_path)

        if pg.is_pdf:
            reader = PdfReader(pg.source_path)
            src_page = reader.pages[pg.page_idx]
            pw, ph = float(src_page.mediabox.width), float(src_page.mediabox.height)

            if pg.orientation == "auto":
                needs_rot = pw > ph
            else:
                want_land = (pg.orientation == "landscape")
                page_is_land = pw > ph
                needs_rot = (want_land != page_is_land)
            if needs_rot:
                src_page.rotate(90)

            if pg.has_layers:
                import fitz
                doc = fitz.open(pg.source_path)
                page = doc[pg.page_idx]
                render_scale = dpi / 72.0
                pix = page.get_pixmap(matrix=fitz.Matrix(render_scale, render_scale), alpha=False)
                from PIL import Image as PILImage
                base_img = PILImage.frombytes("RGB", (pix.width, pix.height), pix.samples)
                doc.close()
                if needs_rot:
                    base_img = base_img.rotate(-90, expand=True)
                # 缩放图层坐标：编辑器空间 → 导出空间
                coord_scale = dpi / (72.0 * EDITOR_RENDER_SCALE)
                scaled = _scale_layer_dicts(pg.layers, coord_scale)
                composited = composite_layers(base_img, scaled)
                buf = BytesIO()
                composited.save(buf, format="PDF", resolution=dpi)
                buf.seek(0)
                writer.add_page(PdfReader(buf).pages[0])
            else:
                writer.add_page(src_page)
            log(f"  + {fname} p{pg.page_idx + 1}")
        else:
            img = Image.open(pg.source_path)
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
            orig_w, orig_h = img.size

            if pg.orientation == "auto":
                use_land = orig_w > orig_h
            else:
                use_land = (pg.orientation == "landscape")
                img_is_land = orig_w > orig_h
                if use_land != img_is_land:
                    img = img.rotate(-90, expand=True)
                    orig_w, orig_h = orig_h, orig_w

            if use_land:
                tw, th = portrait_h_px, portrait_w_px
                lbl = "横向"
            else:
                tw, th = portrait_w_px, portrait_h_px
                lbl = "纵向"

            sf = pg.scale / 100.0
            tw, th = int(tw * sf), int(th * sf)

            fit_scale = min(tw / orig_w, th / orig_h)
            nw, nh = int(orig_w * fit_scale), int(orig_h * fit_scale)
            img_r = img.resize((nw, nh), Image.LANCZOS)
            if pg.has_layers:
                # 缩放图层坐标：原图像素空间 → 缩放后空间
                scaled = _scale_layer_dicts(pg.layers, fit_scale)
                img_r = composite_layers(img_r, scaled)
            buf = BytesIO()
            img_r.save(buf, format="PDF", resolution=dpi)
            buf.seek(0)
            writer.add_page(PdfReader(buf).pages[0])
            log(f"  + {fname} ({orig_w}x{orig_h} -> {nw}x{nh}px, {lbl})")
            img.close()
            img_r.close()

    with open(output_path, "wb") as f:
        writer.write(f)
    writer.close()
    return output_path


def _scale_layer_dicts(layer_dicts: list[dict], scale: float) -> list[dict]:
    """按比例缩放图层坐标和尺寸。"""
    if scale == 1.0:
        return layer_dicts
    result = []
    for d in layer_dicts:
        sd = dict(d)
        sd["x"] = d["x"] * scale
        sd["y"] = d["y"] * scale
        sd["width"] = d["width"] * scale
        sd["height"] = d["height"] * scale
        result.append(sd)
    return result
