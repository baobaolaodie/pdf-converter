"""staging.py — 素材栏面板：图片导入、缩略图列表、拖出到编辑区"""

from __future__ import annotations
import os
import tkinter as tk
from tkinter import ttk, filedialog
from typing import TYPE_CHECKING, Callable

from PIL import Image, ImageTk

from constants import IMAGE_EXTS

if TYPE_CHECKING:
    from editor import PageEditor


class StagingImage:
    """素材栏中的一张图片"""
    def __init__(self, path: str, pil_img: Image.Image, thumb: ImageTk.PhotoImage):
        self.path = path
        self.pil_img = pil_img
        self.thumb = thumb


class StagingPanel(ttk.Frame):
    """右侧素材栏面板"""

    THUMB_SIZE = 60

    def __init__(self, master, get_editor: Callable[[], PageEditor | None]):
        super().__init__(master)
        self._get_editor = get_editor
        self._images: list[StagingImage] = []
        self._photo_refs: list[ImageTk.PhotoImage] = []
        self._dragging_idx: int = -1
        self._drag_win: tk.Toplevel | None = None

        self._build()

    def _build(self):
        header = ttk.Frame(self)
        header.pack(fill="x", padx=4, pady=(4, 2))
        ttk.Label(header, text="素材栏", font=("", 10, "bold")).pack(side="left")
        ttk.Button(header, text="+ 添加", width=6, command=self._add_files).pack(side="right", padx=1)
        ttk.Button(header, text="清空", width=4, command=self.clear).pack(side="right", padx=1)

        self._canvas = tk.Canvas(self, bg="#f5f5f5", highlightthickness=0, width=90)
        self._canvas.pack(fill="both", expand=True, padx=4, pady=4)

        self._canvas.bind("<Button-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_motion)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)

        self._try_enable_dnd()

    def _try_enable_dnd(self):
        try:
            import tkinterdnd2
            self.drop_target_register(tkinterdnd2.DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)
        except (ImportError, Exception):
            pass

    def _on_drop(self, event):
        raw = event.data.strip()
        paths = []
        if raw.startswith("{") and "}" in raw:
            import re
            paths = [m.group(1) for m in re.finditer(r'\{([^}]+)\}', raw)]
        else:
            paths = raw.split()
        valid = [p for p in paths if os.path.splitext(p)[1].lower() in IMAGE_EXTS and os.path.isfile(p)]
        if valid:
            self.add_files(valid)

    def _add_files(self):
        exts = " ".join(f"*{e}" for e in sorted(IMAGE_EXTS))
        paths = filedialog.askopenfilenames(
            title="选择图片",
            filetypes=[("图片文件", exts), ("所有文件", "*.*")],
        )
        if paths:
            self.add_files(list(paths))

    def add_files(self, paths: list[str]):
        for path in paths:
            try:
                img = Image.open(path)
                if img.mode in ("RGBA", "P", "LA"):
                    img = img.convert("RGB")
                thumb = img.copy()
                thumb.thumbnail((self.THUMB_SIZE, self.THUMB_SIZE), Image.LANCZOS)
                photo = ImageTk.PhotoImage(thumb)
                self._photo_refs.append(photo)
                self._images.append(StagingImage(path, img, photo))
            except Exception:
                continue
        self._render_thumbs()

    def clear(self):
        self._images.clear()
        self._photo_refs.clear()
        self._render_thumbs()

    def _render_thumbs(self):
        self._canvas.delete("all")
        cols = max(1, self._canvas.winfo_width() // (self.THUMB_SIZE + 8))
        for i, simg in enumerate(self._images):
            col = i % cols
            row = i // cols
            x = 4 + col * (self.THUMB_SIZE + 8)
            y = 4 + row * (self.THUMB_SIZE + 8)
            self._canvas.create_image(x + self.THUMB_SIZE // 2, y + self.THUMB_SIZE // 2,
                                      image=simg.thumb, tags=f"staging_{i}")
        rows = (len(self._images) + cols - 1) // cols if self._images else 0
        self._canvas.configure(scrollregion=(0, 0, 200, rows * (self.THUMB_SIZE + 8) + 8))

    def _idx_at(self, x: int, y: int) -> int:
        cols = max(1, self._canvas.winfo_width() // (self.THUMB_SIZE + 8))
        col = x // (self.THUMB_SIZE + 8)
        row = y // (self.THUMB_SIZE + 8)
        idx = row * cols + col
        return idx if 0 <= idx < len(self._images) else -1

    def _on_press(self, event):
        idx = self._idx_at(event.x, event.y)
        if idx < 0:
            return
        self._dragging_idx = idx
        simg = self._images[idx]
        # 创建跟随光标的半透明窗口
        self._drag_win = tw = tk.Toplevel(self)
        tw.overrideredirect(True)
        tw.attributes("-topmost", True)
        tw.attributes("-alpha", 0.6)
        lbl = tk.Label(tw, image=simg.thumb, bg="white", relief="solid")
        lbl.pack()
        tw.geometry(f"+{event.x_root - self.THUMB_SIZE // 2}+{event.y_root - self.THUMB_SIZE // 2}")

    def _on_motion(self, event):
        if self._drag_win:
            self._drag_win.geometry(f"+{event.x_root - self.THUMB_SIZE // 2}+{event.y_root - self.THUMB_SIZE // 2}")

    def _on_release(self, event):
        if self._drag_win:
            self._drag_win.destroy()
            self._drag_win = None
        if self._dragging_idx < 0:
            return
        idx = self._dragging_idx
        self._dragging_idx = -1

        editor = self._get_editor()
        if editor is None:
            return
        # 将屏幕坐标转换为编辑器 Canvas 坐标
        cx = event.x_root - editor.canvas.winfo_rootx()
        cy = event.y_root - editor.canvas.winfo_rooty()
        w = editor.canvas.winfo_width()
        h = editor.canvas.winfo_height()
        if 0 <= cx <= w and 0 <= cy <= h:
            editor.add_layer_from_staging(self._images[idx], cx, cy)
