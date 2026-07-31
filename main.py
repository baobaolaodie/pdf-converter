"""main.py — 入口"""

import argparse
import sys
import tkinter as tk

from gui import MergeApp


def main():
    parser = argparse.ArgumentParser(description="PDFer — PDF 批量合并与导出工具")
    parser.add_argument("path", nargs="?", help="父文件夹路径（合并模式）或 PDF 文件路径（--edit 模式）")
    parser.add_argument("--edit", action="store_true", help="进入独立 PDF 编辑模式")
    parser.add_argument("--export", metavar="PDF", help="将 PDF 导出为图片（不启动 GUI）")
    parser.add_argument("--format", choices=["png", "jpg"], default="png", help="导出格式（默认 png）")
    parser.add_argument("--dpi", type=int, default=150, help="导出 DPI（默认 150）")
    parser.add_argument("--quality", type=int, default=95, help="JPG 质量 1-100（默认 95）")
    parser.add_argument("--pages", default="", help="页码，如 1,3-5,8（留空=全部）")
    parser.add_argument("--output-dir", default=None, help="输出目录（默认: PDF 同目录下同名子文件夹）")
    args = parser.parse_args()

    # CLI 导出分支
    if args.export:
        import os
        from export import parse_pages, export_pdf

        pdf_path = args.export
        if not os.path.isfile(pdf_path):
            print(f"错误: 文件不存在: {pdf_path}")
            sys.exit(1)

        try:
            import fitz
            doc = fitz.open(pdf_path)
            total = len(doc)
            doc.close()
        except Exception as e:
            print(f"错误: 无法打开 PDF: {e}")
            sys.exit(1)

        try:
            page_indices = parse_pages(args.pages, total)
        except ValueError as e:
            print(f"错误: {e}")
            sys.exit(1)

        output_dir = args.output_dir or os.path.join(
            os.path.dirname(pdf_path),
            os.path.splitext(os.path.basename(pdf_path))[0],
        )

        def on_progress(cur, total_pages):
            print(f"\r导出中: {cur}/{total_pages}", end="", flush=True)

        result = export_pdf(
            pdf_path, output_dir,
            fmt=args.format, dpi=args.dpi, quality=args.quality,
            pages=page_indices, progress_cb=on_progress,
        )
        print()
        print(f"导出完成: 成功 {result['success']} 页")
        if result["failed"]:
            print(f"  跳过 {len(result['failed'])} 页: {', '.join('#' + str(p[0]) for p in result['failed'])}")
        print(f"输出目录: {result['output_dir']}")
        sys.exit(0)

    root = tk.Tk()
    MergeApp(root, initial_path=args.path, standalone_edit=args.edit)
    root.mainloop()


if __name__ == "__main__":
    main()
