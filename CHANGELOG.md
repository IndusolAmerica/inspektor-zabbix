# Changelog

## 0.1.1 (2026-10-21)

Validated against live EtherNet/IP and PROFIBUS networks.

- **PROFIBUS:** the DP master no longer shows up as a slave.
- **Jitter (PROFINET, EtherNet/IP):** now suppressed only for a minute with a
  breakdown, or when the value reads +/-100 % or beyond. Frame gaps alone no longer
  hide it: a station with frame gaps still reports a valid jitter, as the INspektor
  web page shows.
- **Frame gaps:** trigger severity is now *Warning* on both PROFINET and
  EtherNet/IP (EtherNet/IP was *Average*).
- Template vendor version 7.0-2. Re-import it over 7.0-1; existing hosts keep
  their data.

## 0.1.0 (2026-10-20)

First release. PROFINET validated on a live network; template validated on a clean
Zabbix 7.0.31.
