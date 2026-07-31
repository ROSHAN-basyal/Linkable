from __future__ import annotations

from collections import defaultdict

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from linkable_desktop.app.compatibility import CompatibilityCheck, CompatibilityReport, FixCommand
from linkable_desktop.ui_pyqt.constants import tr
from linkable_desktop.ui_pyqt.theme import size, space


class CommandRow(QFrame):
    """Displays one fix command with a per-command clipboard button."""

    def __init__(self, command: FixCommand) -> None:
        super().__init__()
        self.setObjectName("SoftPanel")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(space("sm"), space("sm"), space("sm"), space("sm"))
        layout.setSpacing(space("sm"))

        text = QLabel(f"{command.label}: {command.command}")
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text.setWordWrap(True)
        text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        copy_button = QPushButton(tr("startup.copy"))
        copy_button.clicked.connect(lambda: QGuiApplication.clipboard().setText(command.command))

        layout.addWidget(text, 1)
        layout.addWidget(copy_button)


class CheckCard(QFrame):
    """Renders a single startup compatibility check and its remediation commands."""

    def __init__(self, check: CompatibilityCheck) -> None:
        super().__init__()
        self.setObjectName("CompatibilityCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(space("card_x"), space("card_y"), space("card_x"), space("card_y"))
        layout.setSpacing(space("sm"))

        header = QHBoxLayout()
        marker = QLabel("✓" if check.ok else "✕")
        marker.setObjectName("SuccessChip" if check.ok else "DangerChip")
        title = QLabel(check.title)
        title.setObjectName("CardTitle")
        severity = QLabel(tr("startup.critical") if check.critical else tr("startup.optional"))
        severity.setObjectName("DangerChip" if check.critical and not check.ok else "InfoChip")
        header.addWidget(marker)
        header.addWidget(title, 1)
        header.addWidget(severity)
        layout.addLayout(header)

        detail = QLabel(check.detail or check.explanation)
        detail.setWordWrap(True)
        detail.setObjectName("MutedLabel")
        layout.addWidget(detail)

        if check.fix_commands:
            grouped: dict[bool, list[FixCommand]] = defaultdict(list)
            for command in check.fix_commands:
                grouped[command.requires_sudo].append(command)
            for requires_sudo, commands in grouped.items():
                heading = QLabel(tr("startup.sudo") if requires_sudo else tr("startup.user"))
                heading.setObjectName("CommandHeading")
                layout.addWidget(heading)
                for command in commands:
                    layout.addWidget(CommandRow(command))


class CompatibilityGate(QDialog):
    """Startup gate that blocks the main UI until required desktop checks pass."""

    recheck_requested = pyqtSignal()

    def __init__(self, report: CompatibilityReport) -> None:
        super().__init__()
        self.report = report
        self.skip_noncritical = False
        self.setWindowTitle(tr("startup.title"))
        self.setMinimumSize(size("startup_min_w"), size("startup_min_h"))
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(space("panel_x"), space("panel_x"), space("panel_x"), space("panel_x"))
        root.setSpacing(space("md"))

        title = QLabel(tr("startup.title"))
        title.setObjectName("SectionTitle")
        intro = QLabel(tr("startup.intro"))
        intro.setObjectName("SectionSubtitle")
        intro.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(intro)

        summary = QLabel(self._summary_text())
        summary.setObjectName("SuccessChip" if not self.report.failed_checks else "WarningChip")
        root.addWidget(summary)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(space("none"), space("none"), space("none"), space("none"))
        content_layout.setSpacing(space("sm"))
        for check in self.report.checks:
            content_layout.addWidget(CheckCard(check))
        content_layout.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        buttons = QHBoxLayout()
        recheck = QPushButton(tr("startup.recheck"))
        recheck.clicked.connect(self.recheck_requested.emit)
        exit_button = QPushButton(tr("startup.exit"))
        exit_button.clicked.connect(self.reject)
        continue_key = "startup.continue_anyway" if self.report.can_skip_noncritical else "startup.continue"
        continue_button = QPushButton(tr(continue_key))
        continue_button.setObjectName("PrimaryButton")
        continue_button.setEnabled(not self.report.failed_critical_checks)
        continue_button.clicked.connect(self._continue)
        skip_button = QPushButton(tr("startup.skip"))
        skip_button.setEnabled(self.report.can_skip_noncritical)
        skip_button.clicked.connect(self._skip_and_accept)
        buttons.addWidget(recheck)
        buttons.addStretch(1)
        buttons.addWidget(exit_button)
        buttons.addWidget(skip_button)
        buttons.addWidget(continue_button)
        root.addLayout(buttons)

    def _summary_text(self) -> str:
        if not self.report.failed_checks:
            return tr("startup.pass")
        failed = len(self.report.failed_checks)
        critical = len(self.report.failed_critical_checks)
        return f"{tr('startup.fail')}: {failed} failed, {critical} required"

    def _skip_and_accept(self) -> None:
        self.skip_noncritical = True
        self.accept()

    def _continue(self) -> None:
        self.skip_noncritical = bool(self.report.failed_noncritical_checks)
        self.accept()
