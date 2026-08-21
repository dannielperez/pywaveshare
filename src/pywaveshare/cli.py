"""Operator CLI for relay validation and ZLAN provisioning."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from pywaveshare.exceptions import PyWaveshareError
from pywaveshare.relay import RelayClient
from pywaveshare.serial_server import SerialParity, SerialServerProfile
from pywaveshare.zlan import ZlanClient


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pywaveshare",
        description="Waveshare relay and ZLAN utility / Utilidad para relés Waveshare y ZLAN",
    )
    families = parser.add_subparsers(dest="family", required=True)

    relay = families.add_parser("relay", help="HTTP relay control / Control HTTP del relé")
    relay.add_argument("--host", required=True)
    relay.add_argument("--port", type=int, default=8000)
    relay.add_argument("--device-address", type=int, default=1)
    relay.add_argument("--connect-timeout", type=float, default=3.0)
    relay.add_argument("--read-timeout", type=float, default=3.0)
    relay_commands = relay.add_subparsers(dest="operation", required=True)
    relay_commands.add_parser("status", help="Read all channels / Leer todos los canales")

    state = relay_commands.add_parser("set", help="Set a channel / Cambiar un canal")
    state.add_argument("channel", type=int)
    state.add_argument("state", choices=("on", "off"))
    state.add_argument("--confirm", action="store_true")

    toggle = relay_commands.add_parser("toggle", help="Toggle a channel / Alternar un canal")
    toggle.add_argument("channel", type=int)
    toggle.add_argument("--confirm", action="store_true")

    pulse = relay_commands.add_parser("pulse", help="Pulse a channel / Pulsar un canal")
    pulse.add_argument("channel", type=int)
    pulse.add_argument("duration_ms", type=int)
    pulse.add_argument("--active-off", action="store_true")
    pulse.add_argument("--confirm", action="store_true")

    pulse_url = relay_commands.add_parser(
        "pulse-url",
        help="Print an Akuvox-compatible URL / Mostrar URL compatible con Akuvox",
    )
    pulse_url.add_argument("channel", type=int)
    pulse_url.add_argument("duration_ms", type=int)
    pulse_url.add_argument("--active-off", action="store_true")

    zlan = families.add_parser("zlan", help="UDP provisioning / Aprovisionamiento UDP")
    zlan.add_argument("--timeout", type=float, default=1.0)
    zlan.add_argument("--management-port", type=int, default=1092)
    zlan_commands = zlan.add_subparsers(dest="operation", required=True)

    read = zlan_commands.add_parser("read", help="Read by IP/VPN / Leer por IP/VPN")
    read.add_argument("--host", required=True)

    discover = zlan_commands.add_parser(
        "discover",
        help="Local Layer-2 discovery / Descubrimiento local de capa 2",
    )
    discover.add_argument("--bind-host", default="0.0.0.0")
    discover.add_argument("--broadcast-host", default="255.255.255.255")

    dhcp = zlan_commands.add_parser("dhcp", help="Enable DHCP / Activar DHCP")
    dhcp.add_argument("--host", required=True)
    dhcp.add_argument("--confirm-restart", action="store_true")

    profile = zlan_commands.add_parser(
        "relay-profile",
        help="Set HTTP transport fields / Configurar transporte HTTP",
    )
    profile.add_argument("--host", required=True)
    profile.add_argument("--relay-port", type=int, default=8000)
    profile.add_argument("--confirm-restart", action="store_true")

    serial = zlan_commands.add_parser(
        "serial-profile",
        help="Set transparent TCP client / Configurar cliente TCP transparente",
    )
    serial.add_argument("--host", required=True)
    serial.add_argument("--destination-ip", required=True)
    serial.add_argument("--destination-port", type=int, required=True)
    serial.add_argument("--local-port", type=int, default=0)
    serial.add_argument("--baud-rate", type=int, required=True)
    serial.add_argument("--data-bits", type=int, choices=(5, 6, 7, 8), default=8)
    serial.add_argument(
        "--parity",
        choices=tuple(item.value for item in SerialParity),
        default=SerialParity.NONE.value,
    )
    serial.add_argument("--stop-bits", type=int, choices=(1, 2), default=1)
    serial.add_argument("--packet-interval-ms", type=int)
    serial.add_argument("--packet-length", type=int)
    serial.add_argument("--reconnect-seconds", type=int, default=5)
    serial.add_argument("--keep-alive-seconds", type=int, default=15)
    buffer_policy = serial.add_mutually_exclusive_group(required=True)
    buffer_policy.add_argument("--preserve-serial-buffer", action="store_true")
    buffer_policy.add_argument("--clear-serial-buffer", action="store_true")
    serial.add_argument("--confirm-restart", action="store_true")
    return parser


def _relay_client(args: argparse.Namespace) -> RelayClient:
    return RelayClient(
        args.host,
        port=args.port,
        device_address=args.device_address,
        connect_timeout=args.connect_timeout,
        read_timeout=args.read_timeout,
    )


def _run_relay(args: argparse.Namespace) -> object:
    client = _relay_client(args)
    if args.operation == "status":
        return client.status().as_dict()
    if args.operation == "set":
        client.set_state(args.channel, args.state == "on", confirm=args.confirm)
        return {"ok": True, "operation": "set"}
    if args.operation == "toggle":
        client.toggle(args.channel, confirm=args.confirm)
        return {"ok": True, "operation": "toggle"}
    if args.operation == "pulse":
        client.pulse(
            args.channel,
            args.duration_ms,
            active_on=not args.active_off,
            confirm=args.confirm,
        )
        return {"ok": True, "operation": "pulse"}
    if args.operation == "pulse-url":
        return {
            "url": client.pulse_url(
                args.channel,
                args.duration_ms,
                active_on=not args.active_off,
            )
        }
    raise AssertionError("unhandled relay operation")


def _run_zlan(args: argparse.Namespace) -> object:
    client = ZlanClient(timeout=args.timeout, port=args.management_port)
    if args.operation == "read":
        return client.read(args.host).as_dict()
    if args.operation == "discover":
        return [
            item.as_dict()
            for item in client.discover(
                bind_host=args.bind_host,
                broadcast_host=args.broadcast_host,
            )
        ]
    current = client.read(args.host)
    if args.operation == "dhcp":
        changed = current.with_dhcp(True)
        client.apply(args.host, changed, confirm_restart=args.confirm_restart)
        return {"ok": True, "operation": "dhcp", "restart_expected": True}
    if args.operation == "relay-profile":
        changed = current.with_http_relay_profile(local_port=args.relay_port)
        client.apply(args.host, changed, confirm_restart=args.confirm_restart)
        return {
            "ok": True,
            "operation": "relay-profile",
            "restart_expected": True,
            "http_files_still_require_vircom_upload": True,
        }
    if args.operation == "serial-profile":
        profile = SerialServerProfile(
            destination_ip=args.destination_ip,
            destination_port=args.destination_port,
            local_port=args.local_port,
            baud_rate=args.baud_rate,
            data_bits=args.data_bits,
            parity=SerialParity(args.parity),
            stop_bits=args.stop_bits,
            packet_interval_ms=args.packet_interval_ms,
            packet_length=args.packet_length,
            reconnect_seconds=args.reconnect_seconds,
            keep_alive_seconds=args.keep_alive_seconds,
            preserve_serial_buffer=args.preserve_serial_buffer,
        )
        changed = profile.apply(current)
        client.apply(args.host, changed, confirm_restart=args.confirm_restart)
        return {
            "ok": True,
            "operation": "serial-profile",
            "restart_expected": True,
            "readback_required": True,
            "desired": profile.as_dict(),
        }
    raise AssertionError("unhandled ZLAN operation")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        result = _run_relay(args) if args.family == "relay" else _run_zlan(args)
    except (PyWaveshareError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

