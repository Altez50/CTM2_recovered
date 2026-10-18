<#
.SYNOPSIS
  Перенос базы данных SQLite с localhost на prod.

.DESCRIPTION
  SSH login as `root` is DISABLED on prod. Этот скрипт подключается как
  `kassir` (password auth) через LAN IP, делегируя paramiko-движку push_db.py:
    1. Остановить api-контейнер (docker compose stop api) — освобождает хэндл SQLite.
    2. Бэкап удалённой БД: <remote_db>.bak-<timestamp>.
    3. SFTP локальной БД (+ -wal/-shm при наличии) во временное имя, затем mv на место.
    4. Запустить api-контейнер.
    5. Health check GET /api/health.

  Windows OpenSSH не умеет single-prompt password auth, поэтому скрипт только:
    1. Спрашивает пароль kassir один раз (Read-Host -AsSecureString).
    2. Находит Python с paramiko (D:\ptn313\python.exe / $CTM_PYTHON).
    3. Запускает push_db.py, передавая пароль через CTM_KASSIR_PASS.

  ВНИМАНИЕ: операция перезаписывает prod-базу.
#>
[CmdletBinding()]
param(
    [string]$ConfigPath,   # принимается для совместимости; не используется
    [string]$RepoRoot,
    [string]$LogFile
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'

if ($LogFile) { Start-Transcript -Path $LogFile -Force | Out-Null }

# --- paths --------------------------------------------------------------------
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $RepoRoot) { $RepoRoot = (Resolve-Path (Split-Path -Parent $ScriptDir)).Path }
$EngineScript = Join-Path $ScriptDir 'push_db.py'

# --- python with paramiko -----------------------------------------------------
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
    Write-Host '=== Push DB to prod ===' -ForegroundColor Green
    Write-Host 'Target : kassir@192.168.0.39 (LAN — key auth, root is disabled)' -ForegroundColor DarkGray
    Write-Host 'Engine : push_db.py (paramiko)' -ForegroundColor DarkGray

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

    # --- run the paramiko engine (streams remote output live) ----------------
    Write-Host "`n>>> Launching push_db.py ..." -ForegroundColor Cyan
    & $Py $EngineScript --repo-root $RepoRoot
    $rc = $LASTEXITCODE

    if ($rc -ne 0) {
        Write-Host "`n[!] Push DB failed (exit $rc)." -ForegroundColor Red
    }
} catch {
    Write-Host "`n[!] ОШИБКА ПЕРЕНОСА БД: $($_.Exception.Message)" -ForegroundColor Red
} finally {
    [Environment]::SetEnvironmentVariable('CTM_KASSIR_PASS', $null, 'Process')
    if ($LogFile) { try { Stop-Transcript | Out-Null } catch { } }
}

if (-not $LogFile) { Read-Host 'Press Enter to close this window' }
