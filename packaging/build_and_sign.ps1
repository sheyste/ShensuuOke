# PowerShell script to build ShensuuOke standalone app and Windows setup installer
$ErrorActionPreference = "Stop"

# Automatically switch working directory to the project root for both PowerShell and Win32 child processes
$rootDir = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $rootDir
[System.IO.Directory]::SetCurrentDirectory($rootDir)

Write-Host "=== Building ShensuuOke Standalone Windows Executable ===" -ForegroundColor Cyan
Write-Host "Project directory: $rootDir" -ForegroundColor Gray
Write-Host "Note: PyInstaller takes ~45-90 seconds to bundle PySide6 and native libraries. Please wait..." -ForegroundColor Yellow

$pyinstaller = "$rootDir\.venv\Scripts\pyinstaller.exe"
if (-not (Test-Path $pyinstaller)) {
    $pyinstaller = "pyinstaller"
}

# Unpack Git-friendly compressed runtime archives if extracted binaries are missing
$ffmpegExe = "$rootDir\runtime\ffmpeg\ffmpeg.exe"
$ffmpegZip = "$rootDir\runtime\ffmpeg\ffmpeg.zip"
if ((-not (Test-Path $ffmpegExe)) -and (Test-Path $ffmpegZip)) {
    Write-Host "Unpacking runtime\ffmpeg\ffmpeg.zip..." -ForegroundColor Cyan
    Expand-Archive -Path $ffmpegZip -DestinationPath "$rootDir\runtime\ffmpeg" -Force
}

$sfFile = "$rootDir\runtime\soundfonts\DreamSam 8202 (SPHE).sf2"
$p1 = "$rootDir\runtime\soundfonts\DreamSam.zip.part1"
$p2 = "$rootDir\runtime\soundfonts\DreamSam.zip.part2"
if ((-not (Test-Path $sfFile)) -and (Test-Path $p1) -and (Test-Path $p2)) {
    Write-Host "Unpacking DreamSam SoundFont from git parts..." -ForegroundColor Cyan
    $py = if (Test-Path "$rootDir\.venv\Scripts\python.exe") { "$rootDir\.venv\Scripts\python.exe" } else { "python" }
    & $py -c "import io, zipfile; data = open(r'$p1','rb').read() + open(r'$p2','rb').read(); zipfile.ZipFile(io.BytesIO(data)).extractall(r'$rootDir\runtime\soundfonts')"
}

$ffmpeg = "$rootDir\runtime\ffmpeg\ffmpeg.exe"
if (-not (Test-Path $ffmpeg)) {
    Write-Error "Missing runtime\ffmpeg\ffmpeg.exe"
}

$fluidsynth = "$rootDir\runtime\fluidsynth"
if (-not (Test-Path "$fluidsynth\libfluidsynth-3.dll")) {
    Write-Error "Missing runtime\fluidsynth\libfluidsynth-3.dll"
}

# Clean previous build artifacts without Windows file lock issues
if (Test-Path "$rootDir\build") {
    cmd /c "attrib -r -s -h `"$rootDir\build`" /s /d & rmdir /s /q `"$rootDir\build`""
}
if (Test-Path "$rootDir\dist\ShensuuOke") {
    cmd /c "attrib -r -s -h `"$rootDir\dist\ShensuuOke`" /s /d & rmdir /s /q `"$rootDir\dist\ShensuuOke`""
}

$versionFile = "$rootDir\packaging\file_version_info.txt"
$iconFile = "$rootDir\app\resources\icons\logo.ico"

& $pyinstaller --noconfirm --windowed --name ShensuuOke `
  --icon $iconFile `
  --version-file $versionFile `
  --distpath "$rootDir\dist" `
  --workpath "$rootDir\build" `
  --specpath "$rootDir" `
  --add-data "$rootDir\app\resources;app\resources" `
  --add-data "$rootDir\runtime\soundfonts;runtime\soundfonts" `
  --add-binary "$rootDir\runtime\ffmpeg\ffmpeg.exe;runtime\ffmpeg" `
  --add-binary "$rootDir\runtime\fluidsynth\*.dll;runtime\fluidsynth" `
  --collect-all sounddevice `
  --collect-all qrcode `
  --collect-all pyfluidsynth `
  "$rootDir\main.py"

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nPyInstaller build succeeded!" -ForegroundColor Green

    # Locate Inno Setup Compiler
    $iscc = @(
        "C:\Users\Sheyste\AppData\Local\Programs\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe",
        (Get-Command iscc.exe -ErrorAction SilentlyContinue).Source
    ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1

    if ($iscc) {
        Write-Host "`nBuilding Windows Setup Installer (ShensuuOke-Setup.exe)..." -ForegroundColor Cyan
        & $iscc "$rootDir\packaging\installer.iss"
    }

    Write-Host "`n==============================================================" -ForegroundColor Green
    Write-Host "  Build and Packaging Complete!" -ForegroundColor Green
    Write-Host "  Standalone App:   $rootDir\dist\ShensuuOke\ShensuuOke.exe" -ForegroundColor Green
    if (Test-Path "$rootDir\dist\ShensuuOke-Setup.exe") {
        Write-Host "  Windows Installer: $rootDir\dist\ShensuuOke-Setup.exe" -ForegroundColor Green
    }
    Write-Host "==============================================================" -ForegroundColor Green
} else {
    Write-Error "PyInstaller build failed with exit code $LASTEXITCODE"
}
