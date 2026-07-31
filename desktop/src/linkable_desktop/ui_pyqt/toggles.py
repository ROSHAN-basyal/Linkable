from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QAbstractButton, QHBoxLayout, QLabel, QSizePolicy, QWidget

from linkable_desktop.ui_pyqt.theme import color, size, space


class SwitchButton(QAbstractButton):
    """Painted switch control with a sliding knob, used instead of checkable text buttons."""

    def __init__(self, *, checked: bool = False, dual_choice: bool = False) -> None:
        super().__init__()
        self.dual_choice = dual_choice
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(size("switch_w"), size("switch_h"))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggled.connect(lambda _: self.update())

    def paintEvent(self, event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        track = QRectF(2, 2, self.width() - 4, self.height() - 4)
        if self.dual_choice:
            track_color = color("success_soft")
        else:
            track_color = color("success") if self.isChecked() else color("white")
        if not self.isEnabled():
            track_color = color("surface_alt")
        painter.setPen(QPen(QColor(color("black")), 1.4))
        painter.setBrush(QColor(track_color))
        painter.drawRoundedRect(track, track.height() / 2, track.height() / 2)

        margin = 4
        knob_size = self.height() - margin * 2
        knob_x = self.width() - knob_size - margin if self.isChecked() else margin
        knob = QRectF(knob_x, margin, knob_size, knob_size)
        if self.dual_choice:
            knob_color = color("accent")
        else:
            knob_color = color("white") if self.isChecked() else color("surface_alt")
        painter.setPen(QPen(QColor(color("black")), 1.0))
        painter.setBrush(QColor(knob_color))
        painter.drawEllipse(knob)
        painter.end()


class SwitchControl(QWidget):
    """Compact label + switch pair for all boolean settings in the desktop UI."""

    toggled = pyqtSignal(bool)

    def __init__(self, text: str, *, checked: bool = False) -> None:
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(space("none"), space("none"), space("none"), space("none"))
        layout.setSpacing(space("sm"))
        self.label = QLabel(text)
        self.label.setObjectName("SwitchLabel")
        self.switch = SwitchButton(checked=checked)
        self.switch.toggled.connect(self.toggled.emit)
        layout.addWidget(self.label)
        layout.addWidget(self.switch)

    def setText(self, text: str) -> None:
        self.label.setText(text)

    def text(self) -> str:
        return self.label.text()

    def setChecked(self, checked: bool) -> None:
        self.switch.setChecked(checked)

    def isChecked(self) -> bool:
        return self.switch.isChecked()

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        self.label.setEnabled(enabled)
        self.switch.setEnabled(enabled)

    def mousePressEvent(self, event: object) -> None:
        if self.isEnabled() and event.button() == Qt.MouseButton.LeftButton:
            self.switch.toggle()
            event.accept()
            return
        super().mousePressEvent(event)


class DualSwitchControl(QWidget):
    """Two-label switch for mutually exclusive choices such as USB/LAN or Front/Back."""

    toggled = pyqtSignal(bool)

    def __init__(self, left_text: str, right_text: str, *, checked: bool = False) -> None:
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(space("none"), space("none"), space("none"), space("none"))
        layout.setSpacing(space("sm"))
        self.left_label = QLabel(left_text)
        self.left_label.setObjectName("SwitchLabel")
        self.right_label = QLabel(right_text)
        self.right_label.setObjectName("SwitchLabel")
        self.switch = SwitchButton(checked=checked, dual_choice=True)
        self.switch.toggled.connect(self._handle_toggled)
        layout.addWidget(self.left_label)
        layout.addWidget(self.switch)
        layout.addWidget(self.right_label)
        self._sync_label_state(checked)

    def setChecked(self, checked: bool) -> None:
        self.switch.setChecked(checked)
        self._sync_label_state(checked)

    def isChecked(self) -> bool:
        return self.switch.isChecked()

    def mousePressEvent(self, event: object) -> None:
        if self.isEnabled() and event.button() == Qt.MouseButton.LeftButton:
            self.switch.toggle()
            event.accept()
            return
        super().mousePressEvent(event)

    def _handle_toggled(self, checked: bool) -> None:
        self._sync_label_state(checked)
        self.toggled.emit(checked)

    def _sync_label_state(self, checked: bool) -> None:
        self.left_label.setProperty("active", "false" if checked else "true")
        self.right_label.setProperty("active", "true" if checked else "false")
        self.left_label.style().unpolish(self.left_label)
        self.left_label.style().polish(self.left_label)
        self.right_label.style().unpolish(self.right_label)
        self.right_label.style().polish(self.right_label)
