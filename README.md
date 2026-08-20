# pywaveshare

Independent, public Python SDK for Waveshare Ethernet devices used by UniqueOS. The first supported
family is the 8-channel **Modbus PoE ETH Relay** running Waveshare's uploaded HTTP GET profile. ZLAN
UDP discovery and safe read-modify-write provisioning are included because the Ethernet module is
configured by VirCom/ZLAN. The PoE serial-server family is the next planned integration.

This is not an official Waveshare package.

## English

### What works

- Read all eight relay states through HTTP on port 8000.
- Turn, toggle, or pulse one relay with validated Modbus RTU CRC and response echo.
- Produce a ready-to-paste Akuvox web-relay URL without contacting the device.
- Discover ZLAN modules by local Layer-2 broadcast from an operator computer.
- Read a known module by unicast UDP 1092, including across a routed VPN.
- Enable DHCP or set the HTTP relay transport fields using a credential-safe read-modify-write.
- Use the Python API or bilingual `pywaveshare` CLI.

### Install

```console
python -m pip install git+https://github.com/dannielperez/pywaveshare.git
```

For development:

```console
python -m pip install -e ".[dev]"
python -m pytest --cov=pywaveshare
python -m ruff check .
python -m mypy src
```

### Relay API

The HTTP profile must already be uploaded with VirCom. It extracts the hexadecimal `data` query
parameter, passes it to the relay controller as Modbus RTU, and returns the controller response.

```python
from pywaveshare import RelayClient

relay = RelayClient("192.0.2.20", port=8000)
print(relay.status().as_dict())

# State-changing calls require explicit confirmation and are attempted exactly once.
relay.pulse(1, 1000, confirm=True)

# Generate only; useful when provisioning an Akuvox web relay.
print(relay.pulse_url(1, 1000))
# http://192.0.2.20:8000/?data=01050200000A4C75
```

Equivalent operator commands:

```console
pywaveshare relay --host 192.0.2.20 status
pywaveshare relay --host 192.0.2.20 pulse-url 1 1000
pywaveshare relay --host 192.0.2.20 pulse 1 1000 --confirm
```

For Akuvox, create a web-relay action using HTTP GET and paste the generated pulse URL. Use one
URL per door/relay channel. Select the event that should unlock the door (for example, the model's
unlock key or DTMF action), then test while physically observing the correct door. Akuvox menu names
vary by model and firmware; do not embed relay credentials because this Waveshare HTTP profile has no
authentication field.

### ZLAN provisioning

Local discovery uses an Ethernet broadcast and therefore must run on an on-site operator computer:

```console
pywaveshare zlan discover
```

Once the IP is known, read-only unicast works over the site VPN:

```console
pywaveshare zlan read --host 192.0.2.20
```

Enabling DHCP or applying the relay transport profile restarts the device. Each command first reads
the complete current parameter block, changes only approved offsets, preserves the device ID and all
unknown/password bytes, and sends one write with no retry:

```console
pywaveshare zlan dhcp --host 192.0.2.20 --confirm-restart
pywaveshare zlan relay-profile --host 192.0.2.20 --relay-port 8000 --confirm-restart
```

The second command configures TCP-server/transparent transport and buffer preservation. It **does
not upload** Waveshare's HTTP directory. That upload remains a VirCom operator step because its wire
protocol is not publicly documented and has not been implemented from an authorized capture.

### Safety model

- ZLAN parameter packets may contain a management password. Raw packets are private, excluded from
  object representations, and never returned by the CLI.
- ZLAN writes are accepted only from a full packet previously read from the device.
- Relay writes and configuration restarts require explicit confirmation.
- Every network operation has a finite timeout.
- Writes, pulses, and restarts are never retried automatically.
- HTTP is unauthenticated and unencrypted; limit access with the site VLAN/VPN/firewall and do not
  expose ports 8000 or 1092 to the public internet.

## Español

### Funciones disponibles

- Leer el estado de los ocho relés por HTTP en el puerto 8000.
- Encender, apagar, alternar o pulsar un relé validando el CRC y la respuesta Modbus RTU.
- Generar una URL lista para configurar como web relay en Akuvox, sin contactar el equipo.
- Descubrir módulos ZLAN por broadcast de capa 2 desde la computadora local del operador.
- Leer por unicast UDP 1092 cuando ya se conoce la IP, incluso mediante una VPN enrutada.
- Activar DHCP o configurar el transporte HTTP mediante lectura-modificación-escritura segura.
- Utilizar una API Python o el CLI bilingüe `pywaveshare`.

### Uso del relé

El perfil HTTP debe cargarse primero con VirCom. Para un pulso de un segundo en el relé 1:

```console
pywaveshare relay --host 192.0.2.20 pulse-url 1 1000
pywaveshare relay --host 192.0.2.20 pulse 1 1000 --confirm
```

En Akuvox, cree una acción de web relay con método HTTP GET y pegue la URL generada. Configure una
URL por puerta/canal, asóciela al evento de apertura correspondiente y valide físicamente que opera
la puerta correcta. Los nombres de menús cambian según el modelo y firmware. Este perfil HTTP de
Waveshare no ofrece autenticación, así que no incluya credenciales en la URL.

### Aprovisionamiento ZLAN

El descubrimiento requiere que la computadora del operador esté en la red local:

```console
pywaveshare zlan discover
```

Después de conocer la IP, UniqueOS o el operador puede consultar el equipo por la VPN:

```console
pywaveshare zlan read --host 192.0.2.20
```

Los cambios reinician el equipo y requieren confirmación explícita:

```console
pywaveshare zlan dhcp --host 192.0.2.20 --confirm-restart
pywaveshare zlan relay-profile --host 192.0.2.20 --relay-port 8000 --confirm-restart
```

La carga del directorio HTTP continúa siendo un paso manual en VirCom; su protocolo no está
documentado públicamente. Los paquetes ZLAN pueden contener contraseñas: la biblioteca conserva esos
bytes sin mostrarlos ni registrarlos. Nunca se reintentan automáticamente pulsos, escrituras o
reinicios.

## Supported protocol references / Referencias

- [Waveshare Modbus PoE ETH Relay](https://www.waveshare.com/wiki/Modbus_POE_ETH_Relay)
- [Waveshare HTTP profile guide](https://www.waveshare.com/wiki/Modbus_POE_ETH_Relay_HTTP)
- [ZLAN UDP management protocol](https://www.zlmcu.com/download/UDP_port_protocol.pdf)

## Roadmap / Próximos pasos

1. Relay SDK and ZLAN provisioning (this release).
2. Authorized capture and implementation of the VirCom HTTP-directory upload, if the protocol can be
   reproduced safely.
3. PoE serial-server typed configuration and transport support under `pywaveshare.serial_server`.

MIT licensed. See [SECURITY.md](SECURITY.md) before deploying relay control on a production network.
