"""Auto-increment version number across ShensuuOke build configurations."""
from __future__ import annotations
import json
import os
import re
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
VERSION_JSON = os.path.join(ROOT_DIR, "packaging", "version.json")
VERSION_PY = os.path.join(ROOT_DIR, "app", "version.py")
FILE_VER_INFO = os.path.join(ROOT_DIR, "packaging", "file_version_info.txt")
INSTALLER_ISS = os.path.join(ROOT_DIR, "packaging", "installer.iss")


def get_current_version() -> str:
    if os.path.exists(VERSION_JSON):
        try:
            with open(VERSION_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
            return str(data.get("version", "1.0.0"))
        except Exception:
            pass
    return "1.0.0"


def bump_version(force: bool = False) -> str:
    # Avoid bumping twice in the exact same build process/pipeline run
    if not force and os.environ.get("SHENSUUOKE_VERSION_BUMPED") == "1":
        return get_current_version()

    major = 1
    minor = 0
    patch = 0

    if os.path.exists(VERSION_JSON):
        try:
            with open(VERSION_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
            major = int(data.get("major", 1))
            minor = int(data.get("minor", 0))
            patch = int(data.get("patch", 0)) + 1
        except Exception:
            patch = 1
    else:
        patch = 1

    ver_str = f"{major}.{minor}.{patch}"
    win_ver_tuple = f"({major}, {minor}, {patch}, 0)"
    win_ver_str = f"{major}.{minor}.{patch}.0"

    # 1. Update packaging/version.json
    try:
        with open(VERSION_JSON, "w", encoding="utf-8") as f:
            json.dump({
                "major": major,
                "minor": minor,
                "patch": patch,
                "version": ver_str,
            }, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not update {VERSION_JSON}: {e}", file=sys.stderr)

    # 2. Update app/version.py
    try:
        os.makedirs(os.path.dirname(VERSION_PY), exist_ok=True)
        with open(VERSION_PY, "w", encoding="utf-8") as f:
            f.write(f'"""ShensuuOke application version information."""\n__version__ = "{ver_str}"\n')
    except Exception as e:
        print(f"Warning: Could not update {VERSION_PY}: {e}", file=sys.stderr)

    # 3. Update packaging/file_version_info.txt
    try:
        fvi_content = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={win_ver_tuple},
    prodvers={win_ver_tuple},
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
            StringStruct('FileVersion', '{win_ver_str}'),
            StringStruct('InternalName', 'ShensuuOke'),
            StringStruct('LegalCopyright', 'Copyright (C) 2026 Shensuu. All rights reserved.'),
            StringStruct('OriginalFilename', 'ShensuuOke.exe'),
            StringStruct('ProductName', 'ShensuuOke'),
            StringStruct('ProductVersion', '{win_ver_str}')
          ]
        )
      ]
    ),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
        with open(FILE_VER_INFO, "w", encoding="utf-8") as f:
            f.write(fvi_content)
    except Exception as e:
        print(f"Warning: Could not update {FILE_VER_INFO}: {e}", file=sys.stderr)

    # 4. Update packaging/installer.iss
    try:
        if os.path.exists(INSTALLER_ISS):
            with open(INSTALLER_ISS, "r", encoding="utf-8") as f:
                iss_text = f.read()
            iss_text = re.sub(r'#define MyAppVersion ".*?"', f'#define MyAppVersion "{ver_str}"', iss_text)
            with open(INSTALLER_ISS, "w", encoding="utf-8") as f:
                f.write(iss_text)
    except Exception as e:
        print(f"Warning: Could not update {INSTALLER_ISS}: {e}", file=sys.stderr)

    # 5. Write packaging/version.txt
    try:
        ver_txt_path = os.path.join(ROOT_DIR, "packaging", "version.txt")
        with open(ver_txt_path, "w", encoding="utf-8") as f:
            f.write(ver_str.strip())
    except Exception as e:
        print(f"Warning: Could not update version.txt: {e}", file=sys.stderr)

    os.environ["SHENSUUOKE_VERSION_BUMPED"] = "1"
    return ver_str


if __name__ == "__main__":
    v = bump_version(force=True)
    print(v)
