"""tests/test_export_dialog.py — tests for ExportProgressDialog."""

import os
import tkinter as tk
from tkinter import ttk

import fitz
import pytest

from pdfer.export import ExportProgressDialog


@pytest.fixture()
def tmp_pdf(tmp_path):
    """Create a small 3-page PDF for testing."""
    pdf_path = str(tmp_path / "sample.pdf")
    doc = fitz.open()
    for i in range(3):
        page = doc.new_page(width=200, height=200)
        page.insert_text((50, 100), f"Page {i + 1}", fontsize=20)
    doc.save(pdf_path)
    doc.close()
    return pdf_path


def _pump(root, ms=200):
    """Process pending Tk events for *ms* milliseconds.

    Uses mainloop/quit so worker-thread ``after()`` calls work
    (they require the main thread to be inside mainloop).
    """
    root.after(ms, root.quit)
    root.mainloop()


# ---- Test 1: instantiation ----

class TestExportProgressDialogInit:
    """ExportProgressDialog should be creatable with valid params."""

    def test_instantiation(self, _tk_root, tmp_pdf, tmp_path):
        out_dir = str(tmp_path / "out")
        dlg = ExportProgressDialog(
            parent=_tk_root,
            pdf_path=tmp_pdf,
            output_dir=out_dir,
            fmt="png",
            dpi=72,
            quality=95,
            pages=[0, 1, 2],
        )
        try:
            assert dlg.winfo_exists()
            assert dlg.title() == "正在导出"
        finally:
            dlg.destroy()


# ---- Test 2: _result populated after export ----

class TestExportProgressDialogResult:
    """After the background export finishes, _result should be set."""

    def test_result_populated(self, _tk_root, tmp_pdf, tmp_path):
        out_dir = str(tmp_path / "out")
        dlg = ExportProgressDialog(
            parent=_tk_root,
            pdf_path=tmp_pdf,
            output_dir=out_dir,
            fmt="png",
            dpi=72,
            quality=95,
            pages=[0, 1, 2],
        )
        try:
            # Wait for the background thread to finish and after() callback
            import time
            deadline = time.monotonic() + 10
            while dlg._result is None and time.monotonic() < deadline:
                _pump(_tk_root, 100)

            assert dlg._result is not None
            r = dlg._result
            assert r["success"] == 3
            assert r["failed"] == []
            assert r["output_dir"] == out_dir
        finally:
            dlg.destroy()


# ---- Test 3: result view shows correct info ----

class TestExportProgressDialogResultView:
    """After export, the dialog should show success count and output dir."""

    def test_result_view_success(self, _tk_root, tmp_pdf, tmp_path):
        out_dir = str(tmp_path / "out")
        dlg = ExportProgressDialog(
            parent=_tk_root,
            pdf_path=tmp_pdf,
            output_dir=out_dir,
            fmt="png",
            dpi=72,
            quality=95,
            pages=[0, 1, 2],
        )
        try:
            import time
            deadline = time.monotonic() + 10
            while dlg._result is None and time.monotonic() < deadline:
                _pump(_tk_root, 100)

            # _show_result is triggered via after(0, ...); pump once more
            _pump(_tk_root, 100)

            # Find all labels in the dialog
            labels = _find_labels(dlg)
            label_texts = [lbl.cget("text") for lbl in labels]

            # Should contain success message
            assert any("3" in t and "成功" in t for t in label_texts), (
                f"Expected success label with '3', got: {label_texts}"
            )

            # Should contain output dir
            assert any(out_dir in t for t in label_texts), (
                f"Expected output dir label, got: {label_texts}"
            )

            # Should have an "打开文件夹" button
            buttons = _find_buttons(dlg)
            btn_texts = [b.cget("text") for b in buttons]
            assert "打开文件夹" in btn_texts, f"Expected '打开文件夹' button, got: {btn_texts}"
            assert "关闭" in btn_texts, f"Expected '关闭' button, got: {btn_texts}"
        finally:
            dlg.destroy()


# ---- Test 4: result view shows failed pages ----

class TestExportProgressDialogResultViewFailed:
    """When some pages fail, the dialog should show failed page numbers."""

    def test_result_view_with_failures(self, _tk_root, tmp_path):
        """Create a 1-page valid PDF, request non-existent page indices to force failures."""
        pdf_path = str(tmp_path / "onepage.pdf")
        doc = fitz.open()
        doc.new_page(width=200, height=200)
        doc.save(pdf_path)
        doc.close()

        out_dir = str(tmp_path / "out")
        # Request pages [0, 5, 99] — only page 0 exists; 5 and 99 will fail
        dlg = ExportProgressDialog(
            parent=_tk_root,
            pdf_path=pdf_path,
            output_dir=out_dir,
            fmt="png",
            dpi=72,
            quality=95,
            pages=[0, 5, 99],
        )
        try:
            import time
            deadline = time.monotonic() + 10
            while dlg._result is None and time.monotonic() < deadline:
                _pump(_tk_root, 100)

            _pump(_tk_root, 100)

            r = dlg._result
            assert r["success"] == 1
            assert len(r["failed"]) == 2

            # Check labels for failure info
            labels = _find_labels(dlg)
            label_texts = [lbl.cget("text") for lbl in labels]

            # Should show "跳过 2 页" with page numbers
            assert any("跳过" in t and "2" in t for t in label_texts), (
                f"Expected failure label with '跳过 2', got: {label_texts}"
            )
        finally:
            dlg.destroy()


# ---- helpers ----

def _find_labels(parent):
    """Recursively find all ttk.Label widgets."""
    result = []
    for w in parent.winfo_children():
        if isinstance(w, ttk.Label):
            result.append(w)
        result.extend(_find_labels(w))
    return result


def _find_buttons(parent):
    """Recursively find all ttk.Button widgets."""
    result = []
    for w in parent.winfo_children():
        if isinstance(w, ttk.Button):
            result.append(w)
        result.extend(_find_buttons(w))
    return result
