from __future__ import annotations

import threading
from typing import Callable

from linkable_desktop.discovery.models import DiscoveredDevice


class StatusWindowUnavailable(RuntimeError):
    """Raised when the optional status window cannot be launched."""


def launch_status_window(
    title: str,
    device_provider: Callable[[], list[DiscoveredDevice]],
    refresh_ms: int = 1000,
) -> None:
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception as exc:  # pragma: no cover - depends on local tkinter availability
        raise StatusWindowUnavailable("tkinter is not available on this system") from exc

    root = tk.Tk()
    root.title(title)
    root.geometry("900x420")

    columns = ("name", "endpoint", "version", "device_id", "source")
    tree = ttk.Treeview(root, columns=columns, show="headings")
    headings = {
        "name": "Name",
        "endpoint": "Endpoint",
        "version": "Version",
        "device_id": "Device ID",
        "source": "Source",
    }
    for column, heading in headings.items():
        tree.heading(column, text=heading)
        tree.column(column, width=140 if column != "device_id" else 220, anchor="w")
    tree.pack(fill="both", expand=True)

    stop_event = threading.Event()

    def refresh() -> None:
        if stop_event.is_set():
            return
        devices = device_provider()
        tree.delete(*tree.get_children())
        for device in devices:
            tree.insert(
                "",
                "end",
                values=(
                    device.name,
                    device.endpoint,
                    device.protocol_version,
                    device.device_id,
                    device.source.value,
                ),
            )
        root.after(refresh_ms, refresh)

    def on_close() -> None:
        stop_event.set()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    refresh()
    root.mainloop()

