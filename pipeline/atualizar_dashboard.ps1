# Abre o dashboard Power BI (PBIP) e mostra status do CSV de demo.
# Uso: .\atualizar_dashboard.ps1  (a partir da pasta pipeline)

$ErrorActionPreference = "Stop"

function Find-PBIDesktopExe {
    $candidates = @(
        "${env:ProgramFiles}\Microsoft Power BI Desktop\bin\PBIDesktop.exe",
        "${env:ProgramFiles(x86)}\Microsoft Power BI Desktop\bin\PBIDesktop.exe",
        "$env:LOCALAPPDATA\Programs\Microsoft Power BI Desktop\bin\PBIDesktop.exe"
    )
    try {
        $pkg = Get-AppxPackage -Name "Microsoft.MicrosoftPowerBIDesktop" -ErrorAction SilentlyContinue |
            Sort-Object Version -Descending | Select-Object -First 1
        if ($pkg -and $pkg.InstallLocation) {
            $storeExe = Join-Path $pkg.InstallLocation "bin\PBIDesktop.exe"
            if (Test-Path $storeExe) { return (Resolve-Path $storeExe).Path }
        }
    } catch { }
    foreach ($path in $candidates) {
        if ($path -and (Test-Path $path)) { return (Resolve-Path $path).Path }
    }
    return $null
}

$PipelineDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot    = Split-Path -Parent $PipelineDir
$Csv         = Join-Path $RepoRoot "data\sample\spotify_dashboard.csv"
$Pbip        = Join-Path $RepoRoot "powerbi\dashboards\spotify-fgv\SpotifyDashboardFGV.pbip"

if (-not (Test-Path $Csv)) {
    Write-Host "[ERRO] CSV demo nao encontrado: $Csv" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $Pbip)) {
    Write-Host "[ERRO] PBIP nao encontrado: $Pbip" -ForegroundColor Red
    exit 1
}

$Pbip = (Resolve-Path $Pbip).Path
$csvInfo = Get-Item $Csv
Write-Host "CSV demo: $Csv ($($csvInfo.Length) bytes, $($csvInfo.LastWriteTime))" -ForegroundColor Cyan
Write-Host "PBIP: $Pbip" -ForegroundColor Cyan
Write-Host "Dica: no Power BI, ajuste o parametro PastaDados para o caminho absoluto de data\sample" -ForegroundColor Yellow

$pbi = Find-PBIDesktopExe
if (-not $pbi) {
    Write-Host "[ERRO] Power BI Desktop nao encontrado." -ForegroundColor Red
    exit 1
}

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $pbi
$psi.Arguments = "`"$Pbip`""
$psi.WorkingDirectory = Split-Path $Pbip -Parent
$psi.UseShellExecute = $true
[void][System.Diagnostics.Process]::Start($psi)
Write-Host "[OK] Power BI aberto." -ForegroundColor Green