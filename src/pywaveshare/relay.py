"""HTTP control for Waveshare Modbus PoE Ethernet relays."""

from __future__ import annotations

import http.client
from dataclasses import dataclass
from typing import Protocol

from pywaveshare import modbus
from pywaveshare._network import validate_host, validate_port, validate_timeout
from pywaveshare.exceptions import (
    ConfigurationError,
    ProtocolError,
    SafetyConfirmationRequired,
    TransportError,
)


class RelayTransport(Protocol):
    def exchange(self, command: bytes) -> bytes: ...


def _decode_modbus_body(body: bytes) -> bytes:
    stripped = body.strip()
    try:
        text = stripped.decode("ascii")
    except UnicodeDecodeError:
        return body
    compact = "".join(text.split())
    if compact and len(compact) % 2 == 0:
        try:
            return bytes.fromhex(compact)
        except ValueError:
            pass
    return body


@dataclass(frozen=True)
class RelayStatus:
    """Eight relay states in channel order (1 through 8)."""

    device_address: int
    channels: tuple[bool, ...]

    def is_on(self, channel: int) -> bool:
        if not 1 <= channel <= len(self.channels):
            raise ValueError(f"channel must be between 1 and {len(self.channels)}")
        return self.channels[channel - 1]

    def as_dict(self) -> dict[str, object]:
        return {
            "device_address": self.device_address,
            "channels": {str(index): state for index, state in enumerate(self.channels, 1)},
        }


class HttpRelayTransport:
    """One-attempt HTTP GET transport for the device's uploaded HTTP profile."""

    def __init__(
        self,
        host: str,
        *,
        port: int = 8000,
        connect_timeout: float = 3.0,
        read_timeout: float = 3.0,
    ) -> None:
        self.host = validate_host(host)
        validate_port(port)
        validate_timeout(connect_timeout, "connect_timeout")
        validate_timeout(read_timeout, "read_timeout")
        self.port = port
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout

    def exchange(self, command: bytes) -> bytes:
        connection = http.client.HTTPConnection(
            self.host,
            self.port,
            timeout=self.connect_timeout,
        )
        try:
            connection.connect()
            if connection.sock is None:
                raise TransportError("HTTP connection did not create a socket")
            connection.sock.settimeout(self.read_timeout)
            connection.request("GET", f"/?data={command.hex().upper()}")
            response = connection.getresponse()
            body = response.read()
            if response.status < 200 or response.status >= 300:
                raise TransportError(f"relay returned HTTP status {response.status}")
            return _decode_modbus_body(body)
        except TimeoutError as exc:
            raise TransportError("relay HTTP request timed out") from exc
        except (OSError, http.client.HTTPException) as exc:
            raise TransportError("relay HTTP request failed") from exc
        finally:
            connection.close()


class RelayClient:
    """Validated relay operations with no automatic write retries."""

    def __init__(
        self,
        host: str | None = None,
        *,
        port: int = 8000,
        device_address: int = 1,
        connect_timeout: float = 3.0,
        read_timeout: float = 3.0,
        transport: RelayTransport | None = None,
    ) -> None:
        if not 1 <= device_address <= 247:
            raise ConfigurationError("device_address must be between 1 and 247")
        if transport is None:
            if host is None:
                raise ConfigurationError("host is required when transport is not supplied")
            transport = HttpRelayTransport(
                host,
                port=port,
                connect_timeout=connect_timeout,
                read_timeout=read_timeout,
            )
        self.host = validate_host(host) if host is not None else None
        validate_port(port)
        self.port = port
        self.device_address = device_address
        self._transport = transport

    def _exchange(self, request: bytes) -> bytes:
        response = self._transport.exchange(request)
        if not isinstance(response, bytes):
            raise ProtocolError("relay transport returned a non-bytes response")
        return response

    def status(self) -> RelayStatus:
        request = modbus.read_status_request(device_address=self.device_address)
        parsed = modbus.parse_status_response(
            self._exchange(request),
            device_address=self.device_address,
        )
        return RelayStatus(parsed.device_address, parsed.channels)

    def set_state(self, channel: int, on: bool, *, confirm: bool = False) -> None:
        self._require_confirmation(confirm)
        request = modbus.write_state_request(
            channel,
            on,
            device_address=self.device_address,
        )
        modbus.validate_write_echo(request, self._exchange(request))

    def toggle(self, channel: int, *, confirm: bool = False) -> None:
        self._require_confirmation(confirm)
        request = modbus.toggle_request(channel, device_address=self.device_address)
        modbus.validate_write_echo(request, self._exchange(request))

    def pulse(
        self,
        channel: int,
        duration_ms: int,
        *,
        active_on: bool = True,
        confirm: bool = False,
    ) -> None:
        self._require_confirmation(confirm)
        request = modbus.pulse_request(
            channel,
            duration_ms,
            active_on=active_on,
            device_address=self.device_address,
        )
        modbus.validate_write_echo(request, self._exchange(request))

    def command_url(self, command: bytes) -> str:
        """Return an Akuvox-compatible URL without sending it."""

        if self.host is None:
            raise ConfigurationError("command URLs require a client configured with a host")
        display_host = f"[{self.host}]" if ":" in self.host else self.host
        return f"http://{display_host}:{self.port}/?data={command.hex().upper()}"

    def pulse_url(self, channel: int, duration_ms: int, *, active_on: bool = True) -> str:
        return self.command_url(
            modbus.pulse_request(
                channel,
                duration_ms,
                active_on=active_on,
                device_address=self.device_address,
            )
        )

    @staticmethod
    def _require_confirmation(confirm: bool) -> None:
        if not confirm:
            raise SafetyConfirmationRequired(
                "state-changing relay operations require confirm=True"
            )
