from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QEvent, QUrl, Qt
from PyQt6.QtGui import QDesktopServices, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QSlider,
    QHeaderView,
    QSplitter,
    QStyle,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from linkable_desktop.app.runtime import DesktopRuntime
from linkable_desktop.proto import calls_pb2, contacts_pb2, notifications_pb2
from linkable_desktop.ui_pyqt.constants import tr
from linkable_desktop.ui_pyqt.theme import space


class NotificationsPanel(QFrame):
    """Panel that renders mirrored phone notifications and queues reply/action commands."""

    def __init__(self, runtime: DesktopRuntime) -> None:
        super().__init__()
        self.runtime = runtime
        self.setObjectName("Panel")
        self._items_layout: QVBoxLayout | None = None
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = panel_layout(self)
        root.addWidget(section_title(tr("notifications.title"), tr("notifications.subtitle")))
        scroll, content_layout = scroll_column()
        self._items_layout = content_layout
        root.addWidget(scroll, 1)

    def refresh(self) -> None:
        if self._items_layout is None:
            return
        clear_layout(self._items_layout)
        grouped: dict[str, list[notifications_pb2.NotificationPosted]] = defaultdict(list)
        for notification in self.runtime.notifications():
            app_name = notification.app_name or notification.package_name or tr("notifications.unknown_app")
            grouped[app_name].append(notification)
        if not grouped:
            self._items_layout.addWidget(empty_label(tr("notifications.empty")))
            self._items_layout.addStretch(1)
            return
        for app_name in sorted(grouped):
            heading = QLabel(app_name)
            heading.setObjectName("CardTitle")
            self._items_layout.addWidget(heading)
            for notification in grouped[app_name]:
                self._items_layout.addWidget(NotificationCard(self.runtime, notification))
        self._items_layout.addStretch(1)


class NotificationCard(QFrame):
    """One mirrored notification with app icon, body text, and supported Android actions."""

    def __init__(self, runtime: DesktopRuntime, notification: notifications_pb2.NotificationPosted) -> None:
        super().__init__()
        self.runtime = runtime
        self.notification = notification
        self.setObjectName("Card")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(space("card_x"), space("card_y"), space("card_x"), space("card_y"))
        layout.setSpacing(space("sm"))

        top = QHBoxLayout()
        icon = QLabel()
        icon.setFixedSize(36, 36)
        if self.notification.app_icon_png:
            pixmap = QPixmap()
            pixmap.loadFromData(self.notification.app_icon_png)
            icon.setPixmap(pixmap.scaled(36, 36, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        title_box = QVBoxLayout()
        title = QLabel(self.notification.title or tr("notifications.default_title"))
        title.setObjectName("CardTitle")
        title.setWordWrap(True)
        body = QLabel(self.notification.body)
        body.setObjectName("MutedLabel")
        body.setWordWrap(True)
        title_box.addWidget(title)
        if self.notification.body:
            title_box.addWidget(body)
        top.addWidget(icon)
        top.addLayout(title_box, 1)
        layout.addLayout(top)

        timestamp = QLabel(self._timestamp())
        timestamp.setObjectName("MutedLabel")
        layout.addWidget(timestamp)

        actions = QHBoxLayout()
        for action in self.notification.actions:
            if action.supports_remote_input:
                button = QPushButton(action.title or tr("notifications.reply"))
                button.clicked.connect(lambda checked=False, item=action: self._reply(item.action_id))
                actions.addWidget(button)
            elif action.supports_plain_intent:
                button = QPushButton(action.title or tr("notifications.run_action"))
                button.clicked.connect(lambda checked=False, item=action: self._run_action(item.action_id))
                actions.addWidget(button)
        actions.addStretch(1)
        layout.addLayout(actions)

    def _timestamp(self) -> str:
        posted = self.notification.posted_at.unix_epoch_ms
        if not posted:
            return ""
        return datetime.fromtimestamp(posted / 1000).strftime("%Y-%m-%d %H:%M")

    def _reply(self, action_id: str) -> None:
        reply, ok = QInputDialog.getText(self, tr("notifications.reply"), self.notification.title)
        if ok:
            self.runtime.queue_notification_reply(self.notification.notification_id, action_id, reply)

    def _run_action(self, action_id: str) -> None:
        self.runtime.queue_notification_action(self.notification.notification_id, action_id)


class FilesPanel(QFrame):
    """Panel for sending files, lazy phone browsing, and the desktop received-file folder."""

    def __init__(self, runtime: DesktopRuntime) -> None:
        super().__init__()
        self.runtime = runtime
        self.setObjectName("Panel")
        self._files_layout: QVBoxLayout | None = None
        self._phone_listing_path = ""
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = panel_layout(self)
        root.addWidget(section_title(tr("files.title"), tr("files.subtitle")))

        workspace = QSplitter(Qt.Orientation.Horizontal)
        workspace.setObjectName("FileWorkspace")
        workspace.setChildrenCollapsible(False)
        workspace.addWidget(self._phone_browser())
        workspace.addWidget(self._file_side_panel())
        workspace.setStretchFactor(0, 5)
        workspace.setStretchFactor(1, 1)
        workspace.setSizes([860, 260])
        root.addWidget(workspace, 1)

    def _file_side_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Card")
        panel.setMinimumWidth(260)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(space("card_x"), space("card_y"), space("card_x"), space("card_y"))
        layout.setSpacing(space("sm"))

        transfer_title = QLabel(tr("files.transfer_actions"))
        transfer_title.setObjectName("CardTitle")
        layout.addWidget(transfer_title)
        send = QPushButton(tr("files.send"))
        send.setObjectName("PrimaryButton")
        send.clicked.connect(self._pick_file)
        open_received = QPushButton(tr("files.open_received"))
        open_received.clicked.connect(self._open_received)
        layout.addWidget(send)
        layout.addWidget(open_received)

        heading = QLabel(tr("files.received"))
        heading.setObjectName("CardTitle")
        layout.addWidget(heading)
        scroll, content_layout = scroll_column()
        self._files_layout = content_layout
        layout.addWidget(scroll, 1)
        return panel

    def refresh(self) -> None:
        if self._files_layout is None:
            return
        self._refresh_phone_files()
        clear_layout(self._files_layout)
        files = self.runtime.received_files()
        if not files:
            self._files_layout.addWidget(empty_label(tr("files.empty")))
            self._files_layout.addStretch(1)
            return
        for path in files:
            self._files_layout.addWidget(FileRow(path))
        self._files_layout.addStretch(1)

    def _pick_file(self) -> None:
        file_name, _ = QFileDialog.getOpenFileName(self, tr("files.send"), str(Path.home()))
        if not file_name:
            return
        path = Path(file_name)
        if self.runtime.queue_send_file(path):
            QMessageBox.information(self, tr("files.title"), f"Queued {path.name} for phone transfer.")
        else:
            QMessageBox.warning(self, tr("files.title"), f"Cannot send selected file:\n{path}")

    def _open_received(self) -> None:
        path = self.runtime.received_files_dir()
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        self.refresh()

    def _phone_browser(self) -> QFrame:
        browser = QFrame()
        browser.setObjectName("Card")
        layout = QVBoxLayout(browser)
        layout.setContentsMargins(space("card_x"), space("card_y"), space("card_x"), space("card_y"))
        layout.setSpacing(space("sm"))

        header = QHBoxLayout()
        title = QLabel(tr("files.phone_browser"))
        title.setObjectName("CardTitle")
        root = QPushButton(tr("files.root"))
        root.clicked.connect(lambda: self.runtime.request_phone_file_list(""))
        up = QPushButton(tr("files.up"))
        up.clicked.connect(self._go_up_phone_folder)
        refresh = QPushButton(tr("files.refresh_folder"))
        refresh.clicked.connect(self._refresh_current_phone_folder)
        header.addWidget(title, 1)
        header.addWidget(root)
        header.addWidget(up)
        header.addWidget(refresh)
        layout.addLayout(header)

        address = QHBoxLayout()
        address_label = QLabel(tr("files.location"))
        address_label.setObjectName("MutedLabel")
        self.phone_path = QLineEdit()
        self.phone_path.setObjectName("PathInput")
        self.phone_path.setPlaceholderText("/")
        self.phone_path.returnPressed.connect(self._go_to_phone_path)
        go = QPushButton(tr("files.go"))
        go.clicked.connect(self._go_to_phone_path)
        address.addWidget(address_label)
        address.addWidget(self.phone_path, 1)
        address.addWidget(go)
        layout.addLayout(address)

        self.phone_status = QLabel("")
        self.phone_status.setObjectName("MutedLabel")
        self.phone_status.setWordWrap(True)
        layout.addWidget(self.phone_status)

        self.phone_tree = QTreeWidget()
        self.phone_tree.setObjectName("PhoneFileTree")
        self.phone_tree.setHeaderLabels([
            tr("files.column.name"),
            tr("files.column.type"),
            tr("files.column.size"),
            tr("files.column.modified"),
        ])
        self.phone_tree.setRootIsDecorated(False)
        self.phone_tree.setAlternatingRowColors(True)
        self.phone_tree.setUniformRowHeights(False)
        self.phone_tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.phone_tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.phone_tree.setMinimumHeight(440)
        self.phone_tree.itemDoubleClicked.connect(lambda item, column: self._activate_phone_item(item))
        self.phone_tree.itemActivated.connect(lambda item, column: self._activate_phone_item(item))
        self.phone_tree.itemSelectionChanged.connect(self._sync_phone_actions)
        header_view = self.phone_tree.header()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.phone_tree, 1)

        action_row = QHBoxLayout()
        self.phone_open = QPushButton(tr("files.open_folder"))
        self.phone_open.clicked.connect(self._open_selected_phone_entry)
        self.phone_copy = QPushButton(tr("files.copy_selected"))
        self.phone_copy.setObjectName("PrimaryButton")
        self.phone_copy.clicked.connect(self._copy_selected_phone_entry)
        action_row.addStretch(1)
        action_row.addWidget(self.phone_open)
        action_row.addWidget(self.phone_copy)
        layout.addLayout(action_row)
        return browser

    def _refresh_phone_files(self) -> None:
        listing = self.runtime.phone_file_listing()
        self.phone_status.setText(self.runtime.phone_file_status())
        if listing is None:
            self.phone_path.setText("")
            self.phone_status.setText(tr("files.no_phone_folder"))
            self.phone_tree.clear()
            self._sync_phone_actions()
            return
        self._phone_listing_path = listing.path
        self.phone_path.setText(listing.path or "/")
        self.phone_tree.clear()
        if not listing.success:
            item = QTreeWidgetItem([listing.detail, tr("files.error"), "", ""])
            self.phone_tree.addTopLevelItem(item)
            self._sync_phone_actions()
            return
        for entry in listing.entries:
            item = QTreeWidgetItem([
                entry.name or entry.path or "/",
                tr("files.type_folder") if entry.directory else (entry.mime_type or tr("files.type_file")),
                "" if entry.directory else format_size(entry.size_bytes),
                format_epoch_ms(entry.modified_epoch_ms),
            ])
            item.setIcon(
                0,
                self.style().standardIcon(
                    QStyle.StandardPixmap.SP_DirIcon if entry.directory else QStyle.StandardPixmap.SP_FileIcon,
                ),
            )
            item.setToolTip(0, entry.path)
            item.setData(0, Qt.ItemDataRole.UserRole, entry)
            if entry.directory:
                font = item.font(0)
                font.setBold(True)
                item.setFont(0, font)
            self.phone_tree.addTopLevelItem(item)
        if not listing.entries:
            self.phone_tree.addTopLevelItem(QTreeWidgetItem([tr("files.empty_folder"), "", "", ""]))
        else:
            self.phone_status.setText(
                f"{self.runtime.phone_file_status()}  {tr('files.item_count', count=len(listing.entries))}",
            )
        self._sync_phone_actions()

    def _selected_phone_entry(self) -> object | None:
        selected = self.phone_tree.selectedItems()
        if not selected:
            return None
        return selected[0].data(0, Qt.ItemDataRole.UserRole)

    def _activate_phone_item(self, item: QTreeWidgetItem) -> None:
        entry = item.data(0, Qt.ItemDataRole.UserRole)
        if entry is None:
            return
        if entry.directory:
            self.runtime.request_phone_file_list(entry.path)
        else:
            self.runtime.request_phone_file_pull(entry.path)

    def _sync_phone_actions(self) -> None:
        entry = self._selected_phone_entry()
        if entry is None:
            self.phone_open.setEnabled(False)
            self.phone_copy.setEnabled(False)
            return
        self.phone_open.setEnabled(entry.directory)
        self.phone_copy.setEnabled(not entry.directory)

    def _open_selected_phone_entry(self) -> None:
        entry = self._selected_phone_entry()
        if entry is not None and entry.directory:
            self.runtime.request_phone_file_list(entry.path)

    def _copy_selected_phone_entry(self) -> None:
        entry = self._selected_phone_entry()
        if entry is not None and not entry.directory:
            self.runtime.request_phone_file_pull(entry.path)

    def _go_up_phone_folder(self) -> None:
        self.runtime.request_phone_file_list(parent_path(self._phone_listing_path))

    def _refresh_current_phone_folder(self) -> None:
        self.runtime.request_phone_file_list(self._phone_listing_path)

    def _go_to_phone_path(self) -> None:
        text = self.phone_path.text().strip()
        self.runtime.request_phone_file_list("" if text == "/" else text)


class FileRow(QFrame):
    """Compact row for one file already received from the phone."""

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path
        self.setObjectName("Card")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(space("card_x"), space("sm"), space("card_x"), space("sm"))
        name = QLabel(path.name)
        name.setObjectName("CardTitle")
        meta = QLabel(tr("files.bytes", size=path.stat().st_size))
        meta.setObjectName("MutedLabel")
        open_button = QPushButton(tr("common.open"))
        open_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))))
        layout.addWidget(name, 1)
        layout.addWidget(meta)
        layout.addWidget(open_button)


class MirrorPanel(QFrame):
    """Panel that checks ADB/scrcpy state and launches USB or LAN mirroring."""

    def __init__(self, runtime: DesktopRuntime) -> None:
        super().__init__()
        self.runtime = runtime
        self.setObjectName("Panel")
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = panel_layout(self)
        root.addWidget(section_title(tr("mirror.title"), tr("mirror.subtitle")))
        actions = QHBoxLayout()
        refresh = QPushButton(tr("mirror.refresh"))
        usb = QPushButton(tr("mirror.usb"))
        lan = QPushButton(tr("mirror.lan"))
        usb.setObjectName("PrimaryButton")
        refresh.clicked.connect(self.refresh)
        usb.clicked.connect(self._mirror_usb)
        lan.clicked.connect(self._mirror_lan)
        actions.addWidget(refresh)
        actions.addWidget(usb)
        actions.addWidget(lan)
        actions.addStretch(1)
        root.addLayout(actions)
        self.status = QPlainTextEdit()
        self.status.setReadOnly(True)
        root.addWidget(self.status, 1)

    def refresh(self) -> None:
        self.status.setPlainText(self.runtime.mirror_status().format())

    def _mirror_usb(self) -> None:
        launch = self.runtime.launch_usb_mirror()
        self.status.setPlainText(launch.result.compact_output())

    def _mirror_lan(self) -> None:
        launch = self.runtime.launch_lan_mirror()
        self.status.setPlainText(launch.result.compact_output())


class CallAudioPanel(QFrame):
    """Phone Call panel with contact search, recent contacts, SIM dialing, and call audio controls."""

    def __init__(self, runtime: DesktopRuntime) -> None:
        super().__init__()
        self.runtime = runtime
        self.setObjectName("Panel")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._build_ui()
        self._install_keyboard_dialing()
        self.refresh()

    def _build_ui(self) -> None:
        root = panel_layout(self)
        root.addWidget(section_title(tr("calls.title"), tr("calls.subtitle")))

        content = QHBoxLayout()
        content.setSpacing(space("md"))
        root.addLayout(content, 1)

        dialer = QFrame()
        dialer.setObjectName("Card")
        dialer_layout = QVBoxLayout(dialer)
        dialer_layout.setContentsMargins(space("card_x"), space("card_y"), space("card_x"), space("card_y"))
        dialer_layout.setSpacing(space("sm"))
        dialer_title = QLabel(tr("calls.dialer"))
        dialer_title.setObjectName("CardTitle")
        dialer_layout.addWidget(dialer_title)
        self.number = QLineEdit()
        self.number.setPlaceholderText(tr("calls.number"))
        dialer_layout.addWidget(self.number)
        dialer_layout.addLayout(self._dialpad())
        sim_row = QHBoxLayout()
        sim_one = QPushButton(tr("calls.dial_sim_1"))
        sim_one.setObjectName("PrimaryButton")
        sim_one.clicked.connect(lambda: self._dial(1))
        sim_two = QPushButton(tr("calls.dial_sim_2"))
        sim_two.setObjectName("PrimaryButton")
        sim_two.clicked.connect(lambda: self._dial(2))
        sim_row.addWidget(sim_one)
        sim_row.addWidget(sim_two)
        dialer_layout.addLayout(sim_row)

        self.speaker = self._slider(tr("calls.speaker"), self.runtime.set_speaker_volume)
        self.microphone = self._slider(tr("calls.microphone"), self.runtime.set_microphone_volume)
        dialer_layout.addLayout(self.speaker)
        dialer_layout.addLayout(self.microphone)

        action_row = QHBoxLayout()
        for label, callback in (
            (tr("calls.accept"), lambda: self.runtime.queue_call_control(calls_pb2.CALL_CONTROL_ACTION_ACCEPT)),
            (tr("calls.reject"), lambda: self.runtime.queue_call_control(calls_pb2.CALL_CONTROL_ACTION_REJECT)),
            (tr("calls.hangup"), lambda: self.runtime.queue_call_control(calls_pb2.CALL_CONTROL_ACTION_HANGUP)),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            action_row.addWidget(button)
        dialer_layout.addLayout(action_row)

        utility_row = QHBoxLayout()
        ring = QPushButton(tr("calls.ring"))
        ring.clicked.connect(lambda: self.runtime.queue_ring_phone(True))
        stop_ring = QPushButton(tr("calls.stop_ring"))
        stop_ring.clicked.connect(lambda: self.runtime.queue_ring_phone(False))
        diagnostics = QPushButton(tr("calls.diagnostics"))
        diagnostics.clicked.connect(lambda: self.runtime.queue_telephony_diagnostics())
        utility_row.addWidget(ring)
        utility_row.addWidget(stop_ring)
        utility_row.addWidget(diagnostics)
        dialer_layout.addLayout(utility_row)

        self.status = QLabel("")
        self.status.setObjectName("MutedLabel")
        self.status.setWordWrap(True)
        dialer_layout.addWidget(self.status)
        dialer_layout.addStretch(1)
        content.addWidget(dialer, 1)

        contacts = QFrame()
        contacts.setObjectName("Card")
        contacts_layout = QVBoxLayout(contacts)
        contacts_layout.setContentsMargins(space("card_x"), space("card_y"), space("card_x"), space("card_y"))
        contacts_layout.setSpacing(space("sm"))
        contacts_title = QLabel(tr("calls.contacts"))
        contacts_title.setObjectName("CardTitle")
        contacts_layout.addWidget(contacts_title)
        self.contact_search = QLineEdit()
        self.contact_search.setPlaceholderText(tr("calls.contact_search"))
        self.contact_search.textChanged.connect(self._search_contacts)
        contacts_layout.addWidget(self.contact_search)
        self.contact_status = QLabel("")
        self.contact_status.setObjectName("MutedLabel")
        self.contact_status.setWordWrap(True)
        contacts_layout.addWidget(self.contact_status)

        search_heading = QLabel(tr("calls.search_results"))
        search_heading.setObjectName("CardTitle")
        contacts_layout.addWidget(search_heading)
        self.search_results = QVBoxLayout()
        contacts_layout.addLayout(self.search_results)

        recent_heading = QLabel(tr("calls.recent_contacts"))
        recent_heading.setObjectName("CardTitle")
        contacts_layout.addWidget(recent_heading)
        self.recent_contacts = QVBoxLayout()
        contacts_layout.addLayout(self.recent_contacts)
        contacts_layout.addStretch(1)
        content.addWidget(contacts, 1)

    def refresh(self) -> None:
        self.status.setText(self.runtime.call_status())
        connected = self.runtime.has_active_phone()
        self.contact_search.setEnabled(connected)
        if not connected:
            self.contact_search.setPlaceholderText(tr("calls.contact_search_disabled"))
        else:
            self.contact_search.setPlaceholderText(tr("calls.contact_search"))
        self._refresh_contacts()

    def _dial(self, sim_slot: int) -> None:
        if not self.runtime.queue_dial(self.number.text(), sim_slot):
            QMessageBox.information(self, tr("calls.title"), tr("calls.number"))

    def eventFilter(self, watched: object, event: object) -> bool:
        """Route hardware keyboard dialing keys to the dialer while this panel is visible."""

        if event.type() == QEvent.Type.KeyPress and self._should_handle_keyboard_dialing():
            if self._handle_keyboard_dial_event(event):
                return True
        return super().eventFilter(watched, event)

    def _dialpad(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setSpacing(space("sm"))
        keys = (
            ("1", ""), ("2", "ABC"), ("3", "DEF"),
            ("4", "GHI"), ("5", "JKL"), ("6", "MNO"),
            ("7", "PQRS"), ("8", "TUV"), ("9", "WXYZ"),
            ("*", ""), ("0", "+"), ("#", ""),
        )
        for index, (digit, letters) in enumerate(keys):
            button = QPushButton(f"{digit}\n{letters}".strip())
            button.setObjectName("DialPadButton")
            button.clicked.connect(lambda checked=False, value=digit: self._append_digit(value))
            grid.addWidget(button, index // 3, index % 3)
        return grid

    def _append_digit(self, digit: str) -> None:
        self.number.setText(f"{self.number.text()}{digit}")
        self.number.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def _install_keyboard_dialing(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def _should_handle_keyboard_dialing(self) -> bool:
        if not self.isVisible() or QApplication.activeModalWidget() is not None:
            return False
        focus = QApplication.focusWidget()
        if focus is self.contact_search:
            return False
        if isinstance(focus, QLineEdit) and focus is not self.number:
            return False
        return True

    def _handle_keyboard_dial_event(self, event: object) -> bool:
        key = event.key()
        modifiers = event.modifiers()
        command_modifier = (
            Qt.KeyboardModifier.ControlModifier |
            Qt.KeyboardModifier.AltModifier |
            Qt.KeyboardModifier.MetaModifier
        )
        if modifiers & command_modifier:
            if key == Qt.Key.Key_1:
                self._dial(1)
                return True
            if key == Qt.Key.Key_2:
                self._dial(2)
                return True
            return False
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._dial(1)
            return True
        if key == Qt.Key.Key_F1:
            self._dial(1)
            return True
        if key == Qt.Key.Key_F2:
            self._dial(2)
            return True
        if key == Qt.Key.Key_Backspace:
            self.number.setText(self.number.text()[:-1])
            return True
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Escape):
            self.number.clear()
            return True
        text = event.text()
        if text in "0123456789*#+":
            self._append_digit(text)
            return True
        return False

    def _search_contacts(self, text: str) -> None:
        query = text.strip()
        if query:
            self.runtime.request_contacts(query, limit=20)
        self._refresh_contacts()

    def _refresh_contacts(self) -> None:
        self.contact_status.setText(self.runtime.contacts_status())
        clear_layout(self.search_results)
        clear_layout(self.recent_contacts)
        if self.contact_search.text().strip():
            results = self.runtime.contact_results()
            if results:
                for contact in results:
                    self.search_results.addWidget(ContactRow(contact, self._use_contact))
            else:
                self.search_results.addWidget(empty_label(tr("calls.no_search_results")))
        else:
            self.search_results.addWidget(empty_label(tr("calls.search_hint")))
        recents = self.runtime.recent_contacts()
        if recents:
            for contact in recents:
                self.recent_contacts.addWidget(ContactRow(contact, self._use_contact))
        else:
            self.recent_contacts.addWidget(empty_label(tr("calls.no_recents")))

    def _use_contact(self, contact: contacts_pb2.PhoneContact) -> None:
        self.number.setText(contact.phone_number)

    def _slider(self, label: str, callback: object) -> QHBoxLayout:
        row = QHBoxLayout()
        text = QLabel(label)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setMinimum(0)
        slider.setMaximum(150)
        slider.setValue(80)
        slider.sliderReleased.connect(lambda: callback(slider.value()))
        row.addWidget(text)
        row.addWidget(slider, 1)
        return row


class ContactRow(QFrame):
    """Selectable contact row that fills the dialer with the phone number."""

    def __init__(self, contact: contacts_pb2.PhoneContact, on_use: object) -> None:
        super().__init__()
        self.contact = contact
        self.on_use = on_use
        self.setObjectName("SoftPanel")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(space("sm"), space("xs"), space("sm"), space("xs"))
        name = QLabel(contact.display_name or contact.phone_number)
        name.setObjectName("CardTitle")
        number = QLabel(self._detail())
        number.setObjectName("MutedLabel")
        text = QVBoxLayout()
        text.addWidget(name)
        text.addWidget(number)
        use = QPushButton(tr("calls.use_contact"))
        use.clicked.connect(lambda: self.on_use(self.contact))
        layout.addLayout(text, 1)
        layout.addWidget(use)

    def _detail(self) -> str:
        parts = [self.contact.phone_number]
        if self.contact.label:
            parts.append(self.contact.label)
        if self.contact.last_interaction_epoch_ms:
            parts.append(datetime.fromtimestamp(self.contact.last_interaction_epoch_ms / 1000).strftime("%Y-%m-%d %H:%M"))
        return " - ".join(part for part in parts if part)


class SharedAppsPanel(QFrame):
    """Panel showing phone-published shared app shortcuts and launching them on Android."""

    def __init__(self, runtime: DesktopRuntime) -> None:
        super().__init__()
        self.runtime = runtime
        self.setObjectName("Panel")
        self._apps_layout: QVBoxLayout | None = None
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = panel_layout(self)
        root.addWidget(section_title(tr("shared_apps.title"), tr("shared_apps.subtitle")))
        scroll, layout = scroll_column()
        self._apps_layout = layout
        root.addWidget(scroll, 1)

    def refresh(self) -> None:
        if self._apps_layout is None:
            return
        clear_layout(self._apps_layout)
        apps = self.runtime.shared_apps()
        if not apps:
            self._apps_layout.addWidget(empty_label(tr("shared_apps.empty")))
            self._apps_layout.addStretch(1)
            return
        grouped: dict[str, list[object]] = defaultdict(list)
        for app in apps:
            category = app.category or tr("shared_apps.other")
            grouped[category].append(app)
        for category in sorted(grouped):
            heading = QLabel(category)
            heading.setObjectName("CardTitle")
            self._apps_layout.addWidget(heading)
            for app in grouped[category]:
                self._apps_layout.addWidget(SharedAppRow(self.runtime, app))
        self._apps_layout.addStretch(1)


class SharedAppRow(QFrame):
    """One shared Android app shortcut that queues a desktop-originated launch request."""

    def __init__(self, runtime: DesktopRuntime, app: object) -> None:
        super().__init__()
        self.runtime = runtime
        self.app = app
        self.setObjectName("Card")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(space("card_x"), space("sm"), space("card_x"), space("sm"))
        icon = QLabel()
        icon.setFixedSize(36, 36)
        if app.icon_png:
            pixmap = QPixmap()
            pixmap.loadFromData(app.icon_png)
            icon.setPixmap(pixmap.scaled(36, 36, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        title = QLabel(app.label)
        title.setObjectName("CardTitle")
        package = QLabel(app.package_name)
        package.setObjectName("MutedLabel")
        text = QVBoxLayout()
        text.addWidget(title)
        text.addWidget(package)
        launch = QPushButton(tr("shared_apps.launch"))
        launch.setObjectName("PrimaryButton")
        launch.clicked.connect(lambda: self._launch_app(runtime, app.package_name))
        layout.addWidget(icon)
        layout.addLayout(text, 1)
        layout.addWidget(launch)

    def _launch_app(self, runtime: DesktopRuntime, package_name: str) -> None:
        launch = runtime.launch_shared_app(package_name)
        if not launch.result.ok:
            QMessageBox.warning(self, tr("shared_apps.title"), launch.result.compact_output())


def panel_layout(widget: QWidget) -> QVBoxLayout:
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(space("panel_x"), space("panel_y"), space("panel_x"), space("panel_y"))
    layout.setSpacing(space("md"))
    return layout


def section_title(title: str, subtitle: str) -> QWidget:
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(space("none"), space("none"), space("none"), space("none"))
    title_label = QLabel(title)
    title_label.setObjectName("SectionTitle")
    subtitle_label = QLabel(subtitle)
    subtitle_label.setObjectName("SectionSubtitle")
    subtitle_label.setWordWrap(True)
    layout.addWidget(title_label)
    layout.addWidget(subtitle_label)
    return box


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


def format_size(size_bytes: int) -> str:
    value = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size_bytes} B"


def format_epoch_ms(epoch_ms: int) -> str:
    if not epoch_ms:
        return ""
    return datetime.fromtimestamp(epoch_ms / 1000).strftime("%Y-%m-%d %H:%M")
