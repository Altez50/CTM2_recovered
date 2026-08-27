<#
.SYNOPSIS
  Управление api-контейнером на prod (start/stop/restart/status).

.DESCRIPTION
  SSH login as `root` is DISABLED on prod. This wrapper connects as `kassir`
  (password auth) over the LAN IP by delegating to the paramiko-based engine
  prod_service.py, which runs `sudo docker-compose <action> api`. For
  start/restart it also runs a health check on GET /api/health.

  Windows OpenSSH cannot do single-prompt password auth across ssh calls (no
  ControlMaster, no -pw), so this script only:
    1. Prompts for the kassir password once (Read-Host -AsSecureString).
    2. Locates the paramiko-capable Python (D:\ptn313\python.exe / $CTM_PYTHON).
    3. Runs prod_service.py, forwarding the password via CTM_KASSIR_PASS.

.PARAMETER Action
  start | stop | restart | status  (по умолчанию status)

.PARAMETER ConfigPath
  Принимается для совместимости сигнатуры; не используется.
#>
[CmdletBinding()]
param(
    [ValidateSet('start', 'stop', 'restart', 'status')][string]$Action = 'status',
    [string]$ConfigPath,
    [string]$RepoRoot,
    [string]$LogFile
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'

# When launched from the runner (-LogFile), mirror the console session to a
# file the runner tails live.
if ($LogFile) { Start-Transcript -Path $LogFile -Force | Out-Null }

# --- paths --------------------------------------------------------------------
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $RepoRoot) { $RepoRoot = (Resolve-Path (Split-Path -Parent $ScriptDir)).Path }
$EngineScript = Join-Path $ScriptDir 'prod_service.py'

# --- python with paramiko -----------------------------------------------------
# The portable f:\2026f\ctm3\.python does NOT have paramiko; D:\ptn313\python.exe does.
$Py = $null
foreach ($cand in @($env:CTM_PYTHON, 'D:\ptn313\python.exe')) {
    if ($cand -and (Test-Path -LiteralPath $cand)) { $Py = $cand; break }
}
if (-not $Py) {
    Write-Host "[!] paramiko-capable Python not found (looked for `$CTM_PYTHON or D:\ptn313\python.exe)." -ForegroundColor Red
    Write-Host "    Install paramiko into a Python and set CTM_PYTHON, or fix the path." -ForegroundColor Yellow
    if ($LogFile) { try { Stop-Transcript | Out-Null } catch { } }
    if (-not $LogFile) { Read-Host 'Press Enter to close this window' }
    exit 1
}
if (-not (Test-Path -LiteralPath $EngineScript)) {
    Write-Host "[!] Missing: $EngineScript" -ForegroundColor Red
    if ($LogFile) { try { Stop-Transcript | Out-Null } catch { } }
    if (-not $LogFile) { Read-Host 'Press Enter to close this window' }
    exit 1
}

try {
    Write-Host '=== Prod service control ===' -ForegroundColor Green
    Write-Host "Target : kassir@192.168.0.39 (LAN, password auth — root is disabled)" -ForegroundColor DarkGray
    Write-Host "Action : $Action" -ForegroundColor DarkGray
    Write-Host 'Engine : prod_service.py (paramiko)' -ForegroundColor DarkGray

    # --- prompt for the kassir password once --------------------------------
    Write-Host 'Enter the kassir password (SSH login; sudo is passwordless on prod).' -ForegroundColor DarkGray
    $sec = Read-Host 'kassir password' -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
    try {
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto($ptr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
    $env:CTM_KASSIR_PASS = $plain
    $sec = $null; $plain = $null

    # --- run the paramiko engine (streams remote output live) ----------------
    Write-Host "`n>>> Launching prod_service.py ..." -ForegroundColor Cyan
    & $Py $EngineScript --action $Action
    $rc = $LASTEXITCODE

    if ($rc -ne 0) {
        Write-Host "`n[!] Action '$Action' failed (exit $rc)." -ForegroundColor Red
    }
} catch {
    Write-Host "`n[!] ОШИБКА: $($_.Exception.Message)" -ForegroundColor Red
} finally {
    # Wipe the password from the process environment.
    [Environment]::SetEnvironmentVariable('CTM_KASSIR_PASS', $null, 'Process')
    if ($LogFile) { try { Stop-Transcript | Out-Null } catch { } }
}

if (-not $LogFile) { Read-Host 'Press Enter to close this window' }
