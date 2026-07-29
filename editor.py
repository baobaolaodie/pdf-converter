"""editor.py — Canvas 图层编辑器"""

from __future__ import annotations
import math
import os
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from PIL import Image, ImageTk

from constants import (
    Page, PAPER_SIZES_MM, HANDLE_SIZE, ROTATE_OFFSET,
    HANDLE_COLOR, SELECT_COLOR, IMAGE_EXTS,
)
from layers import Layer, LayerStack

if TYPE_CHECKING:
    from staging import StagingImage


class PageEditor(ttk.Frame):
    """在 Canvas 上编辑单个 PDF 页面的浮动图片图层"""

    def __init__(self, master, paper_w_mm: float, paper_h_mm: float):
        super().__init__(master)
        self._paper_w_mm = paper_w_mm
        self._paper_h_mm = paper_h_mm

        self._layer_stacks: dict[int, LayerStack] = {}
        self._page_index: int = -1
        self._page_image: ImageTk.PhotoImage | None = None
        self._page_pil: Image.Image | None = None
        self._pil_cache: dict[str, Image.Image] = {}

        # Canvas 变换
        self._scale_factor: float = 1.0
        self._offset_x: float = 0.0
        self._offset_y: float = 0.0

        # 交互状态
        self._interaction: str = ""  # "", "drag", "resize", "rotate", "pan"
        self._interact_data: dict = {}

        # Canvas item 引用
        self._bg_item: int | None = None
        self._layer_items: dict[int, list[int]] = {}
        self._handle_items: list[int] = []
        self._photo_refs: list[ImageTk.PhotoImage] = []

        # 页面上下文（由 set_context 设置）
        self._pages: list[Page] = []
        self._base_images: list = []

        # Undo/Redo
        self._undo_stack: list[tuple[int, list[dict]]] = []
        self._redo_stack: list[tuple[int, list[dict]]] = []
        self._MAX_UNDO = 30

        self._build()

    def _build(self):
        self._build_toolbar()
        self._build_canvas()

    def _build_toolbar(self):
        self._toolbar = ttk.Frame(self)
        self._toolbar.pack(fill="x", padx=4, pady=2)
        self._btn_back = ttk.Button(self._toolbar, text="< 返回画廊", command=lambda: self._on_back())
        self._btn_back.pack(side="left")
        self._page_label = ttk.Label(self._toolbar, text="", font=("", 10))
        self._page_label.pack(side="left", padx=12)
        ttk.Button(self._toolbar, text="上一页", command=lambda: self.navigate(-1)).pack(side="left", padx=2)
        ttk.Button(self._toolbar, text="下一页", command=lambda: self.navigate(1)).pack(side="left", padx=2)

        ttk.Button(self._toolbar, text="删除选中", command=self.delete_selected).pack(side="right", padx=2)
        ttk.Button(self._toolbar, text="上移层", command=lambda: self._move_layer(1)).pack(side="right", padx=2)
        ttk.Button(self._toolbar, text="下移层", command=lambda: self._move_layer(-1)).pack(side="right", padx=2)

    def _build_canvas(self):
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(body, bg="#e0e0e0", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Configure>", self._on_configure)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-2>", self._on_mid_press)
        self.canvas.bind("<B2-Motion>", self._on_mid_motion)
        self.canvas.bind("<ButtonRelease-2>", self._on_mid_release)
        self.canvas.bind("<Delete>", lambda e: self.delete_selected())
        self.canvas.bind("<BackSpace>", lambda e: self.delete_selected())
        self.canvas.bind("<Control-z>", lambda e: self.undo())
        self.canvas.bind("<Control-y>", lambda e: self.redo())
        self.canvas.focus_set()

    # ── 坐标变换 ──

    def _page_to_canvas(self, px: float, py: float) -> tuple[float, float]:
        return px * self._scale_factor + self._offset_x, py * self._scale_factor + self._offset_y

    def _canvas_to_page(self, cx: float, cy: float) -> tuple[float, float]:
        return (cx - self._offset_x) / self._scale_factor, (cy - self._offset_y) / self._scale_factor

    def _size_to_canvas(self, s: float) -> float:
        return s * self._scale_factor

    def _size_to_page(self, s: float) -> float:
        return s / self._scale_factor

    # ── 页面加载 ──

    def load_page(self, page_index: int, pages: list[Page], base_images: list):
        self._page_index = page_index
        pg = pages[page_index]

        if page_index not in self._layer_stacks:
            if pg.layers:
                self._layer_stacks[page_index] = self._restore_stack(pg.layers)
            else:
                self._layer_stacks[page_index] = LayerStack()

        base = base_images[page_index] if page_index < len(base_images) else None
        if base is not None:
            self._page_pil = self._render_base(pg, base)
            self._page_image = ImageTk.PhotoImage(self._page_pil)
        else:
            self._page_pil = None
            self._page_image = None

        self._update_page_label(len(pages))
        self._fit_to_canvas()
        self._redraw()

    def _render_base(self, pg: Page, base_img: Image.Image) -> Image.Image:
        img = base_img
        if pg.orientation != "auto":
            use_land = (pg.orientation == "landscape")
            page_is_land = (pg.orig_w > pg.orig_h) if pg.is_pdf else (img.width > img.height)
            if use_land != page_is_land:
                img = img.rotate(-90, expand=True)
        return img

    def _fit_to_canvas(self):
        if self._page_pil is None:
            return
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 50 or ch < 50:
            cw, ch = 800, 600
        pw, ph = self._page_pil.size
        self._scale_factor = min(cw / pw, ch / ph) * 0.9
        self._offset_x = (cw - pw * self._scale_factor) / 2
        self._offset_y = (ch - ph * self._scale_factor) / 2

    def _on_configure(self, event):
        if self._page_pil:
            old_sf = self._scale_factor
            self._fit_to_canvas()
            if old_sf != self._scale_factor:
                self._redraw()

    def _update_page_label(self, total: int):
        self._page_label.config(text=f"页面 {self._page_index + 1}/{total}")

    # ── 翻页 ──

    def navigate(self, direction: int):
        new_idx = self._page_index + direction
        if 0 <= new_idx < len(self._pages):
            self._sync_layers_to_page()
            self.load_page(new_idx, self._pages, self._base_images)

    def set_context(self, pages: list[Page], base_images: list):
        self._pages = pages
        self._base_images = base_images

    def _restore_stack(self, layer_dicts: list[dict]) -> LayerStack:
        stack = LayerStack()
        for d in layer_dicts:
            lyr = Layer.from_dict(d)
            lyr.pil_image = self._pil_cache.get(lyr.image_path)
            if lyr.pil_image is None:
                try:
                    img = Image.open(lyr.image_path)
                    if img.mode in ("RGBA", "P", "LA"):
                        img = img.convert("RGBA") if img.mode != "RGBA" else img
                    self._pil_cache[lyr.image_path] = img
                    lyr.pil_image = img
                except Exception:
                    continue
            stack.layers.append(lyr)
        return stack

    def _sync_layers_to_page(self):
        if self._pages and 0 <= self._page_index < len(self._pages):
            stack = self._layer_stacks.get(self._page_index)
            if stack and stack.layers:
                self._pages[self._page_index].layers = stack.snapshot()
            elif stack and not stack.layers:
                self._pages[self._page_index].layers = None

    # ── Canvas 绘制 ──

    def _redraw(self):
        self.canvas.delete("all")
        self._layer_items.clear()
        self._handle_items.clear()

        if self._page_image:
            pw, ph = self._page_pil.size
            cx, cy = self._page_to_canvas(pw / 2, ph / 2)
            self._bg_item = self.canvas.create_image(cx, cy, image=self._page_image)

        stack = self._layer_stacks.get(self._page_index)
        if not stack:
            return
        for i, layer in enumerate(stack.layers):
            self._draw_layer(i, layer)

        if stack.selected_index >= 0 and stack.selected_index < len(stack.layers):
            self._draw_handles(stack.layers[stack.selected_index])

    def _draw_layer(self, idx: int, layer: Layer):
        if layer.pil_image is None:
            return

        cx, cy = self._page_to_canvas(layer.x + layer.width / 2,
                                       layer.y + layer.height / 2)
        cw = self._size_to_canvas(layer.width)
        ch = self._size_to_canvas(layer.height)

        disp_w = max(1, int(cw))
        disp_h = max(1, int(ch))
        img = layer.pil_image.resize((disp_w, disp_h), Image.LANCZOS)
        if layer.rotation != 0:
            img = img.rotate(-layer.rotation, expand=True, resample=Image.BICUBIC)

        photo = ImageTk.PhotoImage(img)
        self._photo_refs.append(photo)

        item = self.canvas.create_image(cx, cy, image=photo, tags=f"layer_{idx}")
        self._layer_items[idx] = [item]

    def _draw_handles(self, layer: Layer):
        cx, cy = self._page_to_canvas(layer.x + layer.width / 2,
                                       layer.y + layer.height / 2)
        hw = self._size_to_canvas(layer.width) / 2
        hh = self._size_to_canvas(layer.height) / 2

        rid = self.canvas.create_rectangle(
            cx - hw, cy - hh, cx + hw, cy + hh,
            outline=SELECT_COLOR, width=1, dash=(4, 4), tags="handles"
        )
        self._handle_items.append(rid)

        positions = [
            (cx - hw, cy - hh), (cx, cy - hh), (cx + hw, cy - hh),
            (cx - hw, cy), (cx + hw, cy),
            (cx - hw, cy + hh), (cx, cy + hh), (cx + hw, cy + hh),
        ]
        hs = HANDLE_SIZE / 2
        for hx, hy in positions:
            hid = self.canvas.create_rectangle(
                hx - hs, hy - hs, hx + hs, hy + hs,
                fill=HANDLE_COLOR, outline="white", width=1, tags="handles"
            )
            self._handle_items.append(hid)

        ry = cy - hh - ROTATE_OFFSET
        lid = self.canvas.create_line(cx, cy - hh, cx, ry,
                                       fill=HANDLE_COLOR, width=1, tags="handles")
        self._handle_items.append(lid)
        rid2 = self.canvas.create_oval(
            cx - 5, ry - 5, cx + 5, ry + 5,
            fill=HANDLE_COLOR, outline="white", width=1, tags="handles"
        )
        self._handle_items.append(rid2)

    # ── 命中检测 ──

    def _hit_test(self, cx: float, cy: float) -> tuple[str, int]:
        stack = self._layer_stacks.get(self._page_index)
        if not stack or not stack.layers:
            return ("none", -1)

        if stack.selected_index >= 0 and stack.selected_index < len(stack.layers):
            layer = stack.layers[stack.selected_index]
            lcx, lcy = self._page_to_canvas(layer.x + layer.width / 2,
                                             layer.y + layer.height / 2)
            lhh = self._size_to_canvas(layer.height) / 2
            ry = lcy - lhh - ROTATE_OFFSET
            if math.hypot(cx - lcx, cy - ry) < 8:
                return ("rotate", 0)

        if stack.selected_index >= 0 and stack.selected_index < len(stack.layers):
            layer = stack.layers[stack.selected_index]
            lcx, lcy = self._page_to_canvas(layer.x + layer.width / 2,
                                             layer.y + layer.height / 2)
            lhw = self._size_to_canvas(layer.width) / 2
            lhh = self._size_to_canvas(layer.height) / 2
            positions = [
                (lcx - lhw, lcy - lhh), (lcx, lcy - lhh), (lcx + lhw, lcy - lhh),
                (lcx - lhw, lcy), (lcx + lhw, lcy),
                (lcx - lhw, lcy + lhh), (lcx, lcy + lhh), (lcx + lhw, lcy + lhh),
            ]
            for i, (hx, hy) in enumerate(positions):
                if abs(cx - hx) < HANDLE_SIZE and abs(cy - hy) < HANDLE_SIZE:
                    return ("handle", i)

        for i in range(len(stack.layers) - 1, -1, -1):
            layer = stack.layers[i]
            lcx, lcy = self._page_to_canvas(layer.x + layer.width / 2,
                                             layer.y + layer.height / 2)
            lhw = self._size_to_canvas(layer.width) / 2
            lhh = self._size_to_canvas(layer.height) / 2
            if (lcx - lhw <= cx <= lcx + lhw and lcy - lhh <= cy <= lcy + lhh):
                return ("layer", i)

        return ("none", -1)

    def _push_undo(self):
        stack = self._layer_stacks.get(self._page_index)
        if not stack:
            return
        self._undo_stack.append((self._page_index, stack.snapshot()))
        if len(self._undo_stack) > self._MAX_UNDO:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    # ── 鼠标交互 ──

    def _on_press(self, event):
        cx, cy = event.x, event.y
        hit_type, hit_idx = self._hit_test(cx, cy)
        stack = self._layer_stacks.get(self._page_index)
        if not stack:
            return

        if hit_type == "rotate":
            self._push_undo()
            layer = stack.selected
            lcx, lcy = self._page_to_canvas(layer.x + layer.width / 2,
                                             layer.y + layer.height / 2)
            self._interaction = "rotate"
            self._interact_data = {"start_angle": math.degrees(math.atan2(cy - lcy, cx - lcx)),
                                    "orig_rotation": layer.rotation,
                                    "center_cx": lcx, "center_cy": lcy}
        elif hit_type == "handle":
            self._push_undo()
            self._interaction = "resize"
            self._interact_data = {"handle_idx": hit_idx, "start_cx": cx, "start_cy": cy,
                                    "orig_x": stack.selected.x, "orig_y": stack.selected.y,
                                    "orig_w": stack.selected.width, "orig_h": stack.selected.height}
        elif hit_type == "layer":
            self._push_undo()
            stack.select(hit_idx)
            self._interaction = "drag"
            px, py = self._canvas_to_page(cx, cy)
            layer = stack.selected
            self._interact_data = {"offset_px": px - layer.x, "offset_py": py - layer.y}
            self._redraw()
        else:
            stack.deselect()
            self._interaction = ""
            self._redraw()

    def _on_motion(self, event):
        if not self._interaction:
            return
        cx, cy = event.x, event.y
        stack = self._layer_stacks.get(self._page_index)
        if not stack or not stack.selected:
            return
        layer = stack.selected

        if self._interaction == "drag":
            px, py = self._canvas_to_page(cx, cy)
            layer.x = px - self._interact_data["offset_px"]
            layer.y = py - self._interact_data["offset_py"]
            self._redraw()

        elif self._interaction == "resize":
            d = self._interact_data
            dx_page = self._size_to_page(cx - d["start_cx"])
            dy_page = self._size_to_page(cy - d["start_cy"])
            hi = d["handle_idx"]

            new_x, new_y = d["orig_x"], d["orig_y"]
            new_w, new_h = d["orig_w"], d["orig_h"]

            if hi in (0, 3, 5):
                new_x = d["orig_x"] + dx_page
                new_w = d["orig_w"] - dx_page
            if hi in (2, 4, 7):
                new_w = d["orig_w"] + dx_page
            if hi in (0, 1, 2):
                new_y = d["orig_y"] + dy_page
                new_h = d["orig_h"] - dy_page
            if hi in (5, 6, 7):
                new_h = d["orig_h"] + dy_page

            if event.state & 0x1:
                ratio = d["orig_w"] / max(1, d["orig_h"])
                if abs(dx_page) > abs(dy_page):
                    new_h = new_w / ratio
                else:
                    new_w = new_h * ratio

            if new_w > 10 and new_h > 10:
                layer.x, layer.y = new_x, new_y
                layer.width, layer.height = new_w, new_h
                self._redraw()

        elif self._interaction == "rotate":
            d = self._interact_data
            angle = math.degrees(math.atan2(cy - d["center_cy"], cx - d["center_cx"]))
            layer.rotation = d["orig_rotation"] + (angle - d["start_angle"])
            self._redraw()

    def _on_release(self, event):
        self._interaction = ""
        self._interact_data = {}

    # ── 中键平移 ──

    def _on_mid_press(self, event):
        self._interaction = "pan"
        self._interact_data = {"start_x": event.x, "start_y": event.y,
                                "orig_ox": self._offset_x, "orig_oy": self._offset_y}

    def _on_mid_motion(self, event):
        if self._interaction == "pan":
            d = self._interact_data
            self._offset_x = d["orig_ox"] + (event.x - d["start_x"])
            self._offset_y = d["orig_oy"] + (event.y - d["start_y"])
            self._redraw()

    def _on_mid_release(self, event):
        if self._interaction == "pan":
            self._interaction = ""
            self._interact_data = {}

    # ── 滚轮缩放 ──

    def _on_mousewheel(self, event):
        delta = event.delta / 120
        factor = 1.1 if delta > 0 else 0.9
        old_sf = self._scale_factor
        self._scale_factor *= factor
        self._scale_factor = max(0.1, min(5.0, self._scale_factor))
        real_x = (event.x - self._offset_x) / old_sf
        real_y = (event.y - self._offset_y) / old_sf
        self._offset_x = event.x - real_x * self._scale_factor
        self._offset_y = event.y - real_y * self._scale_factor
        self._redraw()

    # ── 图层操作 ──

    def add_layer_from_staging(self, simg: StagingImage, canvas_x: float, canvas_y: float):
        stack = self._layer_stacks.get(self._page_index)
        if not stack:
            return
        self._push_undo()

        img = simg.pil_img
        if img.mode not in ("RGBA",):
            img = img.convert("RGBA")
        self._pil_cache[simg.path] = img

        if self._page_pil:
            max_w = self._page_pil.size[0] * 0.5
            max_h = self._page_pil.size[1] * 0.5
        else:
            max_w, max_h = 400, 400
        iw, ih = img.size
        scale = min(max_w / iw, max_h / ih, 1.0)
        w, h = iw * scale, ih * scale

        px, py = self._canvas_to_page(canvas_x, canvas_y)
        layer = Layer(image_path=simg.path, x=px - w / 2, y=py - h / 2,
                      width=w, height=h, pil_image=img)
        stack.add(layer)
        self._redraw()

    def delete_selected(self):
        stack = self._layer_stacks.get(self._page_index)
        if not stack or stack.selected_index < 0:
            return
        self._push_undo()
        stack.remove(stack.selected_index)
        self._redraw()

    def _move_layer(self, direction: int):
        stack = self._layer_stacks.get(self._page_index)
        if not stack or stack.selected_index < 0:
            return
        self._push_undo()
        if direction > 0:
            stack.move_up(stack.selected_index)
        else:
            stack.move_down(stack.selected_index)
        self._redraw()

    def set_opacity(self, opacity: float):
        stack = self._layer_stacks.get(self._page_index)
        if stack and stack.selected:
            self._push_undo()
            stack.selected.opacity = max(0.0, min(1.0, opacity))

    # ── Undo / Redo ──

    def undo(self):
        if not self._undo_stack:
            return
        stack = self._layer_stacks.get(self._page_index)
        if stack:
            self._redo_stack.append((self._page_index, stack.snapshot()))
        page_idx, snap = self._undo_stack.pop()
        self._layer_stacks[page_idx] = self._restore_stack(snap)
        self._page_index = page_idx
        self._redraw()

    def redo(self):
        if not self._redo_stack:
            return
        stack = self._layer_stacks.get(self._page_index)
        if stack:
            self._undo_stack.append((self._page_index, stack.snapshot()))
        page_idx, snap = self._redo_stack.pop()
        self._layer_stacks[page_idx] = self._restore_stack(snap)
        self._page_index = page_idx
        self._redraw()

    # ── 导出 ──

    def get_stacks(self) -> dict[int, LayerStack]:
        return self._layer_stacks

    def sync_current_layers(self):
        self._sync_layers_to_page()

    def _on_back(self):
        pass


def composite_layers(base_img: Image.Image, layer_dicts: list[dict]) -> Image.Image:
    """将图层合成到底图上。接受 Layer dict 列表（可序列化格式）。"""
    result = base_img.copy()
    for d in layer_dicts:
        path = d["image_path"]
        try:
            img = Image.open(path)
            if img.mode not in ("RGBA",):
                img = img.convert("RGBA")
        except Exception:
            continue

        w, h = int(d["width"]), int(d["height"])
        img = img.resize((w, h), Image.LANCZOS)

        rot = d.get("rotation", 0.0)
        if rot != 0:
            img = img.rotate(-rot, expand=True, resample=Image.BICUBIC)

        opacity = d.get("opacity", 1.0)
        if opacity < 1.0 and img.mode == "RGBA":
            alpha = img.getchannel("A")
            from PIL import Image as PILImage
            alpha = PILImage.blend(alpha, PILImage.new("L", img.size, 0), 1 - opacity)
            img.putalpha(alpha)

        x, y = int(d["x"]), int(d["y"])
        if result.mode not in ("RGBA", "RGB"):
            result = result.convert("RGB")
        if img.mode == "RGBA":
            result.paste(img, (x, y), mask=img)
        else:
            result.paste(img, (x, y))
    return result
