# Helper script to auto-increment version number across ShensuuOke build configurations
$ErrorActionPreference = "Stop"
$rootDir = (Resolve-Path "$PSScriptRoot\..").Path
$versionJsonPath = "$rootDir\packaging\version.json"

$major = 1
$minor = 0
$patch = 0

if (Test-Path $versionJsonPath) {
    try {
        $vJson = Get-Content $versionJsonPath -Raw | ConvertFrom-Json
        $major = [int]$vJson.major
        $minor = [int]$vJson.minor
        $patch = [int]$vJson.patch + 1
    } catch {
        $patch = 1
    }
} else {
    $patch = 1
}

$versionStr = "$major.$minor.$patch"
$winVerTuple = "($major, $minor, $patch, 0)"
$winVerStr = "$major.$minor.$patch.0"

# 1. Update packaging/version.json
$newVObj = [PSCustomObject]@{
    major = $major
    minor = $minor
    patch = $patch
    version = $versionStr
}
$newVObj | ConvertTo-Json | Set-Content $versionJsonPath -Encoding UTF8

# 2. Update app/version.py
$pyVerContent = @"
"""ShensuuOke application version information."""
__version__ = "$versionStr"
"@
Set-Content "$rootDir\app\version.py" $pyVerContent -Encoding UTF8

# 3. Update packaging/file_version_info.txt
$fviContent = @"
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=$winVerTuple,
    prodvers=$winVerTuple,
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          '040904B0',
          [
            StringStruct('CompanyName', 'Shensuu'),
            StringStruct('FileDescription', 'ShensuuOke Desktop Karaoke System'),
            StringStruct('FileVersion', '$winVerStr'),
            StringStruct('InternalName', 'ShensuuOke'),
            StringStruct('LegalCopyright', 'Copyright (C) 2026 Shensuu. All rights reserved.'),
            StringStruct('OriginalFilename', 'ShensuuOke.exe'),
            StringStruct('ProductName', 'ShensuuOke'),
            StringStruct('ProductVersion', '$winVerStr')
          ]
        )
      ]
    ),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"@
Set-Content "$rootDir\packaging\file_version_info.txt" $fviContent -Encoding UTF8

# 4. Update packaging/installer.iss
$issPath = "$rootDir\packaging\installer.iss"
if (Test-Path $issPath) {
    (Get-Content $issPath) -replace '#define MyAppVersion ".*"', "#define MyAppVersion `"$versionStr`"" | Set-Content $issPath -Encoding UTF8
}

return $versionStr
