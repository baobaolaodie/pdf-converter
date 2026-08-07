"""standalone.py — 独立编辑模式：直接打开 PDF 进行图片叠加编辑"""

import os
import threading
import tkinter as tk
from tkinter import ttk

from .constants import PAPER_SIZES_MM
from .editor import PageEditor
from .staging import StagingPanel


class StandaloneMixin:
    """MergeApp 的独立编辑模式 mixin。"""

    def _start_standalone_edit(self):
        path = self.folder_var.get().strip()
        if not path:
            from tkinter import filedialog
            path = filedialog.askopenfilename(
                title="选择 PDF 文件",
                filetypes=[("PDF 文件", "*.pdf"), ("所有文件", "*.*")],
            )
            if not path:
                return
            self.folder_var.set(path)

        if not path.lower().endswith(".pdf") or not os.path.isfile(path):
            from tkinter import messagebox
            messagebox.showerror("错误", "请选择一个有效的 PDF 文件。")
            return

        from .core import build_page_list
        folder = os.path.dirname(path)
        fname = os.path.basename(path)
        entries = [(0, ".pdf", fname)]
        pages = build_page_list(folder, fname, entries, "auto")
        bases = [None] * len(pages)

        self._pages_cache[fname] = pages
        self._base_images[fname] = bases
        self._selected_name = fname

        self._enter_edit_mode_standalone(pages, bases)

        from .preview import _load_base_image

        def load_all():
            for i, pg in enumerate(pages):
                bases[i] = _load_base_image(pg)
                self.root.after(0, lambda idx=i: self._update_single_standalone(idx, fname))

        threading.Thread(target=load_all, daemon=True).start()

    def _enter_edit_mode_standalone(self, pages, bases):
        self._edit_mode = True
        paper = PAPER_SIZES_MM[self.paper_var.get()]

        # 隐藏合并相关的顶部/底部栏
        for child in self.root.winfo_children():
            if isinstance(child, ttk.Frame):
                try:
                    if child.winfo_children() and any(
                        isinstance(w, ttk.Button) and w.cget("text") == "开始合并"
                        for w in child.winfo_children()
                    ):
                        child.pack_forget()
                except Exception:
                    pass

        # 隐藏左侧文件夹栏 (PanedWindow)
        for child in self.root.winfo_children():
            if isinstance(child, ttk.PanedWindow):
                child.pack_forget()
                break

        self._editor_container = ttk.Frame(self.root)
        self._editor_container.pack(fill="both", expand=True)

        self._editor = PageEditor(self._editor_container, paper[0], paper[1])
        self._editor.pack(side="left", fill="both", expand=True)
        self._editor.set_context(pages, bases)

        # 独立模式：隐藏返回按钮
        self._editor._btn_back.pack_forget()
        self._editor.load_page(0, pages, bases)

        # 添加保存按钮
        ttk.Button(self._editor._toolbar, text="保存 PDF",
                   command=self._save_standalone).pack(side="right", padx=4)

        self._staging = StagingPanel(self._editor_container,
                                      get_editor=lambda: self._editor)
        self._staging.pack(side="right", fill="y", padx=(4, 0))

    def _update_single_standalone(self, idx, fname):
        if self._editor and self._edit_mode:
            pages = self._pages_cache.get(fname, [])
            bases = self._base_images.get(fname, [])
            self._editor.set_context(pages, bases)
            if self._editor._page_index == idx:
                self._editor.load_page(idx, pages, bases)

    def _save_standalone(self):
        if self._editor:
            self._editor.sync_current_layers()

        from tkinter import filedialog, messagebox

        path = filedialog.asksaveasfilename(
            title="保存 PDF",
            defaultextension=".pdf",
            filetypes=[("PDF 文件", "*.pdf")],
        )
        if not path:
            return

        pages = self._pages_cache.get(self._selected_name, [])
        if not pages:
            return

        try:
            dpi = self._get_dpi()
        except Exception:
            dpi = 150

        try:
            from .core import composite_layers, _scale_layer_dicts
            from pypdf import PdfReader, PdfWriter
            from io import BytesIO
            import fitz

            writer = PdfWriter()
            editor = self._editor
            stacks = editor.get_stacks()
            for i, pg in enumerate(pages):
                stack = stacks.get(i)
                if stack and stack.layers:
                    pg.layers = stack.snapshot()

            for i, pg in enumerate(pages):
                if pg.has_layers:
                    doc = fitz.open(pg.source_path)
                    page = doc[pg.page_idx]
                    render_scale = dpi / 72.0
                    pix = page.get_pixmap(matrix=fitz.Matrix(render_scale, render_scale), alpha=False)
                    from PIL import Image as PILImage
                    base_img = PILImage.frombytes("RGB", (pix.width, pix.height), pix.samples)
                    doc.close()
                    if pg.orientation != "auto":
                        use_land = (pg.orientation == "landscape")
                        page_is_land = (pg.orig_w > pg.orig_h)
                        if use_land != page_is_land:
                            base_img = base_img.rotate(-90, expand=True)
                    coord_scale = dpi / (72.0 * 1.5)
                    scaled = _scale_layer_dicts(pg.layers, coord_scale)
                    composited = composite_layers(base_img, scaled)
                    if composited.mode in ("RGBA", "P", "LA"):
                        composited = composited.convert("RGB")
                    buf = BytesIO()
                    composited.save(buf, format="PDF", resolution=dpi)
                    buf.seek(0)
                    writer.add_page(PdfReader(buf).pages[0])
                else:
                    writer.add_page(PdfReader(pg.source_path).pages[pg.page_idx])

            with open(path, "wb") as f:
                writer.write(f)
            writer.close()
            messagebox.showinfo("完成", f"已保存到: {path}")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {e}")
