@echo off
setlocal
chcp 65001 >nul
title Video Analyzer
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

echo.
echo   ==============================
echo      V I D E O   A N A L Y Z E R
echo   ==============================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo   Python is not installed on this computer.
  echo.
  echo   Get it from  https://www.python.org/downloads/
  echo   During setup, TICK the box "Add python.exe to PATH".
  echo   Then close this window and open it again.
  goto end
)

where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo   FFmpeg is missing - it is what reads the video.
  echo.
  echo   Open a terminal and run:   winget install Gyan.FFmpeg
  echo   Then close this window and open it again.
  goto end
)

python -c "import yt_dlp" >nul 2>&1
if errorlevel 1 (
  echo   Installing the YouTube downloader, one moment...
  python -m pip install --quiet yt-dlp
  if errorlevel 1 (
    echo.
    echo   That failed. Check your internet connection and try again.
    goto end
  )
  echo   Done.
  echo.
)

set "URL="
set /p "URL=  Paste the YouTube link and press Enter: "
if not defined URL (
  echo.
  echo   No link entered - nothing to do.
  goto end
)

echo.
python extract.py "%URL%"
set "CODE=%errorlevel%"

echo.
if "%CODE%"=="0" (
  echo   Opening the frames folder...
  start "" "%~dp0frames"
) else (
  echo   It did not finish. The reason is printed above.
)

:end
echo.
echo   Press any key to close this window.
pause >nul
endlocal
