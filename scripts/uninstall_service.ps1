# Убирает автозапуск. Данные и настройки остаются на месте.
#
# Запуск:  powershell -ExecutionPolicy Bypass -File scripts\uninstall_service.ps1

$ErrorActionPreference = "Stop"
$TaskName = "LocalWorkflowAutomator"

try {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction Stop
} catch {}

try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
    Write-Host "Сервис снят с автозапуска."
} catch {
    Write-Host "Задание $TaskName не найдено — снимать нечего."
}
