"""
INspektor-Zabbix
Reads Indu-Sol INspektor NT devices (PROFINET, EtherNet/IP, PROFIBUS) and
pushes raw metrics to Zabbix through the trapper protocol. Zabbix decides
what is a problem; thresholds live in the template macros, not here.

Usage:
    INspektor-Zabbix.exe              run forever (scheduled task)
    INspektor-Zabbix.exe --once       one cycle, then exit
    INspektor-Zabbix.exe --test       send one heartbeat per host and show the server answer
    INspektor-Zabbix.exe --dump       save raw INspektor JSON to the dumps folder
    INspektor-Zabbix.exe --provision  create host group and hosts through the Zabbix API
"""

import argparse
import json
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler

import settings
from adapters import ADAPTERS
from buffer import ValueBuffer
from model import TEMPLATE_BY_TYPE, discovery_value, metric_values
from zbx_sender import ZabbixSender, ZabbixSendError, make_value

VERSION = "0.1.1"
FLUSH_MAX_PER_CYCLE = 20 * 250   # values drained from the buffer per cycle

log = logging.getLogger("inspektor-zabbix")


def setup_logging():
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    log.addHandler(sh)
    fh = RotatingFileHandler(os.path.join(settings.base_dir(), "INspektor-Zabbix.log"),
                             maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    log.addHandler(fh)


def make_sender(s):
    return ZabbixSender(s.zabbix_server, s.zabbix_port,
                        tls_ca=s.tls_ca_file, tls_cert=s.tls_cert_file, tls_key=s.tls_key_file)


def report_errors(s):
    for e in s.errors:
        log.warning("config.txt: %s", e)


# --------------------------------------------------------------------------- cycle

class Collector:
    def __init__(self):
        self.cfg = settings.ReloadingSettings()
        self.buffer = ValueBuffer(os.path.join(settings.base_dir(), "buffer.sqlite"))
        self._last_failed_warn = 0.0

    def read_all(self, s):
        snaps = []
        for ins in s.inspektors:
            try:
                snap = ADAPTERS[ins.type].read(ins, s.http_timeout)
            except Exception as exc:   # one INspektor never stops the others
                from model import Snapshot
                snap = Snapshot(host=ins.name, type=ins.type, reachable=False,
                                error=f"Adapter crash: {type(exc).__name__}: {exc}")
                log.exception("%s (%s): adapter crashed", ins.name, ins.ip)
            if snap.reachable:
                log.info("%-20s %-3s %3d devices", ins.name, ins.type, len(snap.devices))
            else:
                log.warning("%-20s %-3s NOT REACHABLE  %s", ins.name, ins.type, snap.error)
            snaps.append(snap)
        return snaps

    def send_discovery(self, sender, snaps):
        """Discovery is sent directly, never buffered: an old device list
        replayed later is wrong by definition."""
        vals = [v for v in (discovery_value(s) for s in snaps) if v]
        if not vals:
            return
        try:
            r = sender.send(vals)
            if r.failed:
                log.warning("Discovery: %s. Check that each host exists in Zabbix with the template linked.", r)
        except ZabbixSendError as exc:
            log.warning("Discovery not sent: %s", exc)

    def flush(self, sender):
        """Returns (sent, rejected)."""
        sent = rejected = 0
        while sent < FLUSH_MAX_PER_CYCLE:
            rows = self.buffer.peek(250)
            if not rows:
                break
            r = sender.send([v for _, v in rows])   # raises on transport failure
            self.buffer.delete_upto(rows[-1][0])
            sent += len(rows)
            rejected += r.failed
            if r.failed and time.time() - self._last_failed_warn > 600:
                self._last_failed_warn = time.time()
                log.warning(
                    "Zabbix rejected %d of %d values. Usual causes: host name in config.txt "
                    "does not match Zabbix, template not linked, new devices still being "
                    "discovered (clears in one cycle), or this PC is not in 'Allowed hosts'.",
                    r.failed, r.total)
        return sent, rejected

    def cycle(self):
        s, changed = self.cfg.get()
        if changed:
            log.info("config.txt loaded: %d INspektor(s), Zabbix %s:%s",
                     len(s.inspektors), s.zabbix_server, s.zabbix_port)
            report_errors(s)
            self.buffer.max_rows = s.buffer_max_rows
        if not s.zabbix_server or not s.inspektors:
            return s

        snaps = self.read_all(s)
        sender = make_sender(s)
        self.send_discovery(sender, snaps)

        values = []
        for snap in snaps:
            values.extend(metric_values(snap, VERSION))
        # Everything goes through the buffer, so order is preserved after an outage.
        dropped = self.buffer.push(values)
        if dropped:
            log.warning("Buffer full: dropped %d oldest values.", dropped)
        try:
            n, rej = self.flush(sender)
            pending = self.buffer.count()
            msg = f"Sent {n} values, {n - rej} accepted"
            if rej:
                msg += f", {rej} REJECTED"
            if pending:
                msg += f", {pending} still buffered"
            (log.warning if rej else log.info)(msg + ".")
        except ZabbixSendError as exc:
            log.warning("Zabbix not reachable, %d values buffered: %s", self.buffer.count(), exc)
        return s

    def run_forever(self):
        log.info("INspektor-Zabbix %s started", VERSION)
        while True:
            t0 = time.time()
            try:
                s = self.cycle()
                interval = s.check_interval
            except Exception:
                log.exception("Cycle failed")
                interval = 30
            time.sleep(max(1.0, interval - (time.time() - t0)))


# --------------------------------------------------------------------------- tools

def cmd_test():
    s = settings.load()
    report_errors(s)
    sender = make_sender(s)
    print(f"Sending one heartbeat per host to {s.zabbix_server}:{s.zabbix_port}\n")
    ok = True
    for ins in s.inspektors:
        try:
            r = sender.send([make_value(ins.name, "inspektor.heartbeat", 1)])
            state = "OK" if r.processed == 1 else "REJECTED"
            ok &= r.processed == 1
            print(f"  {ins.name:<24} {state:<9} {r.info}")
        except ZabbixSendError as exc:
            ok = False
            print(f"  {ins.name:<24} NO CONNECTION  {exc}")
    if not ok:
        print("\nREJECTED means the server was reached but did not accept the value:\n"
              "  - the host name in Zabbix must be exactly NAME from config.txt\n"
              "  - the host must have the INspektor template linked\n"
              "  - the 'Allowed hosts' field of the trapper items must include this PC")
    return 0 if ok else 1


def cmd_dump():
    s = settings.load()
    out_dir = os.path.join(settings.base_dir(), "dumps")
    os.makedirs(out_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for ins in s.inspektors:
        try:
            data = ADAPTERS[ins.type].dump(ins, s.http_timeout)
            path = os.path.join(out_dir, f"{ins.name}-{stamp}.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
            print(f"  {ins.name:<24} saved {path}")
        except Exception as exc:
            print(f"  {ins.name:<24} FAILED {type(exc).__name__}: {exc}")
    return 0


def cmd_provision():
    from zbx_api import ZabbixApi, ZabbixApiError
    s = settings.load()
    report_errors(s)
    if not s.zabbix_api_url or not s.zabbix_api_token:
        print("ZABBIX_API_URL and ZABBIX_API_TOKEN must be set in config.txt for --provision.")
        return 1
    try:
        api = ZabbixApi(s.zabbix_api_url, s.zabbix_api_token)
        print(f"Zabbix API version {api.version}")
        gid = api.ensure_host_group(s.zabbix_host_group)
        for ins in s.inspektors:
            tid = api.template_id(TEMPLATE_BY_TYPE[ins.type])
            hid, created = api.ensure_host(
                ins.name, gid, tid, ins.ip,
                description=f"Indu-Sol INspektor NT {ins.type} at {ins.ip}. Data pushed by INspektor-Zabbix.")
            print(f"  {ins.name:<24} {'created' if created else 'exists, template checked'} (hostid {hid})")
    except ZabbixApiError as exc:
        print(f"ERROR: {exc}")
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser(description="INspektor NT to Zabbix collector")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--once", action="store_true")
    g.add_argument("--test", action="store_true")
    g.add_argument("--dump", action="store_true")
    g.add_argument("--provision", action="store_true")
    a = ap.parse_args()

    if a.test:
        return cmd_test()
    if a.dump:
        return cmd_dump()
    if a.provision:
        return cmd_provision()

    setup_logging()
    c = Collector()
    if a.once:
        c.cycle()
        return 0
    try:
        c.run_forever()
    except KeyboardInterrupt:
        log.info("Stopped by user.")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
