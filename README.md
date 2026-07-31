# PDFer

将文件夹中的图片和 PDF 按编号顺序合并为单个 PDF 的 Windows 桌面工具，内置图片编辑器，支持在 PDF 页面上放置浮动图层，支持将 PDF 导出为图片。

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%3E%3D3.10-blue.svg)](https://www.python.org/)

## 功能

### 合并

- 扫描父文件夹下的子文件夹，按文件名数字后缀排序，每个子文件夹合并为一个 PDF
- 支持 jpg / jpeg / png / webp / bmp / tiff / gif 图片及 PDF 文件
- 多种纸张尺寸：A3 / A4 / A5 / Letter / Legal / B5（ISO/JIS）
- 多种 DPI：72 / 96 / 150 / 300 / 自定义
- 每页可单独设置方向（自动 / 纵向 / 横向）和缩放比例（10%–100%）
- 可视化缩略图预览，支持拖拽排序、点击切换方向
- 批量处理多个子文件夹

### 图片编辑器

- 在 PDF 页面上放置、移动、缩放、旋转浮动图片图层（签名、印章、水印、拼贴等）
- 双击画廊缩略图进入编辑模式，编辑后缩略图自动显示图层预览
- 素材栏：批量导入图片（文件对话框或从资源管理器拖入），跨页面保留
- 滚轮垂直平移画布，Ctrl+滚轮缩放
- 图层操作：拖动移动、拖拽句柄缩放、拖拽顶部圆点旋转、Delete 删除
- 支持透明 PNG（保留 alpha 通道）
- Ctrl+Z / Ctrl+Y 撤销重做（最多 30 步）
- 独立编辑模式：直接打开任意 PDF 文件进行图片叠加编辑（`--edit`）

### PDF 导出为图片

- 将 PDF 每页导出为 PNG 或 JPG 图片
- 支持 DPI 预设（72/150/300）和自定义
- JPG 质量预设（60/80/95）和自定义
- 页码范围：全部、指定页码（`3`）、范围（`3-7`）、混合（`1,3-5,8`）
- 输出目录默认为 PDF 同目录下同名子文件夹，可自选
- 合并模式右键菜单和编辑模式工具栏均可触发导出

## 快速上手

```bash
git clone https://github.com/baobaolaodie/pdfer.git
cd pdfer

# 方式一：uv（推荐）
uv venv && uv pip install -r requirements.txt

# 方式二：手动 venv
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux
pip install -r requirements.txt
```

```bash
python main.py                     # 选择文件夹 → 预览 → 合并
python main.py "D:\Photos\Albums"  # 直接加载指定文件夹
python main.py --edit file.pdf     # 打开 PDF 进行图片编辑
python main.py --edit              # 弹出文件选择对话框
python main.py --export file.pdf   # 将 PDF 导出为图片
python main.py --export file.pdf --format jpg --dpi 300 --pages 1,3-5
```

## 使用流程

### 合并模式

1. 启动后选择包含图片/PDF 的父文件夹
2. 左侧勾选要处理的子文件夹，右侧预览缩略图
3. 拖拽缩略图调整顺序，点击徽章切换方向，编辑框修改缩放比例
4. 双击缩略图可进入图片编辑器（可选）
5. 设置纸张尺寸和 DPI，点击「开始合并」
6. 每个子文件夹生成一个同名 PDF

### 编辑模式

1. 从素材栏「+ 添加」导入图片，或从资源管理器直接拖入
2. 从素材栏拖动图片到编辑区放置为浮动图层
3. 点击图层选中，拖动移动 / 拖拽角句柄缩放 / 拖拽顶部圆点旋转
4. 工具栏可调整图层层序、删除选中图层
5. 点击「< 返回画廊」回到缩略图视图（素材栏图片保留）

### 独立编辑模式

```bash
python main.py --edit report.pdf   # 打开已有 PDF
python main.py --edit              # 弹出文件选择
```

直接进入编辑器，可翻页编辑每一页。编辑完成后点击「保存 PDF」导出。

## 依赖

| 包 | 最低版本 | 用途 |
|---|---|---|
| [Pillow](https://python-pillow.org/) | 10.0 | 图片加载、格式转换、缩放、PDF 输出 |
| [pypdf](https://github.com/py-pdf/pypdf) | 4.0 | PDF 读写 |
| [PyMuPDF](https://pymupdf.readthedocs.io/) | 1.24 | PDF 页面渲染为像素图 |

GUI 框架：tkinter（Python 标准库）

可选：[tkinterdnd2](https://github.com/pmgagne/tkinterdnd2) — 安装后支持从资源管理器直接拖放文件到素材栏，不安装时使用文件对话框导入。

## 项目结构

```
main.py         入口（--edit / --export 参数）
gui.py          MergeApp 协调器（UI 构建、文件夹扫描、合并编排）
gallery.py      GalleryMixin 画廊视图（缩略图渲染、拖拽排序、图层预览、右键导出）
standalone.py   StandaloneMixin 独立编辑模式
editor.py       Canvas 图层编辑器 (PageEditor)
export.py       PDF 导出为图片（parse_pages、export_pdf、ExportDialog、ExportProgressDialog）
core.py         文件收集、页面构建、PDF 合并、图层合成
layers.py       图层数据模型 (Layer, LayerStack)
staging.py      素材栏面板 (StagingPanel)
preview.py      缩略图加载与渲染
constants.py    数据结构 (Page) 与常量定义
```

依赖方向：`constants ← core / preview / layers / export ← editor / staging ← gallery / standalone ← gui ← main`

## 环境要求

- Python >= 3.10
- Windows 优先（tkinter 文件对话框、venv 路径），tkinter 本身跨平台

## Contributing

欢迎提交 Issue 和 Pull Request。

## License

本项目基于 [MIT 许可证](LICENSE) 开源。
