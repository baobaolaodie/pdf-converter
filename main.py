"""main.py — 入口"""

import sys
import tkinter as tk

from gui import MergeApp


def main():
    initial = sys.argv[1] if len(sys.argv) > 1 else None
    root = tk.Tk()
    MergeApp(root, initial)
    root.mainloop()


if __name__ == "__main__":
    main()
