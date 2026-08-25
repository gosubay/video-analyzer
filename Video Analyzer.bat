@echo off
rem ---------------------------------------------------------------------------
rem  KEEP THIS FILE PURE ASCII.
rem  cmd.exe reads a .bat by byte offset. A single non-ASCII character (a dash
rem  like the ones in this project's other files, a box-drawing line, an emoji)
rem  shifts that offset and cmd resumes parsing mid-word - it then runs garbage
rem  like '001' and 'yzer' as commands and takes every branch at once.
rem  If you edit this file, stick to plain ASCII.
rem ---------------------------------------------------------------------------
setlocal
title Video Analyzer
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

where python >nul 2>&1
if errorlevel 1 goto nopython

where ffmpeg >nul 2>&1
if errorlevel 1 goto noffmpeg

python -c "import yt_dlp, webview" >nul 2>&1
if errorlevel 1 goto install

:launch
start "" pythonw "%~dp0app.py"
exit /b 0

:install
echo.
echo   Setting up a couple of things, one moment...
python -m pip install --quiet --disable-pip-version-check yt-dlp pywebview
if errorlevel 1 goto nonet
echo   All set.
goto launch

:nopython
echo.
echo   Python is not installed on this computer.
echo.
echo   Get it from  https://www.python.org/downloads/
echo   During setup, TICK the box "Add python.exe to PATH".
echo   Then close this window and open it again.
goto hold

:noffmpeg
echo.
echo   FFmpeg is missing - it is what reads the video.
echo.
echo   Open a terminal and run:   winget install Gyan.FFmpeg
echo   Then close this window and open it again.
goto hold

:nonet
echo.
echo   That download failed. Check your internet connection and try again.
goto hold

:hold
echo.
echo   Press any key to close this window.
pause >nul
endlocal
