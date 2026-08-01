# HomeLab MCP Server — installatiegids (v1: alleen UniFi)

Complete installatie van begin tot eind.

Scope van deze versie: **alleen UniFi**. Proxmox en Home Assistant komen
later als apart uitbreidingsproject.

Jouw omgeving:
- Docker-host: `192.168.1.101`
- Portainer CE 2.39.3 LTS: `http://192.168.1.101:9000`
- Nginx Proxy Manager: `http://192.168.1.101:81` (nog niet ingezet, optioneel later)
- UniFi Gateway: `192.168.1.1`

Secrets-strategie: environment variables rechtstreeks via het Portainer
stack-formulier — geen los `.env` bestand, geen Vault (voor nu).

---

## Stap 1 — UniFi API key aanmaken

1. Log in op je lokale UniFi Network-interface via `https://192.168.1.1`.
2. Ga naar **Settings → Control Plane → Integrations → API Keys → Create API Key**.
3. Kopieer de key (wordt maar één keer getoond).

---

## Stap 2 — Project op de server zetten

Kopieer de `mcp-server` map naar `192.168.1.101`, bijvoorbeeld:
```bash
scp -r mcp-server user@192.168.1.101:/opt/homelab-mcp
```

---

## Stap 3 — Stack aanmaken in Portainer

1. Ga naar `http://192.168.1.101:9000` en log in.
2. **Stacks → Add stack**.
3. Naam: bv. `homelab-mcp`.
4. Kies **Repository** (als je `/opt/homelab-mcp` als build-context wil
   gebruiken, kies dan **Upload** of verwijs naar het pad op de host) of
   **Web editor** en plak de inhoud van `docker-compose.yml`.
5. Scroll naar **Environment variables** onderaan het stack-formulier en
   voeg toe:

   | Naam               | Waarde                          |
   | ------------------ | -------------------------------- |
   | `UNIFI_HOST`        | `https://192.168.1.1`            |
   | `UNIFI_API_KEY`     | *(jouw API key uit stap 1)*      |
   | `UNIFI_SITE_ID`     | `default`                        |
   | `UNIFI_VERIFY_SSL`  | `false`                          |

6. Klik **Deploy the stack**.

---

## Stap 4 — Controleren of het werkt

**Containers → homelab-mcp → Logs**. Je moet zien:
```
[INFO]: Starting MCP server 'HomeLab Manager' with transport 'streamable-http' on http://0.0.0.0:8000/mcp
Uvicorn running on http://0.0.0.0:8000
```

---

## Stap 5 — Verbinden vanuit Claude Code

```bash
claude mcp add --transport http homelab http://192.168.1.101:8000/mcp
```
Test met:
> "Welke clients zijn verbonden met mijn UniFi-netwerk?"

---

## Stap 6 — Verbinden vanuit Claude Desktop

Open je `claude_desktop_config.json`:
- macOS: `~/Library/Application Support/Claude/config.json`
- Windows: `%APPDATA%\Claude\config.json`

Voeg toe:
```json
{
  "mcpServers": {
    "homelab": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://192.168.1.101:8000/mcp"]
    }
  }
}
```
Herstart Claude Desktop.

---

## Later toe te voegen (apart project)

- Proxmox- en Home Assistant-tools (code bestaat al, kan later teruggezet worden)
- Reverse proxy + toegangsbeveiliging via Nginx Proxy Manager
- Eventueel Vault of een lichtere secrets-manager, als het aantal secrets/services groeit
