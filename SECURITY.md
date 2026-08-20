# Security policy / Política de seguridad

## Reporting / Reporte

Do not open a public issue containing a device password, packet capture, public IP address, VPN
address, or customer/site name. Report sensitive findings privately to the repository owner through
GitHub's security-advisory channel.

No publique issues que incluyan contraseñas, capturas de paquetes, direcciones IP públicas o de VPN,
ni nombres de clientes o sitios. Informe hallazgos sensibles de forma privada mediante el canal de
avisos de seguridad de GitHub.

## Deployment assumptions / Suposiciones de despliegue

The Waveshare HTTP profile has no TLS or application authentication. Deploy it only on a restricted
site VLAN reachable through an authenticated VPN. Firewall relay HTTP and ZLAN UDP management ports
from untrusted networks. Treat possession of a pulse URL as permission to operate the relay.

El perfil HTTP no tiene TLS ni autenticación de aplicación. Úselo solamente en una VLAN restringida,
accesible mediante una VPN autenticada. Bloquee los puertos HTTP del relé y UDP ZLAN desde redes no
confiables. Considere que quien tenga la URL de pulso puede operar el relé.

The SDK redacts ZLAN parameter blocks because they can contain a management password. Applications
must not access private `_raw` members or enable debug logging of socket payloads.

