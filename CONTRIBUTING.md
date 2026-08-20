# Contributing / Contribuir

Keep device-family behavior in typed modules and preserve the public exception hierarchy. Network
calls require finite timeouts. Never retry state-changing operations automatically.

Mantenga cada familia de equipos en módulos tipados. Toda llamada de red requiere un tiempo límite y
las operaciones que cambian estado nunca deben reintentarse automáticamente.

Before opening a pull request / Antes de abrir un pull request:

```console
python -m pytest --cov=pywaveshare
python -m ruff check .
python -m mypy src
```

Tests must use synthetic, sanitized packets and fake transports. Do not commit live captures,
passwords, customer addresses, or device identifiers.

