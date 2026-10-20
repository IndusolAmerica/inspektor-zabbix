"""
Protocol-neutral snapshot of one INspektor, and the mapping to Zabbix keys.

Adapters fill a Snapshot. This module turns it into trapper values.
Rule: a metric that does not exist or is not meaningful is None, and None
is never sent. Zabbix gets no value instead of a fake zero.
"""

import time
from dataclasses import dataclass, field
from typing import Optional

from zbx_sender import make_value

# Template names. Must match what tools/make_template.py generates.
TEMPLATE_BY_TYPE = {
    "PN": "INspektor NT PROFINET by Zabbix trapper",
    "EIP": "INspektor NT EtherNet-IP by Zabbix trapper",
    "PB": "INspektor NT PROFIBUS by Zabbix trapper",
}


@dataclass
class Device:
    id: str                 # PN/EIP: MAC address, PB: station address
    name: str
    ip: str = ""
    kind: str = "device"    # device | switch | slave
    metrics: dict = field(default_factory=dict)   # metrics.py key -> value or None


@dataclass
class Snapshot:
    host: str                       # Zabbix host name == NAME in config.txt
    type: str                       # PN / EIP / PB
    reachable: bool
    devices: list = field(default_factory=list)
    bus_status: Optional[int] = None
    unack_alerts: Optional[int] = None
    clock: float = field(default_factory=time.time)
    error: str = ""


def discovery_value(snap: Snapshot) -> Optional[dict]:
    """LLD payload. Only sent when the INspektor answered: an empty list sent
    during an outage would make Zabbix mark every device as lost."""
    if not snap.reachable:
        return None
    rows = [{"{#ID}": d.id, "{#NAME}": d.name, "{#IP}": d.ip, "{#KIND}": d.kind}
            for d in snap.devices]
    return make_value(snap.host, "inspektor.discovery", rows, snap.clock)


def metric_values(snap: Snapshot, service_version: str) -> list:
    c, h = snap.clock, snap.host
    out = [
        make_value(h, "inspektor.heartbeat", 1, c),
        make_value(h, "inspektor.status", 1 if snap.reachable else 0, c),
        make_value(h, "inspektor.service.version", service_version, c),
        make_value(h, "inspektor.error", snap.error[:1000], c),
    ]
    if not snap.reachable:
        return out

    out.append(make_value(h, "inspektor.devices.total", len(snap.devices), c))
    if snap.bus_status is not None:
        out.append(make_value(h, "inspektor.bus.status", snap.bus_status, c))
    if snap.unack_alerts is not None:
        out.append(make_value(h, "inspektor.alerts.unack", snap.unack_alerts, c))

    for d in snap.devices:
        for key, v in d.metrics.items():
            if v is None:
                continue
            if isinstance(v, float):
                v = round(v, 6)
            out.append(make_value(h, f"device.{key}[{d.id}]", v, c))
    return out
