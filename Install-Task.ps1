# Registers INspektor-Zabbix as a Windows scheduled task that starts at boot
# and restarts itself if it stops. Run from an elevated PowerShell in the
# folder that contains INspektor-Zabbix.exe:
#
#   powershell -ExecutionPolicy Bypass -File .\Install-Task.ps1
#   powershell -ExecutionPolicy Bypass -File .\Install-Task.ps1 -Remove

param([switch]$Remove)

$TaskName = "INspektor-Zabbix"
$Here     = Split-Path -Parent $MyInvocation.MyCommand.Path
$Exe      = Join-Path $Here "INspektor-Zabbix.exe"

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Task '$TaskName' removed."
    exit 0
}

if (-not (Test-Path $Exe)) {
    Write-Error "INspektor-Zabbix.exe not found in $Here"
    exit 1
}

$action   = New-ScheduledTaskAction -Execute $Exe -WorkingDirectory $Here
$trigger  = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force | Out-Null

Start-ScheduledTask -TaskName $TaskName
Write-Host "Task '$TaskName' registered and started. Log: $Here\INspektor-Zabbix.log"
