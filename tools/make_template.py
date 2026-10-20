"""
Generates zbx_template_inspektor.yaml from metrics.py.

Format 7.0: imports into 7.0, 7.2, 7.4 and 8.0. A newer format does NOT
import into an older server, so 7.0 is the floor. --format 6.0 writes the
same content with the 6.0 header (trigger syntax is identical since 5.4);
untested until we have a 6.0 server.

UUIDs are derived from names, so the file is stable between runs and a
re-import updates objects instead of duplicating them.

Usage:  python tools/make_template.py [--format 7.0] [--out path]
"""

import argparse
import hashlib
import os
import sys
import uuid

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from metrics import BUS_STATUS, BY_TYPE, PROTOCOL_NAME  # noqa: E402
from model import TEMPLATE_BY_TYPE                       # noqa: E402

VENDOR = "InduSol America"
AUTHOR = "Luis Aguirre, InduSol America"
REPO_URL = "https://github.com/IndusolAmerica/inspektor-zabbix"
TEMPLATE_GROUP = "Templates/Industrial networks"
COMMUNITY_DIR = "template_indusol_inspektor_nt"


def uid(*parts) -> str:
    h = hashlib.sha256("|".join(parts).encode()).digest()[:16]
    return uuid.UUID(bytes=h, version=4).hex


def tags(**kw):
    return [{"tag": k, "value": v} for k, v in kw.items()]


def build_template(typ: str, fmt: str) -> dict:
    T = TEMPLATE_BY_TYPE[typ]
    proto = PROTOCOL_NAME[typ]
    metrics = BY_TYPE[typ]
    has_jitter = any(m.key.startswith("jitter") for m in metrics)
    has_netload = any(m.key.startswith("netload") for m in metrics)

    def item(name, key, vtype="UNSIGNED", units="", history="31d", desc="",
             component="inspektor", triggers=None, discard_unchanged=None, valuemap=None):
        it = {"uuid": uid(T, "item", key), "name": name, "type": "TRAP", "key": key,
              "history": history, "value_type": vtype}
        if vtype in ("CHAR", "TEXT", "LOG"):
            it["trends"] = "0"
        if units:
            it["units"] = units
        if desc:
            it["description"] = desc
        if valuemap:
            it["valuemap"] = {"name": valuemap}
        if discard_unchanged:
            it["preprocessing"] = [{"type": "DISCARD_UNCHANGED_HEARTBEAT",
                                    "parameters": [discard_unchanged]}]
        it["tags"] = tags(component=component)
        if triggers:
            it["triggers"] = triggers
        return it

    def trig(name, expr, prio, desc="", key=None):
        t = {"uuid": uid(T, "trigger", key or name), "expression": expr,
             "name": name, "priority": prio}
        if desc:
            t["description"] = desc
        t["tags"] = tags(scope="availability" if prio in ("HIGH", "DISASTER") else "performance")
        return t

    items = [
        item("Service heartbeat", "inspektor.heartbeat", history="7d", component="service",
             desc="Sent every cycle by INspektor-Zabbix. Missing data means the collector stopped.",
             triggers=[trig("INspektor-Zabbix service is not sending data",
                            f"nodata(/{T}/inspektor.heartbeat,{{$INSPEKTOR.NODATA}})=1", "HIGH",
                            "No data from the INspektor-Zabbix collector. Check the scheduled task "
                            "on the collector PC and access to the Zabbix server or proxy on port 10051.")]),
        item("Service version", "inspektor.service.version", vtype="CHAR", component="service",
             discard_unchanged="1d"),
        item("INspektor reachable", "inspektor.status",
             desc="1 = the INspektor answered over HTTP, 0 = it did not.",
             triggers=[trig("INspektor is not reachable",
                            f"max(/{T}/inspektor.status,#3)=0", "HIGH",
                            "The collector could not read the INspektor for 3 consecutive cycles. "
                            "The collector itself is running.")]),
        item("Last read error", "inspektor.error", vtype="TEXT", history="7d", discard_unchanged="1h"),
        item("Devices", "inspektor.devices.total",
             desc="Devices currently reported by the INspektor after filtering."),
        item("Bus status", "inspektor.bus.status", valuemap="INspektor bus status",
             desc="Overall bus status of the current INspektor measurement.",
             triggers=[
                 trig("Bus status is Error", f"last(/{T}/inspektor.bus.status)=4", "HIGH", key="bus-error"),
                 trig("Bus status is Warning", f"last(/{T}/inspektor.bus.status)=3", "WARNING", key="bus-warn"),
             ]),
        item("Unacknowledged alerts", "inspektor.alerts.unack",
             desc="Alerts not yet acknowledged on the INspektor web interface."),
    ]

    win = "{$INSPEKTOR.EVENT.WINDOW}"
    protos = []
    for m in metrics:
        key = f"device.{m.key}[{{#ID}}]"
        k = f"/{T}/{key}"
        tps = []
        if m.trigger:
            prio, rule, macro = m.trigger
            if rule == "increase":
                tps.append(trig(f"{{#NAME}}: {m.name} increased",
                                f"last({k})-min({k},{win})>0", prio,
                                f"The counter went up within {win}. Resolves when the window is clean.",
                                key=key))
            elif rule == "above":
                ctx = macro[:-1] + ':"{#ID}"}'      # per-device override via macro context
                expr = f"last({k})>{ctx}"
                if m.key.startswith("jitter"):
                    # jitter stops arriving while the station is in breakdown;
                    # without this the problem would stay open on a stale value
                    expr += f" and nodata({k},{{$INSPEKTOR.NODATA}})=0"
                tps.append(trig(f"{{#NAME}}: {m.name} above {ctx}{m.units}", expr, prio, key=key))
        p = item(f"{{#NAME}}: {m.name}", key, vtype=m.vtype, units=m.units, desc=m.desc,
                 component="device")
        p["tags"].append({"tag": "kind", "value": "{#KIND}"})
        if tps:
            p["trigger_prototypes"] = tps
        protos.append(p)

    lld = {
        "uuid": uid(T, "lld", "inspektor.discovery"),
        "name": f"{proto} devices discovery",
        "type": "TRAP",
        "key": "inspektor.discovery",
        "lifetime": "{$INSPEKTOR.LLD.LIFETIME}",
        "description": ("Device list pushed by INspektor-Zabbix. Only sent while the INspektor "
                        "is reachable, so an outage does not mark devices as lost. "
                        "{#ID} is the MAC address (PROFINET, EtherNet/IP) or the station address (PROFIBUS)."),
        "item_prototypes": protos,
    }

    macros = [
        {"macro": "{$INSPEKTOR.NODATA}", "value": "5m",
         "description": "Time without data before the collector is considered stopped."},
        {"macro": "{$INSPEKTOR.EVENT.WINDOW}", "value": "1h",
         "description": "A counter increase inside this window raises a problem."},
        {"macro": "{$INSPEKTOR.LLD.LIFETIME}", "value": "7d",
         "description": "How long a device that left the network keeps its items."},
    ]
    if has_jitter:
        macros.append({"macro": "{$INSPEKTOR.JITTER.WARN}", "value": "50",
                       "description": 'Jitter peak warning, %. Per device: {$INSPEKTOR.JITTER.WARN:"<MAC>"}.'})
    if has_netload:
        macros.append({"macro": "{$INSPEKTOR.NETLOAD.WARN}", "value": "20",
                       "description": 'Network load warning, % of 100 Mbit/s. Per device: {$INSPEKTOR.NETLOAD.WARN:"<MAC>"}.'})

    tpl = {
        "uuid": uid(T, "template"),
        "template": T,
        "name": T,
        "description": (f"Indu-Sol INspektor NT ({proto}) diagnostics pushed by the INspektor-Zabbix "
                        "collector through Zabbix trapper. One host per INspektor; the host name "
                        "must match NAME in config.txt.\n\n"
                        f"Setup and collector: {REPO_URL}\n"
                        f"Author: {AUTHOR}"),
        "vendor": {"name": VENDOR, "version": f"{fmt}-1"},
        "groups": [{"name": TEMPLATE_GROUP}],
        "items": items,
        "discovery_rules": [lld],
        "tags": [{"tag": "class", "value": "network"}, {"tag": "target", "value": "inspektor"}],
        "macros": macros,
        "valuemaps": [{
            "uuid": uid(T, "valuemap", "bus"),
            "name": "INspektor bus status",
            "mappings": [{"value": str(k), "newvalue": v} for k, v in BUS_STATUS.items()],
        }],
    }
    return tpl


def build(fmt: str) -> dict:
    return {"zabbix_export": {
        "version": fmt,
        "template_groups": [{"uuid": uid("group", TEMPLATE_GROUP), "name": TEMPLATE_GROUP}],
        "templates": [build_template(t, fmt) for t in ("PN", "EIP", "PB")],
    }}


def _dump(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        yaml.dump(data, fh, sort_keys=False, allow_unicode=True, width=1000)
    print(f"Written {path}")


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser()
    ap.add_argument("--format", default="7.0", choices=["6.0", "6.4", "7.0", "7.2", "7.4", "8.0"])
    a = ap.parse_args()
    data = build(a.format)
    if a.format == "6.0":
        data["zabbix_export"]["groups"] = data["zabbix_export"].pop("template_groups")

    # 1) copy shipped next to the .exe
    _dump(data, os.path.join(root, "zbx_template_inspektor.yaml"))
    # 2) Zabbix community layout: template/<name>/<version>/<name>.yaml + README.md
    vdir = os.path.join(root, "template", COMMUNITY_DIR, a.format)
    _dump(data, os.path.join(vdir, f"{COMMUNITY_DIR}.yaml"))
    import make_readme
    make_readme.write(data, os.path.join(vdir, "README.md"), a.format)


if __name__ == "__main__":
    main()
