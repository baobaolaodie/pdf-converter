# 合并为 PDF

将文件夹中的图片和 PDF 按编号顺序合并为单个 PDF 的桌面工具，支持在 PDF 页面上放置、移动、缩放、旋转浮动图片图层。

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%3E%3D3.10-blue.svg)](https://www.python.org/)

## About

批量扫描文件夹中的图片和 PDF 文件，按文件名编号自动排序，合并输出为单个 PDF。支持逐页调整方向、缩放比例，并提供可视化缩略图预览和拖拽排序。内置图片编辑器，可在 PDF 页面上自由放置浮动图片图层（签名、印章、拼贴等）。

适合需要将大量扫描件、照片或其他图片素材整理为 PDF 的场景。

## Features

- 自动扫描子文件夹，按 `{name}-{num}.{ext}` 命名规则收集并排序
- 支持 jpg / jpeg / png / webp / bmp / tiff / gif 图片及 PDF 文件
- 多种纸张尺寸：A3 / A4 / A5 / Letter / Legal / B5
- 多种 DPI 设置：72 / 96 / 150 / 300 / 自定义
- 每页可单独设置方向（自动 / 纵向 / 横向）和缩放比例（10%–100%）
- 可视化缩略图预览，支持拖拽排序、点击切换方向
- 批量处理多个子文件夹
- 图片编辑器：在 PDF 页面上放置、移动、缩放、旋转浮动图片图层
- 素材栏：批量导入图片，拖放到编辑区
- 双击缩略图进入编辑模式，支持 Ctrl+Z/Y 撤销重做
- 独立编辑模式：直接打开 PDF 文件进行图片叠加编辑（`--edit`）

## Installation

### Requirements

- Python >= 3.10

### Setup

```bash
git clone https://github.com/baobaolaodie/pdf-converter.git
cd pdf-converter

python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux

pip install -r requirements.txt
```

## Usage

```bash
# 通过对话框选择文件夹（合并模式）
python main.py

# 直接指定父文件夹路径
python main.py "D:\Photos\Albums"

# 独立编辑模式：打开 PDF 进行图片编辑
python main.py --edit file.pdf
python main.py --edit
```

合并模式下：

1. 选择包含图片/PDF 的父文件夹
2. 在缩略图中预览、调整页面顺序和方向
3. 双击缩略图可进入图片编辑器，在页面上放置浮动图层
4. 设置纸张尺寸和 DPI
5. 点击合并，每个子文件夹生成一个同名 PDF

编辑器交互：

- 滚轮垂直平移画布，Ctrl+滚轮缩放
- 从素材栏拖动图片到编辑区放置图层
- 点击图层选中后可拖动移动、拖拽句柄缩放/旋转
- Delete 删除选中图层，Ctrl+Z / Ctrl+Y 撤销重做

## Dependencies

| 依赖 | 用途 |
|------|------|
| [Pillow](https://python-pillow.org/) | 图片处理与格式转换 |
| [pypdf](https://github.com/py-pdf/pypdf) | PDF 读写 |
| [PyMuPDF](https://pymupdf.readthedocs.io/) | PDF 页面渲染为预览图 |

GUI 框架：tkinter（标准库）
可选依赖：tkinterdnd2（系统拖放支持，不安装时自动降级为文件对话框导入）

## Project Structure

```
main.py         入口（支持 --edit 参数）
gui.py          MergeApp 协调器（UI 构建、文件夹扫描、合并编排）
gallery.py      GalleryMixin 画廊视图（缩略图渲染、拖拽排序）
standalone.py   StandaloneMixin 独立编辑模式
editor.py       Canvas 图层编辑器 (PageEditor)
core.py         文件收集、页面构建、PDF 合并、图层合成
layers.py       图层数据模型 (Layer, LayerStack)
staging.py      素材栏面板 (StagingPanel)
preview.py      缩略图加载与渲染
constants.py    数据结构 (Page) 与常量定义
```

依赖方向：`constants ← core / preview / layers ← editor / staging ← gallery / standalone ← gui ← main`

## Contributing

欢迎提交 Issue 和 Pull Request。

## License

本项目基于 [MIT 许可证](LICENSE) 开源。
