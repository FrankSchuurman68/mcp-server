"""Tools om je UniFi Gateway lokaal te bevragen en clients te beheren,
via de lokale Network Integration API (rechtstreeks op je LAN, geen cloud-proxy nodig)."""

import os
import requests
from app import mcp

UNIFI_HOST = os.environ["UNIFI_HOST"].rstrip("/")  # bv. https://192.168.1.1
UNIFI_API_KEY = os.environ["UNIFI_API_KEY"]
UNIFI_SITE_ID = os.environ.get("UNIFI_SITE_ID", "default")
UNIFI_VERIFY_SSL = os.environ.get("UNIFI_VERIFY_SSL", "false").lower() == "true"

BASE_URL = f"{UNIFI_HOST}/proxy/network/integration/v1"
HEADERS = {"X-API-KEY": UNIFI_API_KEY, "Accept": "application/json", "Content-Type": "application/json"}


@mcp.tool
def uf_list_devices() -> dict:
    """Lijst alle UniFi netwerk-apparaten (APs, switches, gateway) op de site."""
    r = requests.get(
        f"{BASE_URL}/sites/{UNIFI_SITE_ID}/devices", headers=HEADERS, verify=UNIFI_VERIFY_SSL, timeout=15
    )
    r.raise_for_status()
    return r.json()


@mcp.tool
def uf_list_clients() -> dict:
    """Lijst alle verbonden clients met hun MAC-adres, naam en blokkeer-status."""
    r = requests.get(
        f"{BASE_URL}/sites/{UNIFI_SITE_ID}/clients", headers=HEADERS, verify=UNIFI_VERIFY_SSL, timeout=15
    )
    r.raise_for_status()
    return r.json()


def _find_client_id(mac: str) -> str:
    mac = mac.lower().replace(":", "").replace("-", "")
    for c in uf_list_clients().get("data", []):
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
        f"{BASE_URL}/sites/{UNIFI_SITE_ID}/clients/{client_id}/actions",
        headers=HEADERS,
        json={"action": action},
        verify=UNIFI_VERIFY_SSL,
        timeout=15,
    )
    r.raise_for_status()
    return r.json()
