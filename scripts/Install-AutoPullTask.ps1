# Instala tarefa agendada de auto-pull. Execute uma vez por máquina.
param(
    [string]$RepoPath = "",
    [string]$TaskName = "PowerBI GitHub AutoPull",
    [int]$IntervalMinutes = 60
)

if (-not $RepoPath) {
    $RepoPath = Split-Path -Parent $PSScriptRoot
}

$ScriptPath = Join-Path $RepoPath "scripts\AutoPull-PowerBI.ps1"
if (!(Test-Path $ScriptPath)) {
    Write-Host "Script não encontrado: $ScriptPath" -ForegroundColor Red
    exit 1
}

# Sem -SkipWhenPowerBiOpen (default=true) para evitar truncamento no Agendador de Tarefas.
$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$ScriptPath`" -RepoPath `"$RepoPath`" -Branch main"

$StartAt = (Get-Date).AddHours(1)
$Trigger = New-ScheduledTaskTrigger `
    -Once `
    -At $StartAt `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable

$Existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($Existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Faz auto-pull seguro do repositório Power BI PBIP no GitHub" | Out-Null

Write-Host "Tarefa criada: $TaskName" -ForegroundColor Green
if ($IntervalMinutes -ge 60 -and ($IntervalMinutes % 60) -eq 0) {
    $intervalLabel = "a cada $($IntervalMinutes / 60) hora(s)"
} else {
    $intervalLabel = "a cada $IntervalMinutes minuto(s)"
}
Write-Host "Primeira execução: $($StartAt.ToString('dd/MM/yyyy HH:mm'))" -ForegroundColor Green
Write-Host "Intervalo: $intervalLabel" -ForegroundColor Green
Write-Host "Repositório: $RepoPath" -ForegroundColor Green