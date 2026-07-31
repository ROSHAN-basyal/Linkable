from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PyQt6.QtCore import QByteArray, QRectF, QSize, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QToolButton

from linkable_desktop.ui_pyqt.theme import color, size


ICONS_DIR = Path(__file__).resolve().parents[4] / "Icons"


@lru_cache(maxsize=256)
def svg_icon(file_name: str, color_name: str = "ink", icon_size: int = 24) -> QIcon:
    """Load one generated Linkable SVG as a recolorable Qt icon."""

    path = ICONS_DIR / file_name
    if not path.exists():
        return QIcon()
    svg = path.read_text(encoding="utf-8").replace("currentColor", color(color_name))
    pixmap = QPixmap(icon_size, icon_size)
    pixmap.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    painter = QPainter(pixmap)
    renderer.render(painter, QRectF(0, 0, icon_size, icon_size))
    painter.end()
    return QIcon(pixmap)


class IconButton(QToolButton):
    """Uniform icon-only button for explicit icon actions in the redesigned shell."""

    def __init__(
        self,
        icon_file: str,
        tooltip: str,
        *,
        color_name: str = "ink",
        object_name: str = "IconButton",
        icon_size: int | None = None,
    ) -> None:
        super().__init__()
        actual_size = icon_size or size("icon_md")
        self.setObjectName(object_name)
        self.setToolTip(tooltip)
        self.setAccessibleName(tooltip)
        self.setIcon(svg_icon(icon_file, color_name=color_name, icon_size=actual_size))
        self.setIconSize(QSize(actual_size, actual_size))
        self.setFixedSize(size("icon_button"), size("icon_button"))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
