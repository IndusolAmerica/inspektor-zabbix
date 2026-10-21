"""
Single source of truth for what is published per protocol.

The adapters fill Device.metrics with these keys, the template generator
builds item prototypes and triggers from the same list. Adding a metric is
one line here plus one line in the adapter.

Fields:
    key       suffix of the Zabbix key: device.<key>[{#ID}]
    name      item name shown in Zabbix (prefixed with "{#NAME}: ")
    vtype     UNSIGNED | FLOAT
    units     Zabbix units
    kind      counter  cumulative since measurement start (INspektor "History" column)
              gauge    value of the last minute (INspektor "Last minute" column)
    trigger   None, or (severity, rule, macro)
              rule "increase"  counter went up inside {$INSPEKTOR.EVENT.WINDOW}
              rule "above"     last value above the macro threshold
    desc      item description
"""

from collections import namedtuple

M = namedtuple("M", "key name vtype units kind trigger desc")

_CNT = "Cumulative since the INspektor measurement started (History column on the device). Resets when a new measurement starts."
_JIT = ("Last minute. Not sent for a minute in which the station had a breakdown, or when the "
        "value is +/-100% or beyond: no telegrams arrived, so it is an artefact, not a measurement.")
_NL = "Peak of the last minute, as % of a 100 Mbit/s link (12,500,000 bytes/s)."

PROFINET = [
    M("breakdowns",   "Breakdowns",        "UNSIGNED", "", "counter", ("AVERAGE", "increase", None), _CNT),
    M("restarts",     "Restarts",          "UNSIGNED", "", "counter", ("WARNING", "increase", None), _CNT),
    M("framegaps",    "Frame gaps",        "UNSIGNED", "", "counter", ("WARNING", "increase", None), _CNT),
    M("framegaps.max", "Max consecutive frame gaps", "UNSIGNED", "", "counter", None,
      "Longest run of consecutive frame gaps since measurement start. 3 or more usually means a breakdown is close."),
    M("overtakes",    "Frame overtakes",   "UNSIGNED", "", "counter", ("WARNING", "increase", None), _CNT),
    M("errorframes",  "Error frames",      "UNSIGNED", "", "counter", ("AVERAGE", "increase", None),
      _CNT + " Physical error frames sent + received (cable, connector, EMC)."),
    M("alarms.high",  "Alarms high",       "UNSIGNED", "", "counter", ("AVERAGE", "increase", None),
      _CNT + " PROFINET-related issue on the device side."),
    M("alarms.low",   "Alarms low",        "UNSIGNED", "", "counter", ("INFO", "increase", None),
      _CNT + " Issue external to PROFINET (I/O, motor, etc.)."),
    M("jitter.peak",  "Jitter peak",       "FLOAT", "%", "gauge",
      ("WARNING", "above", "{$INSPEKTOR.JITTER.WARN}"), "max(|min|, |max|), the value the INspektor web page shows. " + _JIT),
    M("jitter.min",   "Jitter min",        "FLOAT", "%", "gauge", None, _JIT),
    M("jitter.max",   "Jitter max",        "FLOAT", "%", "gauge", None, _JIT),
    M("netload.in",   "Network load in",   "FLOAT", "%", "gauge",
      ("WARNING", "above", "{$INSPEKTOR.NETLOAD.WARN}"), _NL),
    M("netload.out",  "Network load out",  "FLOAT", "%", "gauge",
      ("WARNING", "above", "{$INSPEKTOR.NETLOAD.WARN}"), _NL),
]

ETHERNETIP = [
    M("breakdowns",   "Breakdowns",        "UNSIGNED", "", "counter", ("AVERAGE", "increase", None), _CNT),
    M("restarts",     "Restarts",          "UNSIGNED", "", "counter", ("WARNING", "increase", None), _CNT),
    M("framegaps",    "Frame gaps",        "UNSIGNED", "", "counter", ("WARNING", "increase", None), _CNT),
    M("overtakes",    "Frame overtakes",   "UNSIGNED", "", "counter", ("WARNING", "increase", None), _CNT),
    M("errorframes",  "Error frames",      "UNSIGNED", "", "counter", ("AVERAGE", "increase", None),
      _CNT + " Physical error frames sent + received (cable, connector, EMC)."),
    M("jitter.peak",  "Jitter peak",       "FLOAT", "%", "gauge",
      ("WARNING", "above", "{$INSPEKTOR.JITTER.WARN}"), "max(|min|, |max|), the value the INspektor web page shows. " + _JIT),
    M("jitter.min",   "Jitter min",        "FLOAT", "%", "gauge", None, _JIT),
    M("jitter.max",   "Jitter max",        "FLOAT", "%", "gauge", None, _JIT),
    M("cycletime",    "Cycle time",        "FLOAT", "s", "gauge", None, "Average cycle time (RPI) of the last minute."),
    M("netload.in",   "Network load in",   "FLOAT", "%", "gauge",
      ("WARNING", "above", "{$INSPEKTOR.NETLOAD.WARN}"), _NL),
    M("netload.out",  "Network load out",  "FLOAT", "%", "gauge",
      ("WARNING", "above", "{$INSPEKTOR.NETLOAD.WARN}"), _NL),
]

PROFIBUS = [
    M("breakdowns",   "Breakdowns",              "UNSIGNED", "", "counter", ("AVERAGE", "increase", None), _CNT),
    M("restarts",     "Restarts",                "UNSIGNED", "", "counter", ("WARNING", "increase", None), _CNT),
    M("errorframes",  "Error telegrams",         "UNSIGNED", "", "counter", ("AVERAGE", "increase", None),
      _CNT + " Physical issue on the segment: cable, connector, termination, EMC."),
    M("repeats",      "Repeat telegrams",        "UNSIGNED", "", "counter", ("WARNING", "increase", None), _CNT),
    M("repeats.max",  "Max repeats per cycle",   "UNSIGNED", "", "counter", None, "Highest repeat count in one cycle since measurement start."),
    M("diag.unanswered", "Unanswered slave diagnosis", "UNSIGNED", "", "counter", ("WARNING", "increase", None), _CNT),
    M("diag.internal","Diagnosis internal",      "UNSIGNED", "", "counter", ("AVERAGE", "increase", None),
      _CNT + " PROFIBUS-related issue on the device side (card, GSD)."),
    M("diag.external","Diagnosis external",      "UNSIGNED", "", "counter", ("INFO", "increase", None),
      _CNT + " Issue external to PROFIBUS (I/O short circuit, motor fault)."),
]

BY_TYPE = {"PN": PROFINET, "EIP": ETHERNETIP, "PB": PROFIBUS}
PROTOCOL_NAME = {"PN": "PROFINET", "EIP": "EtherNet/IP", "PB": "PROFIBUS"}

# INspektor bus status codes (chronic meta.status), shared by all three.
BUS_STATUS = {0: "Unknown", 1: "NoData", 2: "Active", 3: "Warning", 4: "Error", 5: "Deactivated"}
