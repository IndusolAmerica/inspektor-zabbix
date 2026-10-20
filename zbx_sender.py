"""
Minimal Zabbix sender (trapper protocol), no external dependencies.

Protocol reference: https://www.zabbix.com/documentation/current/en/manual/appendix/protocols/header_datalen

Packet layout (request and response):
    b"ZBXD"            4 bytes  protocol signature
    flags              1 byte   0x01 = Zabbix protocol, 0x02 = zlib compressed,
                                0x04 = large packet (8-byte length fields)
    datalen            4 bytes  little-endian (8 bytes if 0x04)
    reserved           4 bytes  little-endian, uncompressed size when 0x02 is set
                                (8 bytes if 0x04)
    data               JSON

We send uncompressed, standard-size packets. We accept any flag combination on
the response so a server that answers compressed does not break us.
"""

import json
import socket
import ssl
import struct
import time
import zlib
import re

FLAG_PROTOCOL = 0x01
FLAG_COMPRESSED = 0x02
FLAG_LARGE = 0x04

# zabbix_sender itself sends in batches of 250 values. Same here.
DEFAULT_BATCH = 250

_INFO_RE = re.compile(
    r"processed:\s*(\d+);\s*failed:\s*(\d+);\s*total:\s*(\d+)", re.IGNORECASE
)


class ZabbixSendError(Exception):
    """Transport-level failure: the server was not reached or answered garbage.
    Values that hit this error must be buffered and retried."""


class SendResult:
    def __init__(self, processed=0, failed=0, total=0, info=""):
        self.processed = processed
        self.failed = failed
        self.total = total
        self.info = info

    def __iadd__(self, other):
        self.processed += other.processed
        self.failed += other.failed
        self.total += other.total
        self.info = other.info
        return self

    def __repr__(self):
        return f"processed={self.processed} failed={self.failed} total={self.total}"


def _pack(payload: bytes) -> bytes:
    return b"ZBXD" + struct.pack("<BII", FLAG_PROTOCOL, len(payload), 0) + payload


def _recv_exact(sock, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ZabbixSendError(
                f"Connection closed by server after {len(buf)} of {n} bytes"
            )
        buf += chunk
    return buf


def _read_response(sock) -> dict:
    head = _recv_exact(sock, 5)
    if head[:4] != b"ZBXD":
        raise ZabbixSendError(f"Bad response signature: {head[:4]!r}")
    flags = head[4]
    if flags & FLAG_LARGE:
        datalen, reserved = struct.unpack("<QQ", _recv_exact(sock, 16))
    else:
        datalen, reserved = struct.unpack("<II", _recv_exact(sock, 8))
    data = _recv_exact(sock, datalen)
    if flags & FLAG_COMPRESSED:
        data = zlib.decompress(data)
    try:
        return json.loads(data.decode("utf-8"))
    except Exception as exc:
        raise ZabbixSendError(f"Response is not JSON: {data[:200]!r}") from exc


class ZabbixSender:
    def __init__(self, server: str, port: int = 10051, timeout: float = 10.0,
                 tls_ca: str = "", tls_cert: str = "", tls_key: str = "",
                 tls_server_name: str = ""):
        self.server = server
        self.port = int(port)
        self.timeout = timeout
        self._ssl_ctx = None
        self._tls_server_name = tls_server_name or server
        if tls_ca:
            # Certificate-based TLS. PSK is not supported here on purpose:
            # Python's ssl module only gained PSK callbacks in 3.13 and it is
            # not worth the packaging risk until a customer actually needs it.
            ctx = ssl.create_default_context(cafile=tls_ca)
            if tls_cert:
                ctx.load_cert_chain(tls_cert, tls_key or None)
            self._ssl_ctx = ctx

    def _connect(self):
        try:
            sock = socket.create_connection((self.server, self.port), self.timeout)
        except OSError as exc:
            raise ZabbixSendError(
                f"Cannot connect to {self.server}:{self.port}: {exc}"
            ) from exc
        sock.settimeout(self.timeout)
        if self._ssl_ctx:
            sock = self._ssl_ctx.wrap_socket(sock, server_hostname=self._tls_server_name)
        return sock

    def _send_one_batch(self, values: list) -> SendResult:
        now = time.time()
        body = {
            "request": "sender data",
            "data": values,
            "clock": int(now),
            "ns": int((now % 1) * 1e9),
        }
        payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
        sock = self._connect()
        try:
            try:
                sock.sendall(_pack(payload))
                resp = _read_response(sock)
            except (OSError, socket.timeout) as exc:
                raise ZabbixSendError(f"Socket error: {exc}") from exc
        finally:
            try:
                sock.close()
            except OSError:
                pass

        if resp.get("response") != "success":
            raise ZabbixSendError(f"Server answered: {resp}")
        info = resp.get("info", "")
        m = _INFO_RE.search(info)
        if not m:
            return SendResult(total=len(values), info=info)
        p, f, t = (int(x) for x in m.groups())
        return SendResult(p, f, t, info)

    def send(self, values: list, batch: int = DEFAULT_BATCH) -> SendResult:
        """values: list of dicts {host, key, value, clock?, ns?}.

        'failed' in the result means the server received the value but
        rejected it (unknown host or key, wrong type, sender IP not in
        'Allowed hosts'). Those are configuration problems, not network
        problems, and must NOT be retried from the buffer.
        """
        total = SendResult()
        for i in range(0, len(values), batch):
            total += self._send_one_batch(values[i:i + batch])
        return total


def make_value(host: str, key: str, value, clock: float = None) -> dict:
    if clock is None:
        clock = time.time()
    if isinstance(value, bool):
        value = int(value)
    if isinstance(value, (dict, list)):
        value = json.dumps(value, separators=(",", ":"))
    return {
        "host": host,
        "key": key,
        "value": str(value),
        "clock": int(clock),
        "ns": int((clock % 1) * 1e9),
    }
