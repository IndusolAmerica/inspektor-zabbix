INspektor-Zabbix
================

Reads Indu-Sol INspektor NT devices (PROFINET, EtherNet/IP, PROFIBUS) and
sends their diagnostic values to Zabbix. Zabbix decides what is a problem:
all thresholds are template macros you can change per host or per device.

Supported Zabbix versions: 7.0 LTS and newer (the template is in 7.0 format).


1. Import the template
----------------------
Data collection > Templates > Import > zbx_template_inspektor.yaml

This creates three templates:
    INspektor NT PROFINET by Zabbix trapper
    INspektor NT EtherNet-IP by Zabbix trapper
    INspektor NT PROFIBUS by Zabbix trapper


2. Create one host per INspektor
--------------------------------
Either by hand (Data collection > Hosts > Create host) or automatically:

    INspektor-Zabbix.exe --provision      (needs ZABBIX_API_URL and ZABBIX_API_TOKEN)

The host name must be exactly NAME from config.txt. Link the template that
matches the INspektor type. No interface is needed: data is pushed to Zabbix.

If the hosts are monitored by a Zabbix proxy, set ZABBIX_SERVER to the proxy.


3. Configure and test
---------------------
Edit config.txt: ZABBIX_SERVER and one block per INspektor. Then:

    INspektor-Zabbix.exe --test

Every INspektor must show OK. REJECTED means the server was reached but did
not accept the value: wrong host name, template not linked, or this PC is
not allowed to send. NO CONNECTION means port 10051 is blocked or the
address is wrong.


4. Run unattended
-----------------
Elevated PowerShell in this folder:

    powershell -ExecutionPolicy Bypass -File .\Install-Task.ps1

The task starts at boot and restarts if it stops. Output goes to
INspektor-Zabbix.log in this folder.


What is sent
------------
Per INspektor host:
    inspektor.heartbeat        every cycle; missing data raises a HIGH problem
    inspektor.status           1 = INspektor answered, 0 = it did not
    inspektor.bus.status       Unknown / NoData / Active / Warning / Error / Deactivated
    inspektor.alerts.unack     unacknowledged alerts on the INspektor
    inspektor.devices.total
    inspektor.discovery        device list for low-level discovery

Per discovered device. {#ID} is the MAC address on PROFINET and EtherNet/IP,
the station address on PROFIBUS.

    Counters are cumulative since the INspektor measurement started (the
    "History" column on the device). A problem opens when a counter goes up
    inside {$INSPEKTOR.EVENT.WINDOW} (default 1h).
    Gauges are the last minute (the "Last minute" column).

    PROFINET     counters: breakdowns, restarts, framegaps, framegaps.max,
                           overtakes, errorframes, alarms.high, alarms.low
                 gauges:   jitter.peak, jitter.min, jitter.max (%),
                           netload.in, netload.out (% of 100 Mbit/s)
    EtherNet/IP  counters: breakdowns, restarts, framegaps, overtakes, errorframes
                 gauges:   jitter.peak, jitter.min, jitter.max, cycletime (s),
                           netload.in, netload.out
    PROFIBUS     counters: breakdowns, restarts, errorframes, repeats,
                           repeats.max, diag.unanswered, diag.internal,
                           diag.external

PROFIBUS has no jitter, frame gaps or network load, so those items do not
exist on PROFIBUS hosts. Jitter is not sent for a minute in which the station
had breakdowns or frame gaps, because the INspektor then reports +/-100%.

Thresholds are macros on the template. Override them per host, or per device
with a context macro, for example {$INSPEKTOR.JITTER.WARN:"00:20:D5:01:64:92"}.


If Zabbix is down
-----------------
Values are kept in buffer.sqlite with their original time and sent when the
connection is back. Up to BUFFER_MAX_ROWS values are kept.


Troubleshooting
---------------
    INspektor-Zabbix.exe --dump    saves the raw INspektor data to the dumps folder.
                                   Send these files to InduSol America support.
