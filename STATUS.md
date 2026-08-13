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

## Lessons learned / bekende valkuilen

Sectie voor opgeloste problemen die de moeite waard zijn om te onthouden
voor volgende sessies. Voeg nieuwe incidenten onderaan toe.

### UniFi Content Filtering-policy onderschept DNS-verkeer netwerkbreed (2026-08-13)

**Symptoom**: `cloud.confra.nl` bleef intern verouderd resolven
(`188.90.37.16` i.p.v. het correcte `85.146.187.253` uit Cloudflare), zelfs
bij expliciete queries naar `1.1.1.1` of rechtstreeks naar de autoritatieve
nameservers (rose/simon.ns.cloudflare.com), en zelfs vanaf de Pi-hole-VM
zelf.

**Oorzaak**: een UniFi **Content Filtering-policy** ("Basic Adult &
Malicious Filter", te vinden onder een Policies/Traffic Rules-sectie, niet
onder "Security") onderschept transparant al het poort-53-verkeer op het
netwerk en had daarbinnen een verouderde cache-entry. Pi-hole, Nginx, de
Windows DNS-cache en de zoneconfiguratie bij Cloudflare waren nooit het
probleem — Pi-hole's eigen cache-flushes (`pihole reloaddns`,
`systemctl restart pihole-FTL`) leken niet te werken, maar in
werkelijkheid werd elke herhaalde upstream-lookup vanuit Pi-hole gewoon
opnieuw door dezelfde onderscheppende laag beantwoord.

**Diagnose-aanpak die werkte**:
1. Vergelijk resolutie via meerdere bronnen tegelijk (systeem-resolver,
   Cloudflare 1.1.1.1, en rechtstreeks de autoritatieve nameservers) — bij
   mismatch, exporteer de daadwerkelijke zonedata uit Cloudflare zelf om de
   "waarheid" vast te stellen.
2. Test via DNS-over-HTTPS (poort 443, `Invoke-RestMethod` naar
   `https://cloudflare-dns.com/dns-query`) — dat omzeilt lokale
   poort-53-onderschepping en gaf meteen het juiste antwoord, wat
   bevestigde dat het probleem lokaal/netwerkbreed was, niet bij
   Cloudflare.
3. Test vanaf een ander apparaat op het netwerk (de Pi-hole-VM zelf, met
   `dig @1.1.1.1 cloud.confra.nl A +short`) om te bewijzen dat het
   probleem niet bij één specifiek apparaat zat, maar netwerkbreed was.
4. Zoek in de UniFi Network-app naar filtering-/policy-features buiten de
   voor de hand liggende "Security"-tab — deze zaten in dit geval onder een
   losse Policies-sectie.

**Fix**: Content Filtering-policy tijdelijk op **Off** gezet → direct
correcte, verse DNS-antwoorden (TTL 300, matcht Cloudflare exact).

**Les**: bij "DNS geeft overal een verouderd antwoord, ook bij expliciete
externe servers" — verdenk als eerste een netwerkbrede interceptielaag
(content filtering / DNS-filtering op de gateway), niet de individuele
DNS-server of client. Herkenningspunten: het foute antwoord is overal
hetzelfde, cache-flushes op de voor de hand liggende server (hier: Pi-hole)
lossen het niet op, maar DoH (poort 443) geeft wél meteen het juiste
antwoord.

Hulpscript (lokaal bij Frank, niet in deze repo): `Check-CloudConfra-DNS.ps1`
— PowerShell-script dat systeem-resolver, Cloudflare 1.1.1.1, en de
autoritatieve nameservers automatisch vergelijkt en waarschuwt bij een
mismatch.
