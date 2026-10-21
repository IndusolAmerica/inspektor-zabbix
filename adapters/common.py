"""
HTTP and helpers shared by the three adapters.
INspektor NT serves plain HTTP on port 80. PROFIBUS uses /api/v1,
PROFINET and EtherNet/IP use /api/v2.
"""

import json
import urllib.request

LINK_BYTES_PER_SEC = 12_500_000      # 100 Mbit/s


def get_json(ip: str, path: str, timeout: float):
    req = urllib.request.Request(f"http://{ip}{path}", headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def num(value, default=0):
    """Same contract as the AVEVA package: the APIs return None for empty counters."""
    try:
        return type(default)(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def dig(d, *path):
    """Nested dict access that never raises. Returns None if anything is missing."""
    cur = d
    for p in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    return cur


def jitter_triplet(jit: dict):
    """Raw jitter is in TENTHS of a percent (640 -> 64.0 %).
    Returns (peak, min, max) in %, or (None, None, None) if not reported."""
    if not isinstance(jit, dict):
        return None, None, None
    j_min, j_max = jit.get("min"), jit.get("max")
    if j_min is None or j_max is None:
        return None, None, None
    j_min, j_max = j_min / 10.0, j_max / 10.0
    return max(abs(j_min), abs(j_max)), j_min, j_max


JITTER_ARTEFACT_PCT = 100.0


def meaningful_jitter(jit: dict, breakdowns_in_window):
    """Jitter of one window, or (None, None, None) when it is not a measurement.

    Not meaningful when the station had a breakdown in that window, or when the
    value sits at +/-100 % or beyond: no telegrams arrived, so there is no
    timing to measure. Frame gaps alone do NOT suppress it: verified on a live
    EtherNet/IP network (21 Oct 2026) where a station with 3 frame gaps in the
    minute still showed a valid 1.0 % on the INspektor web page."""
    if breakdowns_in_window:
        return None, None, None
    peak, jmin, jmax = jitter_triplet(jit)
    if peak is not None and peak >= JITTER_ARTEFACT_PCT:
        return None, None, None
    return peak, jmin, jmax


def netload_pct(bytes_per_sec):
    if bytes_per_sec is None:
        return None
    # 3 decimals: finer than the 2 the INspektor web page shows
    return round(100.0 * float(bytes_per_sec) / LINK_BYTES_PER_SEC, 3)


def bus_status_v2(ip, timeout):
    chronic = get_json(ip, "/api/v2/chronic", timeout)
    if not chronic:
        return None
    cid = chronic[-1].get("id")
    return get_json(ip, f"/api/v2/chronic/{cid}/meta", timeout).get("status")


def bus_status_v1(ip, timeout):
    chronic = get_json(ip, "/api/v1/chronic", timeout)
    if not chronic:
        return None
    latest = max(chronic, key=lambda c: int(c.get("id", 0)))
    return (latest.get("meta") or {}).get("status")


def unack_alerts(ip, api, timeout):
    return get_json(ip, f"/api/{api}/meta/unacknowledged_alerts", timeout).get("unacknowledged_alerts")


def fill_bus(snap, ip, api, timeout):
    """Bus status and alert count are secondary: a failure here does not make
    the INspektor unreachable, it only leaves those two values out."""
    try:
        code = bus_status_v1(ip, timeout) if api == "v1" else bus_status_v2(ip, timeout)
        snap.bus_status = int(code) if code is not None else None
    except Exception as exc:
        snap.error = f"bus status: {type(exc).__name__}: {exc}"
    try:
        n = unack_alerts(ip, api, timeout)
        snap.unack_alerts = int(n) if n is not None else None
    except Exception:
        pass
