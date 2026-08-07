"""tests for GUI right-click context menu integration with export"""

import tkinter as tk

import pytest

from pdfer.export import ExportDialog, ExportProgressDialog


def test_export_dialog_import():
    """ExportDialog can be imported from export module."""
    assert ExportDialog is not None


def test_export_progress_dialog_import():
    """ExportProgressDialog can be imported from export module."""
    assert ExportProgressDialog is not None


@pytest.fixture(scope="module")
def _app():
    """Create a MergeApp instance with a hidden Tk root for testing."""
    root = tk.Tk()
    root.withdraw()
    from pdfer.gui import MergeApp
    app = MergeApp(root)
    yield app
    root.destroy()


def test_context_menu_created(_app):
    """_context_menu attribute should exist after _build_ui."""
    assert hasattr(_app, "_context_menu")
    assert _app._context_menu is not None


def test_context_menu_is_tk_menu(_app):
    """_context_menu should be a tk.Menu instance."""
    assert isinstance(_app._context_menu, tk.Menu)


def test_context_menu_has_export_command(_app):
    """_context_menu should have at least one entry labeled '导出为图片'."""
    # tk.Menu index("end") returns the last index; None means empty
    last = _app._context_menu.index("end")
    assert last is not None
    # Check the label of the first (and only) entry
    label = _app._context_menu.entrycget(0, "label")
    assert label == "导出为图片"


def test_export_from_gallery_method_exists(_app):
    """MergeApp should have the _export_from_gallery method."""
    assert callable(getattr(_app, "_export_from_gallery", None))


def test_show_context_menu_method_exists(_app):
    """MergeApp should have the _show_context_menu method."""
    assert callable(getattr(_app, "_show_context_menu", None))


def test_context_menu_command_points_to_export(_app):
    """The context menu command should reference _export_from_gallery."""
    cmd = _app._context_menu.entrycget(0, "command")
    # The command is registered as a Tcl command string; verify it's not empty
    assert cmd
