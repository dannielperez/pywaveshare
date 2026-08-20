from __future__ import annotations

import pytest

from pywaveshare import modbus
from pywaveshare.exceptions import DeviceResponseError, ProtocolError


def test_documented_frames() -> None:
    assert modbus.read_status_request().hex().upper() == "0101000000083DCC"
    assert modbus.write_state_request(1, True).hex().upper() == "01050000FF008C3A"
    assert modbus.write_state_request(1, False).hex().upper() == "010500000000CDCA"
    assert modbus.toggle_request(1).hex().upper() == "010500005500F29A"
    assert modbus.pulse_request(1, 1000).hex().upper() == "01050200000A4C75"
    assert modbus.pulse_request(2, 1000).hex().upper() == "01050201000A1DB5"
    assert modbus.pulse_request(3, 1000).hex().upper() == "01050202000AEDB5"


def test_parse_status_bits() -> None:
    response = modbus.append_crc(bytes((1, 1, 1, 0b10000101)))
    parsed = modbus.parse_status_response(response)
    assert parsed.channels == (True, False, True, False, False, False, False, True)


@pytest.mark.parametrize("channel", [0, 9])
def test_channel_bounds(channel: int) -> None:
    with pytest.raises(ValueError, match="channel"):
        modbus.pulse_request(channel, 100)


@pytest.mark.parametrize("duration", [0, 99, 150, 3_276_800])
def test_pulse_duration_bounds(duration: int) -> None:
    with pytest.raises(ValueError, match="duration_ms"):
        modbus.pulse_request(1, duration)


def test_invalid_crc_is_rejected() -> None:
    with pytest.raises(ProtocolError, match="too short"):
        modbus.validate_frame(b"\x01")
    with pytest.raises(ProtocolError, match="CRC"):
        modbus.validate_frame(b"\x01\x01\x00\x00")


def test_wrong_device_and_exception_are_rejected() -> None:
    wrong_device = modbus.append_crc(bytes((2, 1, 1, 0)))
    with pytest.raises(DeviceResponseError, match="device address"):
        modbus.parse_status_response(wrong_device)

    exception = modbus.append_crc(bytes((1, 0x81, 2)))
    with pytest.raises(DeviceResponseError, match="exception"):
        modbus.parse_status_response(exception)


def test_write_requires_exact_echo() -> None:
    request = modbus.write_state_request(1, True)
    other = modbus.write_state_request(1, False)
    with pytest.raises(DeviceResponseError, match="echo"):
        modbus.validate_write_echo(request, other)


def test_device_address_and_status_shape_validation() -> None:
    with pytest.raises(ValueError, match="device_address"):
        modbus.read_status_request(device_address=0)
    malformed = modbus.append_crc(bytes((1, 2, 1, 0)))
    with pytest.raises(DeviceResponseError, match="not an 8-channel"):
        modbus.parse_status_response(malformed)
