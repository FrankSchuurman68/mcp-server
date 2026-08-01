"""Startpunt van de HomeLab MCP-server.

Laadt alle actieve tool-modules (waardoor hun @mcp.tool functies
geregistreerd worden) en start de server via Streamable HTTP, zodat hij
als container bereikbaar is op je LAN/VPN voor Claude Desktop of Claude Code.

Scope: momenteel alleen UniFi. Proxmox en Home Assistant volgen later als
apart uitbreidingsproject (de tool-structuur is er al klaar voor).
"""

from dotenv import load_dotenv

load_dotenv()  # optioneel, alleen relevant voor lokaal draaien buiten Portainer

from app import mcp
# Import hieronder is nodig voor het side-effect (tool-registratie),
# ook al lijkt hij "ongebruikt".
from tools import unifi  # noqa: F401

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)
