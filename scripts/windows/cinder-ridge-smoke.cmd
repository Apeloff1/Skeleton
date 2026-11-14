@echo off
setlocal
cd /d "%~dp0\..\.." || exit /b 2
set "PY="
where py >nul 2>nul
if not errorlevel 1 (
  py -3 -c "import sys;sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
  if not errorlevel 1 set "PY=py -3"
)
if not defined PY (
  where python >nul 2>nul
  if not errorlevel 1 (
    python -c "import sys;sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
    if not errorlevel 1 set "PY=python"
  )
)
if not defined PY (
  echo Python 3.11 or newer is required for Cinder Ridge acceptance.
  pause
  exit /b 2
)
echo [1/2] Cinder Ridge source process save/restart/ending/export acceptance
%PY% -m skeleton.game.gameplay.ridge_rescue consumer smoke
if errorlevel 1 goto :failed
echo [2/2] Cinder Ridge standalone zipapp save/restart/ending/export acceptance
%PY% -m skeleton.game.gameplay.ridge_rescue consumer portable-smoke
if errorlevel 1 goto :failed
echo Cinder Ridge smoke checks passed on this host. This is not release certification.
exit /b 0
:failed
echo Cinder Ridge acceptance FAILED. No release qualification is granted.
pause
exit /b 1
