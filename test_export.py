"""tests for export.parse_pages and export.export_pdf"""

import os
import tempfile

import fitz
import pytest
from export import export_pdf, parse_pages


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


def _make_tiny_pdf(path: str, n_pages: int = 3) -> None:
    """Create a minimal PDF with n_pages blank pages using fitz."""
    doc = fitz.open()
    for _ in range(n_pages):
        doc.new_page(width=200, height=200)
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
