"""main.py — 入口"""

import argparse
import sys
import tkinter as tk

from gui import MergeApp


def main():
    parser = argparse.ArgumentParser(description="合并为 PDF")
    parser.add_argument("path", nargs="?", help="父文件夹路径（合并模式）或 PDF 文件路径（--edit 模式）")
    parser.add_argument("--edit", action="store_true", help="进入独立 PDF 编辑模式")
    args = parser.parse_args()

    root = tk.Tk()
    MergeApp(root, initial_path=args.path, standalone_edit=args.edit)
    root.mainloop()


if __name__ == "__main__":
    main()
