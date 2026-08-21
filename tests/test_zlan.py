from __future__ import annotations

from collections.abc import Iterable

import pytest

from pywaveshare.exceptions import (
    ConfigurationError,
    ProtocolError,
    SafetyConfirmationRequired,
    TransportError,
)
from pywaveshare.zlan import (
    DISCOVER,
    PACKET_LENGTH,
    READ_UNICAST,
    ZlanClient,
    ZlanParameters,
    command_packet,
)


def response_packet(*, device_id: bytes = b"ABCDEF", supports_dhcp: bool = True) -> bytes:
    parameters = bytearray(167)
    parameters[0:4] = bytes((192, 0, 2, 20))
    parameters[4:8] = bytes((255, 255, 255, 0))
    parameters[8:12] = bytes((192, 0, 2, 1))
    parameters[12:16] = bytes((198, 51, 100, 10))
    parameters[16:18] = (8000).to_bytes(2, "big")
    parameters[18:20] = (9000).to_bytes(2, "big")
    parameters[20] = 0
    parameters[21:31] = b"not-a-key!"
    parameters[31:37] = device_id
    parameters[37] = 11
    parameters[48] = 0
    parameters[49] = 3
    parameters[50:52] = (400).to_bytes(2, "big")
    parameters[56] = 0
    parameters[60] = 0
    parameters[61] = 1
    parameters[66:79] = b"198.51.100.10"
    parameters[96] = 5
    parameters[97] = 15
    parameters[98:100] = (80).to_bytes(2, "big")
    parameters[103] = 117
    parameters[104] = (1 << 5) if supports_dhcp else 0
    return b"ZL\x01" + parameters


class FakeSocket:
    def __init__(self, responses: Iterable[bytes] = ()) -> None:
        self.responses = iter(responses)
        self.sent: list[tuple[bytes, tuple[str, int]]] = []
        self.timeouts: list[float] = []
        self.options: list[tuple[int, int, int]] = []
        self.bound: tuple[str, int] | None = None
        self.closed = False

    def settimeout(self, timeout: float) -> None:
        self.timeouts.append(timeout)

    def setsockopt(self, level: int, option: int, value: int) -> None:
        self.options.append((level, option, value))

    def bind(self, address: tuple[str, int]) -> None:
        self.bound = address

    def sendto(self, packet: bytes, address: tuple[str, int]) -> int:
        self.sent.append((packet, address))
        return len(packet)

    def recvfrom(self, _size: int) -> tuple[bytes, tuple[str, int]]:
        try:
            return next(self.responses), ("192.0.2.20", 1092)
        except StopIteration:
            raise TimeoutError from None

    def close(self) -> None:
        self.closed = True


def test_query_packets_are_fixed_size() -> None:
    assert len(command_packet(DISCOVER)) == PACKET_LENGTH
    assert command_packet(DISCOVER)[:3] == b"ZL\x00"
    assert command_packet(READ_UNICAST)[:3] == b"ZL\x04"
    with pytest.raises(ValueError):
        command_packet(2)


def test_parameters_are_redacted_and_typed() -> None:
    parameters = ZlanParameters.from_response(response_packet())
    assert parameters.local_ip == "192.0.2.20"
    assert parameters.netmask == "255.255.255.0"
    assert parameters.gateway == "192.0.2.1"
    assert parameters.local_port == 8000
    assert parameters.destination_ip == "198.51.100.10"
    assert parameters.destination_port == 9000
    assert parameters.baud_rate == 115200
    assert parameters.data_bits == 8
    assert parameters.parity == "none"
    assert parameters.stop_bits == 1
    assert parameters.packet_interval_ms == 3
    assert parameters.packet_length == 400
    assert parameters.reconnect_seconds == 5
    assert parameters.keep_alive_seconds == 15
    assert parameters.application_payloads_disabled
    assert parameters.web_port == 80
    assert parameters.connected
    assert parameters.device_id == "41:42:43:44:45:46"
    assert parameters.firmware_version == "1.500"
    assert "not-a-key" not in repr(parameters)
    assert "not-a-key" not in str(parameters.as_dict())


def test_read_modify_write_preserves_unknown_and_secret_bytes() -> None:
    original = response_packet()
    changed = (
        ZlanParameters.from_response(original)
        .with_dhcp(True)
        .with_http_relay_profile(local_port=9000)
    )
    fake = FakeSocket()
    client = ZlanClient(socket_factory=lambda *_args: fake)
    client.apply("192.0.2.20", changed, confirm_restart=True)
    assert len(fake.sent) == 1
    write_packet, target = fake.sent[0]
    assert write_packet[:3] == b"ZL\x02"
    assert write_packet[3 + 21 : 3 + 31] == b"not-a-key!"
    assert write_packet[3 + 31 : 3 + 37] == b"ABCDEF"
    assert write_packet[3 + 56] == 1
    assert write_packet[3 + 16 : 3 + 18] == (9000).to_bytes(2, "big")
    assert write_packet[3 + 110] & (1 << 7)
    assert target == ("192.0.2.20", 1092)
    assert fake.closed


def test_static_network_disables_dhcp() -> None:
    changed = ZlanParameters.from_response(response_packet()).with_static_network(
        local_ip="198.51.100.50",
        netmask="255.255.255.0",
        gateway="198.51.100.1",
    )
    assert changed.local_ip == "198.51.100.50"
    assert changed.gateway == "198.51.100.1"
    assert not changed.dhcp_enabled
    with pytest.raises(ConfigurationError, match="local_ip"):
        changed.with_static_network(
            local_ip="not-an-ip",
            netmask="255.255.255.0",
            gateway="198.51.100.1",
        )


def test_dhcp_requires_advertised_feature() -> None:
    parameters = ZlanParameters.from_response(response_packet(supports_dhcp=False))
    with pytest.raises(ConfigurationError, match="DHCP"):
        parameters.with_dhcp(True)


def test_apply_requires_confirmation() -> None:
    fake = FakeSocket()
    client = ZlanClient(socket_factory=lambda *_args: fake)
    parameters = ZlanParameters.from_response(response_packet())
    with pytest.raises(SafetyConfirmationRequired):
        client.apply("192.0.2.20", parameters)
    assert fake.sent == []


def test_write_requires_device_origin_and_id() -> None:
    client = ZlanClient(socket_factory=lambda *_args: FakeSocket())
    synthetic = ZlanParameters(bytes(167))
    with pytest.raises(SafetyConfirmationRequired, match="read from the device"):
        client.apply("192.0.2.20", synthetic, confirm_restart=True)
    empty_id = ZlanParameters.from_response(response_packet(device_id=bytes(6)))
    with pytest.raises(ProtocolError, match="device ID"):
        client.apply("192.0.2.20", empty_id, confirm_restart=True)


def test_unicast_read() -> None:
    fake = FakeSocket([response_packet()])
    result = ZlanClient(socket_factory=lambda *_args: fake).read("192.0.2.20")
    assert result.device_id == "41:42:43:44:45:46"
    assert fake.sent == [(command_packet(READ_UNICAST), ("192.0.2.20", 1092))]
    assert fake.closed


def test_unicast_timeout_is_normalized() -> None:
    fake = FakeSocket()
    with pytest.raises(TransportError, match="timed out"):
        ZlanClient(socket_factory=lambda *_args: fake).read("192.0.2.20")
    assert fake.closed


def test_discovery_deduplicates_and_ignores_invalid_packets() -> None:
    first = response_packet(device_id=b"ABCDEF")
    second = response_packet(device_id=b"UVWXYZ")
    fake = FakeSocket([b"invalid", first, first, second])
    found = ZlanClient(socket_factory=lambda *_args: fake).discover()
    assert [item.device_id for item in found] == [
        "41:42:43:44:45:46",
        "55:56:57:58:59:5A",
    ]
    assert fake.sent == [(command_packet(DISCOVER), ("255.255.255.255", 1092))]
    assert fake.bound == ("0.0.0.0", 0)


@pytest.mark.parametrize("packet", [b"", b"ZL\x01" + bytes(10), b"XX\x01" + bytes(167)])
def test_invalid_responses_are_rejected(packet: bytes) -> None:
    with pytest.raises(ProtocolError):
        ZlanParameters.from_response(packet)


def test_profile_can_clear_preserve_buffer_flag() -> None:
    parameters = ZlanParameters.from_response(response_packet()).with_http_relay_profile(
        preserve_serial_buffer=False
    )
    assert not parameters.preserve_serial_buffer


def test_client_configuration_validation() -> None:
    with pytest.raises(ConfigurationError, match="timeout"):
        ZlanClient(timeout=0)
    with pytest.raises(ConfigurationError, match="port"):
        ZlanClient(port=0)


class ShortSendSocket(FakeSocket):
    def sendto(self, packet: bytes, address: tuple[str, int]) -> int:
        super().sendto(packet, address)
        return len(packet) - 1


def test_partial_configuration_send_is_rejected() -> None:
    fake = ShortSendSocket()
    parameters = ZlanParameters.from_response(response_packet())
    with pytest.raises(TransportError, match="not sent completely"):
        ZlanClient(socket_factory=lambda *_args: fake).apply(
            "192.0.2.20", parameters, confirm_restart=True
        )
