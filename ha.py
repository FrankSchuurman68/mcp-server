"""Alleen-lezen tools voor Home Assistant.

Er zijn bewust geen tools die iets schakelen of aanpassen: alleen entiteiten
opvragen, de huidige status lezen en statistieken (bv. uurverbruik in kWh) ophalen.

Configuratie komt uit de omgeving van de container:
  HA_URL    bv. http://192.168.1.104:8123
  HA_TOKEN  long-lived access token (Home Assistant -> profiel -> Beveiliging)

De variabelen worden pas bij gebruik gelezen, zodat de server (en de UniFi-tools)
ook starten als Home Assistant nog niet is ingesteld.
"""

import asyncio
import json
import os
from datetime import datetime, timezone

import requests
import websockets

from app import mcp

MAX_POINTS = 20000
PERIODS = ("5minute", "hour", "day", "week", "month")
STAT_TYPES = ("change", "sum", "state", "mean", "min", "max")


def _cfg() -> tuple[str, str]:
    url = os.environ.get("HA_URL", "").rstrip("/")
    token = os.environ.get("HA_TOKEN", "")
    if not url or not token:
        raise RuntimeError("HA_URL en HA_TOKEN zijn niet ingesteld in de container.")
    return url, token


def _get(path: str):
    url, token = _cfg()
    r = requests.get(f"{url}{path}", headers={"Authorization": f"Bearer {token}"}, timeout=20)
    r.raise_for_status()
    return r.json()


async def _ws_call(payload: dict):
    url, token = _cfg()
    ws_url = url.replace("https://", "wss://", 1).replace("http://", "ws://", 1) + "/api/websocket"
    async with websockets.connect(ws_url, max_size=None, open_timeout=15) as ws:
        await asyncio.wait_for(ws.recv(), 15)  # auth_required
        await ws.send(json.dumps({"type": "auth", "access_token": token}))
        auth = json.loads(await asyncio.wait_for(ws.recv(), 15))
        if auth.get("type") != "auth_ok":
            raise RuntimeError("Home Assistant heeft de token geweigerd.")
        await ws.send(json.dumps({"id": 1, **payload}))
        while True:
            msg = json.loads(await asyncio.wait_for(ws.recv(), 90))
            if msg.get("id") == 1:
                break
    if not msg.get("success"):
        raise RuntimeError(f"Home Assistant fout: {msg.get('error')}")
    return msg["result"]


def _iso(ts) -> str:
    if isinstance(ts, (int, float)):
        if ts > 1e11:  # milliseconden
            ts = ts / 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    return str(ts)


@mcp.tool
def ha_list_entities(
    search: str | None = None,
    domain: str | None = None,
    device_class: str | None = None,
    limit: int = 100,
) -> dict:
    """Zoek Home Assistant-entiteiten (alleen lezen).
    search: deel van entity_id of naam (bv. 'shelly'), domain: bv. 'sensor' of 'switch',
    device_class: bv. 'energy' of 'power'. Geeft entity_id, naam, status en eenheid."""
    needle = search.lower() if search else None
    rows = []
    for s in _get("/api/states"):
        eid = s["entity_id"]
        attrs = s.get("attributes", {})
        name = attrs.get("friendly_name", "")
        if domain and not eid.startswith(domain + "."):
            continue
        if device_class and attrs.get("device_class") != device_class:
            continue
        if needle and needle not in eid.lower() and needle not in name.lower():
            continue
        rows.append(
            {
                "entity_id": eid,
                "name": name,
                "state": s.get("state"),
                "unit": attrs.get("unit_of_measurement"),
                "device_class": attrs.get("device_class"),
                "state_class": attrs.get("state_class"),
            }
        )
    rows.sort(key=lambda r: r["entity_id"])
    return {"total": len(rows), "shown": min(len(rows), limit), "entities": rows[:limit]}


@mcp.tool
def ha_get_state(entity_id: str) -> dict:
    """Lees de huidige status en alle attributen van één entiteit (alleen lezen)."""
    return _get(f"/api/states/{entity_id}")


@mcp.tool
async def ha_statistic_ids(search: str | None = None, limit: int = 200) -> dict:
    """Lijst de statistic-id's waarvoor Home Assistant langetermijnstatistieken bewaart
    (dit zijn de sensoren die je met ha_statistics kunt opvragen, zoals kWh-tellers).
    search: deel van de id of naam."""
    result = await _ws_call({"type": "recorder/list_statistic_ids"})
    needle = search.lower() if search else None
    rows = []
    for r in result:
        sid = r.get("statistic_id", "")
        name = r.get("name") or ""
        if needle and needle not in sid.lower() and needle not in name.lower():
            continue
        rows.append(
            {
                "statistic_id": sid,
                "name": name,
                "unit": r.get("statistics_unit_of_measurement"),
                "has_sum": r.get("has_sum"),
                "has_mean": r.get("has_mean"),
                "source": r.get("source"),
            }
        )
    rows.sort(key=lambda r: r["statistic_id"])
    return {"total": len(rows), "shown": min(len(rows), limit), "statistics": rows[:limit]}


@mcp.tool
async def ha_statistics(
    statistic_ids: list[str],
    start: str,
    end: str | None = None,
    period: str = "hour",
    stat_type: str = "change",
) -> dict:
    """Haal statistieken op uit de Home Assistant-recorder (alleen lezen).
    statistic_ids: bv. ['sensor.p1_meter_energy_import'].
    start/end: ISO-tijd in UTC, bv. '2026-10-01T00:00:00Z'.
    period: 5minute, hour, day, week of month.
    stat_type: 'change' = verbruik per periode (kWh), verder sum, state, mean, min, max.
    Geeft per id een lijst [starttijd_utc, waarde]."""
    if period not in PERIODS:
        raise ValueError(f"period moet een van {PERIODS} zijn")
    if stat_type not in STAT_TYPES:
        raise ValueError(f"stat_type moet een van {STAT_TYPES} zijn")
    payload = {
        "type": "recorder/statistics_during_period",
        "start_time": start,
        "statistic_ids": statistic_ids,
        "period": period,
        "types": [stat_type],
    }
    if end:
        payload["end_time"] = end
    result = await _ws_call(payload)
    series, total = {}, 0
    for sid, rows in result.items():
        pts = [[_iso(r["start"]), None if r.get(stat_type) is None else round(r[stat_type], 4)] for r in rows]
        series[sid] = pts
        total += len(pts)
    if total > MAX_POINTS:
        raise ValueError(
            f"Te veel datapunten ({total}, max {MAX_POINTS}). Kies een kortere periode, "
            "minder id's of een grotere period (bv. day)."
        )
    missing = [i for i in statistic_ids if i not in series]
    return {"period": period, "stat_type": stat_type, "points": total, "missing_ids": missing, "series": series}
