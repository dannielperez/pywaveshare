from __future__ import annotations

import json
from typing import ClassVar

import pytest

from pywaveshare import cli, modbus


def test_pulse_url_command(capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        cli.main(
            [
                "relay",
                "--host",
                "192.0.2.20",
                "pulse-url",
                "1",
                "1000",
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["url"].endswith(modbus.pulse_request(1, 1000).hex().upper())


def test_invalid_pulse_is_redacted_json_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["relay", "--host", "192.0.2.20", "pulse-url", "9", "1000"]) == 2
    error = json.loads(capsys.readouterr().err)
    assert error["ok"] is False
    assert "channel" in error["error"]


class FakeStatus:
    def as_dict(self) -> dict[str, object]:
        return {"channels": {"1": False}}


class FakeRelayClient:
    calls: ClassVar[list[tuple[object, ...]]] = []

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    def status(self) -> FakeStatus:
        self.calls.append(("status",))
        return FakeStatus()

    def set_state(self, channel: int, on: bool, *, confirm: bool) -> None:
        self.calls.append(("set", channel, on, confirm))

    def toggle(self, channel: int, *, confirm: bool) -> None:
        self.calls.append(("toggle", channel, confirm))

    def pulse(
        self,
        channel: int,
        duration_ms: int,
        *,
        active_on: bool,
        confirm: bool,
    ) -> None:
        self.calls.append(("pulse", channel, duration_ms, active_on, confirm))


@pytest.mark.parametrize(
    ("operation", "expected"),
    [
        (["status"], ("status",)),
        (["set", "2", "on", "--confirm"], ("set", 2, True, True)),
        (["toggle", "3", "--confirm"], ("toggle", 3, True)),
        (
            ["pulse", "4", "500", "--active-off", "--confirm"],
            ("pulse", 4, 500, False, True),
        ),
    ],
)
def test_relay_commands(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    operation: list[str],
    expected: tuple[object, ...],
) -> None:
    FakeRelayClient.calls = []
    monkeypatch.setattr(cli, "RelayClient", FakeRelayClient)
    assert cli.main(["relay", "--host", "192.0.2.20", *operation]) == 0
    capsys.readouterr()
    assert FakeRelayClient.calls == [expected]


class FakeParameters:
    already_configured: ClassVar[bool] = False

    def as_dict(self) -> dict[str, object]:
        return {"device_id": "AA:BB:CC:DD:EE:FF"}

    def with_dhcp(self, enabled: bool) -> FakeParameters:
        assert enabled
        return self

    def with_http_relay_profile(self, *, local_port: int) -> FakeParameters:
        assert local_port == 9000
        return self

    def with_serial_server_profile(self, _profile: object) -> FakeParameters:
        return self

    def same_configuration(self, _other: object) -> bool:
        return self.already_configured


class FakeZlanClient:
    latest: ClassVar[FakeZlanClient | None] = None

    def __init__(self, **_kwargs: object) -> None:
        self.applied: list[tuple[str, object, bool]] = []
        FakeZlanClient.latest = self

    def read(self, _host: str) -> FakeParameters:
        return FakeParameters()

    def discover(self, **_kwargs: object) -> tuple[FakeParameters, ...]:
        return (FakeParameters(),)

    def apply(
        self,
        host: str,
        parameters: object,
        *,
        confirm_restart: bool,
    ) -> None:
        self.applied.append((host, parameters, confirm_restart))


@pytest.mark.parametrize(
    "operation",
    [
        ["read", "--host", "192.0.2.20"],
        ["discover"],
        ["dhcp", "--host", "192.0.2.20", "--confirm-restart"],
        [
            "relay-profile",
            "--host",
            "192.0.2.20",
            "--relay-port",
            "9000",
            "--confirm-restart",
        ],
        [
            "serial-profile",
            "--host",
            "192.0.2.20",
            "--destination-ip",
            "192.0.2.40",
            "--destination-port",
            "9036",
            "--baud-rate",
            "115200",
            "--clear-serial-buffer",
            "--confirm-restart",
        ],
    ],
)
def test_zlan_commands(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    operation: list[str],
) -> None:
    monkeypatch.setattr(cli, "ZlanClient", FakeZlanClient)
    FakeParameters.already_configured = False
    assert cli.main(["zlan", *operation]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output
    assert FakeZlanClient.latest is not None
    if operation[0] in {"dhcp", "relay-profile", "serial-profile"}:
        assert FakeZlanClient.latest.applied[0][2] is True


def test_serial_profile_skips_restart_when_already_configured(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "ZlanClient", FakeZlanClient)
    FakeParameters.already_configured = True
    assert (
        cli.main(
            [
                "zlan",
                "serial-profile",
                "--host",
                "192.0.2.20",
                "--destination-ip",
                "192.0.2.40",
                "--destination-port",
                "9036",
                "--baud-rate",
                "115200",
                "--clear-serial-buffer",
                "--confirm-restart",
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["provisioning_status"] == "already_configured"
    assert output["write_attempted"] is False
    assert FakeZlanClient.latest is not None
    assert FakeZlanClient.latest.applied == []
    FakeParameters.already_configured = False
