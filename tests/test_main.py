"""tests for main.py CLI --export entry point"""

import os
import subprocess
import sys
import tempfile
from unittest.mock import patch, MagicMock

import pytest


def _run_main(*args):
    """Run main.main() with given sys.argv, return (exit_code, stdout, stderr)."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(
        [sys.executable, "main.py", *args],
        capture_output=True, text=True, encoding="utf-8",
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))) or ".",
        env=env,
    )
    return result.returncode, result.stdout, result.stderr


def test_help_shows_export_args():
    """--help should list the new --export related arguments."""
    code, stdout, stderr = _run_main("--help")
    combined = stdout + stderr
    for flag in ["--export", "--format", "--dpi", "--quality", "--pages", "--output-dir"]:
        assert flag in combined, f"--help output missing {flag}"


def test_help_shows_new_description():
    """--help description should mention export."""
    code, stdout, stderr = _run_main("--help")
    combined = stdout + stderr
    assert "导出" in combined or "export" in combined.lower()


def test_export_nonexistent_file_exits_1():
    """--export with a nonexistent file should print error and exit 1."""
    code, stdout, stderr = _run_main("--export", "Z:/no_such_file.pdf")
    assert code == 1
    assert "不存在" in stdout or "不存在" in stderr


def test_export_invalid_pages_exits_1():
    """--export with invalid --pages should print error and exit 1."""
    with tempfile.TemporaryDirectory() as tmp:
        # Create a tiny valid PDF
        import fitz
        pdf_path = os.path.join(tmp, "test.pdf")
        doc = fitz.open()
        doc.new_page()
        doc.save(pdf_path)
        doc.close()

        code, stdout, stderr = _run_main("--export", pdf_path, "--pages", "abc")
        assert code == 1
        combined = stdout + stderr
        assert "错误" in combined or "无效" in combined


def test_export_valid_pdf_calls_export(tmp_path):
    """--export with a valid PDF should call export_pdf and print success."""
    import fitz
    pdf_path = str(tmp_path / "test.pdf")
    doc = fitz.open()
    doc.new_page(width=200, height=200)
    doc.new_page(width=200, height=200)
    doc.save(pdf_path)
    doc.close()

    out_dir = str(tmp_path / "out")
    code, stdout, stderr = _run_main(
        "--export", pdf_path, "--output-dir", out_dir, "--dpi", "72"
    )
    assert code == 0
    assert "导出完成" in stdout
    assert "成功 2 页" in stdout
    assert "输出目录" in stdout


def test_export_default_format_png(tmp_path):
    """Default format should be png."""
    import fitz
    pdf_path = str(tmp_path / "t.pdf")
    doc = fitz.open()
    doc.new_page(width=200, height=200)
    doc.save(pdf_path)
    doc.close()

    out_dir = str(tmp_path / "out")
    code, stdout, stderr = _run_main(
        "--export", pdf_path, "--output-dir", out_dir, "--dpi", "72"
    )
    assert code == 0
    files = os.listdir(out_dir)
    assert any(f.endswith(".png") for f in files)


def test_export_jpg_format(tmp_path):
    """--format jpg should produce .jpg files."""
    import fitz
    pdf_path = str(tmp_path / "t.pdf")
    doc = fitz.open()
    doc.new_page(width=200, height=200)
    doc.save(pdf_path)
    doc.close()

    out_dir = str(tmp_path / "out")
    code, stdout, stderr = _run_main(
        "--export", pdf_path, "--format", "jpg", "--output-dir", out_dir, "--dpi", "72"
    )
    assert code == 0
    files = os.listdir(out_dir)
    assert any(f.endswith(".jpg") for f in files)


def test_export_pages_subset(tmp_path):
    """--pages should select only specified pages."""
    import fitz
    pdf_path = str(tmp_path / "t.pdf")
    doc = fitz.open()
    doc.new_page(width=200, height=200)
    doc.new_page(width=200, height=200)
    doc.new_page(width=200, height=200)
    doc.save(pdf_path)
    doc.close()

    out_dir = str(tmp_path / "out")
    code, stdout, stderr = _run_main(
        "--export", pdf_path, "--pages", "1,3", "--output-dir", out_dir, "--dpi", "72"
    )
    assert code == 0
    assert "成功 2 页" in stdout
    files = os.listdir(out_dir)
    assert len(files) == 2


def test_export_default_output_dir(tmp_path):
    """Without --output-dir, output should go to PDF stem subfolder."""
    import fitz
    pdf_path = str(tmp_path / "mydoc.pdf")
    doc = fitz.open()
    doc.new_page(width=200, height=200)
    doc.save(pdf_path)
    doc.close()

    code, stdout, stderr = _run_main("--export", pdf_path, "--dpi", "72")
    assert code == 0
    expected_dir = os.path.join(os.path.dirname(pdf_path), "mydoc")
    assert os.path.isdir(expected_dir)
    assert "输出目录" in stdout


def test_export_failed_pages_print_tuple_page_number(tmp_path, capsys):
    """When export_pdf returns failed tuples, main should print page[0] not page."""
    import fitz
    pdf_path = str(tmp_path / "t.pdf")
    # Create a PDF with 100 pages so parse_pages("1,99", 100) succeeds
    doc = fitz.open()
    for _ in range(100):
        doc.new_page(width=200, height=200)
    doc.save(pdf_path)
    doc.close()

    out_dir = str(tmp_path / "out")
    mock_result = {"success": 1, "failed": [(99, "simulated error")], "output_dir": out_dir}

    with patch("export.export_pdf", return_value=mock_result):
        with patch("sys.argv", ["main.py", "--export", pdf_path, "--pages", "1,99",
                                "--output-dir", out_dir, "--dpi", "72"]):
            from main import main
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    captured = capsys.readouterr()
    assert "成功 1 页" in captured.out
    assert "跳过 1 页" in captured.out
    assert "#99" in captured.out
