@echo off
setlocal
chcp 65001 >nul
title Video Analyzer
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

rem ── Checks first. If anything is missing we stay in this window and explain. ──

where python >nul 2>&1
if errorlevel 1 (
  echo.
  echo   Python is not installed on this computer.
  echo.
  echo   Get it from  https://www.python.org/downloads/
  echo   During setup, TICK the box "Add python.exe to PATH".
  echo   Then close this window and open it again.
  goto hold
)

where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo.
  echo   FFmpeg is missing - it is what reads the video.
  echo.
  echo   Open a terminal and run:   winget install Gyan.FFmpeg
  echo   Then close this window and open it again.
  goto hold
)

python -c "import yt_dlp, webview" >nul 2>&1
if errorlevel 1 (
  echo.
  echo   Setting up a couple of things, one moment...
  python -m pip install --quiet --disable-pip-version-check yt-dlp pywebview
  if errorlevel 1 (
    echo.
    echo   That failed. Check your internet connection and try again.
    goto hold
  )
  echo   All set.
)

rem ── Everything is in place: open the app window and let this one go. ──
start "" pythonw "%~dp0app.py"
exit /b 0

:hold
echo.
echo   Press any key to close this window.
pause >nul
endlocal
