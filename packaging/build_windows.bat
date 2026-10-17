@echo off
rem Build a standalone Windows app with PyInstaller. Run from the project root inside your venv.
set FFMPEG_BIN=runtime\ffmpeg
set FLUIDSYNTH_BIN=runtime\fluidsynth
if not exist "%FFMPEG_BIN%\ffmpeg.exe" (
  echo Missing %FFMPEG_BIN%\ffmpeg.exe
  exit /b 1
)
if not exist "%FLUIDSYNTH_BIN%\*.dll" (
  echo Missing FluidSynth DLLs in %FLUIDSYNTH_BIN%
  exit /b 1
)
pyinstaller --noconfirm --clean --windowed --name ShensuuOke ^
  --icon "app\resources\icons\logo.ico" ^
  --add-binary "%FFMPEG_BIN%\ffmpeg.exe;runtime\ffmpeg" ^
  --add-binary "%FLUIDSYNTH_BIN%\*.dll;runtime\fluidsynth" ^
  --collect-all sounddevice ^
  main.py
echo.
echo Output: dist\ShensuuOke\ShensuuOke.exe
