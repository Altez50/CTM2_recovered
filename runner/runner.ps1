<#
.SYNOPSIS
  CTM Runner (PowerShell) — запасной консольный вариант без tkinter.
.DESCRIPTION
  Интерактивное меню для управления сервером (uvicorn), фронтендом (Vite),
  ребилдом и стаб-деплоем. Каждый процесс пишет свой лог во временные файлы,
  которые можно посмотреть прямо из меню. Использует portable Python из
  f:\2026f\ctm3\.python если он есть, иначе — python из PATH.
.NOTES
  Запуск:  powershell -ExecutionPolicy Bypass -File runner.ps1
#>

#Requires -Version 5.1
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'

# --- Пути --------------------------------------------------------------------
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$BaseDir     = Split-Path -Parent $ScriptDir            # CTM2_recovered
$CurrentDir  = Join-Path $BaseDir 'current'
$WebclientDir= Join-Path $CurrentDir 'web-client'

$ServerHost_ = '127.0.0.1'
$ServerPort  = '8000'

# Portable python (если есть), иначе системный
$PortablePy  = Join-Path $ScriptDir '..\..\.python\python.exe'
if (Test-Path $PortablePy) {
    $PythonExe = (Resolve-Path $PortablePy).Path
} else {
    $PythonExe = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
    if (-not $PythonExe) {
        Write-Host '[!] python.exe не найден ни в portable, ни в PATH.' -ForegroundColor Red
        Read-Host 'Нажмите Enter для выхода'
        exit 1
    }
}

# Каталог для логов
$LogDir = Join-Path $env:TEMP 'ctm-runner-logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$ServerLog   = Join-Path $LogDir 'server.log'
$FrontendLog = Join-Path $LogDir 'frontend.log'
$RebuildLog  = Join-Path $LogDir 'rebuild.log'

# --- Состояние процессов -----------------------------------------------------
# Храним в script-scope, чтобы функции видели
$script:ServerProc   = $null
$script:FrontendProc = $null
$script:RebuildProc  = $null


# --- Хелперы -----------------------------------------------------------------
function Test-PortableUvicorn {
    & $PythonExe -c "import uvicorn" 2>$null
    return $LASTEXITCODE -eq 0
}

function Get-NpmCmd {
    $n = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if ($n) { return $n.Source }
    $n = Get-Command npm -ErrorAction SilentlyContinue
    if ($n) { return $n.Source }
    return $null
}

function Stop-ProcTree {
    param($Proc)
    if (-not $Proc) { return }
    try {
        if ($Proc.HasExited) { return }
        # /T = убить всё дерево, /F = принудительно
        & taskkill.exe /T /F /PID $Proc.Id 2>$null | Out-Null
        Start-Sleep -Milliseconds 200
        if (-not $Proc.HasExited) {
            $Proc.Kill()
            $Proc.WaitForExit(2000) | Out-Null
        }
    } catch {
        Write-Host "[!] Ошибка остановки PID $($Proc.Id): $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

function Test-Running {
    param($Proc)
    return ($Proc -and -not $Proc.HasExited)
}

function Show-StatusLine {
    param([string]$Label, $Proc, [string]$Url)
    if (Test-Running $Proc) {
        $state = 'RUNNING'
        $color = 'Green'
    } else {
        $state = 'stopped'
        $color = 'DarkGray'
    }
    $urlPart = if ($Url) { "  $Url" } else { '' }
    Write-Host ("  [{0}] {1}{2}" -f $state, $Label, $urlPart) -ForegroundColor $color
}

function Show-Menu {
    Clear-Host
    Write-Host '============ CTM Runner (PowerShell) ============' -ForegroundColor Cyan
    Write-Host ''
    Show-StatusLine 'Server  ' $script:ServerProc   "http://${ServerHost_}:${ServerPort}"
    Show-StatusLine 'Frontend' $script:FrontendProc 'npm run dev'
    Show-StatusLine 'Rebuild ' $script:RebuildProc  ''
    Write-Host ''
    Write-Host '------------------------------------------------'
    Write-Host '  1  Start/Stop Server'
    Write-Host '  2  Start/Stop Frontend'
    Write-Host '  3  Start BOTH  (server + frontend)'
    Write-Host '  4  Stop ALL'
    Write-Host '  5  Rebuild frontend (npm run build)'
    Write-Host '  6  Show server log (tail)'
    Write-Host '  7  Show frontend log (tail)'
    Write-Host '  8  Deploy to prod (stub)'
    Write-Host '  9  Open browser: http://localhost:'"$ServerPort"
    Write-Host '  0  Exit'
    Write-Host '------------------------------------------------'
}


# --- Действия ----------------------------------------------------------------
function Start-Server {
    if (Test-Running $script:ServerProc) {
        Write-Host '[i] Server уже работает.' -ForegroundColor Yellow
        return
    }
    if (-not (Test-Path $CurrentDir)) {
        Write-Host "[!] Каталог не найден: $CurrentDir" -ForegroundColor Red
        return
    }
    if (-not (Test-PortableUvicorn)) {
        Write-Host "[!] uvicorn не установлен в $PythonExe" -ForegroundColor Red
        Write-Host "    Установите:  & '$PythonExe' -m pip install -r (Join-Path $CurrentDir 'api\requirements.txt')" -ForegroundColor Yellow
        return
    }
    Write-Host '[+] Запуск сервера ...' -ForegroundColor Green
    # Очищаем лог
    '' | Set-Content -Path $ServerLog -Encoding UTF8
    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $PythonExe
    $psi.Arguments = "-m uvicorn api.main:app --reload --host $ServerHost_ --port $ServerPort"
    $psi.WorkingDirectory = $CurrentDir
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    $proc = [System.Diagnostics.Process]::new()
    $proc.StartInfo = $psi
    # Асинхронно пишем stdout+stderr в лог
    $null = Register-ObjectEvent -InputObject $proc -EventName 'OutputDataReceived' -MessageData $ServerLog -Action {
        if ($EventArgs.Data) { Add-Content -Path $EventData -Value $EventArgs.Data -Encoding UTF8 }
    }
    $null = Register-ObjectEvent -InputObject $proc -EventName 'ErrorDataReceived' -MessageData $ServerLog -Action {
        if ($EventArgs.Data) { Add-Content -Path $EventData -Value $EventArgs.Data -Encoding UTF8 }
    }
    $null = $proc.Start()
    $proc.BeginOutputReadLine()
    $proc.BeginErrorReadLine()
    $script:ServerProc = $proc
    Write-Host "[OK] Сервер запущен (PID $($proc.Id)). Лог: $ServerLog" -ForegroundColor Green
}

function Stop-Server {
    if (-not (Test-Running $script:ServerProc)) {
        Write-Host '[i] Сервер не запущен.' -ForegroundColor Yellow
        return
    }
    Write-Host '[-] Остановка сервера ...' -ForegroundColor Yellow
    Stop-ProcTree $script:ServerProc
    $script:ServerProc = $null
}

function Start-Frontend {
    if (Test-Running $script:FrontendProc) {
        Write-Host '[i] Frontend уже работает.' -ForegroundColor Yellow
        return
    }
    $npm = Get-NpmCmd
    if (-not $npm) {
        Write-Host '[!] npm не найден в PATH.' -ForegroundColor Red
        return
    }
    if (-not (Test-Path $WebclientDir)) {
        Write-Host "[!] Каталог не найден: $WebclientDir" -ForegroundColor Red
        return
    }
    Write-Host '[+] Запуск frontend (npm run dev) ...' -ForegroundColor Green
    '' | Set-Content -Path $FrontendLog -Encoding UTF8
    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $npm
    $psi.Arguments = 'run dev'
    $psi.WorkingDirectory = $WebclientDir
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    $proc = [System.Diagnostics.Process]::new()
    $proc.StartInfo = $psi
    $null = Register-ObjectEvent -InputObject $proc -EventName 'OutputDataReceived' -MessageData $FrontendLog -Action {
        if ($EventArgs.Data) { Add-Content -Path $EventData -Value $EventArgs.Data -Encoding UTF8 }
    }
    $null = Register-ObjectEvent -InputObject $proc -EventName 'ErrorDataReceived' -MessageData $FrontendLog -Action {
        if ($EventArgs.Data) { Add-Content -Path $EventData -Value $EventArgs.Data -Encoding UTF8 }
    }
    $null = $proc.Start()
    $proc.BeginOutputReadLine()
    $proc.BeginErrorReadLine()
    $script:FrontendProc = $proc
    Write-Host "[OK] Frontend запущен (PID $($proc.Id)). Лог: $FrontendLog" -ForegroundColor Green
    Write-Host "     Vite обычно печатает Local URL через 1-2 сек — см. лог (пункт 7)." -ForegroundColor DarkGray
}

function Stop-Frontend {
    if (-not (Test-Running $script:FrontendProc)) {
        Write-Host '[i] Frontend не запущен.' -ForegroundColor Yellow
        return
    }
    Write-Host '[-] Остановка frontend ...' -ForegroundColor Yellow
    Stop-ProcTree $script:FrontendProc
    $script:FrontendProc = $null
}

function Invoke-Rebuild {
    if (Test-Running $script:RebuildProc) {
        Write-Host '[i] Ребилд уже выполняется.' -ForegroundColor Yellow
        return
    }
    $npm = Get-NpmCmd
    if (-not $npm) {
        Write-Host '[!] npm не найден в PATH.' -ForegroundColor Red
        return
    }
    Write-Host '[+] Ребилд (npm run build) ...' -ForegroundColor Green
    '' | Set-Content -Path $RebuildLog -Encoding UTF8
    $script:RebuildProc = Start-Process -FilePath $npm -ArgumentList 'run','build' `
        -WorkingDirectory $WebclientDir -NoNewWindow -PassThru `
        -RedirectStandardOutput $RebuildLog -RedirectStandardError $RebuildLog
    Write-Host "[OK] Ребилд запущен (PID $($script:RebuildProc.Id)). Лог: $RebuildLog" -ForegroundColor Green
}

function Show-Tail {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        Write-Host "[!] Лог не найден: $Path" -ForegroundColor Red
        return
    }
    Write-Host "`n--- $Path (последние 40 строк) ---" -ForegroundColor Cyan
    Get-Content -Path $Path -Tail 40 -Encoding UTF8
    Write-Host '--- конец лога ---' -ForegroundColor Cyan
}

function Invoke-DeployStub {
    Write-Host '[deploy] STUB — не реализовано (требует исследования).' -ForegroundColor Yellow
    Write-Host '         Продуктив использует docker-compose из deploy/ на удалённом хосте (abitek.su).' -ForegroundColor DarkGray
    Write-Host '         Нужно: доступ по SSH/копирование артефактов, секреты, сборка.' -ForegroundColor DarkGray
}

function Open-Browser {
    $url = "http://localhost:$ServerPort"
    Write-Host "[+] Открытие $url ..." -ForegroundColor Green
    Start-Process $url
}

function Stop-All {
    Stop-Server
    Stop-Frontend
    if (Test-Running $script:RebuildProc) {
        Write-Host '[-] Остановка rebuild ...' -ForegroundColor Yellow
        Stop-ProcTree $script:RebuildProc
        $script:RebuildProc = $null
    }
}


# --- Главный цикл ------------------------------------------------------------
function Main {
    Write-Host "Python: $PythonExe" -ForegroundColor DarkGray
    Write-Host "API dir: $CurrentDir" -ForegroundColor DarkGray
    Write-Host "Web dir: $WebclientDir" -ForegroundColor DarkGray
    Start-Sleep -Seconds 1

    while ($true) {
        Show-Menu
        $key = Read-Host 'Выберите действие'

        switch ($key) {
            '1' {
                if (Test-Running $script:ServerProc) { Stop-Server }
                else { Start-Server }
                Start-Sleep -Seconds 1
            }
            '2' {
                if (Test-Running $script:FrontendProc) { Stop-Frontend }
                else { Start-Frontend }
                Start-Sleep -Seconds 1
            }
            '3' { Start-Server; Start-Frontend; Start-Sleep -Seconds 1 }
            '4' { Stop-All; Start-Sleep -Seconds 1 }
            '5' { Invoke-Rebuild; Start-Sleep -Seconds 1 }
            '6' { Show-Tail $ServerLog; Read-Host 'Enter — назад' }
            '7' { Show-Tail $FrontendLog; Read-Host 'Enter — назад' }
            '8' { Invoke-DeployStub; Read-Host 'Enter — назад' }
            '9' { Open-Browser; Start-Sleep -Milliseconds 500 }
            '0' { break }
            default { Write-Host '[?] Неизвестная команда' -ForegroundColor Yellow; Start-Sleep -Seconds 1 }
        }

        if ($key -eq '0') {
            Write-Host 'Останавливаю все процессы перед выходом ...' -ForegroundColor Yellow
            Stop-All
            Write-Host 'До свидания.' -ForegroundColor Green
            break
        }
    }
}

# Обработка Ctrl+C — останавливаем процессы
$null = Register-EngineEvent PowerShell.Exiting -Action { Stop-All }

try {
    Main
} catch {
    Write-Host "`n[!] Непредвиденная ошибка: $($_.Exception.Message)" -ForegroundColor Red
    Stop-All
}
