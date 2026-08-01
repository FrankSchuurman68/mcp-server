# Project status — HomeLab MCP Server

Context-overdracht voor een nieuwe sessie (bv. Claude Code). Lees dit bestand
eerst voor je verder helpt.

## Doel

Een eigen MCP-server bouwen (Docker container) om via Claude het
thuisnetwerk te managen. Fase 1: alleen UniFi. Proxmox en Home Assistant
volgen later als apart uitbreidingsproject (code hiervoor bestaat nog niet
in dit project).

## Infrastructuur / netwerk

- Proxmox-server: `192.168.1.125` (root-SSH werkt inmiddels, wachtwoord is
  gereset)
- Docker/Portainer/Nginx Proxy Manager-host: `192.168.1.101`
  - Portainer CE 2.39.3 LTS: `http://192.168.1.101:9000`
  - Nginx Proxy Manager: `http://192.168.1.101:81`
- UniFi Gateway: `192.168.1.1`
- Pi-hole VM: `192.168.1.126` — heeft een los, nog onopgelost
  netwerkprobleem (TCP-handshake lukt, maar payload/HTTP-response komt niet
  aan, zelfs bij `apt install` naar internet — mogelijk UniFi
  IPS/Threat Management of een MTU-probleem). Dit staat voorlopig
  gepauzeerd, niet blokkerend voor de MCP-server.

## Architectuurkeuzes (al genomen, niet heropenen zonder reden)

- Taal: Python, met de `fastmcp` library
- Transport: Streamable HTTP op poort 8000, alleen bereikbaar binnen
  LAN/VPN — nooit publiek exposen
- Verbinden vanuit Claude Desktop via de `mcp-remote` bridge; vanuit Claude
  Code via `claude mcp add --transport http`
- Secrets: environment variables rechtstreeks via Portainer's
  stack-formulier — geen los `.env` bestand, geen Vault (bewust simpel
  gehouden voor nu)
- Nog géén extra authenticatielaag (geen NPM Access List) — komt evt. later
- Deploy-methode: Portainer stack via Git repository
  (`https://github.com/FrankSchuurman68/mcp-server`, branch `main`), omdat
  Upload/Web editor geen submappen correct meenemen. Structuur is daarom
  bewust plat (geen `tools/`-submap meer, alles los in de repo-root).

## Projectstructuur (huidige staat, allemaal plat in de repo-root)

```
Dockerfile
app.py
server.py
unifi.py
requirements.txt
docker-compose.yml
.env.example
README.md
INSTALLATIE.md
STATUS.md   <- dit bestand
```

## Beschikbare tools (unifi.py)

- `uf_list_devices` — netwerk-apparaten op de site
- `uf_list_clients` — verbonden clients + blokkeer-status
- `uf_client_action` — client blokkeren/deblokkeren op MAC-adres

UniFi API: lokale Network Integration API
(`https://192.168.1.1/proxy/network/integration/v1`), niet de cloud Site
Manager API — sneller en werkt zonder internet.

## Huidige stand / laatste blocker

De Docker build vanuit de git-repo lukt nu (Dockerfile wordt gevonden).
Laatste foutmelding bij deploy:

```
Bind for :::8000 failed: port is already allocated
```

Poort 8000 op `192.168.1.101` is al in gebruik. Nog te doen:

1. Checken wat er op poort 8000 draait: `ss -tlnp | grep :8000` en
   `docker ps --filter "publish=8000"` (zonder `sudo`, root heeft al
   rechten)
2. Als het een oude/vastgelopen `homelab-mcp`-container is: verwijderen via
   Portainer en opnieuw deployen.
3. Als een ander proces de poort echt nodig heeft: externe poort in
   `docker-compose.yml` wijzigen naar bv. `8100:8000`, en dat doorvoeren in
   `INSTALLATIE.md` en de Claude Desktop/Code-configuratie.

## Belangrijk beveiligingspuntje

De UniFi API key is op enig moment zichtbaar geweest in een screenshot
tijdens dit traject. Gebruiker is van plan deze voor productie opnieuw te
genereren — check of dat al gebeurd is voor je verder gaat met een
live-deploy.
