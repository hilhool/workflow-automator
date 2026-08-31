# Ставит автозапуск через «Планировщик заданий» Windows: сервис поднимется
# при входе в систему и переживёт перезагрузку. Снять — scripts\uninstall_service.ps1
#
# Запуск:  powershell -ExecutionPolicy Bypass -File scripts\install_service.ps1

$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $PSScriptRoot
$TaskName = "LocalWorkflowAutomator"
# pythonw не открывает окно консоли; логи всё равно пишутся в data\logs\workflow.log
$Python = Join-Path $ProjectDir ".venv\Scripts\pythonw.exe"

if (-not (Test-Path $Python)) {
    Write-Error "Не найден $Python. Сначала создай окружение: python -m venv .venv"
}

New-Item -ItemType Directory -Force -Path (Join-Path $ProjectDir "data\logs") | Out-Null

$action = New-ScheduledTaskAction -Execute $Python `
    -Argument (Join-Path $ProjectDir "main.py") `
    -WorkingDirectory $ProjectDir
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -RestartCount 999 `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0)

try { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop } catch {}

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "Локальный автоматизатор рутины" | Out-Null
Start-ScheduledTask -TaskName $TaskName

Write-Host "Сервис установлен: $TaskName"
Write-Host "Панель: http://127.0.0.1:8765"
Write-Host "Логи:   $ProjectDir\data\logs\workflow.log"
