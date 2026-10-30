"""Beperkte beheertools voor de trading-advisor container (LXC 111 op pve2).

Dit zijn bewust vaste acties en geen vrije shell. De MCP-server verbindt via SSH met de
gebruiker 'claude-ops' op de container. Die gebruiker heeft een sleutel met een "forced
command" (/usr/local/bin/advisor-ops), dus zelfs met de sleutel kan alleen dat script draaien,
en dat script kent alleen de acties hieronder. De containerkant dwingt dus zelf af wat mag.

Configuratie (environment variables in het Portainer stack-formulier):
  ADVISOR_HOST          IP van de container (standaard 192.168.1.173)
  ADVISOR_PORT          SSH-poort (standaard 22)
  ADVISOR_USER          SSH-gebruiker (standaard claude-ops)
  ADVISOR_SSH_KEY_B64   privésleutel (ed25519, OpenSSH-formaat), base64-gecodeerd
  ADVISOR_HOSTKEY       publieke hostsleutel van de container, bv. "ssh-ed25519 AAAAC3..."
                        (uit /etc/ssh/ssh_host_ed25519_key.pub). Er is geen vertrouwen op
                        het eerste gebruik: zonder deze waarde weigert de module te verbinden.

De variabelen worden pas bij gebruik gelezen, zodat de server ook start als dit nog niet is
ingesteld.
"""

import base64
import io
import logging
import threading
import time
import os
from typing import Literal

import paramiko

from app import mcp

log = logging.getLogger("advisor")

TIMEOUT_VERBINDEN = 10
TIMEOUT_ACTIE = 120
MAX_UITVOER = 8000
# Na een start of herstart van de gateway minimaal zo lang wachten. Elke herstart is een
# nieuwe inlogpoging bij IBKR; te veel pogingen kunnen het paper-account tijdelijk blokkeren.
HERSTART_PAUZE_SEC = 300

# Dit zijn exact de namen die advisor-ops op de container accepteert.
ACTIES = frozenset({
    "status", "logs-gateway", "logs-snapshot", "ibc-log", "logboek",
    "snapshot-nu", "start-gateway", "restart-gateway",
})

_lock = threading.Lock()
_laatste_gateway_actie: float | None = None


def _sleutels():
    """Leest de configuratie en geeft (host, gebruiker, privésleutel, hostsleutel) terug."""
    host = os.environ.get("ADVISOR_HOST", "192.168.1.173").strip()
    port = int(os.environ.get("ADVISOR_PORT", "22"))
    user = os.environ.get("ADVISOR_USER", "claude-ops").strip()
    key_b64 = os.environ.get("ADVISOR_SSH_KEY_B64", "").strip()
    hostkey = os.environ.get("ADVISOR_HOSTKEY", "").strip()
    if not key_b64 or not hostkey:
        raise RuntimeError(
            "ADVISOR_SSH_KEY_B64 en ADVISOR_HOSTKEY zijn niet ingesteld in de container."
        )
    try:
        pem = base64.b64decode(key_b64).decode("utf-8").replace("\r\n", "\n")  # sleutel van Windows kan CRLF hebben
        pkey = paramiko.Ed25519Key.from_private_key(io.StringIO(pem))
    except Exception as exc:  # de inhoud van de sleutel nooit in de melding opnemen
        raise RuntimeError(f"ADVISOR_SSH_KEY_B64 is geen geldige ed25519-sleutel ({type(exc).__name__}).")
    delen = hostkey.split()
    if len(delen) < 2 or delen[0] != "ssh-ed25519":
        raise RuntimeError("ADVISOR_HOSTKEY moet de vorm 'ssh-ed25519 AAAA...' hebben.")
    try:
        server_key = paramiko.Ed25519Key(data=base64.b64decode(delen[1]))
    except Exception as exc:
        raise RuntimeError(f"ADVISOR_HOSTKEY is ongeldig ({type(exc).__name__}).")
    return host, port, user, pkey, server_key


def _verbind():
    host, port, user, pkey, server_key = _sleutels()
    client = paramiko.SSHClient()
    client.get_host_keys().add(host if port == 22 else f"[{host}]:{port}", "ssh-ed25519", server_key)
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect(
        host,
        port=port,
        username=user,
        pkey=pkey,
        timeout=TIMEOUT_VERBINDEN,
        banner_timeout=TIMEOUT_VERBINDEN,
        auth_timeout=TIMEOUT_VERBINDEN,
        look_for_keys=False,
        allow_agent=False,
    )
    return client


def _run(actie: str) -> dict:
    if actie not in ACTIES:
        raise ValueError(f"Onbekende actie '{actie}'.")
    log.warning("advisor-actie: %s", actie)  # zichtbaar in de containerlogs van de MCP-server
    client = _verbind()
    try:
        _, stdout, stderr = client.exec_command(actie, timeout=TIMEOUT_ACTIE)
        uit = stdout.read().decode("utf-8", "replace")
        fout = stderr.read().decode("utf-8", "replace")
        code = stdout.channel.recv_exit_status()
    finally:
        client.close()
    tekst = uit.strip()
    if fout.strip():
        tekst += "\n[stderr]\n" + fout.strip()
    if len(tekst) > MAX_UITVOER:
        tekst = "[ingekort, begin weggelaten]\n" + tekst[-MAX_UITVOER:]
    return {"actie": actie, "exitcode": code, "uitvoer": tekst}


def _gateway_actie(actie: str) -> dict:
    """Start of herstart de gateway, maar niet vaker dan eens per HERSTART_PAUZE_SEC."""
    global _laatste_gateway_actie
    with _lock:
        nu = time.monotonic()
        if _laatste_gateway_actie is not None:
            wacht = HERSTART_PAUZE_SEC - (nu - _laatste_gateway_actie)
            if wacht > 0:
                return {
                    "actie": actie,
                    "geweigerd": f"Er is net een gateway-actie uitgevoerd. Wacht nog {int(wacht)} seconden "
                                 "(elke herstart is een nieuwe inlogpoging bij IBKR).",
                }
        _laatste_gateway_actie = nu
    return _run(actie)


@mcp.tool
def advisor_status() -> dict:
    """Status van de trading-advisor container: diensten xvfb, ibgateway en snapshot.timer,
    gateway-status en aantal herstarts, volgende geplande snapshot, of poort 4002 luistert en uptime."""
    return _run("status")


@mcp.tool
def advisor_logs(bron: Literal["gateway", "snapshot", "ibc"] = "gateway") -> dict:
    """Recente logregels. bron 'gateway' = systemd-journal van ibgateway (laatste 60 regels),
    'snapshot' = journal van de snapshot-dienst (laatste 40), 'ibc' = laatste 40 regels van
    het nieuwste IBC-logboek (inlog, dialogen, herstarts). Wachtwoorden staan hier niet in."""
    return _run({"gateway": "logs-gateway", "snapshot": "logs-snapshot", "ibc": "ibc-log"}[bron])


@mcp.tool
def advisor_logboek() -> dict:
    """Samenvatting van het logboek van de adviseur (alleen lezen): aantal snapshots per dag,
    laatste snapshot en benchmarkkoers, en het aantal adviezen en kostenregels."""
    return _run("logboek")


@mcp.tool
def advisor_snapshot_nu() -> dict:
    """Draait snapshot.py nu eenmalig als gebruiker advisor (leest het IBKR paper-account
    read-only en schrijft een regel in het logboek). Duurt ongeveer 15 seconden."""
    return _run("snapshot-nu")


@mcp.tool
def advisor_gateway_start() -> dict:
    """Start de IB Gateway-dienst (alleen nuttig als hij gestopt is). Maximaal eens per 5 minuten,
    want elke start is een inlogpoging bij IBKR. De gateway heeft ongeveer 100 seconden nodig."""
    return _gateway_actie("start-gateway")


@mcp.tool
def advisor_gateway_herstart() -> dict:
    """Herstart de IB Gateway-dienst. Gebruik dit alleen als advisor_status laat zien dat hij
    niet werkt (poort 4002 luistert niet of de dienst hangt). Maximaal eens per 5 minuten,
    want elke herstart is een inlogpoging bij IBKR. De gateway heeft ongeveer 100 seconden nodig."""
    return _gateway_actie("restart-gateway")
