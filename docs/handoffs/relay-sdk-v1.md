# Relay SDK v1 handoff

## Scope

- Public Python package for the Waveshare Modbus PoE ETH Relay HTTP profile.
- ZLAN Layer-2 discovery plus routed unicast read and safe configuration writes.
- Bilingual operator documentation and CLI.
- No live-device calls or customer packet captures in the repository.

## Safety decisions

- Raw 167-byte ZLAN parameter blocks are private and omitted from representations because the
  password can occupy the key area.
- Configuration is read-modify-write and requires a non-empty device ID from a device response.
- Relay writes require `confirm=True`; ZLAN writes require `confirm_restart=True`.
- State-changing operations have one attempt and no retry.
- HTTP and UDP calls have explicit finite timeouts.
- The undocumented VirCom HTTP-directory upload is intentionally not implemented.

## Validation

- `python -m pytest --cov=pywaveshare --cov-report=term-missing`: 57 passed, 96% coverage.
- `python -m ruff check .`: passed.
- `python -m mypy src`: passed under strict mode.
- `git diff --check`: passed after final formatting cleanup.

## Integration sequence

1. Review and merge the pywaveshare pull request.
2. Pin the merged commit as `vendor/pywaveshare` in UniqueOS.
3. Add only thin UniqueOS adapters/models; keep protocol and transport here.
4. Continue using VirCom for HTTP-directory uploads until an authorized, sanitized capture supports
   a separately reviewed implementation.
5. Add the PoE serial-server family in a later pywaveshare pull request.
