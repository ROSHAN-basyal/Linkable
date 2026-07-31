from __future__ import annotations


THEME: dict[str, object] = {
    "color": {
        "window": "#EEF3EF",
        "surface": "#FAFBF7",
        "surface_alt": "#E4ECE3",
        "ink": "#17221B",
        "muted": "#667268",
        "line": "#CAD5CA",
        "accent": "#186F4D",
        "accent_soft": "#D8EFE5",
        "danger": "#B4342C",
        "danger_soft": "#F8DDD9",
        "warning": "#8A5B13",
        "warning_soft": "#F6E7C7",
        "success": "#1C7A4E",
        "success_soft": "#D9F1E3",
        "pressed": "#123F2E",
        "brown": "#8A6846",
        "brown_soft": "#EFE3D5",
        "white": "#FFFFFF",
        "black": "#000000",
    },
    "radius": {
        "sm": 8,
        "md": 14,
        "lg": 22,
    },
    "space": {
        "none": 0,
        "xs": 4,
        "sm": 8,
        "card_x": 18,
        "card_y": 16,
        "md": 14,
        "panel_x": 24,
        "panel_y": 22,
        "lg": 22,
        "xl": 34,
    },
    "size": {
        "startup_min_w": 780,
        "startup_min_h": 620,
        "wizard_min_w": 760,
        "wizard_min_h": 640,
        "window_min_w": 980,
        "window_min_h": 640,
        "window_w": 1180,
        "window_h": 760,
        "sidebar_w": 245,
        "log_max_h": 150,
        "unit_min_h": 190,
        "icon_md": 22,
        "icon_button": 42,
        "icon_button_sm": 34,
        "switch_w": 52,
        "switch_h": 28,
        "popup_w": 860,
        "popup_h": 620,
        "device_card_min_h": 220,
    },
    "font": {
        "family": "Noto Sans",
        "mono": "JetBrains Mono",
    },
}


def color(name: str) -> str:
    return str(THEME["color"][name])  # type: ignore[index]


def radius(name: str) -> int:
    return int(THEME["radius"][name])  # type: ignore[index]


def space(name: str) -> int:
    return int(THEME["space"][name])  # type: ignore[index]


def size(name: str) -> int:
    return int(THEME["size"][name])  # type: ignore[index]


def build_stylesheet() -> str:
    """Build the application stylesheet from theme constants only."""

    c = THEME["color"]  # type: ignore[assignment]
    r = THEME["radius"]  # type: ignore[assignment]
    f = THEME["font"]  # type: ignore[assignment]
    s = THEME["space"]  # type: ignore[assignment]
    return f"""
    * {{
        font-family: "{f['family']}";
        color: {c['ink']};
    }}
    QMainWindow, QDialog, QDialog#PopupDialog {{
        background: {c['window']};
    }}
    QLabel#AppTitle {{
        font-size: 26px;
        font-weight: 800;
    }}
    QLabel#AppSubtitle, QLabel#MutedLabel {{
        color: {c['muted']};
    }}
    QLabel#TopMetaLabel {{
        color: {c['muted']};
        font-size: 11px;
        font-weight: 750;
    }}
    QLabel#TopMetaValue {{
        background: {c['surface_alt']};
        border: 1px solid {c['line']};
        border-radius: {r['md']}px;
        padding: 7px 10px;
        font-family: "{f['mono']}";
        color: {c['ink']};
    }}
    QLabel#SwitchLabel {{
        font-weight: 750;
        color: {c['muted']};
    }}
    QLabel#SwitchLabel[active="true"] {{
        color: {c['accent']};
    }}
    QLabel#SectionTitle {{
        font-size: 24px;
        font-weight: 800;
    }}
    QLabel#SectionSubtitle {{
        color: {c['muted']};
        font-size: 13px;
    }}
    QLabel#CardTitle {{
        font-weight: 800;
    }}
    QLabel#PathLabel {{
        background: {c['surface_alt']};
        border-radius: {r['sm']}px;
        padding: 7px 9px;
        color: {c['ink']};
        font-family: "{f['mono']}";
    }}
    QLabel#CameraPreview {{
        background: {c['black']};
        border: 1px solid {c['line']};
        border-radius: {r['lg']}px;
        color: {c['white']};
        font-weight: 750;
    }}
    QLabel#DeviceName {{
        font-size: 17px;
        font-weight: 850;
    }}
    QLabel#EmptyStateTitle {{
        font-size: 19px;
        font-weight: 850;
    }}
    QLabel#CommandHeading {{
        font-weight: 750;
    }}
    QFrame#Sidebar {{
        background: {c['surface']};
        border-right: 1px solid {c['line']};
    }}
    QFrame#TopBar {{
        background: {c['surface']};
        border: 1px solid {c['line']};
        border-radius: {r['lg']}px;
    }}
    QFrame#Panel, QFrame#Card, QFrame#CompatibilityCard {{
        background: {c['surface']};
        border: 1px solid {c['line']};
        border-radius: {r['lg']}px;
    }}
    QFrame#HomePanel {{
        background: transparent;
        border: 0;
    }}
    QFrame#DeviceCard {{
        background: {c['surface']};
        border: 1px solid {c['line']};
        border-radius: {r['lg']}px;
    }}
    QFrame#DeviceCard:hover {{
        border-color: {c['accent']};
    }}
    QFrame#ActionStrip {{
        background: {c['surface_alt']};
        border-radius: {r['lg']}px;
    }}
    QFrame#DeviceSettingsSection {{
        background: {c['surface']};
        border: 1px solid {c['line']};
        border-radius: {r['lg']}px;
    }}
    QFrame#Card[selected="true"] {{
        border-color: {c['accent']};
        background: {c['accent_soft']};
    }}
    QFrame#SoftPanel {{
        background: {c['surface_alt']};
        border: 1px solid transparent;
        border-radius: {r['md']}px;
    }}
    QFrame#SoftPanel:hover {{
        border-color: {c['line']};
        background: {c['surface']};
    }}
    QWidget#PopupBody {{
        background: {c['window']};
    }}
    QPushButton, QToolButton {{
        border: 1px solid {c['line']};
        border-radius: {r['md']}px;
        background: {c['white']};
        padding: 9px 13px;
        font-weight: 650;
    }}
    QPushButton {{
        min-width: 0px;
    }}
    QPushButton:hover, QToolButton:hover {{
        background: {c['accent_soft']};
        border-color: {c['accent']};
    }}
    QPushButton:focus, QToolButton:focus {{
        border-color: {c['accent']};
    }}
    QPushButton:pressed, QToolButton:pressed {{
        background: {c['pressed']};
        border-color: {c['pressed']};
        color: {c['white']};
    }}
    QPushButton:disabled, QToolButton:disabled {{
        background: {c['surface_alt']};
        border-color: {c['line']};
        color: {c['muted']};
    }}
    QPushButton#PrimaryButton, QToolButton#PrimaryButton {{
        background: {c['accent']};
        border-color: {c['accent']};
        color: {c['white']};
    }}
    QPushButton#PrimaryButton:hover, QToolButton#PrimaryButton:hover {{
        background: {c['success']};
        border-color: {c['success']};
        color: {c['white']};
    }}
    QPushButton#PrimaryButton:pressed, QToolButton#PrimaryButton:pressed {{
        background: {c['pressed']};
        border-color: {c['pressed']};
        color: {c['white']};
    }}
    QPushButton#DangerButton {{
        background: {c['danger_soft']};
        border-color: {c['danger']};
        color: {c['danger']};
    }}
    QPushButton#DangerButton:hover {{
        background: {c['danger']};
        border-color: {c['danger']};
        color: {c['white']};
    }}
    QPushButton#DangerButton:pressed {{
        background: {c['ink']};
        border-color: {c['ink']};
        color: {c['white']};
    }}
    QPushButton#SegmentButton, QToolButton#SegmentButton {{
        border-radius: {r['md']}px;
        background: {c['surface_alt']};
        padding: 8px 12px;
    }}
    QPushButton#SegmentButton[active="true"], QToolButton#SegmentButton[active="true"] {{
        background: {c['accent']};
        border-color: {c['accent']};
        color: {c['white']};
    }}
    QToolButton#IconButton, QToolButton#IconButtonGreen, QToolButton#IconButtonDanger, QToolButton#IconButtonMuted {{
        min-width: 42px;
        max-width: 42px;
        min-height: 42px;
        max-height: 42px;
        padding: 0;
        border-radius: 21px;
        background: {c['white']};
    }}
    QToolButton#IconButtonGreen {{
        background: {c['success_soft']};
        border-color: {c['success']};
    }}
    QToolButton#IconButtonDanger {{
        background: {c['danger_soft']};
        border-color: {c['danger']};
    }}
    QToolButton#IconButtonMuted {{
        background: {c['surface_alt']};
        border-color: {c['line']};
    }}
    QToolButton#IconButton:hover, QToolButton#IconButtonGreen:hover, QToolButton#IconButtonDanger:hover, QToolButton#IconButtonMuted:hover, QToolButton#RefreshButton:hover {{
        background: {c['accent_soft']};
        border-color: {c['accent']};
    }}
    QToolButton#IconButton:pressed, QToolButton#IconButtonGreen:pressed, QToolButton#IconButtonDanger:pressed, QToolButton#IconButtonMuted:pressed, QToolButton#RefreshButton:pressed {{
        background: {c['pressed']};
        border-color: {c['pressed']};
    }}
    QToolButton#RefreshButton {{
        min-width: 42px;
        max-width: 42px;
        min-height: 42px;
        max-height: 42px;
        padding: 0;
        border-radius: 21px;
    }}
    QPushButton#LanServiceToggle {{
        border-radius: {r['lg']}px;
        padding: 10px 16px;
        background: {c['white']};
        border-color: {c['line']};
        color: {c['ink']};
    }}
    QPushButton#LanServiceToggle[active="true"] {{
        background: {c['success']};
        border-color: {c['success']};
    }}
    QPushButton#AddDeviceButton {{
        background: {c['accent']};
        border-color: {c['accent']};
        color: {c['white']};
        border-radius: 24px;
        padding: 2px 18px 2px 10px;
        min-height: 48px;
    }}
    QPushButton#AddDeviceButton:hover {{
        background: {c['success']};
        border-color: {c['success']};
    }}
    QPushButton#AddDeviceButton:pressed {{
        background: {c['pressed']};
        border-color: {c['pressed']};
    }}
    QLabel#AddDevicePlus {{
        color: {c['white']};
        font-size: 42px;
        font-weight: 900;
        background: transparent;
    }}
    QLabel#AddDeviceLabel {{
        color: {c['white']};
        font-weight: 800;
        background: transparent;
    }}
    QPushButton#WifiAccessToggle {{
        background: {c['surface_alt']};
        border-radius: {r['lg']}px;
        padding: 9px 13px;
    }}
    QPushButton#WifiAccessToggle[mode="all"] {{
        background: {c['success_soft']};
        border-color: {c['success']};
        color: {c['success']};
    }}
    QPushButton#WifiAccessToggle[mode="safe"] {{
        background: {c['brown_soft']};
        border-color: {c['brown']};
        color: {c['brown']};
    }}
    QPushButton#SecondaryActionButton {{
        background: {c['surface_alt']};
    }}
    QPushButton#DialPadButton {{
        min-height: 58px;
        font-size: 18px;
        font-weight: 800;
        background: {c['surface_alt']};
    }}
    QPushButton#SidebarButton {{
        text-align: left;
        border: 0;
        background: transparent;
        padding: 12px 14px;
    }}
    QPushButton#SidebarButton[active="true"] {{
        background: {c['accent_soft']};
        color: {c['accent']};
    }}
    QLabel#StatusChip, QLabel#InfoChip {{
        border-radius: {r['sm']}px;
        padding: 5px 9px;
        background: {c['surface_alt']};
        color: {c['muted']};
    }}
    QLabel#SuccessChip {{
        border-radius: {r['sm']}px;
        padding: 5px 9px;
        background: {c['success_soft']};
        color: {c['success']};
    }}
    QLabel#WarningChip {{
        border-radius: {r['sm']}px;
        padding: 5px 9px;
        background: {c['brown_soft']};
        color: {c['brown']};
    }}
    QLabel#DangerChip {{
        border-radius: {r['sm']}px;
        padding: 5px 9px;
        background: {c['danger_soft']};
        color: {c['danger']};
    }}
    QLabel#StatusIcon {{
        background: {c['surface_alt']};
        border-radius: 18px;
        padding: 6px;
    }}
    QLabel#DeviceMeta {{
        color: {c['muted']};
        font-family: "{f['mono']}";
        font-size: 12px;
    }}
    QFrame#StatusDot {{
        border-radius: 6px;
        min-width: 12px;
        max-width: 12px;
        min-height: 12px;
        max-height: 12px;
    }}
    QFrame#StatusDot[status="connected"] {{
        background: {c['success']};
    }}
    QFrame#StatusDot[status="unavailable"], QFrame#StatusDot[status="manual"] {{
        background: {c['brown']};
    }}
    QTextEdit, QPlainTextEdit, QLineEdit, QSpinBox {{
        border: 1px solid {c['line']};
        border-radius: {r['md']}px;
        background: {c['surface']};
        color: {c['ink']};
        padding: 10px;
    }}
    QLineEdit#PathInput {{
        background: {c['surface_alt']};
        font-family: "{f['mono']}";
        padding: 8px 10px;
    }}
    QTextEdit, QPlainTextEdit {{
        font-family: "{f['mono']}";
    }}
    QTreeWidget#PhoneFileTree {{
        border: 1px solid {c['line']};
        border-radius: {r['md']}px;
        background: {c['surface']};
        alternate-background-color: {c['surface_alt']};
        color: {c['ink']};
        font-size: 14px;
    }}
    QTreeWidget#PhoneFileTree::item {{
        padding: 9px 8px;
        min-height: 34px;
    }}
    QTreeWidget#PhoneFileTree::item:selected {{
        background: {c['accent_soft']};
        color: {c['ink']};
    }}
    QHeaderView::section {{
        background: {c['surface_alt']};
        color: {c['ink']};
        border: 0;
        border-right: 1px solid {c['line']};
        border-bottom: 1px solid {c['line']};
        padding: 7px 8px;
        font-weight: 800;
    }}
    QSplitter#FileWorkspace::handle {{
        background: transparent;
        width: {s['sm']}px;
    }}
    QStackedWidget, QScrollArea QWidget {{
        background: transparent;
    }}
    QDialog#PopupDialog QStackedWidget, QDialog#PopupDialog QScrollArea QWidget {{
        background: {c['window']};
    }}
    QScrollArea {{
        border: 0;
        background: transparent;
    }}
    QScrollArea#DeviceScrollArea, QWidget#DeviceScrollContent, QWidget#DeviceScrollViewport {{
        background: transparent;
    }}
    QFrame#ActionPanel {{
        background: {c['surface']};
        border-radius: {r['md']}px;
        padding: {s['sm']}px;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
    }}
    QScrollBar::handle:vertical {{
        background: {c['line']};
        border-radius: 5px;
    }}
    """
