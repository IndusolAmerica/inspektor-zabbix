"""
Reads config.txt from the folder of the .exe (or of this script when run
from source). The file is re-read whenever it changes on disk, so the
customer can edit it without restarting the scheduled task.

Lesson from previous packages: never cache settings in module globals at
import time. Always call settings.load() and read the returned object.
"""

import os
import sys
from dataclasses import dataclass, field

VALID_TYPES = ("PN", "EIP", "PB")


def base_dir() -> str:
    """Folder the customer sees: next to the .exe, not sys._MEIPASS."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(name: str) -> str:
    """Files bundled inside the .exe (read-only)."""
    root = getattr(sys, "_MEIPASS", base_dir())
    return os.path.join(root, name)


@dataclass
class InspektorCfg:
    index: int
    ip: str
    name: str
    type: str
    subnet: str = ""


@dataclass
class Settings:
    zabbix_server: str = ""
    zabbix_port: int = 10051
    zabbix_api_url: str = ""
    zabbix_api_token: str = ""
    zabbix_host_group: str = "Industrial networks/INspektor"
    tls_ca_file: str = ""
    tls_cert_file: str = ""
    tls_key_file: str = ""
    check_interval: int = 30
    http_timeout: float = 5.0
    buffer_max_rows: int = 500_000
    vendor: str = "InduSol America"
    inspektors: list = field(default_factory=list)
    errors: list = field(default_factory=list)


_BLOCK_KEYS = {"IP", "NAME", "SITE_NAME", "TYPE", "SUBNET"}
_TYPE_ALIASES = {"PROFINET": "PN", "PROFIBUS": "PB", "ETHERNETIP": "EIP",
                 "ETHERNET/IP": "EIP", "ENIP": "EIP", "CIP": "EIP"}


def _parse(path: str):
    """Same block format as the other INspektor packages:
    a new INspektor block starts at every IP= line (or at an [inspektor]
    header). IP / NAME / TYPE / SUBNET belong to the current block, every
    other key is global and may appear anywhere."""
    glob, blocks, cur = {}, [], None
    with open(path, "r", encoding="utf-8-sig") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower() == "[inspektor]":
                if cur and cur.get("IP"):
                    blocks.append(cur)
                cur = {}
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip().upper(), v.strip()
            if k == "IP":
                if cur and cur.get("IP"):
                    blocks.append(cur)
                cur = {"IP": v}
            elif k in _BLOCK_KEYS and cur is not None:
                cur["NAME" if k == "SITE_NAME" else k] = v
            else:
                glob[k] = v
    if cur and cur.get("IP"):
        blocks.append(cur)
    return glob, blocks


def _int(d, k, default, errors):
    try:
        return int(d.get(k, default) or default)
    except ValueError:
        errors.append(f"{k} must be a whole number, got '{d.get(k)}'. Using {default}.")
        return default


def _float(d, k, default, errors):
    try:
        return float(d.get(k, default) or default)
    except ValueError:
        errors.append(f"{k} must be a number, got '{d.get(k)}'. Using {default}.")
        return default


def load(path: str = None) -> Settings:
    path = path or os.path.join(base_dir(), "config.txt")
    d, blocks = _parse(path)
    s = Settings()
    e = s.errors

    s.zabbix_server = d.get("ZABBIX_SERVER", "")
    s.zabbix_port = _int(d, "ZABBIX_PORT", 10051, e)
    s.zabbix_api_url = d.get("ZABBIX_API_URL", "")
    s.zabbix_api_token = d.get("ZABBIX_API_TOKEN", "")
    s.zabbix_host_group = d.get("ZABBIX_HOST_GROUP", "") or s.zabbix_host_group
    s.tls_ca_file = d.get("ZABBIX_TLS_CA_FILE", "")
    s.tls_cert_file = d.get("ZABBIX_TLS_CERT_FILE", "")
    s.tls_key_file = d.get("ZABBIX_TLS_KEY_FILE", "")
    s.check_interval = max(10, _int(d, "CHECK_INTERVAL", 30, e))
    s.http_timeout = _float(d, "HTTP_TIMEOUT", 5.0, e)
    s.buffer_max_rows = _int(d, "BUFFER_MAX_ROWS", 500_000, e)
    s.vendor = d.get("VENDOR", "") or s.vendor

    if not s.zabbix_server:
        e.append("ZABBIX_SERVER is empty.")

    names = set()
    for n, b in enumerate(blocks, 1):
        ip = b["IP"]
        typ = (b.get("TYPE") or "").upper()
        typ = _TYPE_ALIASES.get(typ, typ)
        name = b.get("NAME", "")
        if typ not in VALID_TYPES:
            e.append(f"IP={ip}: TYPE must be PN, EIP or PB, got '{b.get('TYPE', '')}'. Skipped.")
            continue
        if not name:
            e.append(f"IP={ip}: NAME is empty. It must match the host name in Zabbix. Skipped.")
            continue
        if name in names:
            e.append(f"IP={ip}: NAME '{name}' is used twice. Skipped.")
            continue
        names.add(name)
        s.inspektors.append(InspektorCfg(n, ip, name, typ, b.get("SUBNET", "")))

    if not s.inspektors:
        e.append("No INspektor configured.")
    return s


class ReloadingSettings:
    """Re-reads config.txt when its modification time changes."""

    def __init__(self, path: str = None):
        self.path = path or os.path.join(base_dir(), "config.txt")
        self._mtime = None
        self.current = None

    def get(self):
        mtime = os.path.getmtime(self.path)
        changed = mtime != self._mtime
        if changed:
            self.current = load(self.path)
            self._mtime = mtime
        return self.current, changed
