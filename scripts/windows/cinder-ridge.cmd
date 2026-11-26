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
  echo Python 3.11 or newer is required to play Cinder Ridge.
  pause
  exit /b 2
)
%PY% -m skeleton.game.gameplay.ridge_rescue consumer play --ascii
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" (
  echo Cinder Ridge exited with an error. Your last committed save remains on disk.
  pause
)
exit /b %RESULT%
