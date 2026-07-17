@echo off
REM ============================================================
REM Everywaves form-sync (ogni 4 ore, Task Scheduler).
REM Esegue /form-sync headless nel worktree C:\nina-work\claude.
REM Pattern: 36_GinevraSocial/automation/run_weekly.bat (collaudato).
REM
REM AUTH: variabile utente CLAUDE_CODE_OAUTH_TOKEN (da `claude setup-token`).
REM Senza token il run esce con rc=3 senza far danni.
REM ============================================================
setlocal
set "PYTHONUTF8=1"
set "PROJ=C:\nina-work\claude"
set "LOG=C:\nina-work\logs"
if not exist "%LOG%" mkdir "%LOG%"

cd /d "%PROJ%"

if "%CLAUDE_CODE_OAUTH_TOKEN%"=="" (
  echo [%date% %time%] form-sync: CLAUDE_CODE_OAUTH_TOKEN assente, salto. >> "%LOG%\form-sync.log"
  echo   Impostare con: claude setup-token  +  setx CLAUDE_CODE_OAUTH_TOKEN "..." >> "%LOG%\form-sync.log"
  endlocal & exit /b 3
)

echo [%date% %time%] form-sync START >> "%LOG%\form-sync.log"
call claude -p "/form-sync" --permission-mode bypassPermissions --max-turns 30 --output-format json >> "%LOG%\form-sync.log" 2>&1
set "RC=%ERRORLEVEL%"
echo [%date% %time%] form-sync END rc=%RC% >> "%LOG%\form-sync.log"

endlocal & exit /b %RC%
