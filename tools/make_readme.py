"""
Writes the template README.md (Zabbix community layout) from the same
export data the YAML is built from, so the tables never drift from the
template. Called by make_template.py.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from metrics import PROTOCOL_NAME             # noqa: E402
from model import TEMPLATE_BY_TYPE           # noqa: E402

try:
    from make_template import AUTHOR, REPO_URL
except ImportError:                          # pragma: no cover
    AUTHOR, REPO_URL = "InduSol America", ""


def _cell(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def _table(head, rows):
    out = ["|" + "|".join(head) + "|", "|" + "|".join("---" for _ in head) + "|"]
    out += ["|" + "|".join(_cell(c) for c in r) + "|" for r in rows]
    return "\n".join(out)


def _strip(expr, tname):
    return expr.replace(f"/{tname}/", "/TEMPLATE/")


def _section(t, typ):
    T = t["template"]
    proto = PROTOCOL_NAME[typ]
    lld = t["discovery_rules"][0]
    parts = [f"## {T}\n"]

    parts.append("### Macros used\n")
    parts.append(_table(["Name", "Description", "Default"],
                        [(f"`{m['macro']}`", m.get("description", ""), f"`{m['value']}`") for m in t["macros"]]))

    parts.append("\n\n### Items\n")
    parts.append(_table(["Name", "Description", "Type", "Key"],
                        [(i["name"], i.get("description", ""), "Zabbix trapper", f"`{i['key']}`") for i in t["items"]]))

    parts.append("\n\n### Triggers\n")
    rows = [(tr["name"], tr.get("description", ""), f"`{_strip(tr['expression'], T)}`", tr["priority"].capitalize())
            for i in t["items"] for tr in i.get("triggers", [])]
    parts.append(_table(["Name", "Description", "Expression", "Severity"], rows))

    parts.append("\n\n### LLD rule\n")
    parts.append(_table(["Name", "Description", "Type", "Key"],
                        [(lld["name"], lld["description"], "Zabbix trapper", f"`{lld['key']}`")]))

    parts.append(f"\n\n### Item prototypes for {proto} devices discovery\n")
    parts.append(_table(["Name", "Description", "Units", "Key"],
                        [(p["name"], p.get("description", ""), p.get("units", ""), f"`{p['key']}`")
                         for p in lld["item_prototypes"]]))

    parts.append(f"\n\n### Trigger prototypes for {proto} devices discovery\n")
    rows = [(tp["name"], tp.get("description", ""), f"`{_strip(tp['expression'], T)}`", tp["priority"].capitalize())
            for p in lld["item_prototypes"] for tp in p.get("trigger_prototypes", [])]
    parts.append(_table(["Name", "Description", "Expression", "Severity"], rows))
    return "\n".join(parts) + "\n"


def write(export: dict, path: str, fmt: str):
    templates = export["zabbix_export"]["templates"]
    by_name = {t["template"]: t for t in templates}

    doc = [f"""# Indu-Sol INspektor NT by Zabbix trapper

## Overview

Templates for monitoring industrial networks through the **Indu-Sol INspektor NT**
diagnostic devices: PROFINET, EtherNet/IP and PROFIBUS.

The INspektor NT measures the health of a fieldbus or industrial Ethernet network
(breakdowns, frame gaps, jitter, network load, error and repeat telegrams) for every
device on it. A small collector reads each INspektor over its REST API and pushes the
raw values to Zabbix through the trapper protocol. Every threshold lives in this
template as a macro, so it can be tuned per host or per device without touching the
collector.

Three templates, one per protocol. Link exactly one to each INspektor host:

| Template | INspektor type |
|---|---|
| `{TEMPLATE_BY_TYPE['PN']}` | PROFINET |
| `{TEMPLATE_BY_TYPE['EIP']}` | EtherNet/IP |
| `{TEMPLATE_BY_TYPE['PB']}` | PROFIBUS |

Devices are created automatically through low-level discovery. `{{#ID}}` is the MAC
address on PROFINET and EtherNet/IP, and the station address on PROFIBUS.

## Requirements

Zabbix version: {fmt} and higher.

- Indu-Sol INspektor NT reachable over HTTP (port 80) from the collector PC.
- INspektor-Zabbix collector (Windows): {REPO_URL}
- Network access from the collector to the Zabbix server or proxy on TCP 10051.

## Tested versions

This template has been tested on:
- Zabbix 7.0.31 (template import, low-level discovery, trapper values and triggers validated end to end with `test/validate_template.py`)
- Indu-Sol INspektor NT PROFINET, EtherNet/IP and PROFIBUS

## Configuration

1. Import this template: *Data collection > Templates > Import*.
2. Create one host per INspektor. The host name must be exactly `NAME` from the
   collector's `config.txt`. No interface is needed: data is pushed.
   Link the template that matches the INspektor type.
   The collector can create the hosts for you: `INspektor-Zabbix.exe --provision`.
3. On the collector PC, set `ZABBIX_SERVER` (server or proxy) and one block per
   INspektor in `config.txt`, then run `INspektor-Zabbix.exe --test`.
   Every host must show `OK`.
4. Register the collector as a scheduled task with `Install-Task.ps1`.

If the hosts are monitored by a proxy, point `ZABBIX_SERVER` to the proxy.

### Counters and gauges

Counters are cumulative since the INspektor measurement started, matching the
*History* column on the INspektor web page. A problem opens when a counter increases
inside `{{$INSPEKTOR.EVENT.WINDOW}}` and resolves when the window is clean.

Gauges (jitter, network load, cycle time) are the last minute, matching the
*Last minute* column.

Jitter is not sent for a minute in which the device had a breakdown, or when it reads
+/-100 % or beyond: no telegrams arrived, so the value is an artefact and would distort
graphs. Frame gaps alone do not suppress it.
PROFIBUS has no jitter, frame gaps or network load, so those items do not exist on
PROFIBUS hosts.

### Per-device thresholds

Override any threshold for a single device with a context macro on the host, using
the device ID:

```
{{$INSPEKTOR.JITTER.WARN:"00:20:D5:01:64:92"}} = 70
```
"""]
    for typ in ("PN", "EIP", "PB"):
        doc.append(_section(by_name[TEMPLATE_BY_TYPE[typ]], typ))

    doc.append(f"""## Feedback

Author: {AUTHOR}

Issues and questions: {REPO_URL}/issues
""")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(doc))
    print(f"Written {path}")
