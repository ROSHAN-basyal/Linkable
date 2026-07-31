from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from linkable_desktop.app.setup_state import (
    FirstRunState,
    add_safe_wifi_ssid,
    build_systemd_unit,
    current_wifi_ssid,
    install_systemd_user_service,
    save_first_run_state,
    systemd_unit_path,
)
from linkable_desktop.ui_pyqt.constants import tr
from linkable_desktop.ui_pyqt.theme import size, space


class FirstRunWizard(QDialog):
    """Collects first-run desktop setup choices before the main UI opens."""

    def __init__(self, root_dir: Path) -> None:
        super().__init__()
        self.root_dir = root_dir
        self.ssid = current_wifi_ssid()
        self.setWindowTitle(tr("wizard.title"))
        self.setMinimumSize(size("wizard_min_w"), size("wizard_min_h"))
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(space("panel_x"), space("panel_x"), space("panel_x"), space("panel_x"))
        root.setSpacing(space("md"))

        title = QLabel(tr("wizard.title"))
        title.setObjectName("SectionTitle")
        intro = QLabel(tr("wizard.intro"))
        intro.setObjectName("SectionSubtitle")
        intro.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(intro)

        root.addWidget(self._safe_wifi_card())
        root.addWidget(self._autostart_card(), 1)
        root.addWidget(self._notification_card())

        buttons = QHBoxLayout()
        skip = QPushButton(tr("wizard.skip"))
        skip.clicked.connect(self._finish)
        finish = QPushButton(tr("wizard.finish"))
        finish.setObjectName("PrimaryButton")
        finish.clicked.connect(self._finish)
        buttons.addStretch(1)
        buttons.addWidget(skip)
        buttons.addWidget(finish)
        root.addLayout(buttons)

    def _safe_wifi_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(space("card_x"), space("card_y"), space("card_x"), space("card_y"))
        title = QLabel(tr("wizard.ssid"))
        title.setObjectName("CardTitle")
        ssid = QLabel(self.ssid or tr("wizard.ssid.missing"))
        ssid.setObjectName("SuccessChip" if self.ssid else "WarningChip")
        layout.addWidget(title)
        layout.addWidget(ssid)
        return card

    def _autostart_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(space("card_x"), space("card_y"), space("card_x"), space("card_y"))
        layout.setSpacing(space("sm"))
        title = QLabel(tr("wizard.autostart"))
        title.setObjectName("CardTitle")
        detail = QLabel(tr("wizard.autostart.detail"))
        detail.setObjectName("MutedLabel")
        detail.setWordWrap(True)
        unit_text = QTextEdit()
        unit_text.setReadOnly(True)
        unit_text.setPlainText(build_systemd_unit(self.root_dir))
        unit_text.setMinimumHeight(size("unit_min_h"))

        command = f"mkdir -p {systemd_unit_path().parent} && systemctl --user daemon-reload && systemctl --user enable --now linkable-desktop.service"
        command_label = QLabel(f"{tr('wizard.command')}: {command}")
        command_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        command_label.setWordWrap(True)

        buttons = QHBoxLayout()
        install = QPushButton(tr("wizard.install"))
        install.setObjectName("PrimaryButton")
        install.clicked.connect(self._install_service)
        copy_unit = QPushButton(tr("wizard.copy.unit"))
        copy_unit.clicked.connect(lambda: QGuiApplication.clipboard().setText(build_systemd_unit(self.root_dir)))
        copy_command = QPushButton(tr("wizard.copy.command"))
        copy_command.clicked.connect(lambda: QGuiApplication.clipboard().setText(command))
        buttons.addWidget(install)
        buttons.addWidget(copy_unit)
        buttons.addWidget(copy_command)
        buttons.addStretch(1)

        layout.addWidget(title)
        layout.addWidget(detail)
        layout.addWidget(QLabel(tr("wizard.unit")))
        layout.addWidget(unit_text)
        layout.addWidget(command_label)
        layout.addLayout(buttons)
        return card

    def _notification_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(space("card_x"), space("card_y"), space("card_x"), space("card_y"))
        title = QLabel(tr("wizard.notification"))
        title.setObjectName("CardTitle")
        detail = QLabel(tr("wizard.notification.detail"))
        detail.setObjectName("MutedLabel")
        detail.setWordWrap(True)
        confirm = QCheckBox(tr("wizard.notification"))
        confirm.setChecked(True)
        layout.addWidget(title)
        layout.addWidget(detail)
        layout.addWidget(confirm)
        return card

    def _install_service(self) -> None:
        try:
            install_systemd_user_service(self.root_dir)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, tr("wizard.title"), tr("wizard.install.error", error=exc))
            return
        QMessageBox.information(self, tr("wizard.title"), tr("wizard.install.ok"))

    def _finish(self) -> None:
        if self.ssid:
            add_safe_wifi_ssid(self.ssid)
        else:
            save_first_run_state(FirstRunState(completed=True, safe_wifi_ssids=()))
        self.accept()
