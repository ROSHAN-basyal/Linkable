from __future__ import annotations

import argparse
import os
import socket
import sys
import time

from linkable_desktop.config import (
    IDENTITY_PATH,
    TRUST_STORE_PATH,
    ensure_state_dir,
    load_discovery_config,
    save_default_config_if_missing,
)
from linkable_desktop.bluetooth.hfp import HfpManager
from linkable_desktop.crypto.identity import DeviceIdentity
from linkable_desktop.discovery.fallback import parse_direct_connect_endpoint
from linkable_desktop.pairing.pairing_server import PairingServer
from linkable_desktop.transfer.file_sender import SendFileRequest
from linkable_desktop.trust.trust_store import TrustStore
from linkable_desktop.ui.cli import render_device_table


def cmd_advertise(send_file: str | None = None) -> int:
    from linkable_desktop.discovery.mdns_advertiser import DiscoveryAdvertisement

    config = load_discovery_config()
    ensure_state_dir()
    identity = DeviceIdentity.load_or_create(IDENTITY_PATH, device_name=config.device_name)
    config.device_id = identity.device_id
    trust_store = TrustStore(TRUST_STORE_PATH)
    advertisement = DiscoveryAdvertisement(config)
    send_file_request = None
    if send_file is not None:
        try:
            send_file_request = SendFileRequest.from_path(send_file)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    pairing_server = PairingServer(
        config=config,
        identity=identity,
        trust_store=trust_store,
        send_file_request=send_file_request,
    )
    try:
        advertisement.start()
        pairing_server.start()
    except RuntimeError as exc:
        print(f"unable to advertise service: {exc}", file=sys.stderr)
        return 2
    print(f"Advertising {config.device_name} on {config.service_type} port {config.service_port}", flush=True)
    print(f"mDNS backend: {advertisement.backend_name()}", flush=True)
    if advertisement.info is not None:
        addresses = [socket.inet_ntoa(address) for address in advertisement.info.addresses]
        print(f"Advertised IPv4: {', '.join(addresses)}", flush=True)
    print(f"Device ID: {identity.device_id}", flush=True)
    print("Pairing server is listening for phone pairing requests.", flush=True)
    if send_file_request is not None:
        print(f"Will send file to the next trusted phone session: {send_file_request.path}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping advertisement.")
    finally:
        pairing_server.stop()
        advertisement.stop()
    return 0


def cmd_browse(status_window: bool = False) -> int:
    from linkable_desktop.discovery.mdns_browser import DiscoveryBrowserController

    config = load_discovery_config()
    browser = DiscoveryBrowserController(service_type=config.service_type)
    try:
        browser.start()
    except RuntimeError as exc:
        print(f"unable to browse services: {exc}", file=sys.stderr)
        return 2
    try:
        if status_window:
            from linkable_desktop.ui.status_window import StatusWindowUnavailable, launch_status_window

            try:
                launch_status_window("Linkable Discovery", browser.registry.snapshot)
                return 0
            except StatusWindowUnavailable as exc:
                print(f"status window unavailable: {exc}", file=sys.stderr)
                return 2

        while True:
            print("\033[2J\033[H", end="")
            print(f"Browsing {config.service_type} every {config.browse_interval_sec:.1f}s\n")
            print(render_device_table(browser.registry.snapshot()))
            time.sleep(config.browse_interval_sec)
    except KeyboardInterrupt:
        print("\nStopping browser.")
    finally:
        browser.stop()
    return 0


def cmd_connect_by_ip(endpoint: str) -> int:
    config = load_discovery_config()
    candidate = parse_direct_connect_endpoint(endpoint, default_port=config.service_port)
    device = candidate.to_device(device_name="Direct Connect Candidate")
    print(render_device_table([device]))
    print("\nTransport bootstrap is not implemented in Milestone 2 yet.")
    return 0


def cmd_list_trusted() -> int:
    records = TrustStore(TRUST_STORE_PATH).list_records()
    if not records:
        print("No trusted devices paired yet.")
        return 0
    for record in records:
        print(f"{record.device_name} ({record.device_id}) paired_at={record.paired_at_epoch_ms}")
    return 0


def cmd_forget_trusted(device_id: str) -> int:
    removed = TrustStore(TRUST_STORE_PATH).remove(device_id)
    if removed:
        print(f"Removed trusted device {device_id}.")
        return 0
    print(f"Trusted device {device_id} was not found.", file=sys.stderr)
    return 1


def cmd_hfp_status() -> int:
    print(HfpManager().status().format())
    return 0


def cmd_hfp_install_phone_safe() -> int:
    result = HfpManager().install_phone_safe_mode()
    print(result.compact_output())
    print("Reconnect the phone Bluetooth connection if Android still shows this laptop as media audio.")
    return 0 if result.ok else 1


def cmd_hfp_remove_phone_safe() -> int:
    result = HfpManager().remove_phone_safe_mode()
    print(result.compact_output())
    print("Reconnect Bluetooth devices after removing phone-safe mode.")
    return 0 if result.ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Linkable desktop Milestone 3 utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-config", help="Write the default config file if it does not exist")
    advertise = subparsers.add_parser("advertise", help="Advertise the desktop service on the LAN")
    advertise.add_argument("--send-file", help="Send one file to the next trusted phone session")
    browse = subparsers.add_parser("browse", help="Browse for devices on the LAN")
    browse.add_argument("--status-window", action="store_true", help="Open a Tk status window instead of terminal output")
    direct = subparsers.add_parser("connect-by-ip", help="Parse and display a direct-connect candidate")
    direct.add_argument("endpoint", help="host:port or host")
    subparsers.add_parser("list-trusted", help="List trusted paired devices")
    forget = subparsers.add_parser("forget-trusted", help="Remove a trusted device by device ID")
    forget.add_argument("device_id", help="Trusted device identifier")
    subparsers.add_parser("hfp-status", help="Show Bluetooth HFP/PipeWire readiness for SIM call audio")
    subparsers.add_parser("hfp-install-phone-safe", help="Disable laptop A2DP sink role so phones do not route media audio here")
    subparsers.add_parser("hfp-remove-phone-safe", help="Remove the Linkable WirePlumber phone-safe Bluetooth config")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init-config":
        path = save_default_config_if_missing()
        print(f"Config ready at {path}")
        return 0
    if args.command == "advertise":
        return cmd_advertise(send_file=args.send_file)
    if args.command == "browse":
        return cmd_browse(status_window=args.status_window)
    if args.command == "connect-by-ip":
        return cmd_connect_by_ip(args.endpoint)
    if args.command == "list-trusted":
        return cmd_list_trusted()
    if args.command == "forget-trusted":
        return cmd_forget_trusted(args.device_id)
    if args.command == "hfp-status":
        return cmd_hfp_status()
    if args.command == "hfp-install-phone-safe":
        return cmd_hfp_install_phone_safe()
    if args.command == "hfp-remove-phone-safe":
        return cmd_hfp_remove_phone_safe()
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    exit_code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(exit_code)
