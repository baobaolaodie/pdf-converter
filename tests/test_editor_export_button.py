"""tests for editor toolbar export button integration (Task 6)"""

import tkinter as tk
from tkinter import ttk

import pytest

fitz = pytest.importorskip("fitz", reason="PyMuPDF not installed")


@pytest.fixture(scope="module")
def _app():
    """Create a MergeApp instance with a hidden Tk root for testing."""
    root = tk.Tk()
    root.withdraw()
    from pdfer.gui import MergeApp
    app = MergeApp(root)
    yield app
    root.destroy()


@pytest.fixture(scope="module")
def _editor():
    """Create a standalone PageEditor for toolbar inspection."""
    root = tk.Tk()
    root.withdraw()
    from pdfer.editor import PageEditor
    editor = PageEditor(root, 210.0, 297.0)
    yield editor
    root.destroy()


def test_toolbar_separator_exists(_editor):
    """A ttk.Separator should exist in the toolbar (visual grouping)."""
    children = _editor._toolbar.winfo_children()
    separators = [c for c in children if isinstance(c, ttk.Separator)]
    assert len(separators) >= 1, "Expected at least one separator in toolbar"


def test_toolbar_separator_orient_vertical(_editor):
    """The separator should be vertical."""
    children = _editor._toolbar.winfo_children()
    separators = [c for c in children if isinstance(c, ttk.Separator)]
    vertical = [s for s in separators if str(s.cget("orient")) == "vertical"]
    assert len(vertical) >= 1, "Expected a vertical separator in toolbar"


def test_export_from_editor_method_exists(_app):
    """MergeApp should have the _export_from_editor method."""
    assert callable(getattr(_app, "_export_from_editor", None))


def test_export_from_editor_is_callable(_app):
    """_export_from_editor should be a method (not just an attribute)."""
    assert hasattr(_app, "_export_from_editor")
    assert callable(_app._export_from_editor)
