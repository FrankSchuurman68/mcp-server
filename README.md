# HomeLab MCP Server

Eigen MCP-server om je UniFi-netwerk te beheren via Claude. Proxmox en Home
Assistant volgen later als apart uitbreidingsproject. Draait als Docker
container (via Portainer) en is alleen bereikbaar binnen je eigen netwerk/VPN.

Zie `INSTALLATIE.md` voor de volledige stap-voor-stap gids afgestemd op jouw
Portainer-omgeving.

## 1. Server draaien via Portainer

1. Kopieer deze map naar je Docker-host.
2. Maak in Portainer een nieuwe stack aan met `docker-compose.yml`, en vul
   de UniFi-variabelen in via het **Environment variables**-veld van het
   stack-formulier (geen los `.env` bestand nodig).
3. Deploy de stack.

Wil je lokaal testen buiten Portainer? Kopieer dan `.env.example` naar `.env`
en draai:
   ```bash
   docker compose up -d --build
   ```
4. Controleer of hij draait:
   ```bash
   docker compose logs -f
   ```
   Je moet zien: `Uvicorn running on http://0.0.0.0:8000`

De server is nu bereikbaar op `http://<proxmox-ip>:8000/mcp` binnen je LAN/VPN.
**Zet deze poort nooit publiek open op internet** — dit is puur bedoeld voor
gebruik binnen je eigen netwerk of via VPN (bv. WireGuard/Tailscale).

## 2. Verbinden vanuit Claude Code (eenvoudigst)

```bash
claude mcp add --transport http homelab http://<proxmox-ip>:8000/mcp
```

Test daarna met bijvoorbeeld:
> "Welke VM's draaien er op mijn Proxmox node?"

## 3. Verbinden vanuit Claude Desktop

Claude Desktop verwacht lokale (stdio) servers in zijn configuratiebestand.
Voor een remote server zoals deze gebruik je de `mcp-remote` bridge.

Open je `claude_desktop_config.json`:
- macOS: `~/Library/Application Support/Claude/config.json`
- Windows: `%APPDATA%\Claude\config.json`

En voeg toe:
```json
{
  "mcpServers": {
    "homelab": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://<proxmox-ip>:8000/mcp"]
    }
  }
}
```

Herstart Claude Desktop. Je zou dan de tools van deze server moeten zien
verschijnen (bijv. `ha_list_entities`, `pm_vm_action`, `uf_client_action`).

## 4. Beschikbare tools

| Module | Tool               | Omschrijving                              |
| ------ | ------------------- | ------------------------------------------ |
| UniFi  | `uf_list_devices`    | Netwerk-apparaten op de site                |
| UniFi  | `uf_list_clients`    | Verbonden clients + blokkeer-status          |
| UniFi  | `uf_client_action`   | Client blokkeren/deblokkeren op MAC-adres    |

Proxmox- en Home Assistant-tools staan gepland als los uitbreidingsproject
(de code is al ontworpen, komt later terug).

## 5. Uitbreiden

Voeg een nieuw bestand toe in `tools/`, importeer `mcp` uit `app.py`, en
gebruik `@mcp.tool` boven een functie. Voeg de import toe in `server.py`
zodat de tool geregistreerd wordt bij het opstarten.

## Veiligheidsopmerkingen

- De API-tokens in `.env` geven aanzienlijke controle over je infrastructuur
  (VM's stoppen, firewall/clients blokkeren, Home Assistant-apparaten
  aansturen). Behandel `.env` als een wachtwoordbestand.
- Begin met testen via read-only tools (`*_list_*`, `*_get_*`) voordat je
  Claude actiematige tools laat gebruiken (`pm_vm_action`, `uf_client_action`,
  `ha_call_service`).
- Overweeg een Proxmox API-token met beperkte rechten (niet root) aan te
  maken, specifiek voor deze server.
