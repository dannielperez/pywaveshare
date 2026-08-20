"""Shared validation helpers for network endpoints."""

from __future__ import annotations

import ipaddress

from pywaveshare.exceptions import ConfigurationError


def validate_host(host: str) -> str:
    value = host.strip()
    if not value or value != host or any(char in value for char in "/?#@"):
        raise ConfigurationError("host must be a hostname or IP address without a URL scheme")
    if any(ord(char) < 33 for char in value):
        raise ConfigurationError("host contains invalid characters")
    candidate = value[1:-1] if value.startswith("[") and value.endswith("]") else value
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        labels = candidate.rstrip(".").split(".")
        if not labels or any(
            not label
            or len(label) > 63
            or label[0] == "-"
            or label[-1] == "-"
            or not all(char.isalnum() or char == "-" for char in label)
            for label in labels
        ):
            raise ConfigurationError("host is not a valid hostname or IP address") from None
    return candidate


def validate_port(port: int) -> None:
    if not 1 <= port <= 65535:
        raise ConfigurationError("port must be between 1 and 65535")


def validate_timeout(value: float, name: str) -> None:
    if value <= 0:
        raise ConfigurationError(f"{name} must be greater than zero")

