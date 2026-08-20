# pywaveshare agent policy

- Keep Waveshare/ZLAN protocol, transport, parsing, and timeout behavior in this repository.
- Never add Django or UniqueOS application imports here.
- Never log or expose raw ZLAN parameter packets: they may contain credentials.
- Preserve unknown ZLAN bytes with read-modify-write. Never synthesize a full configuration packet for a real device.
- Every network operation must have a finite timeout.
- Never automatically retry relay writes, pulses, configuration writes, or restarts.
- Tests must use synthetic sanitized packets and fake transports; never call a live device.
- Add support by family (`relay`, `zlan`, later `serial_server`) rather than by one-off product scripts.
- Public documentation and operator-facing CLI help must be available in English and Spanish.

