from __future__ import annotations

import pytest

from pywaveshare._network import validate_host, validate_port, validate_timeout
from pywaveshare.exceptions import ConfigurationError


def test_endpoint_validation_accepts_supported_forms() -> None:
    assert validate_host("relay.example") == "relay.example"
    assert validate_host("[2001:db8::1]") == "2001:db8::1"
    validate_port(1)
    validate_port(65535)
    validate_timeout(0.1, "timeout")


@pytest.mark.parametrize("host", ["", "-bad.example", "bad-.example", "bad..example"])
def test_invalid_hostname_labels(host: str) -> None:
    with pytest.raises(ConfigurationError):
        validate_host(host)


def test_invalid_port_and_timeout() -> None:
    with pytest.raises(ConfigurationError, match="port"):
        validate_port(0)
    with pytest.raises(ConfigurationError, match="timeout"):
        validate_timeout(0, "timeout")
