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
from pywaveshare.zlan import ZlanClient, ZlanParameters

__all__ = [
    "ConfigurationError",
    "DeviceResponseError",
    "ProtocolError",
    "PyWaveshareError",
    "RelayClient",
    "RelayStatus",
    "SafetyConfirmationRequired",
    "TransportError",
    "ZlanClient",
    "ZlanParameters",
]

__version__ = "0.1.0"

