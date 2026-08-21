from __future__ import annotations

import pytest

from pywaveshare.exceptions import ConfigurationError
from pywaveshare.serial_server import SerialParity, SerialServerProfile
from pywaveshare.zlan import ZlanParameters


def response_packet(*, variable_parameters: bytes = bytes(52)) -> bytes:
    parameters = bytearray(167)
    parameters[0:4] = bytes((192, 0, 2, 20))
    parameters[4:8] = bytes((255, 255, 255, 0))
    parameters[8:12] = bytes((192, 0, 2, 1))
    parameters[12:16] = bytes((198, 51, 100, 9))
    parameters[16:18] = (8000).to_bytes(2, "big")
    parameters[18:20] = (8001).to_bytes(2, "big")
    parameters[20] = 0
    parameters[21:31] = b"not-a-key!"
    parameters[31:37] = b"ABCDEF"
    parameters[37] = 4
    parameters[48] = 2
    parameters[49] = 3
    parameters[50:52] = (400).to_bytes(2, "big")
    parameters[56] = 0
    parameters[57] = 1
    parameters[58] = 1
    parameters[59] = 1
    parameters[60] = 2
    parameters[66:79] = b"198.51.100.9"
    parameters[96] = 255
    parameters[97] = 0
    parameters[104] = (1 << 1) | (1 << 5)
    parameters[110] = (1 << 1) | (1 << 5) | (1 << 6) | (1 << 7)
    parameters[114] = 0b1010
    parameters[115:167] = variable_parameters
    return b"ZL\x01" + parameters


def profile(**overrides: object) -> SerialServerProfile:
    values: dict[str, object] = {
        "destination_ip": "192.0.2.40",
        "destination_port": 9036,
        "baud_rate": 115200,
        "data_bits": 8,
        "parity": SerialParity.NONE,
        "stop_bits": 1,
        "local_port": 0,
        "packet_interval_ms": 4,
        "packet_length": 512,
        "reconnect_seconds": 3,
        "keep_alive_seconds": 20,
        "preserve_serial_buffer": False,
    }
    values.update(overrides)
    return SerialServerProfile(**values)  # type: ignore[arg-type]


def test_profile_sets_transparent_tcp_client_and_preserves_private_bytes() -> None:
    current = ZlanParameters.from_response(response_packet())
    changed = profile().apply(current)

    assert changed.destination_ip == "192.0.2.40"
    assert changed.destination_port == 9036
    assert changed.local_port == 0
    assert changed.work_mode == 1
    assert changed.app_protocol == 0
    assert changed.baud_rate == 115200
    assert changed.data_bits == 8
    assert changed.parity == "none"
    assert changed.stop_bits == 1
    assert changed.flow_control == 0
    assert changed.packet_interval_ms == 4
    assert changed.packet_length == 512
    assert changed.reconnect_seconds == 3
    assert changed.keep_alive_seconds == 20
    assert not changed.preserve_serial_buffer
    assert changed.application_payloads_disabled
    assert changed._raw[21:31] == b"not-a-key!"
    assert changed._raw[31:37] == b"ABCDEF"
    assert changed._raw[104] == (1 << 1) | (1 << 5)
    assert changed._raw[110] == 1 << 6
    assert changed._raw[114] == 0b1010


def test_profile_can_preserve_buffer_and_set_two_stop_bits() -> None:
    changed = profile(
        preserve_serial_buffer=True,
        stop_bits=2,
        parity=SerialParity.EVEN,
        data_bits=7,
        baud_rate=9600,
        packet_interval_ms=None,
        packet_length=None,
    ).apply(ZlanParameters.from_response(response_packet()))

    assert changed.preserve_serial_buffer
    assert changed.stop_bits == 2
    assert changed.parity == "even"
    assert changed.data_bits == 7
    assert changed.baud_rate == 9600
    assert changed.packet_interval_ms == 3
    assert changed.packet_length == 400
    assert changed._raw[114] == 0b1011


@pytest.mark.parametrize(
    ("parity", "wire_value"),
    [(SerialParity.EVEN, 1), (SerialParity.ODD, 2)],
)
def test_parity_matches_official_udp_protocol(parity: SerialParity, wire_value: int) -> None:
    changed = profile(parity=parity).apply(ZlanParameters.from_response(response_packet()))

    assert changed._raw[48] == wire_value
    assert changed.parity == parity.value


def test_read_only_counter_tlvs_are_preserved() -> None:
    variable = bytearray(52)
    variable[:12] = bytes((9, 4, 0, 0, 0, 12, 10, 4, 0, 0, 0, 34))
    current = ZlanParameters.from_response(response_packet(variable_parameters=bytes(variable)))
    changed = profile().apply(current)

    assert changed._raw[115:167] == bytes(variable)
    assert changed.application_payloads_disabled


@pytest.mark.parametrize(
    "variable",
    [
        bytes((7, 4, 1, 2, 3, 4)) + bytes(46),
        bytes(16) + b"heartbeat" + bytes(27),
        bytes((9, 51)) + bytes(50),
    ],
)
def test_ambiguous_application_payloads_block_provisioning(variable: bytes) -> None:
    current = ZlanParameters.from_response(response_packet(variable_parameters=variable))
    assert not current.application_payloads_disabled
    with pytest.raises(ConfigurationError, match="registration, heartbeat"):
        profile().apply(current)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"destination_ip": "nvr.local"}, "IPv4"),
        ({"destination_port": 0}, "port"),
        ({"local_port": -1}, "local_port"),
        ({"data_bits": 9}, "data_bits"),
        ({"parity": "invalid"}, "parity"),
        ({"stop_bits": 3}, "stop_bits"),
        ({"packet_interval_ms": 256}, "packet_interval"),
        ({"packet_length": 0}, "packet_length"),
        ({"reconnect_seconds": 256}, "reconnect_seconds"),
        ({"keep_alive_seconds": 256}, "keep_alive_seconds"),
        ({"preserve_serial_buffer": "false"}, "preserve_serial_buffer"),
    ],
)
def test_profile_rejects_unsafe_values(overrides: dict[str, object], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        profile(**overrides)


def test_unmapped_baud_rate_is_rejected_before_write() -> None:
    with pytest.raises(ConfigurationError, match="not mapped"):
        profile(baud_rate=600).apply(ZlanParameters.from_response(response_packet()))


def test_maximum_reconnect_and_keep_alive_values_are_supported() -> None:
    changed = profile(reconnect_seconds=255, keep_alive_seconds=255).apply(
        ZlanParameters.from_response(response_packet())
    )

    assert changed.reconnect_seconds == 255
    assert changed.keep_alive_seconds == 255


def test_profile_summary_is_redacted_and_explicit() -> None:
    summary = profile().as_dict()
    assert summary["work_mode"] == "tcp_client"
    assert summary["application_protocol"] == "transparent"
    assert summary["application_payloads"] == "disabled"
    assert summary["destination_port"] == 9036
