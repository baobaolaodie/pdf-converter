"""export.py — PDF 导出为图片"""

from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import fitz
from PIL import Image

from core import _scale_layer_dicts, composite_layers


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


def export_pages(
    page_list: list,
    output_dir: str,
    fmt: str = "png",
    dpi: int = 150,
    quality: int = 95,
    progress_cb=None,
) -> dict:
    """将 Page 对象列表导出为图片，应用 orientation/scale/layers 编辑。

    Args:
        page_list: Page 对象列表（来自 constants.Page）
        output_dir: 输出目录
        fmt: "png" 或 "jpg"
        dpi: 输出分辨率
        quality: JPG 质量 1-100（PNG 时忽略）
        progress_cb: callback(current_idx, total)

    Returns:
        {"success": int, "failed": list[tuple[int, str]], "output_dir": str}
    """
    from constants import Page  # noqa: F811 — 避免循环导入

    os.makedirs(output_dir, exist_ok=True)
    EDITOR_RENDER_SCALE = 1.5
    success = 0
    failed = []

    for i, pg in enumerate(page_list):
        try:
            if pg.is_pdf:
                doc = fitz.open(pg.source_path)
                page = doc[pg.page_idx]
                render_scale = dpi / 72.0
                pix = page.get_pixmap(
                    matrix=fitz.Matrix(render_scale, render_scale), alpha=False
                )
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                doc.close()
            else:
                img = Image.open(pg.source_path)
                if img.mode in ("RGBA", "P", "LA"):
                    img = img.convert("RGB")

            orig_w, orig_h = img.size

            # 方向旋转
            if pg.orientation == "auto":
                use_land = orig_w > orig_h
            else:
                use_land = pg.orientation == "landscape"
                img_is_land = orig_w > orig_h
                if use_land != img_is_land:
                    img = img.rotate(-90, expand=True)
                    orig_w, orig_h = orig_h, orig_w

            # 缩放
            if pg.scale != 100:
                s = pg.scale / 100.0
                new_w = max(1, int(orig_w * s))
                new_h = max(1, int(orig_h * s))
                img = img.resize((new_w, new_h), Image.LANCZOS)

            # 图层合成
            if pg.has_layers:
                coord_scale = dpi / (72.0 * EDITOR_RENDER_SCALE)
                if pg.scale != 100:
                    coord_scale *= pg.scale / 100.0
                scaled = _scale_layer_dicts(pg.layers, coord_scale)
                img = composite_layers(img, scaled)

            # 保存
            fname = f"page{i + 1}.{fmt}"
            filepath = os.path.join(output_dir, fname)
            if fmt == "jpg":
                img.save(filepath, quality=quality)
            else:
                img.save(filepath)
            success += 1
        except (RuntimeError, ValueError, IndexError, fitz.FileDataError) as exc:
            failed.append((i + 1, str(exc)))

        if progress_cb:
            progress_cb(i + 1, len(page_list))

    return {"success": success, "failed": failed, "output_dir": output_dir}


class ExportDialog(tk.Toplevel):
    """导出设置对话框：格式、DPI、质量、页码、输出目录。"""

    def __init__(self, parent, pdf_path: str, page_list: list | None = None):
        super().__init__(parent)
        self.title("导出为图片")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._pdf_path = pdf_path
        self._page_list = page_list  # Page 对象列表（可选）
        self._result = None  # 确认后存放参数

        self._build()

        # 居中显示
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        self.geometry(f"+{x}+{y}")

    def _build(self):
        pad = {"padx": 8, "pady": 4}
        main = ttk.Frame(self, padding=12)
        main.pack(fill="both", expand=True)

        # -- 格式 --
        fmt_frame = ttk.LabelFrame(main, text="格式", padding=8)
        fmt_frame.pack(fill="x", **pad)

        self._fmt_var = tk.StringVar(value="png")
        ttk.Radiobutton(fmt_frame, text="PNG", variable=self._fmt_var,
                         value="png", command=self._on_fmt_change).pack(side="left", padx=8)
        ttk.Radiobutton(fmt_frame, text="JPG", variable=self._fmt_var,
                         value="jpg", command=self._on_fmt_change).pack(side="left", padx=8)

        # -- DPI --
        dpi_frame = ttk.LabelFrame(main, text="DPI", padding=8)
        dpi_frame.pack(fill="x", **pad)

        self._dpi_var = tk.IntVar(value=150)
        self._dpi_custom_var = tk.StringVar(value="")
        self._use_custom_dpi = tk.BooleanVar(value=False)

        dpi_btn_frame = ttk.Frame(dpi_frame)
        dpi_btn_frame.pack(fill="x")
        for val in [72, 150, 300]:
            ttk.Radiobutton(dpi_btn_frame, text=str(val), variable=self._dpi_var, value=val,
                             command=self._sync_dpi_preset).pack(side="left", padx=4)
        ttk.Radiobutton(dpi_btn_frame, text="自定义", variable=self._use_custom_dpi, value=True,
                         command=self._sync_dpi_custom_toggle).pack(side="left", padx=(12, 4))
        self._dpi_entry = ttk.Entry(dpi_btn_frame, textvariable=self._dpi_custom_var, width=6)
        self._dpi_entry.pack(side="left")

        # -- 质量（仅 JPG）--
        self._quality_frame = ttk.LabelFrame(main, text="质量 (JPG)", padding=8)

        self._quality_var = tk.IntVar(value=95)
        self._quality_custom_var = tk.StringVar(value="")
        self._use_custom_quality = tk.BooleanVar(value=False)

        qual_btn_frame = ttk.Frame(self._quality_frame)
        qual_btn_frame.pack(fill="x")
        for val in [60, 80, 95]:
            ttk.Radiobutton(qual_btn_frame, text=str(val), variable=self._quality_var, value=val,
                             command=self._sync_quality_preset).pack(side="left", padx=4)
        ttk.Radiobutton(qual_btn_frame, text="自定义", variable=self._use_custom_quality, value=True,
                         command=self._sync_quality_custom_toggle).pack(side="left", padx=(12, 4))
        self._quality_entry = ttk.Entry(qual_btn_frame, textvariable=self._quality_custom_var, width=6)
        self._quality_entry.pack(side="left")

        # -- 页码 --
        pages_frame = ttk.LabelFrame(main, text="页码", padding=8)
        pages_frame.pack(fill="x", **pad)

        default_pages = ""
        if self._page_list:
            enabled = [str(i + 1) for i, pg in enumerate(self._page_list) if pg.enabled]
            default_pages = ",".join(enabled)
        self._pages_var = tk.StringVar(value=default_pages)
        ttk.Entry(pages_frame, textvariable=self._pages_var, width=30).pack(side="left", padx=4)
        ttk.Label(pages_frame, text="留空=全部  例: 1,3-5,8",
                   foreground="#888").pack(side="left", padx=4)

        # -- 输出目录 --
        dir_frame = ttk.LabelFrame(main, text="输出目录", padding=8)
        dir_frame.pack(fill="x", **pad)

        stem = os.path.splitext(os.path.basename(self._pdf_path))[0]
        default_dir = os.path.join(os.path.dirname(self._pdf_path), stem)
        self._outdir_var = tk.StringVar(value=default_dir)

        ttk.Entry(dir_frame, textvariable=self._outdir_var, width=36).pack(side="left", padx=4)
        ttk.Button(dir_frame, text="浏览", command=self._browse_dir).pack(side="left")

        # -- 按钮 --
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill="x", pady=(12, 0))
        ttk.Button(btn_frame, text="取消", command=self.destroy).pack(side="right", padx=4)
        ttk.Button(btn_frame, text="确认导出", command=self._on_confirm).pack(side="right", padx=4)

        self._on_fmt_change()  # 初始化质量区域显隐

    def _on_fmt_change(self):
        if self._fmt_var.get() == "jpg":
            self._quality_frame.pack(fill="x", padx=8, pady=4)
        else:
            self._quality_frame.pack_forget()

    def _sync_dpi_preset(self):
        self._use_custom_dpi.set(False)
        self._dpi_custom_var.set("")

    def _sync_dpi_custom_toggle(self):
        self._dpi_entry.focus_set()

    def _sync_quality_preset(self):
        self._use_custom_quality.set(False)
        self._quality_custom_var.set("")

    def _sync_quality_custom_toggle(self):
        self._quality_entry.focus_set()

    def _browse_dir(self):
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self._outdir_var.set(path)

    def _get_dpi(self) -> int:
        if self._use_custom_dpi.get():
            try:
                return int(self._dpi_custom_var.get())
            except ValueError:
                raise ValueError("自定义 DPI 必须是整数")
        return self._dpi_var.get()

    def _get_quality(self) -> int:
        if self._use_custom_quality.get():
            try:
                return int(self._quality_custom_var.get())
            except ValueError:
                raise ValueError("自定义质量必须是整数")
        return self._quality_var.get()

    def _on_confirm(self):
        try:
            dpi = self._get_dpi()
        except ValueError as e:
            messagebox.showerror("参数错误", str(e), parent=self)
            return

        try:
            quality = self._get_quality()
        except ValueError as e:
            messagebox.showerror("参数错误", str(e), parent=self)
            return

        fmt = self._fmt_var.get()
        pages_text = self._pages_var.get().strip()
        output_dir = self._outdir_var.get().strip()

        if not output_dir:
            messagebox.showerror("参数错误", "请选择输出目录", parent=self)
            return

        # 获取 PDF 页数用于解析页码
        try:
            doc = fitz.open(self._pdf_path)
            total = len(doc)
            doc.close()
        except Exception as e:
            messagebox.showerror("错误", f"无法打开 PDF: {e}", parent=self)
            return

        try:
            page_indices = parse_pages(pages_text, total)
        except ValueError as e:
            messagebox.showerror("页码错误", str(e), parent=self)
            return

        # 构建结果
        self._result = {
            "pdf_path": self._pdf_path,
            "output_dir": output_dir,
            "fmt": fmt,
            "dpi": dpi,
            "quality": quality,
            "pages": page_indices,
        }

        # 如果有 Page 列表，过滤出选中的 Page 对象
        if self._page_list is not None:
            selected_pages = [
                self._page_list[i] for i in page_indices if i < len(self._page_list)
            ]
            self._result["page_list"] = selected_pages

        self.destroy()


class ExportProgressDialog(tk.Toplevel):
    """导出进度对话框：显示进度条，完成后显示结果。"""

    def __init__(self, parent, pdf_path: str, output_dir: str,
                 fmt: str, dpi: int, quality: int, pages: list[int],
                 page_list: list | None = None):
        super().__init__(parent)
        self.title("正在导出")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._pdf_path = pdf_path
        self._output_dir = output_dir
        self._fmt = fmt
        self._dpi = dpi
        self._quality = quality
        self._pages = pages
        self._page_list = page_list  # Page 对象列表（可选，编辑感知导出）
        self._result = None

        self.protocol("WM_DELETE_WINDOW", self._on_close)  # 禁用关闭按钮

        self._build()
        self._start_export()

        # 居中显示
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        self.geometry(f"+{x}+{y}")

    def _build(self):
        main = ttk.Frame(self, padding=16)
        main.pack(fill="both", expand=True)

        stem = os.path.splitext(os.path.basename(self._pdf_path))[0]
        ttk.Label(main, text=f"{stem}.pdf → {self._output_dir}\\",
                   font=("", 10)).pack(anchor="w", pady=(0, 8))

        self._progress = ttk.Progressbar(main, length=400, mode="determinate",
                                          maximum=len(self._pages))
        self._progress.pack(fill="x", pady=4)

        self._status_label = ttk.Label(main, text=f"0/{len(self._pages)} 页", font=("", 10))
        self._status_label.pack(anchor="w", pady=4)

    def _start_export(self):
        def worker():
            def on_progress(cur, total):
                self.after(0, lambda: self._update_progress(cur, total))

            if self._page_list is not None:
                result = export_pages(
                    self._page_list, self._output_dir,
                    fmt=self._fmt, dpi=self._dpi, quality=self._quality,
                    progress_cb=on_progress,
                )
            else:
                result = export_pdf(
                    self._pdf_path, self._output_dir,
                    fmt=self._fmt, dpi=self._dpi, quality=self._quality,
                    pages=self._pages, progress_cb=on_progress,
                )
            self._result = result
            self.after(0, self._show_result)

        threading.Thread(target=worker, daemon=True).start()

    def _update_progress(self, cur: int, total: int):
        self._progress["value"] = cur
        self._status_label.config(text=f"{cur}/{total} 页")

    def _show_result(self):
        # 清除进度视图
        for w in self.winfo_children():
            for child in w.winfo_children():
                child.destroy()

        main = ttk.Frame(self, padding=16)
        main.pack(fill="both", expand=True)

        r = self._result
        ttk.Label(main, text=f"✓ 成功导出 {r['success']} 页",
                   font=("", 11), foreground="#27ae60").pack(anchor="w", pady=2)

        if r["failed"]:
            failed_str = ", ".join(f"#{p[0]}({p[1]})" for p in r["failed"])
            ttk.Label(main, text=f"✗ 跳过 {len(r['failed'])} 页: {failed_str}",
                       font=("", 10), foreground="#e74c3c").pack(anchor="w", pady=2)

        ttk.Label(main, text=f"输出目录: {r['output_dir']}",
                   font=("", 10)).pack(anchor="w", pady=(8, 4))

        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill="x", pady=(12, 0))
        ttk.Button(btn_frame, text="打开文件夹",
                   command=lambda: os.startfile(r["output_dir"])).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="关闭", command=self.destroy).pack(side="right", padx=4)

        # 允许关闭
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _on_close(self):
        pass  # 导出中禁止关闭
