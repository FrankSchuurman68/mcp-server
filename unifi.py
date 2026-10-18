"""Tools om je UniFi Gateway lokaal te bevragen en clients te beheren,
via de lokale Network Integration API (rechtstreeks op je LAN, geen cloud-proxy nodig).

Alles is alleen-lezen, behalve `uf_client_action` (BLOCK/UNBLOCK van een client).

Lijst-tools ondersteunen paginering:
  - offset / limit  : één pagina ophalen (limit maximaal 200, zoals de API toestaat)
  - fetch_all=True  : (standaard) alle pagina's achter elkaar ophalen, tot MAX_ITEMS
De API zelf geeft standaard maar 25 items terug; zonder paginering mis je dus clients.
"""

import os
import requests
from app import mcp

UNIFI_HOST = os.environ["UNIFI_HOST"].rstrip("/")  # bv. https://192.168.1.1
UNIFI_API_KEY = os.environ["UNIFI_API_KEY"]
UNIFI_SITE_ID = os.environ.get("UNIFI_SITE_ID", "default")
UNIFI_VERIFY_SSL = os.environ.get("UNIFI_VERIFY_SSL", "false").lower() == "true"

BASE_URL = f"{UNIFI_HOST}/proxy/network/integration/v1"
HEADERS = {"X-API-KEY": UNIFI_API_KEY, "Accept": "application/json", "Content-Type": "application/json"}

PAGE_SIZE = 200  # maximum van de Integration API
MAX_ITEMS = 2000  # veiligheidsgrens voor fetch_all


def _get(path: str, params: dict | None = None) -> dict:
    r = requests.get(
        f"{BASE_URL}{path}", headers=HEADERS, params=params, verify=UNIFI_VERIFY_SSL, timeout=15
    )
    r.raise_for_status()
    return r.json()


def _list(path: str, offset: int = 0, limit: int = 100, fetch_all: bool = True, filter: str | None = None) -> dict:
    """Haal een lijst op met paginering. Geeft {offset, limit, count, totalCount, data}."""
    limit = max(1, min(limit, PAGE_SIZE))
    base = {"filter": filter} if filter else {}

    if not fetch_all:
        return _get(path, {**base, "offset": max(0, offset), "limit": limit})

    items: list = []
    total = None
    pos = max(0, offset)
    size = PAGE_SIZE
    while True:
        try:
            page = _get(path, {**base, "offset": pos, "limit": size})
        except requests.HTTPError as e:
            # Sommige endpoints (bv. firewall) accepteren een kleinere maximale limit: verklein stapsgewijs.
            if e.response is not None and e.response.status_code == 400 and size > 25:
                size = 100 if size > 100 else 50 if size > 50 else 25
                continue
            raise
        data = page.get("data", [])
        total = page.get("totalCount", total)
        items.extend(data)
        pos += len(data)
        if not data or total is None or pos >= total or len(items) >= MAX_ITEMS:
            break
    return {
        "offset": max(0, offset),
        "count": len(items),
        "totalCount": total if total is not None else len(items),
        "truncated": bool(total is not None and max(0, offset) + len(items) < total),
        "data": items,
    }


def _site(path: str) -> str:
    return f"/sites/{UNIFI_SITE_ID}{path}"


# --- Informatie en apparaten ---------------------------------------------------------


@mcp.tool
def uf_info() -> dict:
    """Geef de versie van de UniFi Network-applicatie (applicationVersion) terug."""
    return _get("/info")


@mcp.tool
def uf_list_devices(offset: int = 0, limit: int = 100, fetch_all: bool = True) -> dict:
    """Lijst alle UniFi netwerk-apparaten (APs, switches, gateway) op de site.
    Met fetch_all=False haal je één pagina op via offset/limit (max 200)."""
    return _list(_site("/devices"), offset, limit, fetch_all)


# --- Clients -------------------------------------------------------------------------


@mcp.tool
def uf_list_clients(offset: int = 0, limit: int = 100, fetch_all: bool = True, filter: str | None = None) -> dict:
    """Lijst alle verbonden clients met hun MAC-adres, IP, naam en uplink.
    Met fetch_all=False haal je één pagina op via offset/limit (max 200).
    filter is optioneel en gebruikt de UniFi-filtersyntax, bv. "type.eq('WIRELESS')"."""
    return _list(_site("/clients"), offset, limit, fetch_all, filter)


def _find_client_id(mac: str) -> str:
    mac = mac.lower().replace(":", "").replace("-", "")
    for c in _list(_site("/clients"))["data"]:
        if c.get("macAddress", "").lower().replace(":", "") == mac:
            return c["id"]
    raise ValueError(f"Geen client gevonden met MAC-adres {mac}")


@mcp.tool
def uf_client_action(mac: str, action: str) -> dict:
    """Blokkeer of deblokkeer een client op basis van MAC-adres.
    action moet 'BLOCK' of 'UNBLOCK' zijn."""
    if action not in ("BLOCK", "UNBLOCK"):
        raise ValueError("action moet BLOCK of UNBLOCK zijn")
    client_id = _find_client_id(mac)
    r = requests.post(
        f"{BASE_URL}{_site(f'/clients/{client_id}/actions')}",
        headers=HEADERS,
        json={"action": action},
        verify=UNIFI_VERIFY_SSL,
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


# --- Netwerken, wifi en firewall (alleen-lezen) ---------------------------------------


@mcp.tool
def uf_list_networks(offset: int = 0, limit: int = 100, fetch_all: bool = True) -> dict:
    """Lijst de netwerken/VLAN's van de site (naam, vlanId, management, enabled, DHCP-gegevens)."""
    return _list(_site("/networks"), offset, limit, fetch_all)


@mcp.tool
def uf_list_wifi(offset: int = 0, limit: int = 100, fetch_all: bool = True) -> dict:
    """Lijst de wifi-netwerken (SSID's) met hun gekoppelde netwerk/VLAN, beveiliging en band."""
    return _list(_site("/wifi/broadcasts"), offset, limit, fetch_all)


@mcp.tool
def uf_list_firewall_zones(offset: int = 0, limit: int = 100, fetch_all: bool = True) -> dict:
    """Lijst de firewallzones (zone-based firewall) en welke netwerken erin zitten."""
    return _list(_site("/firewall/zones"), offset, limit, fetch_all)


@mcp.tool
def uf_list_firewall_policies(offset: int = 0, limit: int = 100, fetch_all: bool = True) -> dict:
    """Lijst de firewallregels (policies) tussen zones: bron, bestemming, actie en volgorde."""
    return _list(_site("/firewall/policies"), offset, limit, fetch_all)


@mcp.tool
def uf_list_acl_rules(offset: int = 0, limit: int = 100, fetch_all: bool = True) -> dict:
    """Lijst de ACL-regels (layer-2/3 toegangsregels op switchniveau)."""
    return _list(_site("/acl-rules"), offset, limit, fetch_all)
