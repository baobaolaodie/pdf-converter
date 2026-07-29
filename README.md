# 合并为 PDF

将文件夹中的图片和 PDF 按编号顺序合并为单个 PDF 的桌面工具。

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%3E%3D3.10-blue.svg)](https://www.python.org/)

## About

批量扫描文件夹中的图片和 PDF 文件，按文件名编号自动排序，合并输出为单个 PDF。支持逐页调整方向、缩放比例，并提供可视化缩略图预览和拖拽排序。

适合需要将大量扫描件、照片或其他图片素材整理为 PDF 的场景。

## Features

- 自动扫描子文件夹，按 `{name}-{num}.{ext}` 命名规则收集并排序
- 支持 jpg / jpeg / png / webp / bmp / tiff / gif 图片及 PDF 文件
- 多种纸张尺寸：A3 / A4 / A5 / Letter / Legal / B5
- 多种 DPI 设置：72 / 96 / 150 / 300 / 自定义
- 每页可单独设置方向（自动 / 纵向 / 横向）和缩放比例（10%–100%）
- 可视化缩略图预览，支持拖拽排序、点击切换方向
- 批量处理多个子文件夹

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
# 通过对话框选择文件夹
python main.py

# 直接指定父文件夹路径
python main.py "D:\Photos\Albums"
```

程序启动后会显示 GUI 界面：

1. 选择包含图片/PDF 的父文件夹
2. 在缩略图中预览、调整页面顺序和方向
3. 设置纸张尺寸和 DPI
4. 点击合并，每个子文件夹生成一个同名 PDF

## Dependencies

| 依赖 | 用途 |
|------|------|
| [Pillow](https://python-pillow.org/) | 图片处理与格式转换 |
| [pypdf](https://github.com/py-pdf/pypdf) | PDF 读写 |
| [PyMuPDF](https://pymupdf.readthedocs.io/) | PDF 页面渲染为预览图 |

## Project Structure

```
main.py         入口
gui.py          Tkinter GUI 主界面 (MergeApp)
core.py         文件收集、页面构建、PDF 合并逻辑
preview.py      缩略图加载与渲染
constants.py    数据结构 (Page) 与常量定义
```

依赖方向：`constants ← core / preview ← gui ← main`

## Contributing

欢迎提交 Issue 和 Pull Request。

## License

本项目基于 [MIT 许可证](LICENSE) 开源。
