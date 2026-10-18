"""Alleen-lezen tools voor Pi-hole v6 (REST-API).

Er zijn bewust geen tools die iets wijzigen: alleen de query log, een samenvatting
en de topclients opvragen, per Pi-hole.

Configuratie komt uit de omgeving van de container:
  PIHOLE_HOSTS     komma-gescheiden lijst naam=url, bv.
                   pihole1=http://192.168.1.126,pihole2=http://192.168.1.127
  PIHOLE_PASSWORD  wachtwoord (of app-wachtwoord) voor beide Pi-holes
  PIHOLE_PASSWORD_<NAAM>  optioneel, per Pi-hole een eigen wachtwoord
                   (bv. PIHOLE_PASSWORD_PIHOLE2); gaat voor op PIHOLE_PASSWORD

Bij elke aanroep wordt een sessie geopend en daarna weer afgesloten, zodat de
beperkte sessielimiet van Pi-hole niet volloopt. De variabelen worden pas bij
gebruik gelezen, zodat de server ook start als Pi-hole nog niet is ingesteld.
"""

import os
import time
from contextlib import contextmanager

import requests

from app import mcp

TIMEOUT = 15
MAX_QUERIES = 1000


def _hosts() -> dict[str, str]:
    raw = os.environ.get("PIHOLE_HOSTS", "")
    hosts = {}
    for part in raw.split(","):
        if "=" in part:
            name, url = part.split("=", 1)
            hosts[name.strip().lower()] = url.strip().rstrip("/")
    if not hosts:
        raise RuntimeError("PIHOLE_HOSTS is niet ingesteld in de container.")
    return hosts


def _password(name: str) -> str:
    pw = os.environ.get(f"PIHOLE_PASSWORD_{name.upper()}") or os.environ.get("PIHOLE_PASSWORD", "")
    if not pw:
        raise RuntimeError("PIHOLE_PASSWORD is niet ingesteld in de container.")
    return pw


@contextmanager
def _session(name: str):
    hosts = _hosts()
    name = name.lower()
    if name not in hosts:
        raise ValueError(f"Onbekende Pi-hole '{name}'. Kies uit: {', '.join(hosts)}")
    base = hosts[name]
    r = requests.post(f"{base}/api/auth", json={"password": _password(name)}, timeout=TIMEOUT)
    r.raise_for_status()
    sess = r.json().get("session", {})
    if not sess.get("valid"):
        raise RuntimeError(f"Inloggen op Pi-hole '{name}' mislukt: {sess.get('message', 'onbekende reden')}")
    sid = sess["sid"]
    try:
        yield base, {"sid": sid, "Accept": "application/json"}
    finally:
        try:
            requests.delete(f"{base}/api/auth", headers={"sid": sid}, timeout=TIMEOUT)
        except requests.RequestException:
            pass


@mcp.tool
def pi_list_hosts() -> dict:
    """Geef de geconfigureerde Pi-holes (naam en URL) terug."""
    return _hosts()


@mcp.tool
def pi_summary(host: str) -> dict:
    """Samenvatting van één Pi-hole (queries, geblokkeerd, clients, gravity) plus de versies.
    host is de naam uit pi_list_hosts, bv. 'pihole1'."""
    with _session(host) as (base, h):
        out = {}
        for key, path in (("summary", "/api/stats/summary"), ("version", "/api/info/version")):
            r = requests.get(f"{base}{path}", headers=h, timeout=TIMEOUT)
            r.raise_for_status()
            out[key] = r.json()
        return out


@mcp.tool
def pi_top_clients(host: str, count: int = 20, blocked: bool = False) -> dict:
    """Topclients op aantal queries (of alleen geblokkeerde queries met blocked=True)."""
    with _session(host) as (base, h):
        r = requests.get(
            f"{base}/api/stats/top_clients",
            headers=h,
            params={"count": max(1, min(count, 100)), "blocked": str(blocked).lower()},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return r.json()


@mcp.tool
def pi_queries(
    host: str,
    client: str | None = None,
    domain: str | None = None,
    minutes: int = 60,
    limit: int = 100,
) -> dict:
    """Query log van één Pi-hole van de laatste `minutes` minuten (standaard 60).
    Filter optioneel op client (IP of naam) en/of domein. limit maximaal 1000.
    Geeft per query tijd, domein, type, client, status (allowed/blocked/cache) en antwoord."""
    now = int(time.time())
    params = {
        "from": now - max(1, minutes) * 60,
        "until": now,
        "length": max(1, min(limit, MAX_QUERIES)),
    }
    if client:
        params["client_ip"] = client
    if domain:
        params["domain"] = domain
    with _session(host) as (base, h):
        r = requests.get(f"{base}/api/queries", headers=h, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
    rows = data.get("queries", [])
    if client:  # vangnet: ook filteren op naam/IP als de server de parameter negeert
        rows = [
            q for q in rows
            if client in (q.get("client", {}).get("ip"), q.get("client", {}).get("name"))
        ]
    return {
        "host": host,
        "minutes": minutes,
        "count": len(rows),
        "recordsFiltered": data.get("recordsFiltered"),
        "queries": rows,
    }
