"""
End-to-end validation of the INspektor template against a real Zabbix.

Run against the throwaway Zabbix from docker-compose.yml (never production):

    cd test
    docker compose up -d
    py validate_template.py                 # default http://localhost:8080, Admin / zabbix
    py validate_template.py --cleanup       # also deletes the test hosts at the end

What it proves, in order:
  1. The YAML imports without errors on a fresh Zabbix
  2. The imported templates have exactly the items, prototypes and triggers we expect
  3. Hosts can be created and linked (same code path as --provision)
  4. Low-level discovery over trapper creates the device items
  5. Every value the collector sends is ACCEPTED (failed = 0) and stored
  6. A trigger actually fires (bus status Error on the PROFIBUS host)

Device data comes from realistic payloads (tests/fixtures.py) run through the
real adapters, so this exercises the same code the collector runs.
"""

import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import yaml                                                    # noqa: E402
from adapters import ethernetip, profibus, profinet            # noqa: E402
from fixtures import EIP_STATION, PN_STATION, pb               # noqa: E402
from model import TEMPLATE_BY_TYPE, Snapshot, discovery_value, metric_values  # noqa: E402
from zbx_api import ZabbixApi, ZabbixApiError                  # noqa: E402
from zbx_sender import ZabbixSender                            # noqa: E402

TEMPLATE_FILE = os.path.join(ROOT, "template", "template_indusol_inspektor_nt", "7.0",
                             "template_indusol_inspektor_nt.yaml")
GROUP = "INspektor template test"
HOSTS = {"PN": "TEST-INspektor-PN", "EIP": "TEST-INspektor-EIP", "PB": "TEST-INspektor-PB"}

results = []


def check(name, ok, detail=""):
    results.append((name, ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))
    return ok


def snapshots():
    return {
        "PN": Snapshot(host=HOSTS["PN"], type="PN", reachable=True, bus_status=2, unack_alerts=1,
                       devices=profinet.select([PN_STATION])),
        "EIP": Snapshot(host=HOSTS["EIP"], type="EIP", reachable=True, bus_status=2, unack_alerts=0,
                        devices=ethernetip.select([EIP_STATION])),
        "PB": Snapshot(host=HOSTS["PB"], type="PB", reachable=True, bus_status=4, unack_alerts=0,
                       devices=profibus.select([pb(a) for a in range(0, 128)] +
                                               [pb(4, out_hist=9, name="Valve island")])),
    }


def wait_api(url, seconds=180):
    t0 = time.time()
    while True:
        try:
            return ZabbixApi.login(url, ARGS.user, ARGS.password)
        except Exception as exc:
            if time.time() - t0 > seconds:
                raise SystemExit(f"Zabbix API not reachable at {url}: {exc}")
            print("  waiting for Zabbix to start...")
            time.sleep(10)


def main():
    print("=" * 74)
    print("  INspektor template validation")
    print("=" * 74)
    api = wait_api(ARGS.url)
    print(f"  Zabbix {api.version} at {api.url}\n")

    # 1. import ---------------------------------------------------------------
    with open(TEMPLATE_FILE, encoding="utf-8") as fh:
        source = fh.read()
    cu = {"createMissing": True, "updateExisting": True}
    rules = {
        "template_groups": cu, "templates": cu, "valueMaps": cu,
        "items": dict(cu, deleteMissing=True),
        "discoveryRules": dict(cu, deleteMissing=True),
        "triggers": dict(cu, deleteMissing=True),
        "templateLinkage": {"createMissing": True},
    }
    try:
        api.call("configuration.import", {"format": "yaml", "source": source, "rules": rules})
        check("1. Template imports without errors", True)
    except ZabbixApiError as exc:
        check("1. Template imports without errors", False, str(exc))
        return

    # 2. structure ------------------------------------------------------------
    export = yaml.safe_load(source)["zabbix_export"]
    for t in export["templates"]:
        got = api.call("template.get", {
            "filter": {"host": [t["template"]]}, "output": ["templateid"],
            "selectItems": "count", "selectDiscoveries": "count", "selectTriggers": "count",
            "selectMacros": "count"})
        if not got:
            check(f"2. {t['template']} exists", False)
            continue
        g = got[0]
        protos = api.call("itemprototype.get", {"templateids": g["templateid"], "countOutput": True})
        tprotos = api.call("triggerprototype.get", {"templateids": g["templateid"], "countOutput": True})
        exp_items = len(t["items"])
        exp_trig = sum(len(i.get("triggers", [])) for i in t["items"])
        exp_proto = len(t["discovery_rules"][0]["item_prototypes"])
        exp_tproto = sum(len(p.get("trigger_prototypes", [])) for p in t["discovery_rules"][0]["item_prototypes"])
        ok = (int(g["items"]) == exp_items and int(g["triggers"]) == exp_trig and
              int(protos) == exp_proto and int(tprotos) == exp_tproto and int(g["discoveries"]) == 1)
        check(f"2. {t['template']} structure", ok,
              f"items {g['items']}/{exp_items}, triggers {g['triggers']}/{exp_trig}, "
              f"prototypes {protos}/{exp_proto}, trigger prototypes {tprotos}/{exp_tproto}")

    # 3. hosts ----------------------------------------------------------------
    gid = api.ensure_host_group(GROUP)
    hostids = {}
    for typ, host in HOSTS.items():
        tid = api.template_id(TEMPLATE_BY_TYPE[typ])
        hostids[typ], _ = api.ensure_host(host, gid, tid, "127.0.0.1", "validate_template.py")
    check("3. Test hosts created and linked", len(hostids) == 3)

    print("\n  waiting for the server configuration cache (15 s)...")
    time.sleep(15)

    # 4. discovery ------------------------------------------------------------
    snaps = snapshots()
    sender = ZabbixSender(ARGS.server, ARGS.port)
    r = sender.send([discovery_value(s) for s in snaps.values()])
    check("4a. Discovery values accepted", r.failed == 0, r.info)

    expected = {typ: len(snaps[typ].devices) * len(snaps[typ].devices[0].metrics) for typ in snaps}
    t0 = time.time()
    while True:
        counts = {typ: int(api.call("item.get", {"hostids": hostids[typ], "countOutput": True,
                                                  "filter": {"flags": 4}})) for typ in snaps}
        if all(counts[t] >= expected[t] for t in snaps) or time.time() - t0 > 90:
            break
        time.sleep(5)
    check("4b. Discovery created the device items", all(counts[t] >= expected[t] for t in snaps),
          ", ".join(f"{t} {counts[t]}/{expected[t]}" for t in snaps))

    # 5. values ---------------------------------------------------------------
    values = [v for s in snaps.values() for v in metric_values(s, "validate")]
    failed = None
    t0 = time.time()
    while time.time() - t0 < 90:
        for v in values:
            v["clock"] = int(time.time())
        r = sender.send(values)
        failed = r.failed
        if failed == 0:
            break
        print(f"  {r.failed} of {r.total} rejected, new items still loading into the cache, retrying...")
        time.sleep(10)
    check("5a. Every value accepted by the server", failed == 0, r.info)

    time.sleep(5)
    pn_dev = snaps["PN"].devices[0]
    probe = [
        ("PN", f"device.jitter.peak[{pn_dev.id}]", pn_dev.metrics["jitter.peak"]),
        ("PN", f"device.framegaps[{pn_dev.id}]", pn_dev.metrics["framegaps"]),
        ("EIP", "inspektor.devices.total", 1),
        ("PB", "device.errorframes[4]", 40),
        ("PB", "inspektor.bus.status", 4),
    ]
    for typ, key, want in probe:
        got = api.call("item.get", {"hostids": hostids[typ], "filter": {"key_": key},
                                    "output": ["lastvalue"]})
        val = got[0]["lastvalue"] if got else None
        ok = val is not None and abs(float(val) - float(want)) < 1e-6
        check(f"5b. {HOSTS[typ]} {key} stored", ok, f"got {val}, sent {want}")

    # 6. trigger --------------------------------------------------------------
    t0 = time.time()
    names = []
    while time.time() - t0 < 60:
        probs = api.call("problem.get", {"hostids": hostids["PB"], "output": ["name"]})
        names = [p["name"] for p in probs]
        if any("Bus status is Error" in n for n in names):
            break
        time.sleep(5)
    check("6. Trigger fires (PB bus status Error)", any("Bus status is Error" in n for n in names),
          "; ".join(names) or "no problems")

    # cleanup -----------------------------------------------------------------
    if ARGS.cleanup:
        api.call("host.delete", list(hostids.values()))
        print("\n  Test hosts deleted.")

    print("\n" + "=" * 74)
    passed = sum(ok for _, ok in results)
    print(f"  {passed}/{len(results)} checks passed on Zabbix {api.version}")
    if passed == len(results):
        print("  Put this version in the template README under 'Tested versions'.")
    print("=" * 74)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8080")
    ap.add_argument("--server", default="127.0.0.1", help="Zabbix trapper address")
    ap.add_argument("--port", type=int, default=10051)
    ap.add_argument("--user", default="Admin")
    ap.add_argument("--password", default="zabbix")
    ap.add_argument("--cleanup", action="store_true")
    ARGS = ap.parse_args()
    sys.exit(main() or 0)
