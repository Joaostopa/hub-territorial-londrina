$ErrorActionPreference = 'Stop'
$projectPath = $PSScriptRoot
$pythonPath = Join-Path $projectPath '.venv\Scripts\python.exe'
if (-not (Test-Path $pythonPath)) { throw 'Execute instalar_windows.bat primeiro.' }
$action = New-ScheduledTaskAction -Execute $pythonPath -Argument 'apify_cli.py weekly --business SALE --max-items 100' -WorkingDirectory $projectPath
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At '08:00'
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'ImoveisHub-Apify-Londrina-Venda' -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Coleta semanal Londrina; usa saldo Apify. Usuario deve estar conectado.' -Force
Write-Host 'Agendado: segunda-feira 08:00, horario local do Windows. Computador ligado e usuario conectado.'
