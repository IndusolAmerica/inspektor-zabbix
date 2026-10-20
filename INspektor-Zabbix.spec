# PyInstaller spec. Build with:  pyinstaller INspektor-Zabbix.spec
# Adapters are imported statically, so no hiddenimports are needed for them.
# Only the standard library is used at runtime.

a = Analysis(
    ["inspektor_zabbix.py"],
    pathex=[],
    hiddenimports=["adapters.profinet", "adapters.ethernetip", "adapters.profibus"],
    excludes=["yaml", "pytest", "tkinter"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas,
    name="INspektor-Zabbix",
    console=True,
    upx=False,
)
