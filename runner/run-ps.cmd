@echo off
REM Запасной CTM Runner на PowerShell (без tkinter)
REM Запуск:  двойной клик или команда run-ps.cmd
setlocal
set "PS1=%~dp0runner.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
endlocal
