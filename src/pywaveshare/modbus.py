"""Minimal Modbus RTU framing used by Waveshare Ethernet relay HTTP profiles."""

from __future__ import annotations

from dataclasses import dataclass

from pywaveshare.exceptions import DeviceResponseError, ProtocolError

READ_COILS = 0x01
WRITE_SINGLE_COIL = 0x05
RELAY_COUNT = 8
MAX_PULSE_TICKS = 0x7FFF


def crc16(data: bytes) -> int:
    """Return Modbus CRC-16 as an integer (wire order is low byte first)."""

    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def append_crc(payload: bytes) -> bytes:
    checksum = crc16(payload)
    return payload + checksum.to_bytes(2, "little")


def validate_frame(frame: bytes) -> bytes:
    if len(frame) < 4:
        raise ProtocolError("Modbus response is too short")
    expected = crc16(frame[:-2])
    received = int.from_bytes(frame[-2:], "little")
    if received != expected:
        raise ProtocolError("Modbus response CRC is invalid")
    return frame


def _validate_device_address(device_address: int) -> None:
    if not 1 <= device_address <= 247:
        raise ValueError("device_address must be between 1 and 247")


def _channel_index(channel: int) -> int:
    if not 1 <= channel <= RELAY_COUNT:
        raise ValueError(f"channel must be between 1 and {RELAY_COUNT}")
    return channel - 1


def read_status_request(*, device_address: int = 1) -> bytes:
    _validate_device_address(device_address)
    return append_crc(bytes((device_address, READ_COILS, 0, 0, 0, RELAY_COUNT)))


def write_state_request(channel: int, on: bool, *, device_address: int = 1) -> bytes:
    _validate_device_address(device_address)
    address = _channel_index(channel)
    value = 0xFF00 if on else 0x0000
    payload = bytes((device_address, WRITE_SINGLE_COIL))
    payload += address.to_bytes(2, "big") + value.to_bytes(2, "big")
    return append_crc(payload)


def toggle_request(channel: int, *, device_address: int = 1) -> bytes:
    _validate_device_address(device_address)
    address = _channel_index(channel)
    payload = bytes((device_address, WRITE_SINGLE_COIL))
    payload += address.to_bytes(2, "big") + (0x5500).to_bytes(2, "big")
    return append_crc(payload)


def pulse_request(
    channel: int,
    duration_ms: int,
    *,
    active_on: bool = True,
    device_address: int = 1,
) -> bytes:
    """Build Waveshare's flash-on/off command in 100 ms increments."""

    _validate_device_address(device_address)
    address = _channel_index(channel)
    if duration_ms < 100 or duration_ms % 100:
        raise ValueError("duration_ms must be a positive multiple of 100")
    ticks = duration_ms // 100
    if ticks > MAX_PULSE_TICKS:
        raise ValueError(f"duration_ms must not exceed {MAX_PULSE_TICKS * 100}")
    register = (0x0200 if active_on else 0x0400) + address
    payload = bytes((device_address, WRITE_SINGLE_COIL))
    payload += register.to_bytes(2, "big") + ticks.to_bytes(2, "big")
    return append_crc(payload)


@dataclass(frozen=True)
class ParsedRelayStatus:
    device_address: int
    channels: tuple[bool, ...]


def parse_status_response(frame: bytes, *, device_address: int = 1) -> ParsedRelayStatus:
    validate_frame(frame)
    if frame[0] != device_address:
        raise DeviceResponseError("Modbus response device address does not match request")
    if frame[1] & 0x80:
        code = frame[2] if len(frame) > 2 else -1
        raise DeviceResponseError(f"Modbus exception response: {code}")
    if frame[1] != READ_COILS or len(frame) != 6 or frame[2] != 1:
        raise DeviceResponseError("Modbus response is not an 8-channel relay status")
    states = tuple(bool(frame[3] & (1 << index)) for index in range(RELAY_COUNT))
    return ParsedRelayStatus(device_address=device_address, channels=states)


def validate_write_echo(request: bytes, response: bytes) -> None:
    validate_frame(response)
    if response != request:
        raise DeviceResponseError("Modbus write response does not echo the request")

