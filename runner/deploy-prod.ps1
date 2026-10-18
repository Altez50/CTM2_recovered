<#
.SYNOPSIS
  CTM production deploy — prompts for the kassir password, then uploads
  current/ and deploy/ to prod and rebuilds the docker-compose stack
  (api, frontend, reverse-proxy).

.DESCRIPTION
  SSH login as `root` is DISABLED on prod. The deploy connects as `kassir`
  (password auth) over the LAN IP and runs the build/restart remotely with
  sudo (kassir has passwordless sudo for docker on prod).

  Windows OpenSSH cannot do single-prompt password auth across many ssh/scp
  calls (no ControlMaster, no -pw), so this script delegates to the paramiko-
  based engine deploy_prod.py. paramiko connects once with the password and
  streams the remote docker build output live to this console.

  This script only:
    1. Prompts for the kassir password once (Read-Host -AsSecureString).
    2. Locates the paramiko-capable Python (D:\ptn313\python.exe / $CTM_PYTHON).
    3. Runs deploy_prod.py, forwarding the password via CTM_KASSIR_PASS.

  The frontend is built inside Docker on the server (web-client/Dockerfile),
  so no local build is required before deploying.

  Connection target (kept in deploy_prod.py): kassir@192.168.0.39:22 (LAN).
#>
[CmdletBinding()]
param(
    [string]$ConfigPath,   # accepted for call-signature compatibility; unused
    [string]$RepoRoot,
    [string]$LogFile
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'

# When launched from the runner (-LogFile), mirror the whole console session
# to a file the runner tails live.
if ($LogFile) { Start-Transcript -Path $LogFile -Force | Out-Null }

# --- paths --------------------------------------------------------------------
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $RepoRoot) { $RepoRoot = (Resolve-Path (Split-Path -Parent $ScriptDir)).Path }
$DeployScript = Join-Path $ScriptDir 'deploy_prod.py'

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
if (-not (Test-Path -LiteralPath $DeployScript)) {
    Write-Host "[!] Missing: $DeployScript" -ForegroundColor Red
    if ($LogFile) { try { Stop-Transcript | Out-Null } catch { } }
    if (-not $LogFile) { Read-Host 'Press Enter to close this window' }
    exit 1
}

try {
    Write-Host '=== CTM production deploy ===' -ForegroundColor Green
    Write-Host 'Target : kassir@192.168.0.39 (LAN — key auth, root is disabled)' -ForegroundColor DarkGray
    Write-Host 'Engine : deploy_prod.py (paramiko)' -ForegroundColor DarkGray

    # --- auth: dedicated deploy key, else prompt for the password once ------
    $DeployKey = Join-Path $env:USERPROFILE '.ssh\ctm_prod_ed25519'
    if (Test-Path -LiteralPath $DeployKey) {
        Write-Host "Auth   : deploy key $DeployKey (no password needed)" -ForegroundColor DarkGray
    } else {
        Write-Host 'Deploy key not found; enter the kassir password (legacy auth).' -ForegroundColor DarkGray
        $sec = Read-Host 'kassir password' -AsSecureString
        $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
        try {
            $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto($ptr)
        } finally {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
        }
        $env:CTM_KASSIR_PASS = $plain
        $sec = $null; $plain = $null
    }

    # --- run the paramiko deploy (streams remote docker output live) --------
    Write-Host "`n>>> Launching deploy_prod.py ..." -ForegroundColor Cyan
    & $Py $DeployScript --repo-root $RepoRoot
    $rc = $LASTEXITCODE

    if ($rc -eq 0) {
        Write-Host "`n=== Deploy finished ===" -ForegroundColor Green
        Write-Host 'Open the runner link "Open prod frontend" to verify.' -ForegroundColor DarkGray
    } else {
        Write-Host "`n[!] DEPLOY FAILED (exit $rc)." -ForegroundColor Red
    }
} catch {
    Write-Host "`n[!] DEPLOY FAILED: $($_.Exception.Message)" -ForegroundColor Red
} finally {
    # Wipe the password from the process environment (no Remove-Item on files).
    [Environment]::SetEnvironmentVariable('CTM_KASSIR_PASS', $null, 'Process')
    if ($LogFile) { try { Stop-Transcript | Out-Null } catch { } }
}

if (-not $LogFile) { Read-Host 'Press Enter to close this window' }
