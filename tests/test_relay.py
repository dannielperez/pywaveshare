from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from pywaveshare import modbus
from pywaveshare.exceptions import (
    ConfigurationError,
    ProtocolError,
    SafetyConfirmationRequired,
    TransportError,
)
from pywaveshare.relay import HttpRelayTransport, RelayClient


@dataclass
class FakeTransport:
    response: bytes
    requests: list[bytes] = field(default_factory=list)

    def exchange(self, command: bytes) -> bytes:
        self.requests.append(command)
        return self.response


def test_status_uses_injected_transport() -> None:
    response = modbus.append_crc(bytes((1, 1, 1, 3)))
    transport = FakeTransport(response)
    status = RelayClient(transport=transport).status()
    assert status.is_on(1)
    assert status.is_on(2)
    assert not status.is_on(3)
    assert status.as_dict()["channels"] == {
        "1": True,
        "2": True,
        "3": False,
        "4": False,
        "5": False,
        "6": False,
        "7": False,
        "8": False,
    }
    assert transport.requests == [modbus.read_status_request()]


def test_write_requires_confirmation_without_transport_call() -> None:
    transport = FakeTransport(b"")
    client = RelayClient(transport=transport)
    with pytest.raises(SafetyConfirmationRequired):
        client.pulse(1, 1000)
    assert transport.requests == []


def test_pulse_is_sent_once_and_validated() -> None:
    request = modbus.pulse_request(3, 1000)
    transport = FakeTransport(request)
    RelayClient(transport=transport).pulse(3, 1000, confirm=True)
    assert transport.requests == [request]


def test_other_writes_are_sent_once() -> None:
    state = modbus.write_state_request(2, True)
    state_transport = FakeTransport(state)
    RelayClient(transport=state_transport).set_state(2, True, confirm=True)
    assert state_transport.requests == [state]

    toggle = modbus.toggle_request(2)
    toggle_transport = FakeTransport(toggle)
    RelayClient(transport=toggle_transport).toggle(2, confirm=True)
    assert toggle_transport.requests == [toggle]


def test_akuvox_url_generation() -> None:
    client = RelayClient("10.180.1.56")
    assert client.pulse_url(1, 1000) == (
        "http://10.180.1.56:8000/?data=01050200000A4C75"
    )


@pytest.mark.parametrize("host", ["http://device", "bad/name", " bad", "bad host"])
def test_invalid_hosts_are_rejected(host: str) -> None:
    with pytest.raises(ConfigurationError):
        RelayClient(host)


def test_status_channel_bounds() -> None:
    status = RelayClient(
        transport=FakeTransport(modbus.append_crc(bytes((1, 1, 1, 0))))
    ).status()
    with pytest.raises(ValueError):
        status.is_on(9)


def test_client_configuration_and_transport_contract() -> None:
    with pytest.raises(ConfigurationError, match="host"):
        RelayClient()
    with pytest.raises(ConfigurationError, match="device_address"):
        RelayClient(transport=FakeTransport(b""), device_address=248)
    client = RelayClient(transport=FakeTransport("not bytes"))  # type: ignore[arg-type]
    with pytest.raises(ProtocolError, match="non-bytes"):
        client.status()
    with pytest.raises(ConfigurationError, match="command URLs"):
        RelayClient(transport=FakeTransport(b"")).command_url(b"123")


class FakeSock:
    def __init__(self) -> None:
        self.timeout: float | None = None

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout


class FakeResponse:
    def __init__(self, body: bytes, status: int = 200) -> None:
        self._body = body
        self.status = status

    def read(self) -> bytes:
        return self._body


class FakeConnection:
    response = FakeResponse(b"")
    error: Exception | None = None
    latest: FakeConnection | None = None

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock = FakeSock()
        self.requested: tuple[str, str] | None = None
        self.closed = False
        FakeConnection.latest = self

    def connect(self) -> None:
        if self.error is not None:
            raise self.error

    def request(self, method: str, path: str) -> None:
        self.requested = (method, path)

    def getresponse(self) -> FakeResponse:
        return self.response

    def close(self) -> None:
        self.closed = True


def test_http_transport_decodes_ascii_hex(monkeypatch: pytest.MonkeyPatch) -> None:
    request = modbus.pulse_request(1, 1000)
    FakeConnection.response = FakeResponse(request.hex().encode())
    FakeConnection.error = None
    monkeypatch.setattr("pywaveshare.relay.http.client.HTTPConnection", FakeConnection)
    response = HttpRelayTransport("relay.example", read_timeout=4).exchange(request)
    assert response == request
    assert FakeConnection.latest is not None
    assert FakeConnection.latest.requested == ("GET", f"/?data={request.hex().upper()}")
    assert FakeConnection.latest.sock.timeout == 4
    assert FakeConnection.latest.closed


def test_http_transport_errors_are_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pywaveshare.relay.http.client.HTTPConnection", FakeConnection)
    FakeConnection.error = TimeoutError()
    with pytest.raises(TransportError, match="timed out"):
        HttpRelayTransport("relay.example").exchange(b"123")
    FakeConnection.error = None
    FakeConnection.response = FakeResponse(b"failure", status=500)
    with pytest.raises(TransportError, match="HTTP status 500"):
        HttpRelayTransport("relay.example").exchange(b"123")
