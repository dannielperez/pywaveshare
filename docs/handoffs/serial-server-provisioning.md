# Serial-server provisioning handoff

## Scope

- Typed ZLAN read-modify-write profile for Waveshare serial-to-Ethernet gateways.
- Transparent TCP-client destination, serial framing, packetization, reconnection, keep-alive, and
  explicit disconnected-buffer policy.
- Bilingual Python/CLI documentation, including the TVT NVR POS port 9036 example.
- Synthetic packets and fake transports only; no live gateway or NVR call.

## Safety decisions

- The profile starts from a complete device response and preserves the immutable device ID,
  password-bearing bytes, feature advertisement, variable counters, and all unrelated fields.
- Work mode is TCP Client, application protocol is transparent, and flow control is disabled.
- Send-MAC and periodic ZLAN-parameter output are disabled so they cannot enter the receipt stream.
- Ambiguous/custom variable parameters block provisioning. The SDK does not erase possible
  registration, heartbeat, multi-destination, MQTT, VLAN, or firmware-specific data.
- Configuration writes restart the gateway, require explicit confirmation, and are attempted once.
- The caller must choose whether to preserve or clear disconnected serial data.
- 300/600 baud and 9 data bits remain unsupported because the official public ZLAN mapping does not
  define their byte encodings.

## Validation

- `.venv/Scripts/python.exe -m pytest --cov=pywaveshare --cov-report=term-missing`: 76 passed,
  96% coverage.
- `.venv/Scripts/python.exe -m ruff check .`: passed.
- `.venv/Scripts/python.exe -m mypy src`: passed under strict mode.
- Editable install/build through the Hatchling backend: passed.
- Pending final diff check and PR self-review after documentation cleanup.

## Integration sequence

1. Review and merge this public SDK pull request; do not merge automatically.
2. Pin the reviewed SDK commit in UniqueOS as a separate PR.
3. Add a thin UniqueOS adapter that produces a typed desired profile and orchestrates
   `read -> preview/approval -> apply once -> wait -> readback`.
4. Keep TVT POS-slot protocol and firmware grading in `pytvt`; do not add TVT CGI/XML to this SDK.
5. Run the field guide acceptance test on one POS lane before enabling production provisioning.
