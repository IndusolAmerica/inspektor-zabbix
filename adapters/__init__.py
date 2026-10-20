"""
Protocol adapters. Imported statically on purpose: no importlib, so
PyInstaller finds them without hiddenimports.

Each adapter exposes:
    read(cfg: InspektorCfg, timeout: float) -> model.Snapshot
    dump(cfg: InspektorCfg, timeout: float) -> dict   raw JSON, for --dump
"""

from adapters import profinet, ethernetip, profibus

ADAPTERS = {
    "PN": profinet,
    "EIP": ethernetip,
    "PB": profibus,
}
