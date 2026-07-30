"""gallery.py — 画廊视图：缩略图渲染、点击/拖拽排序、批量操作"""

import os
import tkinter as tk
from tkinter import ttk

from PIL import ImageTk

from constants import (
    PAPER_SIZES_MM, ORIENT_LABELS, ORIENT_SYMBOLS, ORIENT_COLORS, ORIENT_NAMES,
    CELL_W, CELL_H, PAD, THUMB_MAX,
)
from preview import render_preview, _preview_cache


class GalleryMixin:
    """MergeApp 的画廊渲染与交互 mixin。"""

    # ── 布局 ──

    def _on_canvas_resize(self, event):
        new_w = event.width
        if abs(new_w - self._last_gallery_width) > CELL_W:
            self._last_gallery_width = new_w
            if self._selected_name:
                self._render_gallery()

    def _get_cols(self) -> int:
        w = self.canvas.winfo_width()
        return max(1, (w - PAD) // CELL_W) if w > 50 else 4

    def _page_rect(self, i: int) -> tuple[int, int, int, int]:
        cols = self._get_cols()
        col = i % cols
        row = i // cols
        x0 = PAD + col * CELL_W
        y0 = PAD + row * CELL_H
        return x0, y0, x0 + CELL_W, y0 + CELL_H

    # ── 渲染 ──

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

    # ── 点击/拖拽 ──

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

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ── 批量操作 ──

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
