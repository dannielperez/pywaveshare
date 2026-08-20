"""ZLAN UDP management protocol used by Waveshare Ethernet modules.

The protocol packet may contain credentials. This module deliberately exposes only
known non-secret fields and preserves the original 167-byte parameter block privately.
"""

from __future__ import annotations

import ipaddress
import socket
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from pywaveshare._network import validate_host, validate_port, validate_timeout
from pywaveshare.exceptions import (
    ConfigurationError,
    ProtocolError,
    SafetyConfirmationRequired,
    TransportError,
)

MAGIC = b"ZL"
DISCOVER = 0x00
RESPONSE = 0x01
WRITE_AND_RESTART = 0x02
READ_UNICAST = 0x04
MANAGEMENT_PORT = 1092
PARAMETER_LENGTH = 167
PACKET_LENGTH = 170

# Offsets are relative to the 167-byte parameter block, not the three-byte header.
_LOCAL_IP = slice(0, 4)
_NETMASK = slice(4, 8)
_GATEWAY = slice(8, 12)
_LOCAL_PORT = slice(16, 18)
_WORK_MODE = 20
_DEVICE_ID = slice(31, 37)
_IP_MODE = 56
_APP_PROTOCOL = 60
_STATUS = 61
_WEB_PORT = slice(98, 100)
_VERSION = 103
_FEATURES = 104
_FUNCTION_ENABLE = 110

TCP_SERVER = 0
TRANSPARENT_PROTOCOL = 0


def command_packet(command: int) -> bytes:
    if command not in {DISCOVER, READ_UNICAST}:
        raise ValueError("only read-only query commands may be created without parameters")
    return MAGIC + bytes((command,)) + bytes(PARAMETER_LENGTH)


def _parse_response(packet: bytes) -> bytes:
    if len(packet) != PACKET_LENGTH:
        raise ProtocolError(f"ZLAN response must be exactly {PACKET_LENGTH} bytes")
    if packet[:2] != MAGIC or packet[2] != RESPONSE:
        raise ProtocolError("ZLAN response has an invalid header or command")
    return packet[3:]


def _ipv4_from_bytes(raw: bytes) -> str:
    return str(ipaddress.IPv4Address(raw))


def _ipv4_to_bytes(value: str, name: str) -> bytes:
    try:
        return ipaddress.IPv4Address(value).packed
    except ipaddress.AddressValueError:
        raise ConfigurationError(f"{name} must be an IPv4 address") from None


@dataclass(frozen=True)
class ZlanParameters:
    """Redacted view over a complete parameter block read from a device."""

    _raw: bytes = field(repr=False)
    _from_device: bool = field(default=False, repr=False)

    def __post_init__(self) -> None:
        if len(self._raw) != PARAMETER_LENGTH:
            raise ProtocolError(f"ZLAN parameter block must be {PARAMETER_LENGTH} bytes")

    @classmethod
    def from_response(cls, packet: bytes) -> ZlanParameters:
        return cls(_parse_response(packet), _from_device=True)

    @property
    def local_ip(self) -> str:
        return _ipv4_from_bytes(self._raw[_LOCAL_IP])

    @property
    def netmask(self) -> str:
        return _ipv4_from_bytes(self._raw[_NETMASK])

    @property
    def gateway(self) -> str:
        return _ipv4_from_bytes(self._raw[_GATEWAY])

    @property
    def local_port(self) -> int:
        return int.from_bytes(self._raw[_LOCAL_PORT], "big")

    @property
    def web_port(self) -> int:
        return int.from_bytes(self._raw[_WEB_PORT], "big")

    @property
    def dhcp_enabled(self) -> bool:
        return self._raw[_IP_MODE] == 1

    @property
    def work_mode(self) -> int:
        return self._raw[_WORK_MODE]

    @property
    def app_protocol(self) -> int:
        return self._raw[_APP_PROTOCOL]

    @property
    def connected(self) -> bool:
        return bool(self._raw[_STATUS] & 1)

    @property
    def device_id(self) -> str:
        return self._raw[_DEVICE_ID].hex(":").upper()

    @property
    def firmware_version(self) -> str:
        return f"1.{383 + self._raw[_VERSION]:03d}"

    @property
    def supports_dhcp(self) -> bool:
        return bool(self._raw[_FEATURES] & (1 << 5))

    @property
    def preserve_serial_buffer(self) -> bool:
        return bool(self._raw[_FUNCTION_ENABLE] & (1 << 7))

    def as_dict(self) -> dict[str, object]:
        """Return only fields known not to contain the management password."""

        return {
            "device_id": self.device_id,
            "local_ip": self.local_ip,
            "netmask": self.netmask,
            "gateway": self.gateway,
            "dhcp_enabled": self.dhcp_enabled,
            "local_port": self.local_port,
            "web_port": self.web_port,
            "work_mode": self.work_mode,
            "app_protocol": self.app_protocol,
            "connected": self.connected,
            "firmware_version": self.firmware_version,
            "supports_dhcp": self.supports_dhcp,
            "preserve_serial_buffer": self.preserve_serial_buffer,
        }

    def with_dhcp(self, enabled: bool) -> ZlanParameters:
        if enabled and not self.supports_dhcp:
            raise ConfigurationError("device response does not advertise DHCP support")
        return self._changed([(_IP_MODE, 1 if enabled else 0)])

    def with_static_network(
        self,
        *,
        local_ip: str,
        netmask: str,
        gateway: str,
    ) -> ZlanParameters:
        updates: list[tuple[int | slice, int | bytes]] = [
            (_LOCAL_IP, _ipv4_to_bytes(local_ip, "local_ip")),
            (_NETMASK, _ipv4_to_bytes(netmask, "netmask")),
            (_GATEWAY, _ipv4_to_bytes(gateway, "gateway")),
            (_IP_MODE, 0),
        ]
        return self._changed(updates)

    def with_http_relay_profile(
        self,
        *,
        local_port: int = 8000,
        preserve_serial_buffer: bool = True,
    ) -> ZlanParameters:
        """Set transport fields required by Waveshare's separately uploaded HTTP profile."""

        validate_port(local_port)
        function_enable = self._raw[_FUNCTION_ENABLE]
        if preserve_serial_buffer:
            function_enable |= 1 << 7
        else:
            function_enable &= ~(1 << 7)
        return self._changed(
            [
                (_LOCAL_PORT, local_port.to_bytes(2, "big")),
                (_WORK_MODE, TCP_SERVER),
                (_APP_PROTOCOL, TRANSPARENT_PROTOCOL),
                (_FUNCTION_ENABLE, function_enable),
            ]
        )

    def _changed(
        self,
        updates: Iterable[tuple[int | slice, int | bytes]],
    ) -> ZlanParameters:
        changed = bytearray(self._raw)
        for key, value in updates:
            if isinstance(key, int) and isinstance(value, int):
                changed[key] = value
            elif isinstance(key, slice) and isinstance(value, bytes):
                changed[key] = value
            else:  # pragma: no cover - internal update definitions are statically controlled
                raise TypeError("invalid internal ZLAN parameter update")
        return ZlanParameters(bytes(changed), _from_device=self._from_device)

    def _write_packet(self) -> bytes:
        if not self._from_device:
            raise SafetyConfirmationRequired(
                "ZLAN writes require a complete parameter block read from the device"
            )
        device_id = self._raw[_DEVICE_ID]
        if device_id == bytes(6):
            raise ProtocolError("ZLAN device ID is empty; refusing configuration write")
        return MAGIC + bytes((WRITE_AND_RESTART,)) + self._raw


SocketFactory = Callable[[int, int], socket.socket]


class ZlanClient:
    """Bounded UDP discovery/read/write client with no automatic write retries."""

    def __init__(
        self,
        *,
        timeout: float = 1.0,
        port: int = MANAGEMENT_PORT,
        socket_factory: SocketFactory = socket.socket,
    ) -> None:
        validate_timeout(timeout, "timeout")
        validate_port(port)
        self.timeout = timeout
        self.port = port
        self._socket_factory = socket_factory

    def read(self, host: str) -> ZlanParameters:
        target = validate_host(host)
        sock = self._socket_factory(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.settimeout(self.timeout)
            sock.sendto(command_packet(READ_UNICAST), (target, self.port))
            packet, _source = sock.recvfrom(2048)
            return ZlanParameters.from_response(packet)
        except TimeoutError as exc:
            raise TransportError("ZLAN unicast read timed out") from exc
        except OSError as exc:
            raise TransportError("ZLAN unicast read failed") from exc
        finally:
            sock.close()

    def discover(
        self,
        *,
        bind_host: str = "0.0.0.0",
        broadcast_host: str = "255.255.255.255",
    ) -> tuple[ZlanParameters, ...]:
        bind_address = validate_host(bind_host)
        broadcast_address = validate_host(broadcast_host)
        sock = self._socket_factory(socket.AF_INET, socket.SOCK_DGRAM)
        found: dict[str, ZlanParameters] = {}
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.bind((bind_address, 0))
            sock.settimeout(self.timeout)
            sock.sendto(command_packet(DISCOVER), (broadcast_address, self.port))
            deadline = time.monotonic() + self.timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                sock.settimeout(remaining)
                try:
                    packet, _source = sock.recvfrom(2048)
                except TimeoutError:
                    break
                try:
                    parameters = ZlanParameters.from_response(packet)
                except ProtocolError:
                    continue
                found[parameters.device_id] = parameters
        except OSError as exc:
            raise TransportError("ZLAN discovery failed") from exc
        finally:
            sock.close()
        return tuple(found[key] for key in sorted(found))

    def apply(
        self,
        host: str,
        parameters: ZlanParameters,
        *,
        confirm_restart: bool = False,
    ) -> None:
        """Send exactly one configuration write; the device restarts immediately."""

        if not confirm_restart:
            raise SafetyConfirmationRequired(
                "ZLAN configuration writes restart the device; pass confirm_restart=True"
            )
        target = validate_host(host)
        packet = parameters._write_packet()
        sock = self._socket_factory(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.settimeout(self.timeout)
            sent = sock.sendto(packet, (target, self.port))
            if sent != len(packet):
                raise TransportError("ZLAN configuration packet was not sent completely")
        except TimeoutError as exc:
            raise TransportError("ZLAN configuration write timed out") from exc
        except OSError as exc:
            raise TransportError("ZLAN configuration write failed") from exc
        finally:
            sock.close()
