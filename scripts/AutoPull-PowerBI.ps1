# Faz pull automático seguro do repositório Power BI PBIP.
# Uso:
#   powershell.exe -ExecutionPolicy Bypass -File "...\scripts\AutoPull-PowerBI.ps1" -RepoPath "C:\Users\felip\Downloads\Projeto FGV\SpotiScript\powerbi-dashboards"

param(
    [Parameter(Mandatory = $true)]
    [string]$RepoPath,
    [string]$Branch = "main",
    [bool]$SkipWhenPowerBiOpen = $true
)

$ErrorActionPreference = "Stop"
$LogDir = Join-Path $RepoPath "logs"
if (!(Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}
$LogFile = Join-Path $LogDir "auto-pull.log"

function Write-Log($Message) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    $line | Out-File -FilePath $LogFile -Append -Encoding utf8
}

function Resolve-GitExe {
    $cmd = Get-Command git -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) { return $cmd.Source }
    $candidates = @(
        "$env:ProgramFiles\Git\cmd\git.exe",
        "${env:ProgramFiles(x86)}\Git\cmd\git.exe"
    )
    foreach ($path in $candidates) {
        if (Test-Path $path) { return $path }
    }
    throw "Git não encontrado. Instale Git for Windows ou adicione ao PATH."
}

try {
    $GitExe = Resolve-GitExe
    $gitDir = Split-Path $GitExe -Parent
    if ($env:Path -notlike "*$gitDir*") {
        $env:Path = "$gitDir;$env:Path"
    }

    Write-Log "Iniciando auto-pull. Repo=$RepoPath Branch=$Branch Git=$GitExe"
    if (!(Test-Path $RepoPath)) {
        Write-Log "ERRO: RepoPath não existe: $RepoPath"
        exit 1
    }
    Set-Location $RepoPath
    & $GitExe rev-parse --is-inside-work-tree | Out-Null

    if ($SkipWhenPowerBiOpen) {
        $pbi = Get-Process -Name "PBIDesktop" -ErrorAction SilentlyContinue
        if ($pbi) {
            Write-Log "SKIP: Power BI Desktop está aberto. Pull cancelado por segurança."
            exit 0
        }
    }

    $localChanges = & $GitExe status --porcelain
    if ($localChanges) {
        Write-Log "SKIP: existem alterações locais. Pull automático cancelado."
        & $GitExe status --short | Out-File -FilePath $LogFile -Append -Encoding utf8
        exit 0
    }

    & $GitExe fetch origin $Branch | Out-File -FilePath $LogFile -Append -Encoding utf8
    & $GitExe pull --ff-only origin $Branch | Out-File -FilePath $LogFile -Append -Encoding utf8
    Write-Log "Auto-pull finalizado com sucesso."
    exit 0
}
catch {
    Write-Log "ERRO: $($_.Exception.Message)"
    exit 1
}