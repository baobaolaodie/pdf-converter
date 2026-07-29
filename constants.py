"""constants.py — 数据结构与常量定义"""

from dataclasses import dataclass

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif", ".gif"}

PAPER_SIZES_MM = {
    "A4":       (210, 297),
    "A3":       (297, 420),
    "A5":       (148, 210),
    "Letter":   (215.9, 279.4),
    "Legal":    (215.9, 355.6),
    "B5 (ISO)": (176, 250),
    "B5 (JIS)": (182, 257),
}

ORIENT_LABELS = ["auto", "portrait", "landscape"]
ORIENT_SYMBOLS = {"auto": "A", "portrait": "P", "landscape": "L"}
ORIENT_COLORS  = {"auto": "#4a90d9", "portrait": "#27ae60", "landscape": "#e67e22"}
ORIENT_NAMES   = {"auto": "自动", "portrait": "纵向", "landscape": "横向"}

# 缩略图布局
CELL_W   = 180
CELL_H   = 255
PAD      = 12
THUMB_MAX = 140


@dataclass
class Page:
    source_path: str
    file_idx: int
    page_idx: int
    is_pdf: bool
    orientation: str = "auto"
    enabled: bool = True
    orig_w: int = 0
    orig_h: int = 0
    scale: int = 100
