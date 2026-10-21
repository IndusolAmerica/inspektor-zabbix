# Indu-Sol INspektor NT by Zabbix trapper

## Overview

Templates for monitoring industrial networks through the **Indu-Sol INspektor NT**
diagnostic devices: PROFINET, EtherNet/IP and PROFIBUS.

The INspektor NT measures the health of a fieldbus or industrial Ethernet network
(breakdowns, frame gaps, jitter, network load, error and repeat telegrams) for every
device on it. A small collector reads each INspektor over its REST API and pushes the
raw values to Zabbix through the trapper protocol. Every threshold lives in this
template as a macro, so it can be tuned per host or per device without touching the
collector.

Three templates, one per protocol. Link exactly one to each INspektor host:

| Template | INspektor type |
|---|---|
| `INspektor NT PROFINET by Zabbix trapper` | PROFINET |
| `INspektor NT EtherNet-IP by Zabbix trapper` | EtherNet/IP |
| `INspektor NT PROFIBUS by Zabbix trapper` | PROFIBUS |

Devices are created automatically through low-level discovery. `{#ID}` is the MAC
address on PROFINET and EtherNet/IP, and the station address on PROFIBUS.

## Requirements

Zabbix version: 7.0 and higher.

- Indu-Sol INspektor NT reachable over HTTP (port 80) from the collector PC.
- INspektor-Zabbix collector (Windows): https://github.com/IndusolAmerica/inspektor-zabbix
- Network access from the collector to the Zabbix server or proxy on TCP 10051.

## Tested versions

This template has been tested on:
- Zabbix 7.0.31 (template import, low-level discovery, trapper values and triggers validated end to end with `test/validate_template.py`)
- Indu-Sol INspektor NT PROFINET, EtherNet/IP and PROFIBUS

## Configuration

1. Import this template: *Data collection > Templates > Import*.
2. Create one host per INspektor. The host name must be exactly `NAME` from the
   collector's `config.txt`. No interface is needed: data is pushed.
   Link the template that matches the INspektor type.
   The collector can create the hosts for you: `INspektor-Zabbix.exe --provision`.
3. On the collector PC, set `ZABBIX_SERVER` (server or proxy) and one block per
   INspektor in `config.txt`, then run `INspektor-Zabbix.exe --test`.
   Every host must show `OK`.
4. Register the collector as a scheduled task with `Install-Task.ps1`.

If the hosts are monitored by a proxy, point `ZABBIX_SERVER` to the proxy.

### Counters and gauges

Counters are cumulative since the INspektor measurement started, matching the
*History* column on the INspektor web page. A problem opens when a counter increases
inside `{$INSPEKTOR.EVENT.WINDOW}` and resolves when the window is clean.

Gauges (jitter, network load, cycle time) are the last minute, matching the
*Last minute* column.

Jitter is not sent for a minute in which the device had a breakdown, or when it reads
+/-100 % or beyond: no telegrams arrived, so the value is an artefact and would distort
graphs. Frame gaps alone do not suppress it.
PROFIBUS has no jitter, frame gaps or network load, so those items do not exist on
PROFIBUS hosts.

### Per-device thresholds

Override any threshold for a single device with a context macro on the host, using
the device ID:

```
{$INSPEKTOR.JITTER.WARN:"00:20:D5:01:64:92"} = 70
```

## INspektor NT PROFINET by Zabbix trapper

### Macros used

|Name|Description|Default|
|---|---|---|
|`{$INSPEKTOR.NODATA}`|Time without data before the collector is considered stopped.|`5m`|
|`{$INSPEKTOR.EVENT.WINDOW}`|A counter increase inside this window raises a problem.|`1h`|
|`{$INSPEKTOR.LLD.LIFETIME}`|How long a device that left the network keeps its items.|`7d`|
|`{$INSPEKTOR.JITTER.WARN}`|Jitter peak warning, %. Per device: {$INSPEKTOR.JITTER.WARN:"<MAC>"}.|`50`|
|`{$INSPEKTOR.NETLOAD.WARN}`|Network load warning, % of 100 Mbit/s. Per device: {$INSPEKTOR.NETLOAD.WARN:"<MAC>"}.|`20`|


### Items

|Name|Description|Type|Key|
|---|---|---|---|
|Service heartbeat|Sent every cycle by INspektor-Zabbix. Missing data means the collector stopped.|Zabbix trapper|`inspektor.heartbeat`|
|Service version||Zabbix trapper|`inspektor.service.version`|
|INspektor reachable|1 = the INspektor answered over HTTP, 0 = it did not.|Zabbix trapper|`inspektor.status`|
|Last read error||Zabbix trapper|`inspektor.error`|
|Devices|Devices currently reported by the INspektor after filtering.|Zabbix trapper|`inspektor.devices.total`|
|Bus status|Overall bus status of the current INspektor measurement.|Zabbix trapper|`inspektor.bus.status`|
|Unacknowledged alerts|Alerts not yet acknowledged on the INspektor web interface.|Zabbix trapper|`inspektor.alerts.unack`|


### Triggers

|Name|Description|Expression|Severity|
|---|---|---|---|
|INspektor-Zabbix service is not sending data|No data from the INspektor-Zabbix collector. Check the scheduled task on the collector PC and access to the Zabbix server or proxy on port 10051.|`nodata(/TEMPLATE/inspektor.heartbeat,{$INSPEKTOR.NODATA})=1`|High|
|INspektor is not reachable|The collector could not read the INspektor for 3 consecutive cycles. The collector itself is running.|`max(/TEMPLATE/inspektor.status,#3)=0`|High|
|Bus status is Error||`last(/TEMPLATE/inspektor.bus.status)=4`|High|
|Bus status is Warning||`last(/TEMPLATE/inspektor.bus.status)=3`|Warning|


### LLD rule

|Name|Description|Type|Key|
|---|---|---|---|
|PROFINET devices discovery|Device list pushed by INspektor-Zabbix. Only sent while the INspektor is reachable, so an outage does not mark devices as lost. {#ID} is the MAC address (PROFINET, EtherNet/IP) or the station address (PROFIBUS).|Zabbix trapper|`inspektor.discovery`|


### Item prototypes for PROFINET devices discovery

|Name|Description|Units|Key|
|---|---|---|---|
|{#NAME}: Breakdowns|Cumulative since the INspektor measurement started (History column on the device). Resets when a new measurement starts.||`device.breakdowns[{#ID}]`|
|{#NAME}: Restarts|Cumulative since the INspektor measurement started (History column on the device). Resets when a new measurement starts.||`device.restarts[{#ID}]`|
|{#NAME}: Frame gaps|Cumulative since the INspektor measurement started (History column on the device). Resets when a new measurement starts.||`device.framegaps[{#ID}]`|
|{#NAME}: Max consecutive frame gaps|Longest run of consecutive frame gaps since measurement start. 3 or more usually means a breakdown is close.||`device.framegaps.max[{#ID}]`|
|{#NAME}: Frame overtakes|Cumulative since the INspektor measurement started (History column on the device). Resets when a new measurement starts.||`device.overtakes[{#ID}]`|
|{#NAME}: Error frames|Cumulative since the INspektor measurement started (History column on the device). Resets when a new measurement starts. Physical error frames sent + received (cable, connector, EMC).||`device.errorframes[{#ID}]`|
|{#NAME}: Alarms high|Cumulative since the INspektor measurement started (History column on the device). Resets when a new measurement starts. PROFINET-related issue on the device side.||`device.alarms.high[{#ID}]`|
|{#NAME}: Alarms low|Cumulative since the INspektor measurement started (History column on the device). Resets when a new measurement starts. Issue external to PROFINET (I/O, motor, etc.).||`device.alarms.low[{#ID}]`|
|{#NAME}: Jitter peak|max(\|min\|, \|max\|), the value the INspektor web page shows. Last minute. Not sent for a minute in which the station had a breakdown, or when the value is +/-100% or beyond: no telegrams arrived, so it is an artefact, not a measurement.|%|`device.jitter.peak[{#ID}]`|
|{#NAME}: Jitter min|Last minute. Not sent for a minute in which the station had a breakdown, or when the value is +/-100% or beyond: no telegrams arrived, so it is an artefact, not a measurement.|%|`device.jitter.min[{#ID}]`|
|{#NAME}: Jitter max|Last minute. Not sent for a minute in which the station had a breakdown, or when the value is +/-100% or beyond: no telegrams arrived, so it is an artefact, not a measurement.|%|`device.jitter.max[{#ID}]`|
|{#NAME}: Network load in|Peak of the last minute, as % of a 100 Mbit/s link (12,500,000 bytes/s).|%|`device.netload.in[{#ID}]`|
|{#NAME}: Network load out|Peak of the last minute, as % of a 100 Mbit/s link (12,500,000 bytes/s).|%|`device.netload.out[{#ID}]`|


### Trigger prototypes for PROFINET devices discovery

|Name|Description|Expression|Severity|
|---|---|---|---|
|{#NAME}: Breakdowns increased|The counter went up within {$INSPEKTOR.EVENT.WINDOW}. Resolves when the window is clean.|`last(/TEMPLATE/device.breakdowns[{#ID}])-min(/TEMPLATE/device.breakdowns[{#ID}],{$INSPEKTOR.EVENT.WINDOW})>0`|Average|
|{#NAME}: Restarts increased|The counter went up within {$INSPEKTOR.EVENT.WINDOW}. Resolves when the window is clean.|`last(/TEMPLATE/device.restarts[{#ID}])-min(/TEMPLATE/device.restarts[{#ID}],{$INSPEKTOR.EVENT.WINDOW})>0`|Warning|
|{#NAME}: Frame gaps increased|The counter went up within {$INSPEKTOR.EVENT.WINDOW}. Resolves when the window is clean.|`last(/TEMPLATE/device.framegaps[{#ID}])-min(/TEMPLATE/device.framegaps[{#ID}],{$INSPEKTOR.EVENT.WINDOW})>0`|Warning|
|{#NAME}: Frame overtakes increased|The counter went up within {$INSPEKTOR.EVENT.WINDOW}. Resolves when the window is clean.|`last(/TEMPLATE/device.overtakes[{#ID}])-min(/TEMPLATE/device.overtakes[{#ID}],{$INSPEKTOR.EVENT.WINDOW})>0`|Warning|
|{#NAME}: Error frames increased|The counter went up within {$INSPEKTOR.EVENT.WINDOW}. Resolves when the window is clean.|`last(/TEMPLATE/device.errorframes[{#ID}])-min(/TEMPLATE/device.errorframes[{#ID}],{$INSPEKTOR.EVENT.WINDOW})>0`|Average|
|{#NAME}: Alarms high increased|The counter went up within {$INSPEKTOR.EVENT.WINDOW}. Resolves when the window is clean.|`last(/TEMPLATE/device.alarms.high[{#ID}])-min(/TEMPLATE/device.alarms.high[{#ID}],{$INSPEKTOR.EVENT.WINDOW})>0`|Average|
|{#NAME}: Alarms low increased|The counter went up within {$INSPEKTOR.EVENT.WINDOW}. Resolves when the window is clean.|`last(/TEMPLATE/device.alarms.low[{#ID}])-min(/TEMPLATE/device.alarms.low[{#ID}],{$INSPEKTOR.EVENT.WINDOW})>0`|Info|
|{#NAME}: Jitter peak above {$INSPEKTOR.JITTER.WARN:"{#ID}"}%||`last(/TEMPLATE/device.jitter.peak[{#ID}])>{$INSPEKTOR.JITTER.WARN:"{#ID}"} and nodata(/TEMPLATE/device.jitter.peak[{#ID}],{$INSPEKTOR.NODATA})=0`|Warning|
|{#NAME}: Network load in above {$INSPEKTOR.NETLOAD.WARN:"{#ID}"}%||`last(/TEMPLATE/device.netload.in[{#ID}])>{$INSPEKTOR.NETLOAD.WARN:"{#ID}"}`|Warning|
|{#NAME}: Network load out above {$INSPEKTOR.NETLOAD.WARN:"{#ID}"}%||`last(/TEMPLATE/device.netload.out[{#ID}])>{$INSPEKTOR.NETLOAD.WARN:"{#ID}"}`|Warning|

## INspektor NT EtherNet-IP by Zabbix trapper

### Macros used

|Name|Description|Default|
|---|---|---|
|`{$INSPEKTOR.NODATA}`|Time without data before the collector is considered stopped.|`5m`|
|`{$INSPEKTOR.EVENT.WINDOW}`|A counter increase inside this window raises a problem.|`1h`|
|`{$INSPEKTOR.LLD.LIFETIME}`|How long a device that left the network keeps its items.|`7d`|
|`{$INSPEKTOR.JITTER.WARN}`|Jitter peak warning, %. Per device: {$INSPEKTOR.JITTER.WARN:"<MAC>"}.|`50`|
|`{$INSPEKTOR.NETLOAD.WARN}`|Network load warning, % of 100 Mbit/s. Per device: {$INSPEKTOR.NETLOAD.WARN:"<MAC>"}.|`20`|


### Items

|Name|Description|Type|Key|
|---|---|---|---|
|Service heartbeat|Sent every cycle by INspektor-Zabbix. Missing data means the collector stopped.|Zabbix trapper|`inspektor.heartbeat`|
|Service version||Zabbix trapper|`inspektor.service.version`|
|INspektor reachable|1 = the INspektor answered over HTTP, 0 = it did not.|Zabbix trapper|`inspektor.status`|
|Last read error||Zabbix trapper|`inspektor.error`|
|Devices|Devices currently reported by the INspektor after filtering.|Zabbix trapper|`inspektor.devices.total`|
|Bus status|Overall bus status of the current INspektor measurement.|Zabbix trapper|`inspektor.bus.status`|
|Unacknowledged alerts|Alerts not yet acknowledged on the INspektor web interface.|Zabbix trapper|`inspektor.alerts.unack`|


### Triggers

|Name|Description|Expression|Severity|
|---|---|---|---|
|INspektor-Zabbix service is not sending data|No data from the INspektor-Zabbix collector. Check the scheduled task on the collector PC and access to the Zabbix server or proxy on port 10051.|`nodata(/TEMPLATE/inspektor.heartbeat,{$INSPEKTOR.NODATA})=1`|High|
|INspektor is not reachable|The collector could not read the INspektor for 3 consecutive cycles. The collector itself is running.|`max(/TEMPLATE/inspektor.status,#3)=0`|High|
|Bus status is Error||`last(/TEMPLATE/inspektor.bus.status)=4`|High|
|Bus status is Warning||`last(/TEMPLATE/inspektor.bus.status)=3`|Warning|


### LLD rule

|Name|Description|Type|Key|
|---|---|---|---|
|EtherNet/IP devices discovery|Device list pushed by INspektor-Zabbix. Only sent while the INspektor is reachable, so an outage does not mark devices as lost. {#ID} is the MAC address (PROFINET, EtherNet/IP) or the station address (PROFIBUS).|Zabbix trapper|`inspektor.discovery`|


### Item prototypes for EtherNet/IP devices discovery

|Name|Description|Units|Key|
|---|---|---|---|
|{#NAME}: Breakdowns|Cumulative since the INspektor measurement started (History column on the device). Resets when a new measurement starts.||`device.breakdowns[{#ID}]`|
|{#NAME}: Restarts|Cumulative since the INspektor measurement started (History column on the device). Resets when a new measurement starts.||`device.restarts[{#ID}]`|
|{#NAME}: Frame gaps|Cumulative since the INspektor measurement started (History column on the device). Resets when a new measurement starts.||`device.framegaps[{#ID}]`|
|{#NAME}: Frame overtakes|Cumulative since the INspektor measurement started (History column on the device). Resets when a new measurement starts.||`device.overtakes[{#ID}]`|
|{#NAME}: Error frames|Cumulative since the INspektor measurement started (History column on the device). Resets when a new measurement starts. Physical error frames sent + received (cable, connector, EMC).||`device.errorframes[{#ID}]`|
|{#NAME}: Jitter peak|max(\|min\|, \|max\|), the value the INspektor web page shows. Last minute. Not sent for a minute in which the station had a breakdown, or when the value is +/-100% or beyond: no telegrams arrived, so it is an artefact, not a measurement.|%|`device.jitter.peak[{#ID}]`|
|{#NAME}: Jitter min|Last minute. Not sent for a minute in which the station had a breakdown, or when the value is +/-100% or beyond: no telegrams arrived, so it is an artefact, not a measurement.|%|`device.jitter.min[{#ID}]`|
|{#NAME}: Jitter max|Last minute. Not sent for a minute in which the station had a breakdown, or when the value is +/-100% or beyond: no telegrams arrived, so it is an artefact, not a measurement.|%|`device.jitter.max[{#ID}]`|
|{#NAME}: Cycle time|Average cycle time (RPI) of the last minute.|s|`device.cycletime[{#ID}]`|
|{#NAME}: Network load in|Peak of the last minute, as % of a 100 Mbit/s link (12,500,000 bytes/s).|%|`device.netload.in[{#ID}]`|
|{#NAME}: Network load out|Peak of the last minute, as % of a 100 Mbit/s link (12,500,000 bytes/s).|%|`device.netload.out[{#ID}]`|


### Trigger prototypes for EtherNet/IP devices discovery

|Name|Description|Expression|Severity|
|---|---|---|---|
|{#NAME}: Breakdowns increased|The counter went up within {$INSPEKTOR.EVENT.WINDOW}. Resolves when the window is clean.|`last(/TEMPLATE/device.breakdowns[{#ID}])-min(/TEMPLATE/device.breakdowns[{#ID}],{$INSPEKTOR.EVENT.WINDOW})>0`|Average|
|{#NAME}: Restarts increased|The counter went up within {$INSPEKTOR.EVENT.WINDOW}. Resolves when the window is clean.|`last(/TEMPLATE/device.restarts[{#ID}])-min(/TEMPLATE/device.restarts[{#ID}],{$INSPEKTOR.EVENT.WINDOW})>0`|Warning|
|{#NAME}: Frame gaps increased|The counter went up within {$INSPEKTOR.EVENT.WINDOW}. Resolves when the window is clean.|`last(/TEMPLATE/device.framegaps[{#ID}])-min(/TEMPLATE/device.framegaps[{#ID}],{$INSPEKTOR.EVENT.WINDOW})>0`|Warning|
|{#NAME}: Frame overtakes increased|The counter went up within {$INSPEKTOR.EVENT.WINDOW}. Resolves when the window is clean.|`last(/TEMPLATE/device.overtakes[{#ID}])-min(/TEMPLATE/device.overtakes[{#ID}],{$INSPEKTOR.EVENT.WINDOW})>0`|Warning|
|{#NAME}: Error frames increased|The counter went up within {$INSPEKTOR.EVENT.WINDOW}. Resolves when the window is clean.|`last(/TEMPLATE/device.errorframes[{#ID}])-min(/TEMPLATE/device.errorframes[{#ID}],{$INSPEKTOR.EVENT.WINDOW})>0`|Average|
|{#NAME}: Jitter peak above {$INSPEKTOR.JITTER.WARN:"{#ID}"}%||`last(/TEMPLATE/device.jitter.peak[{#ID}])>{$INSPEKTOR.JITTER.WARN:"{#ID}"} and nodata(/TEMPLATE/device.jitter.peak[{#ID}],{$INSPEKTOR.NODATA})=0`|Warning|
|{#NAME}: Network load in above {$INSPEKTOR.NETLOAD.WARN:"{#ID}"}%||`last(/TEMPLATE/device.netload.in[{#ID}])>{$INSPEKTOR.NETLOAD.WARN:"{#ID}"}`|Warning|
|{#NAME}: Network load out above {$INSPEKTOR.NETLOAD.WARN:"{#ID}"}%||`last(/TEMPLATE/device.netload.out[{#ID}])>{$INSPEKTOR.NETLOAD.WARN:"{#ID}"}`|Warning|

## INspektor NT PROFIBUS by Zabbix trapper

### Macros used

|Name|Description|Default|
|---|---|---|
|`{$INSPEKTOR.NODATA}`|Time without data before the collector is considered stopped.|`5m`|
|`{$INSPEKTOR.EVENT.WINDOW}`|A counter increase inside this window raises a problem.|`1h`|
|`{$INSPEKTOR.LLD.LIFETIME}`|How long a device that left the network keeps its items.|`7d`|


### Items

|Name|Description|Type|Key|
|---|---|---|---|
|Service heartbeat|Sent every cycle by INspektor-Zabbix. Missing data means the collector stopped.|Zabbix trapper|`inspektor.heartbeat`|
|Service version||Zabbix trapper|`inspektor.service.version`|
|INspektor reachable|1 = the INspektor answered over HTTP, 0 = it did not.|Zabbix trapper|`inspektor.status`|
|Last read error||Zabbix trapper|`inspektor.error`|
|Devices|Devices currently reported by the INspektor after filtering.|Zabbix trapper|`inspektor.devices.total`|
|Bus status|Overall bus status of the current INspektor measurement.|Zabbix trapper|`inspektor.bus.status`|
|Unacknowledged alerts|Alerts not yet acknowledged on the INspektor web interface.|Zabbix trapper|`inspektor.alerts.unack`|


### Triggers

|Name|Description|Expression|Severity|
|---|---|---|---|
|INspektor-Zabbix service is not sending data|No data from the INspektor-Zabbix collector. Check the scheduled task on the collector PC and access to the Zabbix server or proxy on port 10051.|`nodata(/TEMPLATE/inspektor.heartbeat,{$INSPEKTOR.NODATA})=1`|High|
|INspektor is not reachable|The collector could not read the INspektor for 3 consecutive cycles. The collector itself is running.|`max(/TEMPLATE/inspektor.status,#3)=0`|High|
|Bus status is Error||`last(/TEMPLATE/inspektor.bus.status)=4`|High|
|Bus status is Warning||`last(/TEMPLATE/inspektor.bus.status)=3`|Warning|


### LLD rule

|Name|Description|Type|Key|
|---|---|---|---|
|PROFIBUS devices discovery|Device list pushed by INspektor-Zabbix. Only sent while the INspektor is reachable, so an outage does not mark devices as lost. {#ID} is the MAC address (PROFINET, EtherNet/IP) or the station address (PROFIBUS).|Zabbix trapper|`inspektor.discovery`|


### Item prototypes for PROFIBUS devices discovery

|Name|Description|Units|Key|
|---|---|---|---|
|{#NAME}: Breakdowns|Cumulative since the INspektor measurement started (History column on the device). Resets when a new measurement starts.||`device.breakdowns[{#ID}]`|
|{#NAME}: Restarts|Cumulative since the INspektor measurement started (History column on the device). Resets when a new measurement starts.||`device.restarts[{#ID}]`|
|{#NAME}: Error telegrams|Cumulative since the INspektor measurement started (History column on the device). Resets when a new measurement starts. Physical issue on the segment: cable, connector, termination, EMC.||`device.errorframes[{#ID}]`|
|{#NAME}: Repeat telegrams|Cumulative since the INspektor measurement started (History column on the device). Resets when a new measurement starts.||`device.repeats[{#ID}]`|
|{#NAME}: Max repeats per cycle|Highest repeat count in one cycle since measurement start.||`device.repeats.max[{#ID}]`|
|{#NAME}: Unanswered slave diagnosis|Cumulative since the INspektor measurement started (History column on the device). Resets when a new measurement starts.||`device.diag.unanswered[{#ID}]`|
|{#NAME}: Diagnosis internal|Cumulative since the INspektor measurement started (History column on the device). Resets when a new measurement starts. PROFIBUS-related issue on the device side (card, GSD).||`device.diag.internal[{#ID}]`|
|{#NAME}: Diagnosis external|Cumulative since the INspektor measurement started (History column on the device). Resets when a new measurement starts. Issue external to PROFIBUS (I/O short circuit, motor fault).||`device.diag.external[{#ID}]`|


### Trigger prototypes for PROFIBUS devices discovery

|Name|Description|Expression|Severity|
|---|---|---|---|
|{#NAME}: Breakdowns increased|The counter went up within {$INSPEKTOR.EVENT.WINDOW}. Resolves when the window is clean.|`last(/TEMPLATE/device.breakdowns[{#ID}])-min(/TEMPLATE/device.breakdowns[{#ID}],{$INSPEKTOR.EVENT.WINDOW})>0`|Average|
|{#NAME}: Restarts increased|The counter went up within {$INSPEKTOR.EVENT.WINDOW}. Resolves when the window is clean.|`last(/TEMPLATE/device.restarts[{#ID}])-min(/TEMPLATE/device.restarts[{#ID}],{$INSPEKTOR.EVENT.WINDOW})>0`|Warning|
|{#NAME}: Error telegrams increased|The counter went up within {$INSPEKTOR.EVENT.WINDOW}. Resolves when the window is clean.|`last(/TEMPLATE/device.errorframes[{#ID}])-min(/TEMPLATE/device.errorframes[{#ID}],{$INSPEKTOR.EVENT.WINDOW})>0`|Average|
|{#NAME}: Repeat telegrams increased|The counter went up within {$INSPEKTOR.EVENT.WINDOW}. Resolves when the window is clean.|`last(/TEMPLATE/device.repeats[{#ID}])-min(/TEMPLATE/device.repeats[{#ID}],{$INSPEKTOR.EVENT.WINDOW})>0`|Warning|
|{#NAME}: Unanswered slave diagnosis increased|The counter went up within {$INSPEKTOR.EVENT.WINDOW}. Resolves when the window is clean.|`last(/TEMPLATE/device.diag.unanswered[{#ID}])-min(/TEMPLATE/device.diag.unanswered[{#ID}],{$INSPEKTOR.EVENT.WINDOW})>0`|Warning|
|{#NAME}: Diagnosis internal increased|The counter went up within {$INSPEKTOR.EVENT.WINDOW}. Resolves when the window is clean.|`last(/TEMPLATE/device.diag.internal[{#ID}])-min(/TEMPLATE/device.diag.internal[{#ID}],{$INSPEKTOR.EVENT.WINDOW})>0`|Average|
|{#NAME}: Diagnosis external increased|The counter went up within {$INSPEKTOR.EVENT.WINDOW}. Resolves when the window is clean.|`last(/TEMPLATE/device.diag.external[{#ID}])-min(/TEMPLATE/device.diag.external[{#ID}],{$INSPEKTOR.EVENT.WINDOW})>0`|Info|

## Feedback

Author: Luis Aguirre, InduSol America

Issues and questions: https://github.com/IndusolAmerica/inspektor-zabbix/issues
