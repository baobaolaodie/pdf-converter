"""gui.py — Tkinter GUI 主界面"""

import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import Image, ImageTk

from constants import (
    Page, PAPER_SIZES_MM, ORIENT_LABELS, ORIENT_SYMBOLS, ORIENT_COLORS, ORIENT_NAMES,
    IMAGE_EXTS, CELL_W, CELL_H, PAD, THUMB_MAX,
)
from core import collect_files, build_page_list, merge_folder
from preview import _load_base_image, render_preview, _preview_cache
from editor import PageEditor
from staging import StagingPanel


class MergeApp:
    def __init__(self, root: tk.Tk, initial_path: str | None = None, standalone_edit: bool = False):
        self.root = root
        self.root.title("合并为 PDF")
        self.root.minsize(960, 640)

        self.folder_var = tk.StringVar(value=initial_path or "")
        self.paper_var = tk.StringVar(value="A4")
        self.dpi_var = tk.IntVar(value=150)
        self.custom_dpi_var = tk.StringVar(value="150")
        self.use_custom_dpi = tk.BooleanVar(value=False)

        self._subfolders: list[tuple[str, str]] = []
        self._folder_vars: dict[str, tk.BooleanVar] = {}
        self._folder_cbs: dict[str, ttk.Checkbutton] = {}
        self._selected_name: str | None = None
        self._pages_cache: dict[str, list[Page]] = {}
        self._base_images: dict[str, list[Image.Image | None]] = {}
        self._photo_refs: list[ImageTk.PhotoImage] = []
        self._last_gallery_width: int = 0

        self._selected_page: int = -1
        self._drag_page: int = -1
        self._drag_photo: ImageTk.PhotoImage | None = None
        self._drop_line_id: int | None = None
        self._drop_target: int = -1
        self._drag_start_x: int = -1
        self._drag_start_y: int = -1

        self._edit_mode = False
        self._editor: PageEditor | None = None
        self._staging: StagingPanel | None = None
        self._staging_paths: list[str] = []  # 保留素材栏图片路径
        self._standalone_edit = standalone_edit

        self._build_ui()

        self._entry.bind("<Return>", lambda e: self._scan_folders())
        self._entry.bind("<FocusOut>", lambda e: self._scan_folders())
        self._last_scanned_path: str = ""

        if initial_path:
            self.root.after(100, self._scan_folders)

        if standalone_edit:
            self.root.after(100, self._start_standalone_edit)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill="x")

        ttk.Label(top, text="文件夹:").pack(side="left")
        self._entry = ttk.Entry(top, textvariable=self.folder_var, width=40)
        self._entry.pack(side="left", padx=4)
        ttk.Button(top, text="浏览…", command=self._browse).pack(side="left")
        ttk.Separator(top, orient="vertical").pack(side="left", fill="y", padx=8)

        ttk.Label(top, text="纸张:").pack(side="left")
        ttk.Combobox(top, textvariable=self.paper_var, values=list(PAPER_SIZES_MM.keys()),
                     state="readonly", width=9).pack(side="left", padx=2)

        ttk.Label(top, text="DPI:").pack(side="left", padx=(8, 0))
        for d in [72, 96, 150, 300]:
            ttk.Radiobutton(top, text=str(d), variable=self.dpi_var, value=d,
                            command=self._sync_dpi_preset).pack(side="left")
        ttk.Radiobutton(top, text="", variable=self.use_custom_dpi, value=True,
                        command=self._sync_dpi_custom).pack(side="left")
        self._dpi_entry = ttk.Entry(top, textvariable=self.custom_dpi_var, width=5)
        self._dpi_entry.pack(side="left")

        paned = ttk.PanedWindow(self.root, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=8, pady=4)

        left = ttk.Frame(paned, width=170)
        paned.add(left, weight=0)

        left_header = ttk.Frame(left)
        left_header.pack(fill="x", pady=(0, 4))
        ttk.Label(left_header, text="子文件夹", font=("", 10, "bold")).pack(side="left")
        ttk.Button(left_header, text="全选", width=4,
                   command=lambda: self._set_folders_all(True)).pack(side="right", padx=1)
        ttk.Button(left_header, text="清空", width=4,
                   command=lambda: self._set_folders_all(False)).pack(side="right", padx=1)

        folder_canvas = tk.Canvas(left, width=150, highlightthickness=0)
        folder_scroll = ttk.Scrollbar(left, orient="vertical", command=folder_canvas.yview)
        self._folder_frame = ttk.Frame(folder_canvas)
        self._folder_frame.bind("<Configure>",
                                lambda e: folder_canvas.configure(scrollregion=folder_canvas.bbox("all")))
        folder_canvas.create_window((0, 0), window=self._folder_frame, anchor="nw")
        folder_canvas.configure(yscrollcommand=folder_scroll.set)
        folder_scroll.pack(side="right", fill="y")
        folder_canvas.pack(fill="both", expand=True)

        def _folder_wheel(e):
            folder_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        folder_canvas.bind("<Enter>", lambda e: folder_canvas.bind_all("<MouseWheel>", _folder_wheel))
        folder_canvas.bind("<Leave>", lambda e: folder_canvas.unbind_all("<MouseWheel>"))

        right = ttk.Frame(paned)
        paned.add(right, weight=1)

        header_frame = ttk.Frame(right)
        header_frame.pack(fill="x", pady=(0, 4))
        ttk.Label(header_frame, text="页面预览", font=("", 10, "bold")).pack(side="left")
        self._current_folder_label = ttk.Label(header_frame, text="", font=("", 10, "bold"),
                                                foreground="#2c3e50")
        self._current_folder_label.pack(side="left", padx=(6, 0))
        hint_text = "勾选框控制合并 | 点击选中后拖拽/上下移调整顺序 | 点击徽章切换方向"
        ttk.Label(header_frame, text=hint_text, foreground="#888").pack(side="left", padx=(8, 0))
        self._orient_hint = ttk.Label(header_frame, text="", foreground="#666")
        self._orient_hint.pack(side="right")

        canvas_frame = ttk.Frame(right)
        canvas_frame.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(canvas_frame, bg="#e8e8e8", highlightthickness=0)
        self._scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self._scrollbar.set)
        self._scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.canvas.bind("<Button-1>", self._on_thumb_click)
        self.canvas.bind("<B1-Motion>", self._on_drag_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_drag_release)
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._on_mousewheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))
        self.canvas.bind("<Double-Button-1>", self._on_thumb_doubleclick)

        bottom = ttk.Frame(self.root, padding=8)
        bottom.pack(fill="x")
        self.progress = ttk.Progressbar(bottom, length=500, mode="determinate")
        self.progress.pack(fill="x", pady=(0, 4))
        btn_frame = ttk.Frame(bottom)
        btn_frame.pack()
        ttk.Button(btn_frame, text="全选", command=lambda: self._set_enabled_all(True)).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="全不选", command=lambda: self._set_enabled_all(False)).pack(side="left", padx=4)
        ttk.Separator(btn_frame, orient="vertical").pack(side="left", fill="y", padx=4)
        ttk.Button(btn_frame, text="上移", width=5, command=lambda: self._move_selected(-1)).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="下移", width=5, command=lambda: self._move_selected(1)).pack(side="left", padx=2)
        ttk.Separator(btn_frame, orient="vertical").pack(side="left", fill="y", padx=4)
        ttk.Button(btn_frame, text="全选自动", command=lambda: self._set_all("auto")).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="全选纵向", command=lambda: self._set_all("portrait")).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="全选横向", command=lambda: self._set_all("landscape")).pack(side="left", padx=4)
        ttk.Separator(btn_frame, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Label(btn_frame, text="全部缩放:").pack(side="left")
        self._global_scale_var = tk.IntVar(value=100)
        gscale = ttk.Scale(btn_frame, from_=10, to=100, variable=self._global_scale_var,
                           orient="horizontal", length=100, command=self._on_global_scale)
        gscale.pack(side="left", padx=2)
        self._global_scale_label = ttk.Label(btn_frame, text="100%", width=4)
        self._global_scale_label.pack(side="left")
        ttk.Separator(btn_frame, orient="vertical").pack(side="left", fill="y", padx=8)
        self.start_btn = ttk.Button(btn_frame, text="开始合并", command=self._start)
        self.start_btn.pack(side="left", padx=4)

    # ── DPI ───────────────────────────────────────────────────────────────────

    def _sync_dpi_preset(self):
        self.use_custom_dpi.set(False)
        self.custom_dpi_var.set(str(self.dpi_var.get()))

    def _sync_dpi_custom(self):
        try:
            self.dpi_var.set(int(self.custom_dpi_var.get()))
        except ValueError:
            pass

    def _get_dpi(self) -> int:
        if self.use_custom_dpi.get():
            return int(self.custom_dpi_var.get())
        return self.dpi_var.get()

    # ── 文件夹 ────────────────────────────────────────────────────────────────

    def _browse(self):
        path = filedialog.askdirectory(title="选择文件夹")
        if path:
            self.folder_var.set(path)
            self._last_scanned_path = ""
            self._scan_folders()

    def _scan_folders(self):
        folder = self.folder_var.get().strip()
        if not folder or not os.path.isdir(folder):
            return
        if folder == self._last_scanned_path:
            return
        self._last_scanned_path = folder

        old_vars = dict(self._folder_vars)
        self._subfolders.clear()
        self._folder_vars.clear()
        self._folder_cbs.clear()
        self._pages_cache.clear()
        self._base_images.clear()
        self._selected_name = None
        _preview_cache.clear()

        for w in self._folder_frame.winfo_children():
            w.destroy()

        sub_items = []
        for name in sorted(os.listdir(folder)):
            sub = os.path.join(folder, name)
            if os.path.isdir(sub):
                entries = collect_files(sub)
                if entries:
                    sub_items.append((sub, name, entries))

        direct_entries = collect_files(folder)

        if sub_items:
            for sub, name, entries in sub_items:
                self._subfolders.append((sub, name))
                var = old_vars.get(name, tk.BooleanVar(value=True))
                self._folder_vars[name] = var
                cb = ttk.Checkbutton(self._folder_frame, text=f"📁 {name}  ({len(entries)})",
                                     variable=var,
                                     command=lambda n=name: self._on_folder_click(n))
                cb.pack(anchor="w", padx=4, pady=1)
                self._folder_cbs[name] = cb

            if direct_entries:
                folder_name = os.path.basename(folder)
                self._subfolders.append((folder, folder_name))
                var = old_vars.get(folder_name, tk.BooleanVar(value=True))
                self._folder_vars[folder_name] = var
                cb = ttk.Checkbutton(self._folder_frame,
                                     text=f"📄 {folder_name}/  ({len(direct_entries)})",
                                     variable=var,
                                     command=lambda n=folder_name: self._on_folder_click(n))
                cb.pack(anchor="w", padx=4, pady=1)
                self._folder_cbs[folder_name] = cb

        elif direct_entries:
            folder_name = os.path.basename(folder)
            self._subfolders.append((folder, folder_name))
            var = old_vars.get(folder_name, tk.BooleanVar(value=True))
            self._folder_vars[folder_name] = var
            cb = ttk.Checkbutton(self._folder_frame,
                                 text=f"📄 {folder_name}  ({len(direct_entries)})",
                                 variable=var,
                                 command=lambda n=folder_name: self._on_folder_click(n))
            cb.pack(anchor="w", padx=4, pady=1)
            self._folder_cbs[folder_name] = cb

        if self._subfolders:
            self._on_folder_click(self._subfolders[0][1])

    def _on_folder_click(self, name: str):
        if name == self._selected_name:
            return
        self._selected_name = name
        self._selected_page = -1
        _preview_cache.clear()

        sub = None
        for s, n in self._subfolders:
            if n == name:
                sub = s
                break
        if sub is None:
            return

        if name not in self._pages_cache:
            entries = collect_files(sub)
            pages = build_page_list(sub, name, entries, "auto")
            self._pages_cache[name] = pages
            self._base_images[name] = [None] * len(pages)

            self._render_gallery()
            enabled_count = sum(1 for p in pages if p.enabled)
            self._orient_hint.config(text=f"加载图片中... ({len(pages)} 页，已选 {enabled_count} 页)")

            def load_all():
                for i, pg in enumerate(pages):
                    self._base_images[name][i] = _load_base_image(pg)
                    self.root.after(0, lambda idx=i: self._update_single_page(idx))
                self.root.after(0, lambda: self._update_count_hint())

            threading.Thread(target=load_all, daemon=True).start()
        else:
            self._render_gallery()

    # ── 编辑模式 ──

    def _on_thumb_doubleclick(self, event):
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        page_idx = self._hit_test_page(cx, cy)
        if page_idx is None:
            return
        name = self._selected_name
        if not name:
            return
        pages = self._pages_cache.get(name, [])
        if page_idx >= len(pages):
            return
        self._enter_edit_mode(page_idx)

    def _enter_edit_mode(self, page_idx: int):
        self._edit_mode = True
        paper = PAPER_SIZES_MM[self.paper_var.get()]

        # 隐藏画廊相关组件（canvas 和 scrollbar 在 canvas_frame 内）
        self.canvas.pack_forget()
        self._scrollbar.pack_forget()

        # 创建编辑器容器（放入 canvas_frame，即 canvas 的直接父容器）
        self._editor_container = ttk.Frame(self.canvas.master)
        self._editor_container.pack(fill="both", expand=True)

        # 创建编辑器
        self._editor = PageEditor(self._editor_container, paper[0], paper[1],
                                   on_back=self._exit_edit_mode)
        self._editor.pack(side="left", fill="both", expand=True)

        name = self._selected_name
        pages = self._pages_cache[name]
        bases = self._base_images[name]
        self._editor.set_context(pages, bases)
        self._editor.load_page(page_idx, pages, bases)

        # 复用已有素材栏（跨页面保留已导入的图片）
        self._staging = StagingPanel(self._editor_container,
                                      get_editor=lambda: self._editor)
        if self._staging_paths:
            self._staging.add_files(self._staging_paths)
        self._staging.pack(side="right", fill="y", padx=(4, 0))

    def _exit_edit_mode(self):
        # 保存素材栏图片路径，供下次进入编辑模式时恢复
        if self._staging and self._staging._images:
            self._staging_paths = [simg.path for simg in self._staging._images]
        if self._editor:
            self._editor.sync_current_layers()
        if hasattr(self, '_editor_container') and self._editor_container:
            self._editor_container.destroy()
        self._editor = None
        self._staging = None
        self._edit_mode = False

        # 恢复画廊（canvas_frame = self.canvas.master）
        from preview import _preview_cache
        _preview_cache.clear()
        self._scrollbar.pack(in_=self.canvas.master, side="right", fill="y")
        self.canvas.pack(in_=self.canvas.master, side="left", fill="both", expand=True)
        self._render_gallery()

    # ── 独立编辑模式 ──

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

        from core import build_page_list
        folder = os.path.dirname(path)
        fname = os.path.basename(path)
        entries = [(0, ".pdf", fname)]
        pages = build_page_list(folder, fname, entries, "auto")
        bases = [None] * len(pages)

        self._pages_cache[fname] = pages
        self._base_images[fname] = bases
        self._selected_name = fname

        self._enter_edit_mode_standalone(pages, bases)

        from preview import _load_base_image
        import threading

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

        from editor import PageEditor
        self._editor = PageEditor(self._editor_container, paper[0], paper[1])
        self._editor.pack(side="left", fill="both", expand=True)
        self._editor.set_context(pages, bases)

        # 独立模式：隐藏返回按钮
        self._editor._btn_back.pack_forget()
        self._editor.load_page(0, pages, bases)

        # 添加保存按钮
        ttk.Button(self._editor._toolbar, text="保存 PDF",
                   command=self._save_standalone).pack(side="right", padx=4)

        from staging import StagingPanel
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
            from core import composite_layers, _scale_layer_dicts
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

    # ── 画廊渲染 ──────────────────────────────────────────────────────────────

    def _on_canvas_resize(self, event):
        new_w = event.width
        if abs(new_w - self._last_gallery_width) > CELL_W:
            self._last_gallery_width = new_w
            if self._selected_name:
                self._render_gallery()

    def _get_cols(self) -> int:
        w = self.canvas.winfo_width()
        return max(1, (w - PAD) // CELL_W) if w > 50 else 4

    def _render_gallery(self):
        self.canvas.delete("all")
        self._photo_refs.clear()

        if not self._selected_name:
            return

        name = self._selected_name
        pages = self._pages_cache.get(name, [])
        bases = self._base_images.get(name, [])
        if not pages:
            self.canvas.create_text(200, 100, text="此文件夹无可预览页面",
                                    font=("", 12), fill="gray")
            return

        enabled_count = sum(1 for p in pages if p.enabled)
        self._orient_hint.config(text=f"共 {len(pages)} 页，已选 {enabled_count} 页")
        self._current_folder_label.config(text=f"[ {name} ]")

        paper = PAPER_SIZES_MM[self.paper_var.get()]
        cols = self._get_cols()
        rows = (len(pages) + cols - 1) // cols

        total_w = cols * CELL_W + PAD
        total_h = rows * CELL_H + PAD
        self.canvas.configure(scrollregion=(0, 0, total_w, total_h))

        for i, pg in enumerate(pages):
            col = i % cols
            row = i // cols
            x0 = PAD + col * CELL_W
            y0 = PAD + row * CELL_H
            cx = x0 + CELL_W // 2

            fname = os.path.basename(pg.source_path)
            label = fname + (f" p{pg.page_idx + 1}" if pg.is_pdf else "")
            tag = f"page_{i}"

            base = bases[i] if i < len(bases) else None
            preview = render_preview(pg, base, paper[0], paper[1])

            if preview:
                photo = ImageTk.PhotoImage(preview)
                self._photo_refs.append(photo)
                self.canvas.create_image(cx, y0 + THUMB_MAX // 2 + 2, image=photo, tags=tag)
            else:
                self.canvas.create_rectangle(x0 + 10, y0 + 10, x0 + CELL_W - 10, y0 + THUMB_MAX,
                                             fill="#ddd", outline="#bbb", tags=tag)
                self.canvas.create_text(cx, y0 + THUMB_MAX // 2, text="(无法预览)",
                                        fill="#888", tags=tag)

            self._draw_checkbox(i, x0 + 4, y0 + 4, pg.enabled)

            if i == self._selected_page:
                self.canvas.create_rectangle(x0 + 1, y0 + 1, x0 + CELL_W - 1, y0 + THUMB_MAX + 2,
                                             outline="#2196F3", width=2, tags=(tag, "sel_highlight"))

            self.canvas.create_text(cx, y0 + THUMB_MAX + 14, text=label,
                                    font=("", 8), fill="#333", tags=tag)

            self._draw_badge(i, cx, y0 + THUMB_MAX + 30, pg.orientation)

            scale_y = y0 + THUMB_MAX + 48
            self.canvas.create_text(cx - 24, scale_y, text="缩放:", font=("", 8),
                                    fill="#555", anchor="e", tags=tag)
            sv = tk.StringVar(value=str(pg.scale))
            sv.trace_add("write", lambda *_a, idx=i, var=sv: self._on_scale_input(idx, var))
            entry = ttk.Entry(self.canvas, textvariable=sv, width=4, font=("", 8))
            self.canvas.create_window(cx + 8, scale_y, window=entry, anchor="w", tags=tag)
            self.canvas.create_text(cx + 34, scale_y, text="%", font=("", 8),
                                    fill="#555", anchor="w", tags=tag)

        self._update_scrollregion()

    def _update_scrollregion(self):
        bbox = self.canvas.bbox("all")
        if bbox:
            self.canvas.configure(scrollregion=(0, 0, bbox[2] + PAD, bbox[3] + PAD))

    def _update_count_hint(self):
        if not self._selected_name:
            return
        pages = self._pages_cache.get(self._selected_name, [])
        enabled_count = sum(1 for p in pages if p.enabled)
        self._orient_hint.config(text=f"共 {len(pages)} 页，已选 {enabled_count} 页")
        self._current_folder_label.config(text=f"[ {self._selected_name} ]")

    def _draw_badge(self, page_idx: int, cx: int, cy: int, orient: str):
        sym = ORIENT_SYMBOLS[orient]
        color = ORIENT_COLORS[orient]
        name = ORIENT_NAMES[orient]
        text = f"[{sym}] {name}"

        bg_tag = f"badge_{page_idx}"
        self.canvas.create_rectangle(cx - 32, cy - 9, cx + 32, cy + 9,
                                     fill=color, outline="", tags=(bg_tag, f"page_{page_idx}"))
        self.canvas.create_text(cx, cy, text=text, fill="white",
                                font=("", 9, "bold"), tags=(bg_tag, f"page_{page_idx}"))

    def _draw_checkbox(self, page_idx: int, x: int, y: int, checked: bool):
        tag_cb = f"cb_{page_idx}"
        page_tag = f"page_{page_idx}"
        size = 16
        self.canvas.create_rectangle(x, y, x + 20, y + 20,
                                     fill="", outline="", width=0, tags=(tag_cb, page_tag))
        if checked:
            self.canvas.create_rectangle(x + 2, y + 2, x + size, y + size,
                                         fill="#27ae60", outline="white", width=1,
                                         tags=(tag_cb, page_tag))
            self.canvas.create_text(x + size // 2 + 1, y + size // 2 + 1, text="✓",
                                    fill="white", font=("", 10, "bold"),
                                    tags=(tag_cb, page_tag))
        else:
            self.canvas.create_rectangle(x + 2, y + 2, x + size, y + size,
                                         fill="#ffffff", outline="#999", width=1,
                                         tags=(tag_cb, page_tag))

    # ── 点击切换方向 ──────────────────────────────────────────────────────────

    def _on_thumb_click(self, event):
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)

        page_idx = self._hit_test_page(cx, cy)
        if page_idx is None:
            return

        name = self._selected_name
        if not name:
            return
        pages = self._pages_cache.get(name, [])
        if page_idx >= len(pages):
            return

        x0, y0, _, _ = self._page_rect(page_idx)
        cb_x1, cb_y1 = x0 + 24, y0 + 24
        badge_y = y0 + THUMB_MAX + 22

        if cx <= cb_x1 and cy <= cb_y1:
            pages[page_idx].enabled = not pages[page_idx].enabled
            self._update_single_page(page_idx)
        elif cy >= badge_y:
            pg = pages[page_idx]
            cur = ORIENT_LABELS.index(pg.orientation)
            pg.orientation = ORIENT_LABELS[(cur + 1) % 3]
            self._update_single_page(page_idx)
        else:
            self._selected_page = page_idx
            self._drag_page = page_idx
            self._drag_start_x = cx
            self._drag_start_y = cy
            self._render_gallery()

    def _hit_test_page(self, cx: float, cy: float) -> int | None:
        items = self.canvas.find_closest(cx, cy)
        if not items:
            return None
        for t in self.canvas.gettags(items[0]):
            if t.startswith("page_"):
                try:
                    return int(t.split("_", 1)[1])
                except ValueError:
                    continue
        return None

    def _page_rect(self, i: int) -> tuple[int, int, int, int]:
        cols = self._get_cols()
        col = i % cols
        row = i // cols
        x0 = PAD + col * CELL_W
        y0 = PAD + row * CELL_H
        return x0, y0, x0 + CELL_W, y0 + CELL_H

    def _on_scale_input(self, page_idx: int, var: tk.StringVar):
        name = self._selected_name
        if not name:
            return
        pages = self._pages_cache.get(name, [])
        if page_idx >= len(pages):
            return
        try:
            val = int(var.get())
            val = max(10, min(100, val))
        except ValueError:
            return
        if pages[page_idx].scale != val:
            pages[page_idx].scale = val
            _preview_cache.clear()
            self._update_single_page(page_idx)

    def _on_drag_motion(self, event):
        if self._drag_page < 0:
            return
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)

        # 拖拽阈值：鼠标移动超过 8 像素才开始实际拖拽
        if self._drop_target < 0:
            if self._drag_start_x >= 0:
                dx = abs(cx - self._drag_start_x)
                dy = abs(cy - self._drag_start_y)
                if dx < 8 and dy < 8:
                    return

        name = self._selected_name
        if not name:
            return
        pages = self._pages_cache.get(name, [])
        if not pages:
            return

        cols = self._get_cols()
        col = max(0, min(cols - 1, int((cx - PAD) / CELL_W)))
        row = max(0, int((cy - PAD) / CELL_H))
        target = min(row * cols + col, len(pages) - 1)

        if target == self._drop_target:
            return
        self._drop_target = target

        if self._drop_line_id:
            self.canvas.delete(self._drop_line_id)
            self._drop_line_id = None

        if target == self._drag_page:
            return

        tx0, ty0, tx1, ty1 = self._page_rect(target)
        if target > self._drag_page:
            lx = tx1
        else:
            lx = tx0
        self._drop_line_id = self.canvas.create_line(
            lx, ty0, lx, ty1, fill="red", width=3, tags="drop_line")

    def _on_drag_release(self, event):
        if self._drag_page >= 0 and self._drop_target >= 0 and self._drop_target != self._drag_page:
            name = self._selected_name
            if name:
                pages = self._pages_cache[name]
                bases = self._base_images[name]
                pg = pages.pop(self._drag_page)
                bi = bases.pop(self._drag_page)
                pages.insert(self._drop_target, pg)
                bases.insert(self._drop_target, bi)
                self._selected_page = self._drop_target

        if self._drop_line_id:
            self.canvas.delete(self._drop_line_id)
            self._drop_line_id = None

        self._drag_page = -1
        self._drop_target = -1
        self._drag_start_x = -1
        self._drag_start_y = -1
        self._render_gallery()

    def _move_selected(self, direction: int):
        if self._selected_page < 0 or not self._selected_name:
            return
        pages = self._pages_cache[self._selected_name]
        bases = self._base_images[self._selected_name]
        i = self._selected_page
        j = i + direction
        if j < 0 or j >= len(pages):
            return
        pages[i], pages[j] = pages[j], pages[i]
        bases[i], bases[j] = bases[j], bases[i]
        self._selected_page = j
        self._render_gallery()

    def _update_single_page(self, i: int):
        name = self._selected_name
        pages = self._pages_cache[name]
        bases = self._base_images[name]
        pg = pages[i]
        tag = f"page_{i}"

        cols = self._get_cols()
        col = i % cols
        row = i // cols
        x0 = PAD + col * CELL_W
        y0 = PAD + row * CELL_H
        cx = x0 + CELL_W // 2

        self.canvas.delete(tag)

        paper = PAPER_SIZES_MM[self.paper_var.get()]
        base = bases[i] if i < len(bases) else None
        preview = render_preview(pg, base, paper[0], paper[1])

        fname = os.path.basename(pg.source_path)
        label = fname + (f" p{pg.page_idx + 1}" if pg.is_pdf else "")

        if preview:
            photo = ImageTk.PhotoImage(preview)
            self._photo_refs.append(photo)
            self.canvas.create_image(cx, y0 + THUMB_MAX // 2 + 2, image=photo, tags=tag)
        else:
            self.canvas.create_rectangle(x0 + 10, y0 + 10, x0 + CELL_W - 10, y0 + THUMB_MAX,
                                         fill="#ddd", outline="#bbb", tags=tag)
            self.canvas.create_text(cx, y0 + THUMB_MAX // 2, text="(无法预览)",
                                    fill="#888", tags=tag)

        self.canvas.create_text(cx, y0 + THUMB_MAX + 14, text=label,
                                font=("", 8), fill="#333", tags=tag)
        self._draw_checkbox(i, x0 + 4, y0 + 4, pg.enabled)
        if i == self._selected_page:
            self.canvas.create_rectangle(x0 + 1, y0 + 1, x0 + CELL_W - 1, y0 + THUMB_MAX + 2,
                                         outline="#2196F3", width=2, tags=(tag, "sel_highlight"))
        self._draw_badge(i, cx, y0 + THUMB_MAX + 30, pg.orientation)

        scale_y = y0 + THUMB_MAX + 48
        self.canvas.create_text(cx - 24, scale_y, text="缩放:", font=("", 8),
                                fill="#555", anchor="e", tags=tag)
        sv = tk.StringVar(value=str(pg.scale))
        sv.trace_add("write", lambda *_a, idx=i, var=sv: self._on_scale_input(idx, var))
        entry = ttk.Entry(self.canvas, textvariable=sv, width=4, font=("", 8))
        self.canvas.create_window(cx + 8, scale_y, window=entry, anchor="w", tags=tag)
        self.canvas.create_text(cx + 34, scale_y, text="%", font=("", 8),
                                fill="#555", anchor="w", tags=tag)

        enabled_count = sum(1 for p in pages if p.enabled)
        self._orient_hint.config(text=f"共 {len(pages)} 页，已选 {enabled_count} 页")

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ── 批量 ──────────────────────────────────────────────────────────────────

    def _set_all(self, orient: str):
        if not self._selected_name:
            return
        for pg in self._pages_cache.get(self._selected_name, []):
            pg.orientation = orient
        self._render_gallery()

    def _set_enabled_all(self, enabled: bool):
        if not self._selected_name:
            return
        for pg in self._pages_cache.get(self._selected_name, []):
            pg.enabled = enabled
        self._render_gallery()

    def _set_folders_all(self, enabled: bool):
        for var in self._folder_vars.values():
            var.set(enabled)

    def _on_global_scale(self, val):
        if not self._selected_name:
            return
        scale = int(float(val))
        self._global_scale_label.config(text=f"{scale}%")
        _preview_cache.clear()
        for pg in self._pages_cache.get(self._selected_name, []):
            pg.scale = scale
        self._render_gallery()

    # ── 合并 ──────────────────────────────────────────────────────────────────

    def _start(self):
        parent = self.folder_var.get().strip()
        if not parent or not os.path.isdir(parent):
            messagebox.showerror("错误", "请选择一个有效的父文件夹。")
            return
        if not self._subfolders:
            messagebox.showinfo("提示", "没有找到包含匹配文件的子文件夹。")
            return

        try:
            dpi = self._get_dpi()
        except Exception:
            return

        paper_w, paper_h = PAPER_SIZES_MM[self.paper_var.get()]

        active_folders = [(sub, name) for sub, name in self._subfolders
                          if self._folder_vars.get(name, tk.BooleanVar(value=True)).get()]

        if not active_folders:
            messagebox.showinfo("提示", "没有勾选任何子文件夹。")
            return

        for sub, name in active_folders:
            if name not in self._pages_cache:
                entries = collect_files(sub)
                pages = build_page_list(sub, name, entries, "auto")
                self._pages_cache[name] = pages

        overwrites = [name for sub, name in active_folders
                      if os.path.exists(os.path.join(sub, f"{name}.pdf"))]
        if overwrites:
            msg = "以下已有输出 PDF 将被覆盖:\n\n" + "\n".join(f"  • {n}" for n in overwrites)
            msg += "\n\n是否继续？"
            if not messagebox.askyesno("确认覆盖", msg):
                return

        self.start_btn.config(state="disabled")
        self.progress["maximum"] = len(active_folders)
        self.progress["value"] = 0

        def worker():
            count = 0
            for i, (sub, name) in enumerate(active_folders):
                pages = self._pages_cache.get(name, [])
                enabled_pages = [p for p in pages if p.enabled]
                if not enabled_pages:
                    continue
                try:
                    merge_folder(sub, name, enabled_pages, paper_w, paper_h, dpi)
                    count += 1
                except Exception as e:
                    print(f"[{name}] 错误: {e}")
                self.progress["value"] = i + 1
                self.root.update_idletasks()

            self.start_btn.config(state="normal")
            self.root.after(0, lambda: messagebox.showinfo("完成", f"已处理 {count} 个文件夹。"))

        threading.Thread(target=worker, daemon=True).start()
