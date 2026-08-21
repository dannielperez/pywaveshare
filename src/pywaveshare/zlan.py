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
from typing import TYPE_CHECKING

from pywaveshare._network import validate_host, validate_port, validate_timeout
from pywaveshare.exceptions import (
    ConfigurationError,
    ProtocolError,
    SafetyConfirmationRequired,
    TransportError,
)

if TYPE_CHECKING:
    from pywaveshare.serial_server import SerialServerProfile

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
_DESTINATION_IP = slice(12, 16)
_LOCAL_PORT = slice(16, 18)
_DESTINATION_PORT = slice(18, 20)
_WORK_MODE = 20
_DEVICE_ID = slice(31, 37)
_BAUD_RATE = 37
_PARITY = 48
_PACKET_INTERVAL = 49
_PACKET_LENGTH = slice(50, 52)
_IP_MODE = 56
_FLOW_CONTROL = 57
_DESTINATION_MODE = 58
_DATA_BITS = 59
_APP_PROTOCOL = 60
_STATUS = 61
_DESTINATION_STRING = slice(66, 96)
_RECONNECT_TIME = 96
_KEEP_ALIVE_TIME = 97
_WEB_PORT = slice(98, 100)
_VERSION = 103
_FEATURES = 104
_FUNCTION_ENABLE = 110
_OTHER_BITS = 114
_VARIABLE_PARAMETERS = slice(115, 167)

TCP_SERVER = 0
TCP_CLIENT = 1
TRANSPARENT_PROTOCOL = 0

_BAUD_RATE_BY_INDEX = {
    0: 1200,
    1: 2400,
    2: 4800,
    3: 7200,
    4: 9600,
    5: 14400,
    6: 19200,
    7: 28800,
    8: 38400,
    9: 57600,
    10: 76800,
    11: 115200,
    12: 230400,
    13: 460800,
}
_BAUD_INDEX_BY_RATE = {value: key for key, value in _BAUD_RATE_BY_INDEX.items()}
_PARITY_BY_VALUE = {0: "none", 1: "odd", 2: "even", 3: "mark", 4: "space"}
_PARITY_VALUE_BY_NAME = {value: key for key, value in _PARITY_BY_VALUE.items()}
_DATA_BITS_BY_VALUE = {0: 8, 1: 7, 2: 6, 3: 5}
_DATA_BITS_VALUE_BY_COUNT = {value: key for key, value in _DATA_BITS_BY_VALUE.items()}
_COUNTER_VARIABLE_TYPES = {9, 10}


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
    def destination_ip(self) -> str:
        destination = self._raw[_DESTINATION_STRING].split(b"\0", 1)[0]
        if destination:
            try:
                return str(ipaddress.IPv4Address(destination.decode("ascii")))
            except (UnicodeDecodeError, ipaddress.AddressValueError):
                pass
        return _ipv4_from_bytes(self._raw[_DESTINATION_IP])

    @property
    def destination_port(self) -> int:
        return int.from_bytes(self._raw[_DESTINATION_PORT], "big")

    @property
    def baud_rate(self) -> int | None:
        return _BAUD_RATE_BY_INDEX.get(self._raw[_BAUD_RATE])

    @property
    def parity(self) -> str | None:
        return _PARITY_BY_VALUE.get(self._raw[_PARITY])

    @property
    def packet_interval_ms(self) -> int:
        return self._raw[_PACKET_INTERVAL]

    @property
    def packet_length(self) -> int:
        return int.from_bytes(self._raw[_PACKET_LENGTH], "big")

    @property
    def flow_control(self) -> int:
        return self._raw[_FLOW_CONTROL]

    @property
    def data_bits(self) -> int | None:
        return _DATA_BITS_BY_VALUE.get(self._raw[_DATA_BITS])

    @property
    def stop_bits(self) -> int:
        return 2 if self._raw[_OTHER_BITS] & 1 else 1

    @property
    def reconnect_seconds(self) -> int:
        return self._raw[_RECONNECT_TIME]

    @property
    def keep_alive_seconds(self) -> int:
        return self._raw[_KEEP_ALIVE_TIME]

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

    @property
    def application_payloads_disabled(self) -> bool:
        """Whether the current state emits no known application-layer management payload."""

        function_enable = self._raw[_FUNCTION_ENABLE]
        return (
            self.app_protocol == TRANSPARENT_PROTOCOL
            and not function_enable & (1 << 1)
            and not function_enable & (1 << 5)
            and self._variable_application_payloads_safe()
        )

    def _variable_application_payloads_safe(self) -> bool:
        """Accept only empty variable data or the documented read-only TX/RX counters."""

        raw = self._raw[_VARIABLE_PARAMETERS]
        position = 0
        while position < len(raw):
            parameter_type = raw[position]
            if parameter_type == 0:
                return not any(raw[position + 1 :])
            if position + 1 >= len(raw):
                return False
            length = raw[position + 1]
            end = position + 2 + length
            if end > len(raw):
                return False
            if parameter_type not in _COUNTER_VARIABLE_TYPES or length != 4:
                return False
            position = end
        return True

    def as_dict(self) -> dict[str, object]:
        """Return only fields known not to contain the management password."""

        return {
            "device_id": self.device_id,
            "local_ip": self.local_ip,
            "netmask": self.netmask,
            "gateway": self.gateway,
            "dhcp_enabled": self.dhcp_enabled,
            "local_port": self.local_port,
            "destination_ip": self.destination_ip,
            "destination_port": self.destination_port,
            "web_port": self.web_port,
            "work_mode": self.work_mode,
            "app_protocol": self.app_protocol,
            "baud_rate": self.baud_rate,
            "data_bits": self.data_bits,
            "parity": self.parity,
            "stop_bits": self.stop_bits,
            "flow_control": self.flow_control,
            "packet_interval_ms": self.packet_interval_ms,
            "packet_length": self.packet_length,
            "reconnect_seconds": self.reconnect_seconds,
            "keep_alive_seconds": self.keep_alive_seconds,
            "connected": self.connected,
            "firmware_version": self.firmware_version,
            "supports_dhcp": self.supports_dhcp,
            "preserve_serial_buffer": self.preserve_serial_buffer,
            "application_payloads_disabled": self.application_payloads_disabled,
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

    def with_serial_server_profile(self, profile: SerialServerProfile) -> ZlanParameters:
        """Set a transparent TCP-client profile while preserving unknown/password bytes."""

        if not self._variable_application_payloads_safe():
            raise ConfigurationError(
                "device variable parameters may contain registration, heartbeat, or another "
                "application payload; clear those features in VirCom and read again"
            )
        try:
            baud_index = _BAUD_INDEX_BY_RATE[profile.baud_rate]
        except KeyError:
            raise ConfigurationError(
                "baud_rate is not mapped by the documented ZLAN protocol; supported values are "
                + ", ".join(str(value) for value in _BAUD_INDEX_BY_RATE)
            ) from None
        parity_value = _PARITY_VALUE_BY_NAME[profile.parity.value]
        data_bits_value = _DATA_BITS_VALUE_BY_COUNT[profile.data_bits]
        destination = profile.destination_ip.encode("ascii") + b"\0"
        destination_string = destination.ljust(
            _DESTINATION_STRING.stop - _DESTINATION_STRING.start,
            b"\0",
        )
        function_enable = self._raw[_FUNCTION_ENABLE]
        function_enable &= ~(1 << 1)  # periodic ZLAN parameters to destination
        function_enable &= ~(1 << 5)  # send MAC on TCP connection
        if profile.preserve_serial_buffer:
            function_enable |= 1 << 7
        else:
            function_enable &= ~(1 << 7)
        other_bits = self._raw[_OTHER_BITS]
        if profile.stop_bits == 2:
            other_bits |= 1
        else:
            other_bits &= ~1
        updates: list[tuple[int | slice, int | bytes]] = [
            (_DESTINATION_IP, _ipv4_to_bytes(profile.destination_ip, "destination_ip")),
            (_LOCAL_PORT, profile.local_port.to_bytes(2, "big")),
            (_DESTINATION_PORT, profile.destination_port.to_bytes(2, "big")),
            (_WORK_MODE, TCP_CLIENT),
            (_BAUD_RATE, baud_index),
            (_PARITY, parity_value),
            (_FLOW_CONTROL, 0),
            (_DESTINATION_MODE, 0),
            (_DATA_BITS, data_bits_value),
            (_APP_PROTOCOL, TRANSPARENT_PROTOCOL),
            (_DESTINATION_STRING, destination_string),
            (_RECONNECT_TIME, profile.reconnect_seconds),
            (_KEEP_ALIVE_TIME, profile.keep_alive_seconds),
            (_FUNCTION_ENABLE, function_enable),
            (_OTHER_BITS, other_bits),
        ]
        if profile.packet_interval_ms is not None:
            updates.append((_PACKET_INTERVAL, profile.packet_interval_ms))
        if profile.packet_length is not None:
            updates.append((_PACKET_LENGTH, profile.packet_length.to_bytes(2, "big")))
        return self._changed(updates)

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
