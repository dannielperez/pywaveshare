"""Typed profiles for Waveshare serial-to-Ethernet gateways."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from enum import Enum

from pywaveshare._network import validate_port
from pywaveshare.exceptions import ConfigurationError
from pywaveshare.zlan import ZlanParameters


class SerialParity(str, Enum):
    """Parity values documented by the Waveshare programming interface."""

    NONE = "none"
    ODD = "odd"
    EVEN = "even"
    MARK = "mark"
    SPACE = "space"


@dataclass(frozen=True)
class SerialServerProfile:
    """Desired transparent TCP-client profile for one serial data feed.

    ``preserve_serial_buffer`` is deliberately required. Replaying buffered serial data after a
    network outage and dropping it are both policy choices, so callers must select one explicitly.
    """

    destination_ip: str
    destination_port: int
    baud_rate: int
    preserve_serial_buffer: bool
    data_bits: int = 8
    parity: SerialParity = SerialParity.NONE
    stop_bits: int = 1
    local_port: int = 0
    packet_interval_ms: int | None = None
    packet_length: int | None = None
    reconnect_seconds: int = 5
    keep_alive_seconds: int = 15

    def __post_init__(self) -> None:
        if not isinstance(self.preserve_serial_buffer, bool):
            raise ConfigurationError("preserve_serial_buffer must be a boolean")
        try:
            parsed_ip = ipaddress.IPv4Address(self.destination_ip)
        except ipaddress.AddressValueError:
            raise ConfigurationError("destination_ip must be an IPv4 address") from None
        object.__setattr__(self, "destination_ip", str(parsed_ip))
        validate_port(self.destination_port)
        if not 0 <= self.local_port <= 65535:
            raise ConfigurationError("local_port must be between 0 and 65535")
        if self.data_bits not in {5, 6, 7, 8}:
            raise ConfigurationError("data_bits must be one of 5, 6, 7, or 8")
        try:
            parity = SerialParity(self.parity)
        except ValueError:
            raise ConfigurationError("parity is not supported") from None
        object.__setattr__(self, "parity", parity)
        if self.stop_bits not in {1, 2}:
            raise ConfigurationError("stop_bits must be 1 or 2")
        if self.packet_interval_ms is not None and not 0 <= self.packet_interval_ms <= 255:
            raise ConfigurationError("packet_interval_ms must be between 0 and 255")
        if self.packet_length is not None and not 1 <= self.packet_length <= 1400:
            raise ConfigurationError("packet_length must be between 1 and 1400")
        if not 0 <= self.reconnect_seconds <= 255:
            raise ConfigurationError("reconnect_seconds must be between 0 and 255")
        if not 0 <= self.keep_alive_seconds <= 255:
            raise ConfigurationError("keep_alive_seconds must be between 0 and 255")

    def apply(self, parameters: ZlanParameters) -> ZlanParameters:
        """Return a read-modify-write result without contacting the device."""

        return parameters.with_serial_server_profile(self)

    def as_dict(self) -> dict[str, object]:
        return {
            "destination_ip": self.destination_ip,
            "destination_port": self.destination_port,
            "local_port": self.local_port,
            "baud_rate": self.baud_rate,
            "data_bits": self.data_bits,
            "parity": self.parity.value,
            "stop_bits": self.stop_bits,
            "packet_interval_ms": self.packet_interval_ms,
            "packet_length": self.packet_length,
            "reconnect_seconds": self.reconnect_seconds,
            "keep_alive_seconds": self.keep_alive_seconds,
            "preserve_serial_buffer": self.preserve_serial_buffer,
            "work_mode": "tcp_client",
            "application_protocol": "transparent",
            "flow_control": "none",
            "application_payloads": "disabled",
        }
