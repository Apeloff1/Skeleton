@echo off
setlocal
cd /d "%~dp0\..\.."
where py >nul 2>nul
if not errorlevel 1 (
  py -3 -m skeleton.game.gameplay.ridge_rescue consumer play
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo Python 3 is required to play Cinder Ridge.
    pause
    exit /b 2
  )
  python -m skeleton.game.gameplay.ridge_rescue consumer play
)
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" (
  echo Cinder Ridge exited with an error. Your last committed save remains on disk.
  pause
)
exit /b %RESULT%
