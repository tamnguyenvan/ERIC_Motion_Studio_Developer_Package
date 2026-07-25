"""Application icon loading from the bundled PNG resource directory."""

from __future__ import annotations

from PySide6.QtGui import QIcon

from eric_motion_studio.config import RESOURCE_ROOT

ICON_ROOT = RESOURCE_ROOT / "icons"


def load_icon(name: str) -> QIcon:
    """Load a PNG icon by filename, returning an empty icon when unavailable."""
    return QIcon(str(ICON_ROOT / name))
