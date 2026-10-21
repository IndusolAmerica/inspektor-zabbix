"""
PROFIBUS INspektor NT  (API v1, not v2)

Ported from INspektor-AVEVA protocols/pb.py.

  /api/v1/devices      129 slots: id 0 = master, 1..127 = slaves
  payload is FLAT:     device.lastmin / device.history = {breakdown, restart,
                       error_frames, frame_repeat, max_frame_repeat,
                       diag_intern, diag_extern, unanswered_slave_diag,
                       bytes_in/out, frames_in/out}

No jitter, no netload, no IP per device: slaves are identified by station
address. Those metrics do not exist on PROFIBUS hosts and are never sent.
"""

from adapters.common import fill_bus, get_json, num
from model import Device, Snapshot

MAX_STATION_ADDR = 125

# general.status bit set only on the DP master (seen on a live bus: master at
# address 2 had status 1481, slaves 1449/1465). Confirm the bit map with HQ.
MASTER_STATUS_BIT = 1 << 6


def is_master(dev) -> bool:
    return bool(num((dev.get("general") or {}).get("status")) & MASTER_STATUS_BIT)


def is_active_slave(dev) -> bool:
    """The master GAP-scans every free address, so empty slots pile up
    frames_in (405k+ observed) while frames_out stays 0. Only a real slave
    answers. Verified on a live bus: frames_in > 0 matched all 128 slots,
    frames_out > 0 matched the 6 real ones. status / name catch a slave that
    is configured but has never answered."""
    addr = num(dev.get("id"))
    if addr <= 0 or addr > MAX_STATION_ADDR:
        return False
    if is_master(dev):
        return False
    general = dev.get("general", {}) or {}
    history = dev.get("history", {}) or {}
    lastmin = dev.get("lastmin", {}) or {}
    answered = num(history.get("frames_out")) > 0 or num(lastmin.get("frames_out")) > 0
    configured = num(general.get("status")) != 0
    named = bool((general.get("name") or "").strip())
    return answered or configured or named


def device_name(dev) -> str:
    name = ((dev.get("general") or {}).get("name") or "").strip()
    return name or f"PB-Slave-{dev.get('id', '?')}"


def slave_metrics(dev) -> dict:
    h = dev.get("history", {}) or {}
    return {
        "breakdowns": num(h.get("breakdown")),
        "restarts": num(h.get("restart")),
        "errorframes": num(h.get("error_frames")),
        "repeats": num(h.get("frame_repeat")),
        "repeats.max": num(h.get("max_frame_repeat")),
        "diag.unanswered": num(h.get("unanswered_slave_diag")),
        "diag.internal": num(h.get("diag_intern")),
        "diag.external": num(h.get("diag_extern")),
    }


def select(devices):
    return [
        Device(id=str(num(d.get("id"))), name=device_name(d), ip="", kind="slave",
               metrics=slave_metrics(d))
        for d in devices if is_active_slave(d)
    ]


def dump(cfg, timeout):
    return {"/api/v1/devices": get_json(cfg.ip, "/api/v1/devices", timeout)}


def read(cfg, timeout) -> Snapshot:
    snap = Snapshot(host=cfg.name, type="PB", reachable=False)
    try:
        devices = get_json(cfg.ip, "/api/v1/devices", timeout)
    except Exception as exc:
        snap.error = f"{type(exc).__name__}: {exc}"
        return snap
    snap.reachable = True
    snap.devices = select(devices)
    fill_bus(snap, cfg.ip, "v1", timeout)
    return snap
