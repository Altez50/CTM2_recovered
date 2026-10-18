@echo off
REM CTM Runner launcher (PowerShell, без tkinter)
REM
REM Использование:
REM   run-ps.cmd              — запустить интерактивное меню (сервер + фронт + ребилд)
REM   run-ps.cmd test         — открыть локальный (тестовый) фронтенд
REM   run-ps.cmd prod         — открыть продуктовый фронтенд
REM
REM Адреса настраиваются ниже (TEST_FRONTEND_URL / PROD_FRONTEND_URL).

setlocal
set "TEST_FRONTEND_URL=http://localhost:5173/ctm/"
set "PROD_FRONTEND_URL=https://abitek.su:18443/ctm/"

if /I "%~1"=="test" (
  start "" "%TEST_FRONTEND_URL%"
  echo [run-ps] Открыт тестовый фронтенд: %TEST_FRONTEND_URL%
  echo           (требует запущенного сервера на :8000 и Vite на :5173)
  endlocal
  exit /b 0
)

if /I "%~1"=="prod" (
  start "" "%PROD_FRONTEND_URL%"
  echo [run-ps] Открыт продуктовый фронтенд: %PROD_FRONTEND_URL%
  endlocal
  exit /b 0
)

REM Без аргументов — запускаем интерактивное меню
set "PS1=%~dp0runner.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
endlocal
