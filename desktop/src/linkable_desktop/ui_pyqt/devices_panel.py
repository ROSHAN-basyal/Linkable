from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QRectF, QSize, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from linkable_desktop.app.devices import DeviceAvailability, DeviceViewModel
from linkable_desktop.app.runtime import CallHistoryEntry, DesktopRuntime
from linkable_desktop.camera.preview_reader import PreviewFrame, V4L2PreviewReader
from linkable_desktop.camera.virtual_camera import VirtualCameraSink, list_v4l2_summary
from linkable_desktop.proto import camera_pb2, contacts_pb2, notifications_pb2
from linkable_desktop.ui_pyqt.constants import tr
from linkable_desktop.ui_pyqt.icons import IconButton, svg_icon
from linkable_desktop.ui_pyqt.qt_helpers import repolish
from linkable_desktop.ui_pyqt.theme import color, size, space
from linkable_desktop.ui_pyqt.toggles import DualSwitchControl, SwitchControl


class HomePanel(QFrame):
    """Default desktop landing view with device cards and high-frequency actions."""

    settings_requested = pyqtSignal(object)
    notifications_requested = pyqtSignal(object)

    def __init__(self, runtime: DesktopRuntime) -> None:
        super().__init__()
        self.runtime = runtime
        self._status_message = ""
        self._cards_layout: QVBoxLayout | None = None
        self._safe_wifi_menu_button: IconButton | None = None
        self._wifi_toggle: SwitchControl | None = None
        self._last_devices: tuple[DeviceViewModel, ...] | None = None
        self.setObjectName("HomePanel")
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(space("none"), space("none"), space("none"), space("none"))
        root.setSpacing(space("md"))

        toolbar = QFrame()
        toolbar.setObjectName("ActionStrip")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(space("card_x"), space("sm"), space("card_x"), space("sm"))
        toolbar_layout.setSpacing(space("sm"))

        add_button = AddDeviceButton()
        add_button.clicked.connect(self._allow_new_pairing)
        self._wifi_toggle = SwitchControl("")
        self._wifi_toggle.toggled.connect(self._toggle_wifi_access)
        self._safe_wifi_menu_button = IconButton(
            "icon-safe-wifi-list.svg",
            tr("safe_wifi.title"),
            color_name="brown",
            object_name="IconButtonMuted",
        )
        self._safe_wifi_menu_button.clicked.connect(self._show_safe_wifi_popup)
        hint = QLabel(tr("home.quick_hint"))
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        toolbar_layout.addWidget(add_button)
        toolbar_layout.addWidget(self._wifi_toggle)
        toolbar_layout.addWidget(self._safe_wifi_menu_button)
        toolbar_layout.addWidget(hint, 1)
        root.addWidget(toolbar)

        self.status_label = QLabel("")
        self.status_label.setObjectName("MutedLabel")
        self.status_label.setWordWrap(True)
        self.status_label.hide()
        root.addWidget(self.status_label)

        scroll = QScrollArea()
        scroll.setObjectName("DeviceScrollArea")
        scroll.setWidgetResizable(True)
        content = QWidget()
        self._cards_layout = QVBoxLayout(content)
        self._cards_layout.setContentsMargins(space("none"), space("none"), space("none"), space("none"))
        self._cards_layout.setSpacing(space("md"))
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

    def refresh(self) -> None:
        self._sync_wifi_access()
        self.status_label.setText(self._status_message)
        self.status_label.setVisible(bool(self._status_message))
        if self._cards_layout is None:
            return
        devices = tuple(self.runtime.list_devices())
        if devices == self._last_devices:
            return
        self._last_devices = devices
        clear_layout(self._cards_layout)
        if not devices:
            empty = EmptyHomeCard()
            empty.add_requested.connect(self._allow_new_pairing)
            self._cards_layout.addWidget(empty)
        for device in devices:
            card = DeviceCard(self.runtime, device)
            card.settings_requested.connect(self.settings_requested.emit)
            card.notifications_requested.connect(self.notifications_requested.emit)
            card.status_changed.connect(self._set_status)
            self._cards_layout.addWidget(card)
        self._cards_layout.addStretch(1)

    def _sync_wifi_access(self) -> None:
        policy = self.runtime.safe_wifi_policy()
        if self._wifi_toggle is not None:
            self._wifi_toggle.blockSignals(True)
            mode_key = "home.wifi_all" if policy.allow_all_wifi else "home.wifi_safelisted"
            self._wifi_toggle.setText(f"{tr('home.wifi_access')}: {tr(mode_key)}")
            self._wifi_toggle.setChecked(policy.allow_all_wifi)
            self._wifi_toggle.blockSignals(False)
        if self._safe_wifi_menu_button is not None:
            self._safe_wifi_menu_button.setVisible(not policy.allow_all_wifi)

    def _toggle_wifi_access(self, allow_all: bool) -> None:
        self.runtime.set_allow_all_wifi(allow_all)
        self.refresh()

    def _show_safe_wifi_popup(self) -> None:
        dialog = SafeWifiListDialog(self.runtime, self)
        dialog.exec()
        self.refresh()

    def _allow_new_pairing(self) -> None:
        self.runtime.allow_new_pairing()
        self._set_status(tr("devices.pair.ready"))

    def _set_status(self, message: str) -> None:
        self._status_message = message
        self.refresh()

    def show_status(self, message: str) -> None:
        """Display a short user-facing status message above the device list."""

        self._set_status(message)

    def clear_status(self) -> None:
        """Clear transient home status text when returning from private pages."""

        if not self._status_message:
            return
        self._status_message = ""
        self.refresh()


class DevicesPanel(HomePanel):
    """Compatibility alias for older imports; the visible panel is now HomePanel."""


class EmptyHomeCard(QFrame):
    """Empty state card that points users to the Add Devices action."""

    add_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("DeviceCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(space("lg"), space("lg"), space("lg"), space("lg"))
        layout.setSpacing(space("sm"))
        title = QLabel(tr("home.empty.title"))
        title.setObjectName("EmptyStateTitle")
        body = QLabel(tr("home.empty.body"))
        body.setObjectName("MutedLabel")
        body.setWordWrap(True)
        button = AddDeviceButton()
        button.clicked.connect(self.add_requested.emit)
        layout.addWidget(title)
        layout.addWidget(body)
        layout.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)


class AddDeviceButton(QPushButton):
    """Custom-painted Add Devices action pill with a prominent plus chip."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("AddDeviceButton")
        self.setText(tr("home.add_devices").lstrip("+ ").strip())
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.setMinimumSize(self.sizeHint())

    def sizeHint(self) -> QSize:
        return QSize(158, 48)

    def enterEvent(self, event: object) -> None:
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event: object) -> None:
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        fill = color("accent")
        if self.isDown():
            fill = color("pressed")
        elif self.underMouse():
            fill = color("success")
        if not self.isEnabled():
            fill = color("surface_alt")

        rect = QRectF(1.5, 1.5, self.width() - 3, self.height() - 3)
        painter.setPen(QPen(QColor(color("ink")), 1.2))
        painter.setBrush(QColor(fill))
        painter.drawRoundedRect(rect, 22, 22)

        chip = QRectF(9, 7, 34, 34)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color("white")))
        painter.drawEllipse(chip)

        plus_font = painter.font()
        plus_font.setPointSize(24)
        plus_font.setBold(True)
        painter.setFont(plus_font)
        painter.setPen(QColor(fill if self.isEnabled() else color("muted")))
        painter.drawText(chip, Qt.AlignmentFlag.AlignCenter, "+")

        label_font = painter.font()
        label_font.setPointSize(11)
        label_font.setBold(True)
        painter.setFont(label_font)
        painter.setPen(QColor(color("white") if self.isEnabled() else color("muted")))
        text_rect = QRectF(52, 0, self.width() - 64, self.height())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text())
        painter.end()


class DeviceCard(QFrame):
    """Home device block with direct, icon-led actions for one paired phone."""

    settings_requested = pyqtSignal(object)
    notifications_requested = pyqtSignal(object)
    status_changed = pyqtSignal(str)

    def __init__(self, runtime: DesktopRuntime, device: DeviceViewModel) -> None:
        super().__init__()
        self.runtime = runtime
        self.device = device
        self._ringing = False
        self.setObjectName("DeviceCard")
        self.setMinimumHeight(size("device_card_min_h"))
        self._ring_button: IconButton | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(space("card_x"), space("card_y"), space("card_x"), space("card_y"))
        layout.setSpacing(space("sm"))

        top = QHBoxLayout()
        settings = IconButton("icon-settings.svg", tr("devices.action.settings"), object_name="IconButtonMuted")
        settings.clicked.connect(lambda: self.settings_requested.emit(self.device))
        top.addWidget(settings)
        top.addWidget(self._connection_icon())
        forget = compact_button(tr("devices.action.forget"))
        forget.setObjectName("SecondaryButton")
        forget.clicked.connect(self._confirm_forget)
        top.addWidget(forget)
        top.addStretch(1)
        notifications = IconButton("icon-notifications.svg", tr("devices.action.notifications"), object_name="IconButtonMuted")
        notifications.clicked.connect(lambda: self.notifications_requested.emit(self.device))
        top.addWidget(notifications)
        layout.addLayout(top)

        name_row = QHBoxLayout()
        name = QLabel(self.device.device_name)
        name.setObjectName("DeviceName")
        name_row.addWidget(name, 1)
        name_row.addWidget(self._connection_action_button())
        layout.addLayout(name_row)


        meta = QHBoxLayout()
        device_id = QLabel(tr("devices.id", device_id=self.device.device_id))
        device_id.setObjectName("DeviceMeta")
        endpoint = QLabel(
            tr("devices.endpoint", endpoint=self.device.endpoint)
            if self.device.endpoint
            else tr("devices.endpoint_unknown")
        )
        endpoint.setObjectName("DeviceMeta")
        meta.addWidget(device_id, 1)
        meta.addWidget(endpoint, 1)
        layout.addLayout(meta)

        action_strip = QFrame()
        action_strip.setObjectName("ActionStrip")
        actions = QHBoxLayout(action_strip)
        actions.setContentsMargins(space("sm"), space("xs"), space("sm"), space("xs"))
        actions.setSpacing(space("sm"))
        self._ring_button = IconButton("icon-ring.svg", tr("devices.action.ring"), color_name="success", object_name="IconButtonGreen")
        self._ring_button.clicked.connect(self._toggle_ring)
        action_items = (
            self._ring_button,
            self._action_button("icon-phone-call.svg", tr("devices.action.call"), self._open_dialer),
            self._action_button("icon-contacts.svg", tr("devices.action.contacts"), self._open_contacts),
            self._action_button("icon-browse-files.svg", tr("devices.action.files"), self._open_files),
            self._action_button("icon-send-file.svg", tr("devices.action.send_file"), self._send_file),
            self._action_button("icon-mirror.svg", tr("devices.action.mirror"), self._mirror),
            self._action_button("icon-shared-apps.svg", tr("devices.action.shared_apps"), self._open_shared_apps),
        )
        for item in action_items:
            actions.addWidget(item)
        actions.addStretch(1)
        layout.addWidget(action_strip)

    def _connection_icon(self) -> QLabel:
        if self.device.is_connected and self.device.bluetooth_connected:
            icon_file = "icon-wifi-bluetooth.svg"
            color_name = "success"
            tooltip = tr("devices.status.lan_bt")
        elif self.device.is_connected:
            icon_file = "icon-wifi-online.svg"
            color_name = "success"
            tooltip = tr("devices.status.lan")
        else:
            icon_file = "icon-wifi-offline.svg"
            color_name = "muted"
            tooltip = tr("devices.status.offline")
        label = QLabel()
        label.setObjectName("StatusIcon")
        label.setToolTip(tooltip)
        label.setFixedSize(38, 38)
        label.setPixmap(svg_icon(icon_file, color_name=color_name, icon_size=24).pixmap(24, 24))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return label

    def _connection_action_button(self) -> IconButton:
        if self.device.is_connected:
            button = IconButton("icon-unpair.svg", tr("devices.action.unpair"), color_name="danger", object_name="IconButtonDanger")
            button.clicked.connect(self._confirm_unpair)
            return button
        button = IconButton("icon-reconnect.svg", tr("devices.action.reconnect"), color_name="success", object_name="IconButtonGreen")
        button.clicked.connect(self._allow_reconnect)
        return button

    def _action_button(self, icon_file: str, tooltip: str, callback: object) -> IconButton:
        button = IconButton(icon_file, tooltip)
        button.clicked.connect(callback)
        button.setEnabled(self.device.is_connected or tooltip in {tr("devices.action.mirror"), tr("devices.action.send_file")})
        return button

    def _toggle_ring(self) -> None:
        self._ringing = not self._ringing
        self.runtime.queue_ring_phone(self._ringing)
        if self._ring_button is None:
            return
        if self._ringing:
            self._ring_button.setIcon(svg_icon("icon-ring-stop.svg", color_name="danger", icon_size=size("icon_md")))
            self._ring_button.setObjectName("IconButtonDanger")
            self._ring_button.setToolTip(tr("devices.action.stop_ring"))
        else:
            self._ring_button.setIcon(svg_icon("icon-ring.svg", color_name="success", icon_size=size("icon_md")))
            self._ring_button.setObjectName("IconButtonGreen")
            self._ring_button.setToolTip(tr("devices.action.ring"))
        repolish(self._ring_button)

    def _open_dialer(self) -> None:
        dialog = DialerDialog(self.runtime, self)
        dialog.exec()

    def _open_contacts(self) -> None:
        dialog = ContactsDialog(self.runtime, self)
        dialog.exec()

    def _open_files(self) -> None:
        dialog = PhoneFileBrowserDialog(self.runtime, self)
        dialog.exec()

    def _send_file(self) -> None:
        file_name, _ = QFileDialog.getOpenFileName(self, tr("devices.action.send_file"), str(Path.home()))
        if not file_name:
            return
        path = Path(file_name)
        if self.runtime.queue_send_file(path):
            self.status_changed.emit(f"Queued {path.name} for phone transfer. Waiting for phone confirmation.")
        else:
            QMessageBox.warning(self, tr("devices.action.send_file"), f"Cannot send selected file:\n{path}")

    def _mirror(self) -> None:
        status = self.runtime.mirror_status()
        usb_ready = any(device.is_ready and not device.is_tcp for device in status.devices)
        lan_ready = self.device.is_connected
        if usb_ready and lan_ready:
            launch = self.runtime.launch_usb_mirror() if self._choose_mirror_method() == "usb" else self.runtime.launch_lan_mirror()
        else:
            launch = self.runtime.launch_lan_mirror()
        if not launch.result.ok:
            QMessageBox.warning(self, tr("mirror.title"), launch.result.compact_output())

    def _choose_mirror_method(self) -> str:
        message = QMessageBox(self)
        message.setObjectName("MirrorPopup")
        message.setStyleSheet(
            f"""
            QMessageBox#MirrorPopup {{
                background: {color('white')};
            }}
            QMessageBox#MirrorPopup QLabel {{
                background: {color('white')};
            }}
            QMessageBox#MirrorPopup QPushButton {{
                background: {color('white')};
            }}
            """
        )
        message.setWindowTitle(tr("mirror.choose"))
        message.setText(tr("mirror.choose.body"))
        usb = message.addButton(tr("mirror.usb"), QMessageBox.ButtonRole.AcceptRole)
        lan = message.addButton(tr("mirror.lan"), QMessageBox.ButtonRole.ActionRole)
        message.exec()
        return "usb" if message.clickedButton() is usb else "lan"

    def _open_shared_apps(self) -> None:
        dialog = SharedAppsDialog(self.runtime, self)
        dialog.exec()

    def _allow_reconnect(self) -> None:
        self.runtime.allow_reconnect(self.device.device_id)
        self.status_changed.emit(tr("devices.reconnect.ready"))

    def _confirm_unpair(self) -> None:
        result = QMessageBox.question(self, tr("devices.unpair"), tr("devices.unpair.confirm"))
        if result == QMessageBox.StandardButton.Yes:
            self.runtime.unpair_device(self.device.device_id)
            self.status_changed.emit(tr("devices.unpair.done"))

    def _confirm_forget(self) -> None:
        result = QMessageBox.question(self, tr("devices.forget"), tr("devices.forget.confirm"))
        if result == QMessageBox.StandardButton.Yes:
            self.runtime.forget_device(self.device.device_id)
            self.status_changed.emit(tr("devices.forget.done"))


class SafeWifiListDialog(QDialog):
    """Popup for safelisted Wi-Fi networks, opened only from the Home Wi-Fi menu icon."""

    def __init__(self, runtime: DesktopRuntime, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        prepare_popup(self)
        self.runtime = runtime
        self.setWindowTitle(tr("safe_wifi.title"))
        self.setMinimumWidth(420)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(space("panel_x"), space("panel_y"), space("panel_x"), space("panel_y"))
        layout.setSpacing(space("sm"))
        policy = self.runtime.safe_wifi_policy()
        current = QLabel(tr("safe_wifi.current", ssid=policy.current_ssid) if policy.current_ssid else tr("safe_wifi.current_missing"))
        current.setObjectName("MutedLabel")
        current.setWordWrap(True)
        layout.addWidget(current)
        if not policy.networks:
            layout.addWidget(empty_label(tr("safe_wifi.empty")))
        for network in policy.networks:
            row = SwitchControl(network.ssid, checked=network.enabled)
            row.toggled.connect(lambda enabled, ssid=network.ssid: self._toggle_network(ssid, enabled))
            layout.addWidget(row)
        close = compact_button(tr("common.close"))
        close.clicked.connect(self.accept)
        layout.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)

    def _toggle_network(self, ssid: str, enabled: bool) -> None:
        self.runtime.set_safe_wifi_network_enabled(ssid, enabled)


class DeviceSettingsPage(QFrame):
    """Per-device settings page opened from a device-card settings icon."""

    back_requested = pyqtSignal()

    def __init__(self, runtime: DesktopRuntime, device: DeviceViewModel) -> None:
        super().__init__()
        self.runtime = runtime
        self.device = device
        self.settings = runtime.device_settings(device.device_id)
        self._camera_popup: CameraAliveDialog | None = None
        self._camera_route_switch: DualSwitchControl | None = None
        self.setObjectName("Panel")
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(space("panel_x"), space("panel_y"), space("panel_x"), space("panel_y"))
        root.setSpacing(space("md"))
        header = QHBoxLayout()
        back = IconButton("icon-back.svg", tr("common.back"), object_name="IconButtonMuted")
        back.clicked.connect(self.back_requested.emit)
        title = QLabel(tr("devices.settings.title", name=self.device.device_name))
        title.setObjectName("SectionTitle")
        header.addWidget(back)
        header.addWidget(title, 1)
        root.addLayout(header)
        note = QLabel(tr("settings.backend_live"))
        note.setObjectName("MutedLabel")
        root.addWidget(note)
        root.addWidget(self._camera_section())
        root.addWidget(self._input_section())
        root.addStretch(1)

    def _camera_section(self) -> QFrame:
        section = settings_section(tr("settings.camera"))
        layout = section.layout()
        route = QHBoxLayout()
        route_switch = DualSwitchControl(
            tr("settings.camera.usb"),
            tr("settings.camera.lan"),
            checked=self.settings.camera_route_lan,
        )
        route_switch.toggled.connect(
            lambda checked: self.runtime.set_device_setting(
                self.device.device_id,
                "camera_route_lan",
                checked,
            )
        )
        self._camera_route_switch = route_switch
        test_camera = compact_button(tr("settings.camera.test"))
        test_camera.clicked.connect(lambda: self._open_camera_alive(test_mode=True))
        route.addWidget(route_switch)
        route.addWidget(test_camera)
        route.addStretch(1)
        layout.addLayout(route)
        camera_row = QHBoxLayout()
        camera_on = compact_button(tr("settings.camera.on"), primary=True)
        camera_on.clicked.connect(self._open_camera_alive)
        camera_row.addWidget(camera_on)
        camera_row.addStretch(1)
        layout.addLayout(camera_row)
        return section

    def _open_camera_alive(self, *, test_mode: bool = False) -> None:
        use_lan = True if self._camera_route_switch is None else self._camera_route_switch.isChecked()
        route = camera_pb2.CAMERA_ROUTE_LAN if use_lan else camera_pb2.CAMERA_ROUTE_USB
        self._camera_popup = CameraAliveDialog(self.runtime, route=route, test_mode=test_mode, parent=self)
        self._camera_popup.exec()
        self._camera_popup = None

    def _input_section(self) -> QFrame:
        section = settings_section(tr("settings.input"))
        layout = section.layout()
        enable = switch_control(tr("settings.input.enable"), checked=self.settings.control_input_enabled)
        details = QFrame()
        details.setObjectName("SoftPanel")
        detail_layout = QHBoxLayout(details)
        keyboard = switch_control(tr("settings.input.keyboard"), checked=self.settings.control_keyboard_enabled)
        keyboard.toggled.connect(
            lambda checked: self.runtime.set_device_setting(self.device.device_id, "control_keyboard_enabled", checked)
        )
        mouse = switch_control(tr("settings.input.mouse"), checked=self.settings.control_mouse_enabled)
        mouse.toggled.connect(
            lambda checked: self.runtime.set_device_setting(self.device.device_id, "control_mouse_enabled", checked)
        )
        commands = switch_control(tr("settings.input.commands"), checked=self.settings.control_commands_enabled)
        commands.toggled.connect(
            lambda checked: self.runtime.set_device_setting(self.device.device_id, "control_commands_enabled", checked)
        )
        detail_layout.addWidget(keyboard)
        detail_layout.addWidget(mouse)
        detail_layout.addWidget(commands)
        details.setVisible(self.settings.control_input_enabled)
        enable.toggled.connect(lambda checked: self._toggle_input_details(details, checked))
        layout.addWidget(enable)
        layout.addWidget(details)
        return section

    def _toggle_input_details(self, details: QFrame, checked: bool) -> None:
        self.runtime.set_device_setting(self.device.device_id, "control_input_enabled", checked)
        details.setVisible(checked)


class CameraAliveDialog(QDialog):
    """Mobile camera popup that either tests or minimally controls the Linkable camera feed."""

    status_received = pyqtSignal(str)
    preview_frame_received = pyqtSignal(object)

    def __init__(self, runtime: DesktopRuntime, *, route: int, test_mode: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        prepare_popup(self)
        self.runtime = runtime
        self.route = route
        self.test_mode = test_mode
        self.facing = camera_pb2.CAMERA_FACING_FRONT
        self._handle = None
        self._sink: VirtualCameraSink | None = None
        self._preview_reader: V4L2PreviewReader | None = None
        self._frames_received = 0
        self._phone_frames_sent = 0
        self._preview_frames = 0
        self._preview_retries = 0
        self._preview_retries = 0
        self._stream_width = 640
        self._stream_height = 480
        self._stream_fps = 12
        self._setup_command = ""
        self._ack_timer = QTimer(self)
        self._ack_timer.timeout.connect(self._send_ack)
        self._frame_count_timer = QTimer(self)
        self._frame_count_timer.timeout.connect(self._refresh_frame_count)
        self.status_received.connect(self._set_status)
        self.preview_frame_received.connect(self._set_preview_frame)
        self.setWindowTitle(tr("settings.camera.test.title") if test_mode else tr("settings.camera.on"))
        self.setMinimumSize(760, 620) if test_mode else self.setMinimumSize(420, 150)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(space("card_x"), space("card_y"), space("card_x"), space("card_y"))
        layout.setSpacing(space("md"))
        top = QHBoxLayout()
        self.facing_switch = DualSwitchControl(tr("settings.camera.front"), tr("settings.camera.back"), checked=False)
        self.facing_switch.toggled.connect(self._switch_facing)
        top.addWidget(self.facing_switch)
        top.addStretch(1)
        close_button = compact_button(tr("settings.camera.close_feed"))
        close_button.clicked.connect(self.close)
        top.addWidget(close_button)
        layout.addLayout(top)
        self.route_label = QLabel(self.runtime.camera_route_summary(self.route))
        self.route_label.setObjectName("InfoChip")
        self.route_label.setWordWrap(True)
        layout.addWidget(self.route_label)
        self.preview_label = QLabel(tr("settings.camera.test.preview_waiting"))
        self.preview_label.setObjectName("CameraPreview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(640, 360)
        self.preview_label.setVisible(test_mode)
        layout.addWidget(self.preview_label, 1)
        self.device_label = QLabel(tr("settings.camera.virtual.starting"))
        self.device_label.setObjectName("StatusValue")
        self.device_label.setWordWrap(True)
        self.device_label.setVisible(test_mode)
        layout.addWidget(self.device_label)
        self.frame_label = QLabel(tr("settings.camera.virtual.frames", count=0))
        self.frame_label.setObjectName("MutedLabel")
        self.frame_label.setVisible(test_mode)
        layout.addWidget(self.frame_label)
        self.device_list_label = QLabel("")
        self.device_list_label.setObjectName("MutedLabel")
        self.device_list_label.setWordWrap(True)
        self.device_list_label.setVisible(test_mode)
        layout.addWidget(self.device_list_label)
        self.status = QLabel(tr("settings.camera.alive"))
        self.status.setObjectName("MutedLabel")
        self.status.setWordWrap(True)
        self.status.setVisible(test_mode)
        layout.addWidget(self.status)
        detail = QLabel(tr("settings.camera.virtual.detail"))
        detail.setObjectName("MutedLabel")
        detail.setWordWrap(True)
        detail.setVisible(test_mode)
        self.detail_label = detail
        layout.addWidget(detail)
        self.copy_setup_button = compact_button(tr("settings.camera.copy_setup"))
        self.copy_setup_button.clicked.connect(self._copy_setup_command)
        self.copy_setup_button.setVisible(False)
        layout.addWidget(self.copy_setup_button)
        QTimer.singleShot(0, self._start_stream)

    def _start_stream(self) -> None:
        self._frames_received = 0
        self._phone_frames_sent = 0
        self._preview_frames = 0
        self.route_label.setText(self.runtime.camera_route_summary(self.route))
        if self.test_mode:
            self.device_list_label.setText(tr("settings.camera.devices", devices=list_v4l2_summary()))
        self._sink = VirtualCameraSink(
            width=self._stream_width,
            height=self._stream_height,
            fps=self._stream_fps,
            on_status=self.status_received.emit,
        )
        status = self._sink.start()
        if not status.ok:
            self.device_label.setVisible(True)
            self.frame_label.setVisible(self.test_mode)
            self.status.setVisible(True)
            self.detail_label.setVisible(True)
            self.device_label.setText(tr("settings.camera.virtual.failed"))
            self.status.setText(status.detail)
            if status.fix_commands:
                self._setup_command = status.fix_commands[0]
                self.status.setText(f"{status.detail}\n\n" + "\n".join(status.fix_commands))
                self.copy_setup_button.setVisible(True)
            self._sink = None
            return
        self.copy_setup_button.setVisible(False)
        self.device_label.setText(tr("settings.camera.virtual.active", device=status.device))
        if self.test_mode:
            self.device_list_label.setText(tr("settings.camera.devices", devices=list_v4l2_summary()))
        if self.test_mode:
            QTimer.singleShot(900, lambda device=status.device: self._start_preview_if_active(device))
        self._handle = self.runtime.start_camera_stream(
            route=self.route,
            facing=self.facing,
            width=self._stream_width,
            height=self._stream_height,
            fps=self._stream_fps,
            on_frame=self._handle_frame,
            on_status=self.status_received.emit,
        )
        if self._handle is not None:
            self._ack_timer.start(2_000)
            if self.test_mode:
                self._frame_count_timer.start(500)
        elif self._sink is not None:
            if self._preview_reader is not None:
                self._preview_reader.stop()
                self._preview_reader = None
            self._sink.stop()
            self._sink = None

    def _switch_facing(self, checked: bool) -> None:
        self.facing = camera_pb2.CAMERA_FACING_BACK if checked else camera_pb2.CAMERA_FACING_FRONT
        if self._handle is None:
            return
        self._stop_local_stream(reason="camera facing changed", notify_phone=True)
        self.status.setText(tr("settings.camera.switching"))
        if self.test_mode:
            self.preview_label.setText(tr("settings.camera.test.preview_waiting"))
            self.preview_label.setPixmap(QPixmap())
        QTimer.singleShot(350, self._start_stream)

    def _send_ack(self) -> None:
        if self._handle is not None:
            self.runtime.ack_camera_stream(self._handle.token)

    def _handle_frame(self, frame: bytes) -> None:
        self._frames_received += 1
        sink = self._sink
        if sink is not None:
            sink.push_frame(frame)

    def _start_preview(self, device: str) -> None:
        self._preview_reader = V4L2PreviewReader(
            device=device,
            width=self._stream_width,
            height=self._stream_height,
            fps=self._stream_fps,
            on_frame=self.preview_frame_received.emit,
            on_status=self.status_received.emit,
        )
        if not self._preview_reader.start():
            self._preview_reader = None

    def _start_preview_if_active(self, device: str) -> None:
        if not self.test_mode or self._sink is None or self._preview_reader is not None:
            return
        self._start_preview(device)
        QTimer.singleShot(1_400, self._retry_preview_if_empty)

    def _retry_preview_if_empty(self) -> None:
        if not self.test_mode or self._sink is None or self._preview_frames > 0:
            return
        if self._preview_retries >= 3:
            self.status.setText("Camera test could not read Linkable Camera yet. Keep the popup open or close/reopen it after the camera stream starts.")
            return
        self._preview_retries += 1
        if self._preview_reader is not None:
            self._preview_reader.stop()
            self._preview_reader = None
        device = self._sink.device
        if device:
            self.status.setText(f"Retrying Linkable Camera preview ({self._preview_retries}/3)...")
            QTimer.singleShot(700, lambda: self._start_preview_if_active(device))

    def _set_preview_frame(self, frame: object) -> None:
        if not isinstance(frame, PreviewFrame) or not self.test_mode:
            return
        self._preview_frames += 1
        image = QImage(
            frame.rgb,
            frame.width,
            frame.height,
            frame.width * 3,
            QImage.Format.Format_RGB888,
        ).copy()
        pixmap = QPixmap.fromImage(image)
        self.preview_label.setPixmap(
            pixmap.scaled(
                self.preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _refresh_frame_count(self) -> None:
        written = 0 if self._sink is None else self._sink.frames_written
        self.frame_label.setText(
            tr(
                "settings.camera.test.stats",
                sent=self._phone_frames_sent,
                received=self._frames_received,
                written=written,
                preview=self._preview_frames,
            )
        )

    def _set_status(self, message: str) -> None:
        match = re.search(r"frames=(\d+)", message)
        if match:
            self._phone_frames_sent = max(self._phone_frames_sent, int(match.group(1)))
        self.status.setText(message)
        if self.test_mode:
            self._refresh_frame_count()

    def _copy_setup_command(self) -> None:
        if self._setup_command:
            QApplication.clipboard().setText(self._setup_command)

    def _stop_local_stream(self, *, reason: str, notify_phone: bool) -> None:
        self._ack_timer.stop()
        self._frame_count_timer.stop()
        if self._preview_reader is not None:
            self._preview_reader.stop()
            self._preview_reader = None
        if self._handle is not None:
            self.runtime.stop_camera_stream(reason=reason, notify_phone=notify_phone)
            self._handle = None
        if self._sink is not None:
            self._sink.stop()
            self._sink = None
        self._refresh_frame_count()

    def closeEvent(self, event: object) -> None:
        self._stop_local_stream(reason="camera popup closed", notify_phone=True)
        super().closeEvent(event)


class DeviceNotificationsPage(QFrame):
    """Per-device notification page opened from a device-card notification icon."""

    back_requested = pyqtSignal()

    def __init__(self, runtime: DesktopRuntime, device: DeviceViewModel) -> None:
        super().__init__()
        self.runtime = runtime
        self.device = device
        self._hidden_ids: set[str] = set()
        self._items_layout: QVBoxLayout | None = None
        self.setObjectName("Panel")
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(space("panel_x"), space("panel_y"), space("panel_x"), space("panel_y"))
        root.setSpacing(space("md"))
        header = QHBoxLayout()
        back = IconButton("icon-back.svg", tr("common.back"), object_name="IconButtonMuted")
        back.clicked.connect(self.back_requested.emit)
        title = QLabel(tr("devices.notifications.title", name=self.device.device_name))
        title.setObjectName("SectionTitle")
        clear_all = QPushButton(tr("notifications.clear_all"))
        clear_all.clicked.connect(self._clear_all)
        header.addWidget(back)
        header.addWidget(title, 1)
        header.addWidget(clear_all)
        root.addLayout(header)
        scroll, layout = scroll_column()
        self._items_layout = layout
        root.addWidget(scroll, 1)

    def refresh(self) -> None:
        if self._items_layout is None:
            return
        clear_layout(self._items_layout)
        notifications = [item for item in self.runtime.notifications() if item.notification_id not in self._hidden_ids]
        if not notifications:
            self._items_layout.addWidget(empty_label(tr("notifications.empty")))
            self._items_layout.addStretch(1)
            return
        for notification in notifications:
            self._items_layout.addWidget(NotificationRow(self.runtime, notification, self._hide_notification))
        self._items_layout.addStretch(1)

    def _hide_notification(self, notification_id: str) -> None:
        self._hidden_ids.add(notification_id)
        self.refresh()

    def _clear_all(self) -> None:
        self._hidden_ids.update(item.notification_id for item in self.runtime.notifications())
        self.refresh()


class NotificationCenterPage(QFrame):
    """Global diagnostic notification center for all phone notifications and call events."""

    back_requested = pyqtSignal()

    def __init__(self, runtime: DesktopRuntime) -> None:
        super().__init__()
        self.runtime = runtime
        self._hidden_notification_ids: set[str] = set()
        self._hidden_call_ids: set[str] = set()
        self._items_layout: QVBoxLayout | None = None
        self.setObjectName("Panel")
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(space("panel_x"), space("panel_y"), space("panel_x"), space("panel_y"))
        root.setSpacing(space("md"))

        header = QHBoxLayout()
        back = IconButton("icon-back.svg", tr("common.back"), object_name="IconButtonMuted")
        back.clicked.connect(self.back_requested.emit)
        title_box = QVBoxLayout()
        title = QLabel(tr("notifications.center.title"))
        title.setObjectName("SectionTitle")
        subtitle = QLabel(tr("notifications.center.subtitle"))
        subtitle.setObjectName("SectionSubtitle")
        subtitle.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        clear_all = QPushButton(tr("notifications.clear_all"))
        clear_all.clicked.connect(self._clear_all)
        header.addWidget(back)
        header.addLayout(title_box, 1)
        header.addWidget(clear_all)
        root.addLayout(header)

        scroll, layout = scroll_column()
        self._items_layout = layout
        root.addWidget(scroll, 1)

    def refresh(self) -> None:
        if self._items_layout is None:
            return
        clear_layout(self._items_layout)
        notifications = [
            item for item in self.runtime.notification_history()
            if item.notification_id not in self._hidden_notification_ids
        ]
        calls = [item for item in self.runtime.call_history() if item.event_id not in self._hidden_call_ids]

        self._items_layout.addWidget(NotificationSectionHeader(tr("notifications.center.phone_section"), len(notifications)))
        if notifications:
            for notification in notifications:
                self._items_layout.addWidget(NotificationRow(self.runtime, notification, self._hide_notification))
        else:
            self._items_layout.addWidget(empty_label(tr("notifications.empty")))

        self._items_layout.addWidget(NotificationSectionHeader(tr("notifications.center.call_section"), len(calls)))
        if calls:
            for event in calls:
                self._items_layout.addWidget(CallHistoryRow(event, self._hide_call))
        else:
            self._items_layout.addWidget(empty_label(tr("notifications.calls.empty")))
        self._items_layout.addStretch(1)

    def _hide_notification(self, notification_id: str) -> None:
        self._hidden_notification_ids.add(notification_id)
        self.refresh()

    def _hide_call(self, event_id: str) -> None:
        self._hidden_call_ids.add(event_id)
        self.refresh()

    def _clear_all(self) -> None:
        self._hidden_notification_ids.update(item.notification_id for item in self.runtime.notification_history())
        self._hidden_call_ids.update(item.event_id for item in self.runtime.call_history())
        self.refresh()


class NotificationSectionHeader(QFrame):
    """Compact section header used inside the notification center scroll list."""

    def __init__(self, title: str, count: int) -> None:
        super().__init__()
        self.setObjectName("SoftPanel")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(space("card_x"), space("sm"), space("card_x"), space("sm"))
        label = QLabel(title)
        label.setObjectName("CardTitle")
        count_label = QLabel(str(count))
        count_label.setObjectName("InfoChip")
        layout.addWidget(label, 1)
        layout.addWidget(count_label)


class CallHistoryRow(QFrame):
    """Read-only row describing one SIM or app-call event received from the phone."""

    def __init__(self, event: CallHistoryEntry, on_clear: object) -> None:
        super().__init__()
        self.event = event
        self.on_clear = on_clear
        self.setObjectName("Card")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(space("card_x"), space("card_y"), space("card_x"), space("card_y"))
        layout.setSpacing(space("sm"))

        top = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(svg_icon("icon-phone-call.svg", color_name="accent", icon_size=26).pixmap(30, 30))
        icon.setFixedSize(34, 34)
        text = QVBoxLayout()
        title = QLabel(f"{self.event.source} - {self.event.state}")
        title.setObjectName("CardTitle")
        caller = QLabel(self.event.caller)
        caller.setObjectName("MutedLabel")
        caller.setWordWrap(True)
        text.addWidget(title)
        text.addWidget(caller)
        time_label = QLabel(format_epoch_ms(self.event.timestamp_ms))
        time_label.setObjectName("InfoChip")
        clear = QPushButton(tr("notifications.clear"))
        clear.clicked.connect(lambda: self.on_clear(self.event.event_id))
        top.addWidget(icon)
        top.addLayout(text, 1)
        top.addWidget(time_label)
        top.addWidget(clear)
        layout.addLayout(top)

        chips = QHBoxLayout()
        for value in (self.event.direction, self.event.sim, self.event.route):
            if value:
                chip = QLabel(value)
                chip.setObjectName("InfoChip")
                chips.addWidget(chip)
        chips.addStretch(1)
        layout.addLayout(chips)
        if self.event.detail:
            detail = QLabel(self.event.detail)
            detail.setObjectName("MutedLabel")
            detail.setWordWrap(True)
            layout.addWidget(detail)


class NotificationRow(QFrame):
    """One notification row with reply, copy, OTP copy, and local clear actions."""

    def __init__(self, runtime: DesktopRuntime, notification: notifications_pb2.NotificationPosted, on_clear: object) -> None:
        super().__init__()
        self.runtime = runtime
        self.notification = notification
        self.on_clear = on_clear
        self.setObjectName("Card")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(space("card_x"), space("card_y"), space("card_x"), space("card_y"))
        top = QHBoxLayout()
        icon = QLabel()
        icon.setFixedSize(34, 34)
        if self.notification.app_icon_png:
            pixmap = QPixmap()
            pixmap.loadFromData(self.notification.app_icon_png)
            icon.setPixmap(pixmap.scaled(34, 34, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        text = QVBoxLayout()
        title = QLabel(self.notification.title or tr("notifications.default_title"))
        title.setObjectName("CardTitle")
        body = QLabel(self.notification.body)
        body.setObjectName("MutedLabel")
        body.setWordWrap(True)
        app = QLabel(self.notification.app_name or self.notification.package_name or tr("notifications.unknown_app"))
        app.setObjectName("MutedLabel")
        text.addWidget(app)
        text.addWidget(title)
        if self.notification.body:
            text.addWidget(body)
        top.addWidget(icon)
        top.addLayout(text, 1)
        layout.addLayout(top)
        actions = QHBoxLayout()
        for action in self.notification.actions:
            if action.supports_remote_input:
                reply = QPushButton(action.title or tr("notifications.reply"))
                reply.clicked.connect(lambda checked=False, item=action: self._reply(item.action_id))
                actions.addWidget(reply)
            elif action.supports_plain_intent:
                run_action = QPushButton(action.title or notification_action_label(action.semantic))
                run_action.clicked.connect(lambda checked=False, item=action: self._run_action(item.action_id))
                actions.addWidget(run_action)
        copy_text = QPushButton(tr("notifications.copy_text"))
        copy_text.clicked.connect(self._copy_text)
        copy_otp = QPushButton(tr("notifications.copy_otp"))
        copy_otp.clicked.connect(self._copy_otp)
        clear = QPushButton(tr("notifications.clear"))
        clear.clicked.connect(lambda: self.on_clear(self.notification.notification_id))
        actions.addStretch(1)
        actions.addWidget(copy_text)
        actions.addWidget(copy_otp)
        actions.addWidget(clear)
        layout.addLayout(actions)

    def _reply(self, action_id: str) -> None:
        reply, ok = QInputDialog.getText(self, tr("notifications.reply"), self.notification.title)
        if ok:
            self.runtime.queue_notification_reply(self.notification.notification_id, action_id, reply)

    def _run_action(self, action_id: str) -> None:
        self.runtime.queue_notification_action(self.notification.notification_id, action_id)

    def _copy_text(self) -> None:
        QApplication.clipboard().setText("\n".join(part for part in (self.notification.title, self.notification.body) if part))

    def _copy_otp(self) -> None:
        match = re.search(r"\b\d{4,8}\b", f"{self.notification.title} {self.notification.body}")
        if match:
            QApplication.clipboard().setText(match.group(0))
        else:
            QMessageBox.information(self, tr("notifications.copy_otp"), tr("notifications.no_otp"))


class DialerDialog(QDialog):
    """Android-style dialer popup that sends desktop-originated phone dial requests."""

    def __init__(self, runtime: DesktopRuntime, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        prepare_popup(self)
        self.runtime = runtime
        self.setWindowTitle(tr("calls.title"))
        self.setMinimumSize(360, 560)
        self._build_ui()
        self.number.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(space("panel_x"), space("panel_y"), space("panel_x"), space("panel_y"))
        self.number = QLineEdit()
        self.number.setPlaceholderText(tr("calls.number"))
        self.number.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.number.returnPressed.connect(lambda: self._dial(1))
        layout.addWidget(self.number)
        layout.addLayout(self._dialpad())
        sim_row = QHBoxLayout()
        for sim_slot in range(1, self._sim_count() + 1):
            button = compact_button(f"{tr('calls.dial')} SIM {sim_slot}", primary=True)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.clicked.connect(lambda checked=False, slot=sim_slot: self._dial(slot))
            sim_row.addWidget(button)
        layout.addLayout(sim_row)
        close = compact_button(tr("common.close"))
        close.clicked.connect(self.accept)
        layout.addWidget(close, 0, Qt.AlignmentFlag.AlignHCenter)

    def _dialpad(self) -> QGridLayout:
        grid = QGridLayout()
        keys = (
            ("1", ""), ("2", "ABC"), ("3", "DEF"),
            ("4", "GHI"), ("5", "JKL"), ("6", "MNO"),
            ("7", "PQRS"), ("8", "TUV"), ("9", "WXYZ"),
            ("*", ""), ("0", "+"), ("#", ""),
        )
        for index, (digit, letters) in enumerate(keys):
            button = QPushButton(f"{digit}\n{letters}".strip())
            button.setObjectName("DialPadButton")
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.clicked.connect(lambda checked=False, value=digit: self._append_digit(value))
            grid.addWidget(button, index // 3, index % 3)
        return grid

    def _append_digit(self, digit: str) -> None:
        self.number.setText(f"{self.number.text()}{digit}")
        self.number.setFocus(Qt.FocusReason.OtherFocusReason)

    def keyPressEvent(self, event: object) -> None:
        text = event.text()
        if text in "0123456789*#+":
            self._append_digit(text)
            return
        if event.key() == Qt.Key.Key_Backspace:
            self.number.setText(self.number.text()[:-1])
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._dial(1)
            return
        super().keyPressEvent(event)

    def _dial(self, sim_slot: int) -> None:
        if self.runtime.queue_dial(self.number.text(), sim_slot):
            self.accept()
        else:
            QMessageBox.information(self, tr("calls.title"), tr("calls.number"))

    def _sim_count(self) -> int:
        match = re.search(r"sims=(\d+)", self.runtime.call_status())
        return max(1, min(4, int(match.group(1)))) if match else 2


class ContactsDialog(QDialog):
    """Popup contact browser that fetches recents on open and searches on demand."""

    def __init__(self, runtime: DesktopRuntime, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        prepare_popup(self)
        self.runtime = runtime
        self.setWindowTitle(tr("calls.contacts"))
        self.setMinimumSize(620, 620)
        self._results_layout: QVBoxLayout | None = None
        self._last_render_key = ""
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._send_search_request)
        self._build_ui()
        self.runtime.request_recent_contacts(limit=30)
        self._timer.start(1_500)
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(space("panel_x"), space("panel_y"), space("panel_x"), space("panel_y"))
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("calls.contact_search"))
        self.search.textChanged.connect(self._queue_search)
        layout.addWidget(self.search)
        self.status = QLabel("")
        self.status.setObjectName("MutedLabel")
        layout.addWidget(self.status)
        scroll, content = scroll_column()
        self._results_layout = content
        layout.addWidget(scroll, 1)

    def refresh(self) -> None:
        if self._results_layout is None:
            return
        status = self.runtime.contacts_status()
        contacts = self._visible_contacts()
        render_key = repr(
            (
                status,
                self.search.text().strip(),
                tuple((contact.contact_id, contact.display_name, contact.phone_number) for contact in contacts),
            )
        )
        if render_key == self._last_render_key:
            return
        self._last_render_key = render_key
        self.status.setText(status)
        clear_layout(self._results_layout)
        if not contacts:
            self._results_layout.addWidget(empty_label(tr("calls.no_search_results" if self.search.text().strip() else "calls.no_recents")))
        for contact in contacts:
            self._results_layout.addWidget(ContactDialRow(self.runtime, contact, self._sim_count()))
        self._results_layout.addStretch(1)

    def _queue_search(self, text: str) -> None:
        self._search_timer.start(280)
        self.refresh()

    def _send_search_request(self) -> None:
        text = self.search.text().strip()
        if text:
            self.runtime.request_contacts(text, limit=30)

    def _visible_contacts(self) -> list[contacts_pb2.PhoneContact]:
        query = self.search.text().strip().lower()
        if not query:
            return self.runtime.recent_contacts()
        remote = [
            contact
            for contact in self.runtime.contact_results()
            if query in f"{contact.display_name} {contact.phone_number}".lower()
        ]
        cached = self.runtime.recent_contacts()
        merged: dict[str, contacts_pb2.PhoneContact] = {
            contact.contact_id or contact.phone_number: contact for contact in remote
        }
        for contact in cached:
            haystack = f"{contact.display_name} {contact.phone_number}".lower()
            if query in haystack:
                merged.setdefault(contact.contact_id or contact.phone_number, contact)
        return list(merged.values())

    def closeEvent(self, event: object) -> None:
        self._timer.stop()
        self._search_timer.stop()
        super().closeEvent(event)

    def _sim_count(self) -> int:
        match = re.search(r"sims=(\d+)", self.runtime.call_status())
        return max(1, min(4, int(match.group(1)))) if match else 2


class ContactDialRow(QFrame):
    """Contact row with SIM-specific dial buttons."""

    def __init__(self, runtime: DesktopRuntime, contact: contacts_pb2.PhoneContact, sim_count: int) -> None:
        super().__init__()
        self.runtime = runtime
        self.contact = contact
        self.setObjectName("SoftPanel")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(space("sm"), space("xs"), space("sm"), space("xs"))
        layout.setSpacing(space("sm"))
        text = QVBoxLayout()
        name = QLabel(contact.display_name or contact.phone_number)
        name.setObjectName("CardTitle")
        detail = QLabel(contact.phone_number)
        detail.setObjectName("MutedLabel")
        text.addWidget(name)
        text.addWidget(detail)
        layout.addLayout(text, 1)
        for sim_slot in range(1, sim_count + 1):
            button = compact_button(f"SIM {sim_slot}")
            button.clicked.connect(lambda checked=False, slot=sim_slot: self.runtime.queue_dial(self.contact.phone_number, slot))
            layout.addWidget(button)


class PhoneFileBrowserDialog(QDialog):
    """Updated lazy phone file browser popup with icon navigation and context actions."""

    def __init__(self, runtime: DesktopRuntime, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        prepare_popup(self)
        self.runtime = runtime
        self._phone_listing_path = ""
        self._last_listing_key = ""
        self.setWindowTitle(tr("files.phone_browser"))
        self.setMinimumSize(size("popup_w"), size("popup_h"))
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._build_ui()
        self.runtime.request_phone_file_list("")
        self._timer.start(1_500)
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(space("panel_x"), space("panel_y"), space("panel_x"), space("panel_y"))
        nav = QHBoxLayout()
        home = IconButton("icon-home.svg", tr("files.root"), object_name="IconButtonMuted")
        home.clicked.connect(lambda: self.runtime.request_phone_file_list(""))
        back = IconButton("icon-back.svg", tr("files.up"), object_name="IconButtonMuted")
        back.clicked.connect(lambda: self.runtime.request_phone_file_list(parent_path(self._phone_listing_path)))
        self.path_input = QLineEdit()
        self.path_input.setObjectName("PathInput")
        self.path_input.setPlaceholderText("/")
        self.path_input.returnPressed.connect(self._go_to_path)
        refresh = IconButton("icon-refresh.svg", tr("files.refresh_folder"), object_name="IconButtonMuted")
        refresh.clicked.connect(lambda: self.runtime.request_phone_file_list(self._phone_listing_path))
        nav.addWidget(home)
        nav.addWidget(back)
        nav.addWidget(self.path_input, 1)
        nav.addWidget(refresh)
        layout.addLayout(nav)
        self.status = QLabel("")
        self.status.setObjectName("MutedLabel")
        layout.addWidget(self.status)
        self.tree = QTreeWidget()
        self.tree.setObjectName("PhoneFileTree")
        self.tree.setHeaderLabels([tr("files.column.name"), tr("files.column.modified")])
        self.tree.setRootIsDecorated(False)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._open_context_menu)
        self.tree.itemDoubleClicked.connect(lambda item, column: self._activate_item(item))
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.tree, 1)

    def refresh(self) -> None:
        listing = self.runtime.phone_file_listing()
        status = self.runtime.phone_file_status()
        if listing is None:
            listing_key = repr((status, None))
        else:
            listing_key = repr(
                (
                    status,
                    listing.path,
                    listing.success,
                    listing.detail,
                    tuple((entry.path, entry.name, entry.directory, entry.modified_epoch_ms) for entry in listing.entries),
                )
            )
        if listing_key == self._last_listing_key:
            return
        self._last_listing_key = listing_key
        self.status.setText(status)
        if listing is None:
            self.tree.clear()
            return
        self._phone_listing_path = listing.path
        self.path_input.setText(listing.path or "/")
        self.tree.clear()
        if not listing.success:
            self.tree.addTopLevelItem(QTreeWidgetItem([listing.detail, ""]))
            return
        for entry in listing.entries:
            item = QTreeWidgetItem([entry.name or entry.path or "/", format_epoch_ms(entry.modified_epoch_ms)])
            item.setIcon(0, svg_icon("icon-folder.svg" if entry.directory else "icon-file.svg", color_name="accent" if entry.directory else "muted"))
            item.setData(0, Qt.ItemDataRole.UserRole, entry)
            item.setToolTip(0, entry.path)
            self.tree.addTopLevelItem(item)
        if not listing.entries:
            self.tree.addTopLevelItem(QTreeWidgetItem([tr("files.empty_folder"), ""]))

    def _go_to_path(self) -> None:
        text = self.path_input.text().strip()
        self.runtime.request_phone_file_list("" if text == "/" else text)

    def _activate_item(self, item: QTreeWidgetItem) -> None:
        entry = item.data(0, Qt.ItemDataRole.UserRole)
        if entry is None:
            return
        if entry.directory:
            self.runtime.request_phone_file_list(entry.path)
        else:
            self.runtime.request_phone_file_pull(entry.path)

    def _open_context_menu(self, position: object) -> None:
        item = self.tree.itemAt(position)
        if item is None:
            return
        entry = item.data(0, Qt.ItemDataRole.UserRole)
        if entry is None:
            return
        menu = QMenu(self)
        if entry.directory:
            open_action = QAction(tr("files.context.open"), self)
            open_action.triggered.connect(lambda: self.runtime.request_phone_file_list(entry.path))
            menu.addAction(open_action)
        else:
            copy_action = QAction(tr("files.context.copy"), self)
            copy_action.triggered.connect(lambda: self.runtime.request_phone_file_pull(entry.path))
            send_action = QAction(tr("files.context.send_laptop"), self)
            send_action.triggered.connect(lambda: self.runtime.request_phone_file_pull(entry.path))
            menu.addAction(copy_action)
            menu.addAction(send_action)
        menu.exec(self.tree.viewport().mapToGlobal(position))


class SharedAppsDialog(QDialog):
    """Popup grid/list of shared Android app shortcuts."""

    def __init__(self, runtime: DesktopRuntime, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        prepare_popup(self)
        self.runtime = runtime
        self.setWindowTitle(tr("shared_apps.title"))
        self.setMinimumSize(640, 560)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(space("panel_x"), space("panel_y"), space("panel_x"), space("panel_y"))
        scroll, content = scroll_column()
        apps = self.runtime.shared_apps()
        if not apps:
            content.addWidget(empty_label(tr("shared_apps.empty")))
        current_category = ""
        for app in apps:
            category = app.category or tr("shared_apps.other")
            if category != current_category:
                current_category = category
                heading = QLabel(category)
                heading.setObjectName("CardTitle")
                content.addWidget(heading)
            content.addWidget(SharedAppDialogRow(self.runtime, app))
        content.addStretch(1)
        layout.addWidget(scroll, 1)


class SharedAppDialogRow(QFrame):
    """One app shortcut in the shared apps popup."""

    def __init__(self, runtime: DesktopRuntime, app: object) -> None:
        super().__init__()
        self.setObjectName("SoftPanel")
        layout = QHBoxLayout(self)
        icon = QLabel()
        icon.setFixedSize(36, 36)
        if app.icon_png:
            pixmap = QPixmap()
            pixmap.loadFromData(app.icon_png)
            icon.setPixmap(pixmap.scaled(36, 36, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        text = QVBoxLayout()
        name = QLabel(app.label)
        name.setObjectName("CardTitle")
        package = QLabel(app.package_name)
        package.setObjectName("MutedLabel")
        text.addWidget(name)
        text.addWidget(package)
        launch = compact_button(tr("shared_apps.launch"), primary=True)
        launch.clicked.connect(lambda: self._launch_app(runtime, app.package_name))
        layout.addWidget(icon)
        layout.addLayout(text, 1)
        layout.addWidget(launch)

    def _launch_app(self, runtime: DesktopRuntime, package_name: str) -> None:
        launch = runtime.launch_shared_app(package_name)
        if not launch.result.ok:
            QMessageBox.warning(self, tr("shared_apps.title"), launch.result.compact_output())


def settings_section(title_text: str) -> QFrame:
    section = QFrame()
    section.setObjectName("DeviceSettingsSection")
    layout = QVBoxLayout(section)
    layout.setContentsMargins(space("card_x"), space("card_y"), space("card_x"), space("card_y"))
    layout.setSpacing(space("sm"))
    title = QLabel(title_text)
    title.setObjectName("CardTitle")
    layout.addWidget(title)
    return section


def prepare_popup(dialog: QDialog) -> None:
    dialog.setObjectName("PopupDialog")
    dialog.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    dialog.setStyleSheet(f"QDialog#PopupDialog {{ background: {color('window')}; }}")
    repolish(dialog)


def switch_control(text: str, *, checked: bool = False) -> SwitchControl:
    return SwitchControl(text, checked=checked)


def compact_button(text: str, *, primary: bool = False) -> QPushButton:
    button = QPushButton(text)
    if primary:
        button.setObjectName("PrimaryButton")
    button.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    return button


def scroll_column() -> tuple[QScrollArea, QVBoxLayout]:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(space("none"), space("none"), space("none"), space("none"))
    layout.setSpacing(space("sm"))
    scroll.setWidget(content)
    return scroll, layout


def empty_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("MutedLabel")
    label.setWordWrap(True)
    return label


def clear_layout(layout: QVBoxLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()
        child_layout = item.layout()
        if child_layout is not None:
            clear_layout(child_layout)


def parent_path(path: str) -> str:
    text = path.rstrip("/")
    if not text:
        return ""
    parent = str(Path(text).parent)
    return "" if parent == "." else parent


def format_epoch_ms(epoch_ms: int) -> str:
    if not epoch_ms:
        return ""
    return datetime.fromtimestamp(epoch_ms / 1000).strftime("%Y-%m-%d %H:%M")


def notification_action_label(semantic: int) -> str:
    """Return a clear fallback label for notification actions without titles."""

    labels = {
        notifications_pb2.NOTIFICATION_ACTION_SEMANTIC_ANSWER_CALL: tr("calls.accept"),
        notifications_pb2.NOTIFICATION_ACTION_SEMANTIC_DECLINE_CALL: tr("calls.reject"),
        notifications_pb2.NOTIFICATION_ACTION_SEMANTIC_HANG_UP_CALL: tr("calls.hangup"),
        notifications_pb2.NOTIFICATION_ACTION_SEMANTIC_OPEN: tr("common.open"),
    }
    return labels.get(semantic, tr("notifications.run_action"))
