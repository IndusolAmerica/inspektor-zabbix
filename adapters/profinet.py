"""
PROFINET INspektor NT  (API v2)

Ported from INspektor-AVEVA protocols/pn.py + inspektor.py + diagnostics.py.

  /api/v2/stations     every station, with its measurement windows inline
  windows              lastmin      last 60 s          (Last minute column)
                       history_all  since meas. start  (History column)
  counters             <window>.pn_diagnosis.counter.{breakdown, restart,
                       frame_gaps, frame_overtake, alarm_high, alarm_low}
  jitter               <window>.pn_diagnosis.jitter.{min,max}  TENTHS of %
  netload              <window>.diagnosis.netload_in/out.{average,max}  bytes/s

Only stations with the PROFINET status bit (11) are kept. Devices need a
name; switches are kept with or without one.
"""

from adapters.common import (dig, fill_bus, get_json, jitter_triplet, netload_pct, num)
from model import Device, Snapshot

CUR, HIS = "lastmin", "history_all"


def is_profinet(st):
    return bool(num(dig(st, "general", "status")) & (1 << 11))


def is_switch(st):
    g = st.get("general", {}) or {}
    port_count = num(g.get("portCount"))
    has_ip = len(g.get("ip4s") or []) > 0
    is_ctrl = bool(num(g.get("status")) & (1 << 12))
    dtype = (g.get("deviceTypeName") or "").lower()
    kw = ("switch", "promesh", "scalance", "hirschmann", "managed", "unmanaged", "hub", "xb-", "xl-")
    return (port_count > 2 and has_ip and not is_ctrl) or any(k in dtype for k in kw)


def _counter(st, window, key):
    return num(dig(st, window, "pn_diagnosis", "counter", key))


def jitter_is_meaningful(st, window):
    """A window with a breakdown or frame gaps has no measurable jitter: no
    telegrams arrived, the +/-100 % reported is an artefact."""
    return _counter(st, window, "breakdown") == 0 and _counter(st, window, "frame_gaps") == 0


def station_metrics(st) -> dict:
    peak = jmin = jmax = None
    if jitter_is_meaningful(st, CUR):
        peak, jmin, jmax = jitter_triplet(dig(st, CUR, "pn_diagnosis", "jitter"))
    return {
        "breakdowns": _counter(st, HIS, "breakdown"),
        "restarts": _counter(st, HIS, "restart"),
        "framegaps": _counter(st, HIS, "frame_gaps"),
        "framegaps.max": _counter(st, HIS, "max_frame_gaps"),
        "overtakes": _counter(st, HIS, "frame_overtake"),
        "errorframes": num(dig(st, HIS, "counters", "error_frames_recv")) + num(dig(st, HIS, "counters", "error_frames_send")),
        "alarms.high": _counter(st, HIS, "alarm_high"),
        "alarms.low": _counter(st, HIS, "alarm_low"),
        "jitter.peak": peak,
        "jitter.min": jmin,
        "jitter.max": jmax,
        "netload.in": netload_pct(dig(st, CUR, "diagnosis", "netload_in", "max")),
        "netload.out": netload_pct(dig(st, CUR, "diagnosis", "netload_out", "max")),
    }


def to_device(st, kind) -> Device:
    g = st.get("general", {}) or {}
    mac = (g.get("mac") or "").upper()
    return Device(
        id=mac or str(st.get("id")),
        name=g.get("name") or mac or f"Station-{st.get('id')}",
        ip=(g.get("ip4s") or [""])[0],
        kind=kind,
        metrics=station_metrics(st),
    )


def select(stations):
    pn = [s for s in stations if is_profinet(s)]
    switches = [s for s in pn if is_switch(s)]
    devices = [s for s in pn if not is_switch(s) and dig(s, "general", "name")]
    return [to_device(s, "device") for s in devices] + [to_device(s, "switch") for s in switches]


def dump(cfg, timeout):
    return {"/api/v2/stations": get_json(cfg.ip, "/api/v2/stations", timeout)}


def read(cfg, timeout) -> Snapshot:
    snap = Snapshot(host=cfg.name, type="PN", reachable=False)
    try:
        stations = get_json(cfg.ip, "/api/v2/stations", timeout)
    except Exception as exc:
        snap.error = f"{type(exc).__name__}: {exc}"
        return snap
    snap.reachable = True
    snap.devices = select(stations)
    fill_bus(snap, cfg.ip, "v2", timeout)
    return snap
