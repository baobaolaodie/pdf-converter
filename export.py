"""export.py — PDF 导出为图片"""

from __future__ import annotations

import os
import fitz
from PIL import Image


def parse_pages(text: str, total_pages: int) -> list[int]:
    """解析页码字符串，返回 0-based 页码列表。

    支持格式：
    - "" 或 "all" → 全部页面
    - "3" → 单页（1-based 输入，返回 2）
    - "3-7" → 范围
    - "1,3-5,8" → 混合
    """
    text = text.strip()
    if not text or text.lower() == "all":
        return list(range(total_pages))

    result = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            bounds = part.split("-", 1)
            try:
                start = int(bounds[0].strip())
                end = int(bounds[1].strip())
            except ValueError:
                raise ValueError(f"无效页码范围: '{part}'")
            if start < 1 or end < 1 or start > end:
                raise ValueError(f"无效页码范围: '{part}'（页码必须 >= 1 且 start <= end）")
            for p in range(start, end + 1):
                if p > total_pages:
                    raise ValueError(f"页码 {p} 超出范围（共 {total_pages} 页）")
                result.add(p - 1)
        else:
            try:
                p = int(part)
            except ValueError:
                raise ValueError(f"无效页码: '{part}'")
            if p < 1:
                raise ValueError(f"页码必须 >= 1，收到: {p}")
            if p > total_pages:
                raise ValueError(f"页码 {p} 超出范围（共 {total_pages} 页）")
            result.add(p - 1)

    return sorted(result)


def export_pdf(
    pdf_path: str,
    output_dir: str,
    fmt: str = "png",
    dpi: int = 150,
    quality: int = 95,
    pages: list[int] | None = None,
    progress_cb=None,
) -> dict:
    """将 PDF 导出为图片文件。

    Args:
        pdf_path: PDF 文件路径
        output_dir: 输出目录
        fmt: "png" 或 "jpg"
        dpi: 输出分辨率
        quality: JPG 质量 1-100（PNG 时忽略）
        pages: 0-based 页码列表，None 表示全部
        progress_cb: callback(current_page_idx, total_pages)

    Returns:
        {"success": int, "failed": list[tuple[int, str]], "output_dir": str}

        ``failed`` 列表中每个元素为 ``(page_number, error_message)`` 元组，
        其中 ``page_number`` 为 **1-based** 页码（方便人类阅读，与输入的
        ``pages`` 参数使用的 0-based 索引不同）。
    """
    os.makedirs(output_dir, exist_ok=True)

    with fitz.open(pdf_path) as doc:
        total = len(doc)
        if pages is None:
            pages = list(range(total))

        matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0)
        success = 0
        failed = []
        stem = os.path.splitext(os.path.basename(pdf_path))[0]

        for i, page_idx in enumerate(pages):
            try:
                page = doc[page_idx]
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

                filename = f"{stem}_page{page_idx + 1}.{fmt}"
                filepath = os.path.join(output_dir, filename)

                if fmt == "jpg":
                    img.save(filepath, quality=quality)
                else:
                    img.save(filepath)

                success += 1
            except (RuntimeError, ValueError, IndexError, fitz.FileDataError) as exc:
                failed.append((page_idx + 1, str(exc)))

            if progress_cb:
                progress_cb(i + 1, len(pages))

    return {"success": success, "failed": failed, "output_dir": output_dir}
