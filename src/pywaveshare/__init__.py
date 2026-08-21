"""Waveshare Ethernet device SDK."""

from pywaveshare.exceptions import (
    ConfigurationError,
    DeviceResponseError,
    ProtocolError,
    PyWaveshareError,
    SafetyConfirmationRequired,
    TransportError,
)
from pywaveshare.relay import RelayClient, RelayStatus
from pywaveshare.serial_server import SerialParity, SerialServerProfile
from pywaveshare.zlan import ZlanClient, ZlanParameters

__all__ = [
    "ConfigurationError",
    "DeviceResponseError",
    "ProtocolError",
    "PyWaveshareError",
    "RelayClient",
    "RelayStatus",
    "SafetyConfirmationRequired",
    "SerialParity",
    "SerialServerProfile",
    "TransportError",
    "ZlanClient",
    "ZlanParameters",
]

__version__ = "0.2.0"

