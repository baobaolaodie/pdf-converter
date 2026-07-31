"""gui.py — Tkinter GUI 主界面（协调器）"""

import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import Image, ImageTk

from constants import (
    Page, PAPER_SIZES_MM, IMAGE_EXTS,
)
from core import collect_files, build_page_list, merge_folder
from preview import _load_base_image, _preview_cache
from editor import PageEditor
from staging import StagingPanel
from gallery import GalleryMixin
from standalone import StandaloneMixin
from export import ExportDialog, ExportProgressDialog


class MergeApp(GalleryMixin, StandaloneMixin):
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
        self._staging_paths: list[str] = []
        self._standalone_edit = standalone_edit

        self._build_ui()

        self._entry.bind("<Return>", lambda e: self._scan_folders())
        self._entry.bind("<FocusOut>", lambda e: self._scan_folders())
        self._last_scanned_path: str = ""

        if initial_path:
            self.root.after(100, self._scan_folders)

        if standalone_edit:
            self.root.after(100, self._start_standalone_edit)

    # ── UI 构建 ──────────────────────────────────────────────────────────────

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

        # 右键菜单
        self._context_menu = tk.Menu(self.canvas, tearoff=0)
        self._context_menu.add_command(label="导出为图片", command=self._export_from_gallery)
        self.canvas.bind("<Button-3>", self._show_context_menu)

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

    # ── DPI ──────────────────────────────────────────────────────────────────

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

    # ── 文件夹 ───────────────────────────────────────────────────────────────

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

    # ── 编辑模式入口 ─────────────────────────────────────────────────────────

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

    # ── 右键导出 ───────────────────────────────────────────────────────────

    def _show_context_menu(self, event):
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        page_idx = self._hit_test_page(cx, cy)
        if page_idx is None:
            return
        self._selected_page = page_idx
        self._render_gallery()
        self._context_menu.tk_popup(event.x_root, event.y_root)

    def _export_from_gallery(self):
        if not self._selected_name:
            return
        pages = self._pages_cache.get(self._selected_name, [])
        if not pages:
            return
        # 找到第一个 PDF 页面的路径
        pdf_path = None
        for pg in pages:
            if pg.is_pdf:
                pdf_path = pg.source_path
                break
        if pdf_path is None:
            messagebox.showinfo("提示", "当前文件夹没有 PDF 文件可导出。")
            return

        dialog = ExportDialog(self.root, pdf_path)
        self.root.wait_window(dialog)
        if dialog._result:
            r = dialog._result
            ExportProgressDialog(
                self.root, r["pdf_path"], r["output_dir"],
                r["fmt"], r["dpi"], r["quality"], r["pages"],
            )

    def _export_from_editor(self):
        if not self._selected_name:
            return
        pages = self._pages_cache.get(self._selected_name, [])
        if not pages:
            return
        pdf_path = None
        for pg in pages:
            if pg.is_pdf:
                pdf_path = pg.source_path
                break
        if pdf_path is None:
            messagebox.showinfo("提示", "当前没有 PDF 文件可导出。")
            return

        dialog = ExportDialog(self.root, pdf_path)
        self.root.wait_window(dialog)
        if dialog._result:
            r = dialog._result
            ExportProgressDialog(
                self.root, r["pdf_path"], r["output_dir"],
                r["fmt"], r["dpi"], r["quality"], r["pages"],
            )

    def _enter_edit_mode(self, page_idx: int):
        self._edit_mode = True
        paper = PAPER_SIZES_MM[self.paper_var.get()]

        self.canvas.pack_forget()
        self._scrollbar.pack_forget()

        self._editor_container = ttk.Frame(self.canvas.master)
        self._editor_container.pack(fill="both", expand=True)

        self._editor = PageEditor(self._editor_container, paper[0], paper[1],
                                   on_back=self._exit_edit_mode)
        self._editor.pack(side="left", fill="both", expand=True)

        # 编辑模式导出按钮
        ttk.Button(self._editor._toolbar, text="导出为图片",
                   command=self._export_from_editor).pack(side="right", padx=4)

        name = self._selected_name
        pages = self._pages_cache[name]
        bases = self._base_images[name]
        self._editor.set_context(pages, bases)
        self._editor.load_page(page_idx, pages, bases)

        self._staging = StagingPanel(self._editor_container,
                                      get_editor=lambda: self._editor)
        if self._staging_paths:
            self._staging.add_files(self._staging_paths)
        self._staging.pack(side="right", fill="y", padx=(4, 0))

    def _exit_edit_mode(self):
        if self._staging and self._staging._images:
            self._staging_paths = [simg.path for simg in self._staging._images]
        if self._editor:
            self._editor.sync_current_layers()
        if hasattr(self, '_editor_container') and self._editor_container:
            self._editor_container.destroy()
        self._editor = None
        self._staging = None
        self._edit_mode = False

        _preview_cache.clear()
        self._scrollbar.pack(in_=self.canvas.master, side="right", fill="y")
        self.canvas.pack(in_=self.canvas.master, side="left", fill="both", expand=True)
        self._render_gallery()

    # ── 合并 ─────────────────────────────────────────────────────────────────

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
