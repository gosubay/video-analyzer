@echo off
rem ---------------------------------------------------------------------------
rem  KEEP THIS FILE PURE ASCII - see the note in "Video Analyzer.bat".
rem  Builds the shareable Windows release into dist\ and zips it up.
rem  Double-click this file to rebuild. Takes a few minutes.
rem ---------------------------------------------------------------------------
setlocal
title Building Video Analyzer
cd /d "%~dp0"

echo.
echo   Building Video Analyzer release...
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo   Python is not on this machine. Nothing to build with.
  goto hold
)

python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
  echo   Installing PyInstaller...
  python -m pip install --quiet --disable-pip-version-check pyinstaller
  if errorlevel 1 goto failed
)

echo   [1/3] Packaging...
python -m PyInstaller VideoAnalyzer.spec --noconfirm --clean
if errorlevel 1 goto failed

echo   [2/3] Adding the read-me...
copy /y "release\README.txt" "dist\Video Analyzer\README.txt" >nul
if errorlevel 1 goto failed

echo   [3/3] Zipping...
python release\make_zip.py
if errorlevel 1 goto failed

echo.
echo   Done. The zip to send people is in the release\ folder.
echo.
goto hold

:failed
echo.
echo   The build failed. The error is above.

:hold
echo   Press any key to close this window.
pause >nul
endlocal
