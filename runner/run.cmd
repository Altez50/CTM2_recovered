@echo off
REM CTM Runner launcher — uses the portable Python at f:\2026f\ctm3\.python
setlocal
set "PORTABLE_PY=f:\2026f\ctm3\.python\python.exe"
set "SCRIPT=%~dp0runner.py"

if not exist "%PORTABLE_PY%" (
  echo [run.cmd] Portable Python not found at: %PORTABLE_PY%
  echo [run.cmd] Rebuild it first, or edit PORTABLE_PY in this file.
  pause
  exit /b 1
)

"%PORTABLE_PY%" "%SCRIPT%" %*
endlocal
