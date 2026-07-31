"""conftest.py — shared fixtures for GUI tests."""

import tkinter as tk
import pytest


@pytest.fixture(scope="session")
def _tk_root():
    """Session-scoped Tk root — hidden window for widget tests."""
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()
