"""
Run:  python -m pytest tests -q     (from the package folder)

Covers the parts that do not need real hardware or a real Zabbix:
trapper protocol framing against a mock server, store-and-forward, the
PROFIBUS ghost filter, jitter suppression, netload units, value mapping.
"""

import json
import os
import socket
import struct
import sys
import threading
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from buffer import ValueBuffer
from model import Device, Snapshot, discovery_value, metric_values
from zbx_sender import ZabbixSender, ZabbixSendError, make_value
from adapters import profibus, profinet, ethernetip
import metrics
import model


# ------------------------------------------------------------------ mock trapper

class MockTrapper:
    """Speaks the real wire format. Rejects keys starting with 'bad.'."""

    def __init__(self, compress_reply=False):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        self.received = []
        self.headers = []
        self.compress = compress_reply
        threading.Thread(target=self._loop, daemon=True).start()

    def _recv(self, c, n):
        b = b""
        while len(b) < n:
            b += c.recv(n - len(b))
        return b

    def _loop(self):
        while True:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            head = self._recv(c, 13)
            self.headers.append(head)
            sig, flags, ln, res = head[:4], head[4], *struct.unpack("<II", head[5:])
            body = json.loads(self._recv(c, ln))
            self.received.extend(body["data"])
            bad = sum(1 for d in body["data"] if d["key"].startswith("bad."))
            n = len(body["data"])
            reply = json.dumps({"response": "success",
                                "info": f"processed: {n-bad}; failed: {bad}; total: {n}; seconds spent: 0.0001"}).encode()
            if self.compress:
                z = zlib.compress(reply)
                c.sendall(b"ZBXD" + struct.pack("<BII", 0x03, len(z), len(reply)) + z)
            else:
                c.sendall(b"ZBXD" + struct.pack("<BII", 0x01, len(reply), 0) + reply)
            c.close()

    def close(self):
        self.sock.close()


def test_header_format_and_counts():
    m = MockTrapper()
    s = ZabbixSender("127.0.0.1", m.port)
    r = s.send([make_value("H", "a", 1), make_value("H", "bad.x", 2)])
    assert (r.processed, r.failed, r.total) == (1, 1, 2)
    h = m.headers[0]
    assert h[:4] == b"ZBXD" and h[4] == 0x01
    assert struct.unpack("<I", h[9:13])[0] == 0          # reserved
    m.close()


def test_compressed_reply_is_accepted():
    m = MockTrapper(compress_reply=True)
    r = ZabbixSender("127.0.0.1", m.port).send([make_value("H", "a", 1)])
    assert r.processed == 1
    m.close()


def test_batching():
    m = MockTrapper()
    r = ZabbixSender("127.0.0.1", m.port).send([make_value("H", "a", i) for i in range(600)])
    assert r.total == 600 and len(m.headers) == 3
    m.close()


def test_unreachable_raises():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    with pytest.raises(ZabbixSendError):
        ZabbixSender("127.0.0.1", port, timeout=1).send([make_value("H", "a", 1)])


def test_value_and_clock():
    v = make_value("H", "k", True, clock=1700000000.25)
    assert v["value"] == "1" and v["clock"] == 1700000000 and v["ns"] == 250000000
    assert make_value("H", "k", [{"a": 1}])["value"] == '[{"a":1}]'


# ------------------------------------------------------------------ buffer

def test_buffer_roundtrip_and_cap(tmp_path):
    b = ValueBuffer(str(tmp_path / "b.sqlite"), max_rows=5)
    dropped = b.push([make_value("H", "k", i, clock=1000 + i) for i in range(8)])
    assert dropped == 3 and b.count() == 5
    rows = b.peek(10)
    assert [r[1]["value"] for r in rows] == ["3", "4", "5", "6", "7"]   # oldest dropped
    assert rows[0][1]["clock"] == 1003                                  # timestamp kept
    b.delete_upto(rows[1][0])
    assert b.count() == 3


from fixtures import PN_STATION, EIP_STATION, pb  # noqa: E402


# ------------------------------------------------------------------ PROFIBUS

def test_profibus_gap_scan_ghosts_are_dropped():
    assert not profibus.is_active_slave(pb(40))                # only frames_in
    assert not profibus.is_active_slave(pb(0, out_hist=5))      # master
    assert not profibus.is_active_slave(pb(126, out_hist=5))    # above 125
    assert profibus.is_active_slave(pb(3, out_hist=5))
    assert profibus.is_active_slave(pb(4, out_last=1))
    assert profibus.is_active_slave(pb(5, status=2))
    assert profibus.is_active_slave(pb(6, name="Valve island"))
    devs = [pb(a) for a in range(0, 128)] + [pb(7, out_hist=1)]
    assert len(profibus.select(devs)) == 1


def test_profibus_metrics_and_no_eth_metrics():
    d = profibus.select([pb(12, out_hist=9, name="PB-Drive-12")])[0]
    assert d.id == "12" and d.name == "PB-Drive-12"
    assert d.metrics["errorframes"] == 40 and d.metrics["diag.internal"] == 3
    assert set(d.metrics) == {m.key for m in metrics.PROFIBUS}
    assert not any(k.startswith(("jitter", "netload", "framegaps")) for k in d.metrics)
    assert profibus.select([pb(9, status=1)])[0].name == "PB-Slave-9"


# ------------------------------------------------------------------ PROFINET

def test_pn_jitter_is_tenths_of_percent_and_peak():
    d = profinet.select([PN_STATION])[0]
    assert d.id == "AA:BB:CC:00:00:01" and d.kind == "device"
    assert d.metrics["jitter.max"] == 64.0 and d.metrics["jitter.min"] == -12.0
    assert d.metrics["jitter.peak"] == 64.0
    assert d.metrics["breakdowns"] == 2 and d.metrics["framegaps"] == 12   # history_all
    assert d.metrics["netload.in"] == pytest.approx(10.0)
    assert set(d.metrics) == {m.key for m in metrics.PROFINET}


def test_pn_jitter_suppressed_when_last_minute_had_breakdown():
    st = json.loads(json.dumps(PN_STATION))
    st["lastmin"]["pn_diagnosis"]["counter"]["breakdown"] = 1
    st["lastmin"]["pn_diagnosis"]["jitter"] = {"min": -1000, "max": 1000}
    m = profinet.select([st])[0].metrics
    assert m["jitter.peak"] is None and m["jitter.min"] is None and m["jitter.max"] is None


def test_pn_filters_non_profinet_and_unnamed():
    other = {"id": 9, "general": {"name": "printer", "status": 0, "mac": "x"}}
    unnamed = json.loads(json.dumps(PN_STATION)); unnamed["general"]["name"] = ""
    assert profinet.select([other, unnamed]) == []


# ------------------------------------------------------------------ EtherNet/IP

def test_eip_windows_units_and_name_fallback():
    d = ethernetip.select([EIP_STATION])[0]
    assert d.name == "192.168.1.5"                       # alias empty -> IP
    assert d.metrics["framegaps"] == 956                 # history window, not lastMin
    assert d.metrics["errorframes"] == 1
    assert d.metrics["cycletime"] == pytest.approx(0.049847)
    assert d.metrics["netload.in"] == pytest.approx(18194 / 12_500_000 * 100, abs=0.001)
    # lastMin had a frame gap -> jitter of that minute is not meaningful
    assert d.metrics["jitter.peak"] is None
    assert set(d.metrics) == {m.key for m in metrics.ETHERNETIP}


def test_eip_jitter_when_clean_minute():
    st = json.loads(json.dumps(EIP_STATION))
    st["lastMin"]["etherNetIpDiagnosis"]["counter"]["frameGaps"] = 0
    m = ethernetip.select([st])[0].metrics
    assert m["jitter.peak"] == 1.5 and m["jitter.max"] == 0.7


def test_eip_ignores_non_cip():
    st = json.loads(json.dumps(EIP_STATION)); st["rawStations"] = []
    assert ethernetip.select([st]) == []


# ------------------------------------------------------------------ mapping

def test_none_is_never_sent():
    snap = Snapshot(host="H", type="PN", reachable=True, bus_status=2, unack_alerts=0,
                    devices=[Device(id="AA", name="A", metrics={"breakdowns": 0, "jitter.peak": None})])
    keys = {v["key"] for v in metric_values(snap, "t")}
    assert "device.breakdowns[AA]" in keys and "device.jitter.peak[AA]" not in keys
    assert "inspektor.bus.status" in keys


def test_no_discovery_when_unreachable():
    snap = Snapshot(host="X", type="PN", reachable=False, error="timeout")
    assert discovery_value(snap) is None
    keys = [v["key"] for v in metric_values(snap, "t")]
    assert "inspektor.status" in keys and "inspektor.devices.total" not in keys


def test_discovery_payload():
    snap = Snapshot(host="X", type="PN", reachable=True,
                    devices=[Device(id="AA:BB", name="Drive 12", ip="10.0.0.12", kind="device")])
    v = discovery_value(snap)
    assert json.loads(v["value"]) == [{"{#ID}": "AA:BB", "{#NAME}": "Drive 12",
                                       "{#IP}": "10.0.0.12", "{#KIND}": "device"}]


# ------------------------------------------------------------------ config + template consistency

def test_config_block_format(tmp_path):
    import settings
    p = tmp_path / "config.txt"
    p.write_text("ZABBIX_SERVER=zbx\nIP=1.1.1.1\nNAME=A\nTYPE=profinet\n"
                 "CHECK_INTERVAL=15\nIP=1.1.1.2\nSITE_NAME=B\nTYPE=PB\n"
                 "[inspektor]\nIP=1.1.1.3\nNAME=C\nTYPE=EIP\nIP=1.1.1.4\nNAME=A\nTYPE=PN\n")
    s = settings.load(str(p))
    assert [(i.ip, i.name, i.type) for i in s.inspektors] == [
        ("1.1.1.1", "A", "PN"), ("1.1.1.2", "B", "PB"), ("1.1.1.3", "C", "EIP")]
    assert s.check_interval == 15 and any("used twice" in e for e in s.errors)


def test_template_has_every_published_key():
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
    import make_template
    exp = make_template.build("7.0")["zabbix_export"]
    for t in exp["templates"]:
        typ = {v: k for k, v in model.TEMPLATE_BY_TYPE.items()}[t["template"]]
        proto_keys = {p["key"] for p in t["discovery_rules"][0]["item_prototypes"]}
        assert proto_keys == {f"device.{m.key}[{{#ID}}]" for m in metrics.BY_TYPE[typ]}
        item_keys = {i["key"] for i in t["items"]}
        snap = Snapshot(host="H", type=typ, reachable=True, bus_status=2, unack_alerts=1, error="x")
        assert {v["key"] for v in metric_values(snap, "t")} <= item_keys
