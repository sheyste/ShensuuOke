"""GitHub Releases update checker for ShensuuOke.

Handles checking for new releases on GitHub, supporting both public
and private repositories via Windows Credential Manager or a user-configured
Personal Access Token (PAT).
"""
from __future__ import annotations
import ctypes
import json
import os
import re
import urllib.request
import urllib.error
from ctypes import wintypes
from typing import Optional, Dict, Any, Tuple
from PySide6.QtCore import QObject, QThread, Signal
from app.version import __version__


def get_stored_github_token() -> Optional[str]:
    """Retrieve GitHub token from .env file, environment variables, or Windows Credential Manager."""
    # 1. Look for .env or .env.local in project root or executable folder
    candidate_dirs = [
        os.getcwd(),
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    ]
    if hasattr(os, "sys") and getattr(os.sys, "_MEIPASS", None):
        candidate_dirs.append(getattr(os.sys, "_MEIPASS"))
    if hasattr(os, "sys") and getattr(os.sys, "executable", None):
        candidate_dirs.append(os.path.dirname(os.sys.executable))

    for d in candidate_dirs:
        for fname in (".env", ".env.local"):
            env_path = os.path.join(d, fname)
            if os.path.isfile(env_path):
                try:
                    with open(env_path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("#") or not line or "=" not in line:
                                continue
                            k, v = line.split("=", 1)
                            k, v = k.strip(), v.strip().strip('"').strip("'")
                            if k in ("GITHUB_TOKEN", "GH_TOKEN", "SHENSUUOKE_GITHUB_TOKEN") and v:
                                return v
                except Exception:
                    pass

    # 2. Environment variables
    for env_var in ("GITHUB_TOKEN", "GH_TOKEN", "SHENSUUOKE_GITHUB_TOKEN"):
        val = os.environ.get(env_var)
        if val and val.strip():
            return val.strip()

    # 2. Windows Credential Manager
    if os.name == "nt":
        try:
            class CREDENTIAL(ctypes.Structure):
                _fields_ = [
                    ('Flags', wintypes.DWORD),
                    ('Type', wintypes.DWORD),
                    ('TargetName', wintypes.LPWSTR),
                    ('Comment', wintypes.LPWSTR),
                    ('LastWritten', wintypes.FILETIME),
                    ('CredentialBlobSize', wintypes.DWORD),
                    ('CredentialBlob', ctypes.POINTER(ctypes.c_byte)),
                    ('Persist', wintypes.DWORD),
                    ('AttributeCount', wintypes.DWORD),
                    ('Attributes', ctypes.c_void_p),
                    ('TargetAlias', wintypes.LPWSTR),
                    ('UserName', wintypes.LPWSTR),
                ]

            Advapi32 = ctypes.WinDLL('Advapi32.dll')
            CredReadW = Advapi32.CredReadW
            CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(CREDENTIAL))]
            CredReadW.restype = wintypes.BOOL
            CredFree = Advapi32.CredFree
            CredFree.argtypes = [ctypes.c_void_p]

            targets = (
                "GitHub - https://api.github.com/sheyste",
                "git:https://github.com",
                "legacyGeneric:target=git:https://github.com",
                "ShensuuOke:GitHubToken",
            )
            pcred = ctypes.POINTER(CREDENTIAL)()
            for target in targets:
                if CredReadW(target, 1, 0, ctypes.byref(pcred)):
                    blob = ctypes.string_at(pcred.contents.CredentialBlob, pcred.contents.CredentialBlobSize)
                    token = blob.decode('utf-8', errors='ignore').strip()
                    CredFree(pcred)
                    if token:
                        return token
        except Exception:
            pass

    return None


def parse_version_tuple(ver_str: str) -> Tuple[int, ...]:
    """Parse version string into a numeric tuple (e.g., 'v1.0.24' -> (1, 0, 24))."""
    cleaned = re.sub(r'^[^\d]*', '', ver_str.strip())
    parts = []
    for part in cleaned.split('.'):
        digits = re.match(r'^\d+', part)
        if digits:
            parts.append(int(digits.group(0)))
        else:
            break
    return tuple(parts) if parts else (0,)


def check_for_updates(repo: str = "sheyste/ShensuuOke",
                      token: Optional[str] = None,
                      current_version: str = __version__) -> Dict[str, Any]:
    """Query GitHub releases API and compare against current_version.

    Returns a dict with:
      - 'has_update': bool
      - 'current_version': str
      - 'latest_version': str
      - 'release_name': str
      - 'release_url': str
      - 'download_url': str
      - 'published_at': str
      - 'body': str
      - 'error': str (empty on success)
    """
    effective_token = token.strip() if (token and token.strip()) else get_stored_github_token()
    url = f"https://api.github.com/repos/{repo}/releases"

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"ShensuuOke/{current_version}"
    }
    if effective_token:
        headers["Authorization"] = f"Bearer {effective_token}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 404):
            msg = f"GitHub API error ({e.code} {e.reason})."
            if not effective_token:
                msg += " This repository is private; please configure a GitHub Token in Application Settings."
            return {"has_update": False, "error": msg, "current_version": current_version}
        return {"has_update": False, "error": f"HTTP {e.code}: {e.reason}", "current_version": current_version}
    except Exception as e:
        return {"has_update": False, "error": str(e), "current_version": current_version}

    if not isinstance(data, list) or not data:
        return {"has_update": False, "error": "No releases found.", "current_version": current_version}

    # Find the latest non-draft release
    latest_release = None
    for r in data:
        if not r.get("draft"):
            latest_release = r
            break

    if not latest_release:
        return {"has_update": False, "error": "No published releases found.", "current_version": current_version}

    tag_name = latest_release.get("tag_name", "")
    latest_ver_str = tag_name.lstrip("vV")
    latest_tuple = parse_version_tuple(tag_name)
    current_tuple = parse_version_tuple(current_version)

    has_update = latest_tuple > current_tuple

    # Look for Windows executable installer asset in the release
    download_url = latest_release.get("html_url", "")
    for asset in latest_release.get("assets", []):
        aname = asset.get("name", "").lower()
        if aname.endswith(".exe") or "setup" in aname:
            download_url = asset.get("browser_download_url", download_url)
            break

    return {
        "has_update": has_update,
        "current_version": current_version,
        "latest_version": latest_ver_str or tag_name,
        "release_name": latest_release.get("name") or tag_name,
        "release_url": latest_release.get("html_url", ""),
        "download_url": download_url,
        "published_at": latest_release.get("published_at", ""),
        "body": latest_release.get("body", ""),
        "error": ""
    }


class UpdateCheckWorker(QThread):
    """Background worker thread to check for updates without blocking UI."""
    finished_check = Signal(dict)

    def __init__(self, repo: str = "sheyste/ShensuuOke", token: Optional[str] = None, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.repo = repo
        self.token = token

    def run(self):
        result = check_for_updates(self.repo, self.token)
        self.finished_check.emit(result)
