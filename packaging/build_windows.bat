@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0\.."

echo ==============================================================
echo   Building ShensuuOke Standalone Windows Executable
echo   Working Directory: %CD%
echo ==============================================================
echo Note: PyInstaller takes ~45-90 seconds to bundle PySide6 and native runtimes. Please wait...

set PYINSTALLER=.venv\Scripts\pyinstaller.exe
if not exist "%PYINSTALLER%" (
  set PYINSTALLER=pyinstaller.exe
)

set FFMPEG_BIN=runtime\ffmpeg
set FLUIDSYNTH_BIN=runtime\fluidsynth
if not exist "%FFMPEG_BIN%\ffmpeg.exe" (
  if exist "%FFMPEG_BIN%\ffmpeg.zip" (
    echo Unpacking %FFMPEG_BIN%\ffmpeg.zip...
    powershell -Command "Expand-Archive -Path '%FFMPEG_BIN%\ffmpeg.zip' -DestinationPath '%FFMPEG_BIN%' -Force"
  )
)

if not exist "runtime\soundfonts\KaraOke_King_v2.sf2" (
  if exist "runtime\soundfonts\KaraOke_King_v2.zip.part1" (
    echo Unpacking KaraOke_King_v2 SoundFont from git parts...
    if exist ".venv\Scripts\python.exe" (
      .venv\Scripts\python.exe -c "import io, zipfile; data = open(r'runtime/soundfonts/KaraOke_King_v2.zip.part1','rb').read() + open(r'runtime/soundfonts/KaraOke_King_v2.zip.part2','rb').read(); zipfile.ZipFile(io.BytesIO(data)).extractall(r'runtime/soundfonts')"
    ) else (
      python -c "import io, zipfile; data = open(r'runtime/soundfonts/KaraOke_King_v2.zip.part1','rb').read() + open(r'runtime/soundfonts/KaraOke_King_v2.zip.part2','rb').read(); zipfile.ZipFile(io.BytesIO(data)).extractall(r'runtime/soundfonts')"
    )
  )
)

if not exist "%FFMPEG_BIN%\ffmpeg.exe" (
  echo Missing %FFMPEG_BIN%\ffmpeg.exe
  exit /b 1
)
if not exist "%FLUIDSYNTH_BIN%\*.dll" (
  echo Missing FluidSynth DLLs in %FLUIDSYNTH_BIN%
  exit /b 1
)

taskkill /F /IM ShensuuOke.exe >nul 2>&1

if exist "build" (
  attrib -r -s -h "build" /s /d >nul 2>&1
  rmdir /s /q "build" >nul 2>&1
)
if exist "dist\ShensuuOke" (
  attrib -r -s -h "dist\ShensuuOke" /s /d >nul 2>&1
  rmdir /s /q "dist\ShensuuOke" >nul 2>&1
)

set PYTHON=.venv\Scripts\python.exe
if not exist "%PYTHON%" (
  set PYTHON=python.exe
)

echo.
echo Incrementing version number...
"%PYTHON%" packaging\bump_version.py >nul 2>&1
if exist "packaging\version.txt" (
  set /p APP_VER=<"packaging\version.txt"
) else (
  set APP_VER=1.0.1
)
echo Build Version: v!APP_VER!

echo.
echo Running PyInstaller with embedded Windows Version Info and Assets...
"%PYINSTALLER%" --noconfirm ShensuuOke.spec

if errorlevel 1 (
  echo PyInstaller build failed!
  pause
  exit /b !errorlevel!
)

set ISCC="%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="C:\Users\Sheyste\AppData\Local\Programs\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="C:\Program Files\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC=ISCC.exe

if exist %ISCC% (
  echo.
  echo Building Windows Setup Installer (ShensuuOke-Setup-v!APP_VER!.exe) with Inno Setup...
  %ISCC% "/DMyAppVersion=!APP_VER!" "packaging\installer.iss"
)

echo.
echo ==============================================================
echo   Build and Packaging Complete!
echo   Build Version:     v!APP_VER!
echo   Standalone Folder: dist\ShensuuOke\
echo   Standalone Exe:    dist\ShensuuOke\ShensuuOke.exe
if exist "dist\ShensuuOke-Setup-v!APP_VER!.exe" (
  echo   Setup Installer:   dist\ShensuuOke-Setup-v!APP_VER!.exe
)
echo ==============================================================
pause
