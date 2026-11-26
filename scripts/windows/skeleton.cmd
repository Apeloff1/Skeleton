@echo off
rem Skeleton launcher shim: runs skeleton.ps1 without changing the machine execution policy.
setlocal
where pwsh >nul 2>nul && (set "PS=pwsh") || (set "PS=powershell")
%PS% -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0skeleton.ps1" %*
exit /b %ERRORLEVEL%
