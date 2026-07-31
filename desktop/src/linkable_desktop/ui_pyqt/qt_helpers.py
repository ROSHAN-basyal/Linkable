from __future__ import annotations

from PyQt6.QtWidgets import QWidget


def repolish(widget: QWidget) -> None:
    """Re-apply stylesheet rules after dynamic properties change."""

    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()
