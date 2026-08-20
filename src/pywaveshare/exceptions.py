"""Public exception hierarchy for pywaveshare."""


class PyWaveshareError(Exception):
    """Base class for all SDK errors."""


class ConfigurationError(PyWaveshareError, ValueError):
    """A caller supplied an invalid endpoint or device setting."""


class ProtocolError(PyWaveshareError):
    """A packet did not match the documented protocol."""


class DeviceResponseError(ProtocolError):
    """A device returned a valid packet that did not match the request."""


class TransportError(PyWaveshareError):
    """A bounded network operation failed."""


class SafetyConfirmationRequired(PyWaveshareError):
    """A state-changing operation was attempted without explicit confirmation."""

