@echo off
rem One-command Skeleton first install: double-click or run from a terminal.
setlocal
where pwsh >nul 2>nul && (set "PS=pwsh") || (set "PS=powershell")
%PS% -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap.ps1" -InstallMissing %*
exit /b %ERRORLEVEL%
