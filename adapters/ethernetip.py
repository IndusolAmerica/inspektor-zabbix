"""
EtherNet/IP INspektor NT  (API v2)

Ported from INspektor-AVEVA protocols/eip.py.

  /api/v2/stations     every station, windows inline
  windows              lastMin   last 60 s          (Last minute column)
                       history   since meas. start  (History column)
  counters             <window>.etherNetIpDiagnosis.counter.{breakdown,
                       restart, frameGaps, frameOvertake}
  error frames         <window>.counters.errorFramesRecv + errorFramesSend
  jitter               <window>.etherNetIpDiagnosis.jitter.{min,max}  TENTHS of %
  cycle time           <window>.etherNetIpDiagnosis.cycleTime.average  microseconds
  netload              <window>.diagnosis.netloadIn/Out.{average,max}  BYTES/s

Never read per-device counters from /chronic: a chronic collection is a whole
recording session and gives inflated numbers (206 against 3 real).
Name: general.alias, IP as fallback.
"""

from adapters.common import (dig, fill_bus, get_json, jitter_triplet, netload_pct, num)
from model import Device, Snapshot

CUR, HIS = "lastMin", "history"


def is_cip_device(st) -> bool:
    has_ip = len(dig(st, "general", "ip4s") or []) > 0
    has_cip = any(
        r.get("isCipStation", False) and r.get("srcMac", "00:00:00:00:00:00") != "00:00:00:00:00:00"
        for r in (st.get("rawStations") or [])
    )
    return has_ip and has_cip


def device_name(st) -> str:
    g = st.get("general", {}) or {}
    alias = (g.get("alias") or "").strip()
    if alias:
        return alias
    ips = g.get("ip4s") or []
    return ips[0] if ips else g.get("mac", "Unknown")


def _cnt(st, window, key):
    return num(dig(st, window, "etherNetIpDiagnosis", "counter", key))


def _err_frames(st, window):
    c = dig(st, window, "counters") or {}
    return num(c.get("errorFramesRecv")) + num(c.get("errorFramesSend"))


def jitter_is_meaningful(st, window):
    return _cnt(st, window, "breakdown") == 0 and _cnt(st, window, "frameGaps") == 0


def station_metrics(st) -> dict:
    peak = jmin = jmax = None
    if jitter_is_meaningful(st, CUR):
        peak, jmin, jmax = jitter_triplet(dig(st, CUR, "etherNetIpDiagnosis", "jitter"))
    cyc = dig(st, CUR, "etherNetIpDiagnosis", "cycleTime", "average")
    return {
        "breakdowns": _cnt(st, HIS, "breakdown"),
        "restarts": _cnt(st, HIS, "restart"),
        "framegaps": _cnt(st, HIS, "frameGaps"),
        "overtakes": _cnt(st, HIS, "frameOvertake"),
        "errorframes": _err_frames(st, HIS),
        "jitter.peak": peak,
        "jitter.min": jmin,
        "jitter.max": jmax,
        "cycletime": (cyc / 1_000_000.0) if cyc is not None else None,
        "netload.in": netload_pct(dig(st, CUR, "diagnosis", "netloadIn", "max")),
        "netload.out": netload_pct(dig(st, CUR, "diagnosis", "netloadOut", "max")),
    }


def to_device(st) -> Device:
    g = st.get("general", {}) or {}
    mac = (g.get("mac") or "").upper()
    return Device(
        id=mac or str(st.get("id")),
        name=device_name(st),
        ip=(g.get("ip4s") or [""])[0],
        kind="device",
        metrics=station_metrics(st),
    )


def select(stations):
    return [to_device(s) for s in stations if is_cip_device(s)]


def dump(cfg, timeout):
    return {"/api/v2/stations": get_json(cfg.ip, "/api/v2/stations", timeout)}


def read(cfg, timeout) -> Snapshot:
    snap = Snapshot(host=cfg.name, type="EIP", reachable=False)
    try:
        stations = get_json(cfg.ip, "/api/v2/stations", timeout)
    except Exception as exc:
        snap.error = f"{type(exc).__name__}: {exc}"
        return snap
    snap.reachable = True
    snap.devices = select(stations)
    fill_bus(snap, cfg.ip, "v2", timeout)
    return snap
