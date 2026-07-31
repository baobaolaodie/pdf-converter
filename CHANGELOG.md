# Changelog

本文件记录 PDFer 的主要变更。

## [Unreleased] - 2026-07-31

### 新增
- **PDF 导出为图片**：支持将 PDF 每页导出为 PNG 或 JPG 图片
  - CLI 入口：`python main.py --export <pdf> [--format png|jpg] [--dpi N] [--quality N] [--pages ...] [--output-dir ...]`
  - GUI 入口：合并模式右键菜单「导出为图片」+ 编辑模式工具栏「导出为图片」按钮
  - 导出设置对话框：格式、DPI 预设/自定义、JPG 质量预设/自定义、页码范围、输出目录
  - 导出进度对话框：后台线程执行、进度条、完成后显示结果和「打开文件夹」按钮
- **编辑感知导出**：导出反映用户的编辑结果
  - 自动应用页面方向（orientation）、缩放（scale）、图层（layers）
  - 导出对话框自动预填已勾选（enabled）的页面
- **pytest 测试框架**：76 个测试覆盖核心逻辑、CLI、GUI 集成

### 变更
- 应用重命名为 **PDFer**（原名"合并为 PDF"）
- 窗口标题、README、CLAUDE.md、argparse 描述均已更新
- GitHub 仓库重命名为 `pdfer`

### 项目结构
- 新增 `export.py`（导出逻辑 + GUI 对话框）
- 测试文件统一到 `tests/` 目录

## [0.1.0] - 初始版本

### 功能
- 图片合并为 PDF（扫描子文件夹、按文件名排序、批量合并）
- PDF 页面图层编辑（浮动图片：移动、缩放、旋转、透明度）
- 素材栏面板（图片导入、拖放到编辑区）
- 独立编辑模式（`--edit` 打开任意 PDF）
- 画廊视图（缩略图预览、拖拽排序、图层预览）
