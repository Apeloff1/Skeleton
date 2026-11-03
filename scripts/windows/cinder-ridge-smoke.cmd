@echo off
setlocal
cd /d "%~dp0\..\.."
where py >nul 2>nul
if not errorlevel 1 (
  py -3 -m skeleton.game.gameplay.ridge_rescue consumer smoke
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo Python 3 is required for Cinder Ridge smoke acceptance.
    pause
    exit /b 2
  )
  python -m skeleton.game.gameplay.ridge_rescue consumer smoke
)
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" pause
exit /b %RESULT%
