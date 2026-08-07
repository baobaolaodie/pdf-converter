"""tests for export.parse_pages, export.export_pdf, and ExportDialog"""

import os
import tempfile
import tkinter as tk

import fitz
import pytest
from pdfer.export import export_pdf, parse_pages


def test_empty_means_all():
    assert parse_pages("", 5) == [0, 1, 2, 3, 4]


def test_whitespace_means_all():
    assert parse_pages("   ", 5) == [0, 1, 2, 3, 4]


def test_all_means_all():
    assert parse_pages("all", 5) == [0, 1, 2, 3, 4]


def test_all_case_insensitive():
    assert parse_pages("ALL", 5) == [0, 1, 2, 3, 4]
    assert parse_pages("All", 5) == [0, 1, 2, 3, 4]


def test_single_page():
    assert parse_pages("3", 5) == [2]


def test_single_page_first():
    assert parse_pages("1", 5) == [0]


def test_single_page_last():
    assert parse_pages("5", 5) == [4]


def test_range():
    assert parse_pages("3-7", 10) == [2, 3, 4, 5, 6]


def test_range_from_start():
    assert parse_pages("1-3", 5) == [0, 1, 2]


def test_range_to_end():
    assert parse_pages("3-5", 5) == [2, 3, 4]


def test_range_same_page():
    assert parse_pages("3-3", 5) == [2]


def test_mixed():
    assert parse_pages("1,3-5,8", 10) == [0, 2, 3, 4, 7]


def test_mixed_with_spaces():
    assert parse_pages(" 1 , 3 - 5 , 8 ", 10) == [0, 2, 3, 4, 7]


def test_mixed_overlapping():
    # 3 appears in both single and range; result should be deduplicated
    assert parse_pages("3,3-5", 10) == [2, 3, 4]


def test_out_of_range_single_raises():
    with pytest.raises(ValueError, match="超出范围"):
        parse_pages("11", 10)


def test_out_of_range_in_range_raises():
    with pytest.raises(ValueError, match="超出范围"):
        parse_pages("8-11", 10)


def test_zero_page_raises():
    with pytest.raises(ValueError, match="必须 >= 1"):
        parse_pages("0", 5)


def test_negative_page_raises():
    # "-1" contains "-" so it's parsed as a range; either invalid range or >= 1
    with pytest.raises(ValueError):
        parse_pages("-1", 5)


def test_invalid_number_raises():
    with pytest.raises(ValueError, match="无效页码"):
        parse_pages("abc", 5)


def test_invalid_range_raises():
    with pytest.raises(ValueError, match="无效页码范围"):
        parse_pages("5-3", 10)


def test_total_pages_1():
    assert parse_pages("1", 1) == [0]
    with pytest.raises(ValueError):
        parse_pages("2", 1)


# ── export_pdf tests ──────────────────────────────────────────────


def _make_tiny_pdf(path: str, n_pages: int = 3, width: float = 200,
                   height: float = 200) -> None:
    """Create a minimal PDF with n_pages blank pages using fitz."""
    doc = fitz.open()
    for _ in range(n_pages):
        doc.new_page(width=width, height=height)
    doc.save(path)
    doc.close()


def test_export_creates_output_files():
    """Smoke test: export all pages of a tiny PDF, verify files exist."""
    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = os.path.join(tmp, "test.pdf")
        _make_tiny_pdf(pdf_path, n_pages=2)

        out_dir = os.path.join(tmp, "out")
        result = export_pdf(pdf_path, out_dir, fmt="png", dpi=72)

        assert result["success"] == 2
        assert result["failed"] == []
        assert result["output_dir"] == out_dir
        assert os.path.isdir(out_dir)
        files = sorted(os.listdir(out_dir))
        assert len(files) == 2
        assert files[0] == "test_page1.png"
        assert files[1] == "test_page2.png"


def test_export_specific_pages():
    """Export only selected pages."""
    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = os.path.join(tmp, "doc.pdf")
        _make_tiny_pdf(pdf_path, n_pages=5)

        out_dir = os.path.join(tmp, "out")
        result = export_pdf(pdf_path, out_dir, fmt="png", dpi=72, pages=[0, 2])

        assert result["success"] == 2
        assert result["failed"] == []
        files = sorted(os.listdir(out_dir))
        assert files == ["doc_page1.png", "doc_page3.png"]


def test_export_jpg_format():
    """Export as JPG with quality param."""
    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = os.path.join(tmp, "t.pdf")
        _make_tiny_pdf(pdf_path, n_pages=1)

        out_dir = os.path.join(tmp, "out")
        result = export_pdf(pdf_path, out_dir, fmt="jpg", dpi=72, quality=80)

        assert result["success"] == 1
        files = os.listdir(out_dir)
        assert files == ["t_page1.jpg"]


def test_export_invalid_page_records_failure():
    """An out-of-range page index should be recorded as failure, not crash."""
    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = os.path.join(tmp, "t.pdf")
        _make_tiny_pdf(pdf_path, n_pages=2)

        out_dir = os.path.join(tmp, "out")
        # page 99 does not exist; should fail gracefully
        result = export_pdf(pdf_path, out_dir, fmt="png", dpi=72, pages=[0, 99])

        assert result["success"] == 1
        # failed list records (1-based page number, error message) tuples
        assert len(result["failed"]) == 1
        page_num, msg = result["failed"][0]
        assert page_num == 100
        assert isinstance(msg, str)


def test_export_progress_callback():
    """progress_cb is called for each page."""
    calls = []
    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = os.path.join(tmp, "t.pdf")
        _make_tiny_pdf(pdf_path, n_pages=3)

        out_dir = os.path.join(tmp, "out")
        export_pdf(pdf_path, out_dir, fmt="png", dpi=72, progress_cb=lambda c, t: calls.append((c, t)))

        assert calls == [(1, 3), (2, 3), (3, 3)]


def test_export_doc_handle_released():
    """After export_pdf returns, the fitz document handle must be closed."""
    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = os.path.join(tmp, "t.pdf")
        _make_tiny_pdf(pdf_path, n_pages=1)

        out_dir = os.path.join(tmp, "out")
        export_pdf(pdf_path, out_dir, fmt="png", dpi=72)

        # If handle is leaked, fitz.open may still hold the file on Windows.
        # Verify we can open and immediately close the file without error.
        with open(pdf_path, "rb") as f:
            f.read(1)


def test_export_doc_released_on_progress_error():
    """If progress_cb raises, the fitz document handle must still be released.

    After the fix (using a context manager), doc.close() is guaranteed
    even when an exception propagates out of export_pdf.
    """
    close_called = []
    _orig_open = fitz.open

    def _tracking_open(*args, **kwargs):
        doc = _orig_open(*args, **kwargs)
        _orig_close = doc.close

        def _tracked_close():
            close_called.append(True)
            return _orig_close()

        doc.close = _tracked_close
        return doc

    def _raise(*_args):
        raise RuntimeError("boom")

    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = os.path.join(tmp, "t.pdf")
        _make_tiny_pdf(pdf_path, n_pages=2)

        out_dir = os.path.join(tmp, "out")
        import fitz as _fitz
        _saved = _fitz.open
        _fitz.open = _tracking_open
        try:
            with pytest.raises(RuntimeError, match="boom"):
                export_pdf(pdf_path, out_dir, fmt="png", dpi=72, progress_cb=_raise)
        finally:
            _fitz.open = _saved

        assert len(close_called) == 1, "doc.close() must be called even when progress_cb raises"


def test_export_failed_list_contains_error_info():
    """Failed entries should include error details, not just a bare page number.

    The current code appends only page_idx+1 (an int) to the failed list.
    After the fix, failed entries should be tuples of (page_number, error_message)
    so callers can diagnose what went wrong.
    """
    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = os.path.join(tmp, "t.pdf")
        _make_tiny_pdf(pdf_path, n_pages=2)

        out_dir = os.path.join(tmp, "out")
        # page 99 doesn't exist -> IndexError
        result = export_pdf(pdf_path, out_dir, fmt="png", dpi=72, pages=[0, 99])

        assert result["success"] == 1
        assert len(result["failed"]) == 1
        entry = result["failed"][0]
        # After fix: failed entries are (1-based_page, error_string) tuples
        assert isinstance(entry, tuple), f"Expected tuple, got {type(entry)}"
        assert entry[0] == 100  # 1-based page number
        assert isinstance(entry[1], str)  # error message


# ── ExportDialog tests ──────────────────────────────────────────


@pytest.fixture(scope="session")
def _tk_root():
    """Create a hidden Tk root for dialog testing, shared across tests."""
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def _sample_pdf(tmp_path):
    """Create a 3-page PDF in tmp_path, return its path."""
    pdf_path = str(tmp_path / "sample.pdf")
    _make_tiny_pdf(pdf_path, n_pages=3)
    return pdf_path


def test_dialog_import():
    """ExportDialog can be imported from export module."""
    from pdfer.export import ExportDialog
    assert ExportDialog is not None


def test_dialog_initial_result_none(_tk_root, _sample_pdf):
    """_result should be None right after creation."""
    from pdfer.export import ExportDialog
    dlg = ExportDialog(_tk_root, _sample_pdf)
    try:
        assert dlg._result is None
    finally:
        dlg.destroy()


def test_dialog_default_format_png(_tk_root, _sample_pdf):
    """Default format should be 'png'."""
    from pdfer.export import ExportDialog
    dlg = ExportDialog(_tk_root, _sample_pdf)
    try:
        assert dlg._fmt_var.get() == "png"
    finally:
        dlg.destroy()


def test_dialog_default_dpi_150(_tk_root, _sample_pdf):
    """Default DPI should be 150."""
    from pdfer.export import ExportDialog
    dlg = ExportDialog(_tk_root, _sample_pdf)
    try:
        assert dlg._dpi_var.get() == 150
    finally:
        dlg.destroy()


def test_get_dpi_preset(_tk_root, _sample_pdf):
    """_get_dpi returns the selected preset when custom is off."""
    from pdfer.export import ExportDialog
    dlg = ExportDialog(_tk_root, _sample_pdf)
    try:
        dlg._dpi_var.set(300)
        dlg._use_custom_dpi.set(False)
        assert dlg._get_dpi() == 300
    finally:
        dlg.destroy()


def test_get_dpi_custom(_tk_root, _sample_pdf):
    """_get_dpi returns custom value when custom is on."""
    from pdfer.export import ExportDialog
    dlg = ExportDialog(_tk_root, _sample_pdf)
    try:
        dlg._use_custom_dpi.set(True)
        dlg._dpi_custom_var.set("200")
        assert dlg._get_dpi() == 200
    finally:
        dlg.destroy()


def test_get_dpi_custom_invalid_raises(_tk_root, _sample_pdf):
    """_get_dpi raises ValueError for non-integer custom DPI."""
    from pdfer.export import ExportDialog
    dlg = ExportDialog(_tk_root, _sample_pdf)
    try:
        dlg._use_custom_dpi.set(True)
        dlg._dpi_custom_var.set("abc")
        with pytest.raises(ValueError, match="DPI"):
            dlg._get_dpi()
    finally:
        dlg.destroy()


def test_get_quality_preset(_tk_root, _sample_pdf):
    """_get_quality returns the selected preset when custom is off."""
    from pdfer.export import ExportDialog
    dlg = ExportDialog(_tk_root, _sample_pdf)
    try:
        dlg._quality_var.set(80)
        dlg._use_custom_quality.set(False)
        assert dlg._get_quality() == 80
    finally:
        dlg.destroy()


def test_get_quality_custom(_tk_root, _sample_pdf):
    """_get_quality returns custom value when custom is on."""
    from pdfer.export import ExportDialog
    dlg = ExportDialog(_tk_root, _sample_pdf)
    try:
        dlg._use_custom_quality.set(True)
        dlg._quality_custom_var.set("70")
        assert dlg._get_quality() == 70
    finally:
        dlg.destroy()


def test_get_quality_custom_invalid_raises(_tk_root, _sample_pdf):
    """_get_quality raises ValueError for non-integer custom quality."""
    from pdfer.export import ExportDialog
    dlg = ExportDialog(_tk_root, _sample_pdf)
    try:
        dlg._use_custom_quality.set(True)
        dlg._quality_custom_var.set("xyz")
        with pytest.raises(ValueError, match="质量"):
            dlg._get_quality()
    finally:
        dlg.destroy()


def test_confirm_sets_result(_tk_root, _sample_pdf, tmp_path):
    """Confirm with valid params populates _result with correct keys."""
    from pdfer.export import ExportDialog
    out_dir = str(tmp_path / "out")
    os.makedirs(out_dir, exist_ok=True)
    dlg = ExportDialog(_tk_root, _sample_pdf)
    try:
        dlg._outdir_var.set(out_dir)
        dlg._dpi_var.set(72)
        dlg._use_custom_dpi.set(False)
        dlg._fmt_var.set("png")
        dlg._pages_var.set("")
        dlg._on_confirm()
        assert dlg._result is not None
        assert dlg._result["pdf_path"] == _sample_pdf
        assert dlg._result["output_dir"] == out_dir
        assert dlg._result["fmt"] == "png"
        assert dlg._result["dpi"] == 72
        assert dlg._result["quality"] == 95
        assert dlg._result["pages"] == [0, 1, 2]
    finally:
        if dlg.winfo_exists():
            dlg.destroy()


def test_confirm_jpg_includes_quality(_tk_root, _sample_pdf, tmp_path):
    """Confirm with fmt='jpg' should include quality in _result."""
    from pdfer.export import ExportDialog
    out_dir = str(tmp_path / "out")
    os.makedirs(out_dir, exist_ok=True)
    dlg = ExportDialog(_tk_root, _sample_pdf)
    try:
        dlg._outdir_var.set(out_dir)
        dlg._dpi_var.set(150)
        dlg._use_custom_dpi.set(False)
        dlg._fmt_var.set("jpg")
        dlg._quality_var.set(80)
        dlg._use_custom_quality.set(False)
        dlg._pages_var.set("1,3")
        dlg._on_confirm()
        assert dlg._result is not None
        assert dlg._result["fmt"] == "jpg"
        assert dlg._result["quality"] == 80
        assert dlg._result["pages"] == [0, 2]
    finally:
        if dlg.winfo_exists():
            dlg.destroy()


def test_confirm_empty_dir_shows_error(_tk_root, _sample_pdf, monkeypatch):
    """Confirm with empty output dir should not set _result."""
    from pdfer.export import ExportDialog
    dlg = ExportDialog(_tk_root, _sample_pdf)
    try:
        dlg._outdir_var.set("")
        # Patch messagebox.showerror to capture the call instead of showing a dialog
        errors = []
        import tkinter.messagebox as mb
        monkeypatch.setattr(mb, "showerror", lambda *a, **kw: errors.append(a))
        dlg._on_confirm()
        assert dlg._result is None
        assert len(errors) == 1
        assert "输出目录" in errors[0][1]
    finally:
        if dlg.winfo_exists():
            dlg.destroy()


def test_format_change_png_hides_quality(_tk_root, _sample_pdf):
    """Switching format to 'png' should hide the quality frame."""
    from pdfer.export import ExportDialog
    dlg = ExportDialog(_tk_root, _sample_pdf)
    try:
        dlg._fmt_var.set("jpg")
        dlg._on_fmt_change()
        assert dlg._quality_frame.winfo_manager() == "pack"

        dlg._fmt_var.set("png")
        dlg._on_fmt_change()
        assert dlg._quality_frame.winfo_manager() == ""
    finally:
        dlg.destroy()


def test_format_change_jpg_shows_quality(_tk_root, _sample_pdf):
    """Switching format to 'jpg' should show the quality frame."""
    from pdfer.export import ExportDialog
    dlg = ExportDialog(_tk_root, _sample_pdf)
    try:
        dlg._fmt_var.set("png")
        dlg._on_fmt_change()
        assert dlg._quality_frame.winfo_manager() == ""

        dlg._fmt_var.set("jpg")
        dlg._on_fmt_change()
        assert dlg._quality_frame.winfo_manager() == "pack"
    finally:
        dlg.destroy()


def test_confirm_custom_quality_invalid_shows_error(_tk_root, _sample_pdf, tmp_path, monkeypatch):
    """Confirm with non-integer custom quality should not set _result."""
    from pdfer.export import ExportDialog
    out_dir = str(tmp_path / "out")
    os.makedirs(out_dir, exist_ok=True)
    dlg = ExportDialog(_tk_root, _sample_pdf)
    try:
        dlg._outdir_var.set(out_dir)
        dlg._dpi_var.set(72)
        dlg._use_custom_dpi.set(False)
        dlg._fmt_var.set("jpg")
        dlg._use_custom_quality.set(True)
        dlg._quality_custom_var.set("abc")
        dlg._pages_var.set("")
        errors = []
        import tkinter.messagebox as mb
        monkeypatch.setattr(mb, "showerror", lambda *a, **kw: errors.append(a))
        dlg._on_confirm()
        assert dlg._result is None
        assert len(errors) == 1
        assert "质量" in errors[0][1]
    finally:
        if dlg.winfo_exists():
            dlg.destroy()


def test_result_none_after_cancel(_tk_root, _sample_pdf):
    """_result stays None if destroy is called without confirm."""
    from pdfer.export import ExportDialog
    dlg = ExportDialog(_tk_root, _sample_pdf)
    dlg.destroy()
    # result was never set; but we need to check before destroy
    # Let's re-create and check
    dlg = ExportDialog(_tk_root, _sample_pdf)
    try:
        assert dlg._result is None
    finally:
        dlg.destroy()


# ── export_pages tests ──────────────────────────────────────────


def _make_page(source_path, page_idx=0, is_pdf=True, orientation="auto",
               enabled=True, scale=100, layers=None):
    """Create a Page-like object for testing."""
    from pdfer.constants import Page
    return Page(
        source_path=source_path,
        file_idx=0,
        page_idx=page_idx,
        is_pdf=is_pdf,
        orientation=orientation,
        enabled=enabled,
        scale=scale,
        layers=layers,
    )


def test_export_pages_basic(tmp_path):
    """export_pages exports a Page list to images."""
    from pdfer.export import export_pages
    pdf_path = str(tmp_path / "test.pdf")
    _make_tiny_pdf(pdf_path, n_pages=2)
    out_dir = str(tmp_path / "out")
    pages = [_make_page(pdf_path, page_idx=0), _make_page(pdf_path, page_idx=1)]
    result = export_pages(pages, out_dir, dpi=72)
    assert result["success"] == 2
    assert len(result["failed"]) == 0
    assert os.path.isdir(out_dir)
    files = os.listdir(out_dir)
    assert len(files) == 2


def test_export_pages_orientation(tmp_path):
    """export_pages applies orientation rotation."""
    from pdfer.export import export_pages
    pdf_path = str(tmp_path / "test.pdf")
    _make_tiny_pdf(pdf_path, n_pages=1, width=300, height=100)  # landscape page
    out_dir = str(tmp_path / "out")
    # Force portrait orientation on a landscape page
    pages = [_make_page(pdf_path, page_idx=0, orientation="portrait")]
    result = export_pages(pages, out_dir, dpi=72)
    assert result["success"] == 1
    # The exported image should be rotated (portrait)
    from PIL import Image
    img = Image.open(os.path.join(out_dir, "page1.png"))
    w, h = img.size
    assert h > w  # Should be portrait after rotation


def test_export_pages_with_layers(tmp_path):
    """export_pages composites layers onto the image."""
    from pdfer.export import export_pages
    from PIL import Image as PILImage
    pdf_path = str(tmp_path / "test.pdf")
    _make_tiny_pdf(pdf_path, n_pages=1, width=200, height=200)
    # Create a small red image as the layer
    layer_img_path = str(tmp_path / "stamp.png")
    stamp = PILImage.new("RGBA", (50, 50), (255, 0, 0, 255))
    stamp.save(layer_img_path)
    out_dir = str(tmp_path / "out")
    layer = {
        "x": 10, "y": 10, "width": 50, "height": 50,
        "rotation": 0, "opacity": 1.0,
        "image_path": layer_img_path,
    }
    pages = [_make_page(pdf_path, page_idx=0, layers=[layer])]
    result = export_pages(pages, out_dir, dpi=72)
    assert result["success"] == 1


def test_export_pages_scale(tmp_path):
    """export_pages applies scale factor."""
    from pdfer.export import export_pages
    from PIL import Image
    pdf_path = str(tmp_path / "test.pdf")
    _make_tiny_pdf(pdf_path, n_pages=1, width=200, height=200)
    out_dir = str(tmp_path / "out")
    pages = [_make_page(pdf_path, page_idx=0, scale=50)]
    result = export_pages(pages, out_dir, dpi=72)
    assert result["success"] == 1
    img = Image.open(os.path.join(out_dir, "page1.png"))
    w, h = img.size
    assert w < 200  # Should be scaled down
    assert h < 200


def test_export_pages_progress_callback(tmp_path):
    """export_pages calls progress_cb for each page."""
    from pdfer.export import export_pages
    pdf_path = str(tmp_path / "test.pdf")
    _make_tiny_pdf(pdf_path, n_pages=3)
    out_dir = str(tmp_path / "out")
    pages = [_make_page(pdf_path, page_idx=i) for i in range(3)]
    progress_calls = []
    result = export_pages(pages, out_dir, dpi=72,
                          progress_cb=lambda c, t: progress_calls.append((c, t)))
    assert result["success"] == 3
    assert progress_calls == [(1, 3), (2, 3), (3, 3)]


def test_export_dialog_prefills_enabled_pages(_tk_root, tmp_path):
    """ExportDialog pre-fills page numbers based on enabled pages."""
    from pdfer.export import ExportDialog
    pdf_path = str(tmp_path / "test.pdf")
    _make_tiny_pdf(pdf_path, n_pages=5)
    # Create Page list with pages 0, 2, 4 enabled
    pages = [_make_page(pdf_path, page_idx=i, enabled=(i in [0, 2, 4]))
             for i in range(5)]
    dlg = ExportDialog(_tk_root, pdf_path, page_list=pages)
    try:
        assert dlg._pages_var.get() == "1,3,5"
    finally:
        dlg.destroy()


def test_export_dialog_no_page_list_default_empty(_tk_root, _sample_pdf):
    """ExportDialog without page_list has empty pages field."""
    from pdfer.export import ExportDialog
    dlg = ExportDialog(_tk_root, _sample_pdf)
    try:
        assert dlg._pages_var.get() == ""
    finally:
        dlg.destroy()


def test_export_dialog_result_has_page_list(_tk_root, tmp_path):
    """ExportDialog._result contains page_list when page_list was provided."""
    from pdfer.export import ExportDialog
    pdf_path = str(tmp_path / "test.pdf")
    _make_tiny_pdf(pdf_path, n_pages=3)
    pages = [_make_page(pdf_path, page_idx=i) for i in range(3)]
    out_dir = str(tmp_path / "out")
    dlg = ExportDialog(_tk_root, pdf_path, page_list=pages)
    try:
        # Simulate confirm: set output dir and call _on_confirm
        dlg._outdir_var.set(out_dir)
        dlg._on_confirm()
        assert dlg._result is not None
        assert "page_list" in dlg._result
        assert len(dlg._result["page_list"]) == 3
    finally:
        if dlg.winfo_exists():
            dlg.destroy()
