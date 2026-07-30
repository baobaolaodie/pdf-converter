"""layers.py — 图层数据结构与管理"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image


@dataclass
class Layer:
    image_path: str
    x: float
    y: float
    width: float
    height: float
    rotation: float = 0.0
    opacity: float = 1.0
    pil_image: Image.Image | None = field(default=None, repr=False)

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.width / 2, self.y + self.height / 2)

    def to_dict(self) -> dict:
        return {
            "image_path": self.image_path,
            "x": self.x, "y": self.y,
            "width": self.width, "height": self.height,
            "rotation": self.rotation, "opacity": self.opacity,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Layer:
        return cls(**d)


class LayerStack:
    def __init__(self):
        self.layers: list[Layer] = []
        self.selected_index: int = -1

    def add(self, layer: Layer) -> int:
        self.layers.append(layer)
        self.selected_index = len(self.layers) - 1
        return self.selected_index

    def remove(self, index: int):
        if 0 <= index < len(self.layers):
            self.layers.pop(index)
            if index < self.selected_index:
                self.selected_index -= 1
            elif self.selected_index >= len(self.layers):
                self.selected_index = len(self.layers) - 1

    def move_up(self, index: int):
        if 0 <= index < len(self.layers) - 1:
            self.layers[index], self.layers[index + 1] = self.layers[index + 1], self.layers[index]
            if self.selected_index == index:
                self.selected_index = index + 1
            elif self.selected_index == index + 1:
                self.selected_index = index

    def move_down(self, index: int):
        if 0 < index < len(self.layers):
            self.layers[index], self.layers[index - 1] = self.layers[index - 1], self.layers[index]
            if self.selected_index == index:
                self.selected_index = index - 1
            elif self.selected_index == index - 1:
                self.selected_index = index

    def select(self, index: int):
        if -1 <= index < len(self.layers):
            self.selected_index = index

    def deselect(self):
        self.selected_index = -1

    @property
    def selected(self) -> Layer | None:
        if 0 <= self.selected_index < len(self.layers):
            return self.layers[self.selected_index]
        return None

    def snapshot(self) -> list[dict]:
        return [lyr.to_dict() for lyr in self.layers]
