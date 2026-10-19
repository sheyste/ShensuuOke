import json
import os
import re
import importlib.util

root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_spec = importlib.util.spec_from_file_location("bump_version", os.path.join(root, "packaging", "bump_version.py"))
_bump_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bump_mod)
bump_version = _bump_mod.bump_version
get_current_version = _bump_mod.get_current_version
from app.version import __version__


def test_bump_version_increments():
    cur = get_current_version()
    major, minor, patch = [int(x) for x in cur.split(".")]

    next_ver = bump_version(force=True)
    expected = f"{major}.{minor}.{patch + 1}"
    assert next_ver == expected

    # Check version.json
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    with open(os.path.join(root, "packaging", "version.json"), "r", encoding="utf-8") as f:
        v_data = json.load(f)
    assert v_data["version"] == expected
    assert v_data["patch"] == patch + 1

    # Check app/version.py
    with open(os.path.join(root, "app", "version.py"), "r", encoding="utf-8") as f:
        py_content = f.read()
    assert f'__version__ = "{expected}"' in py_content

    # Check packaging/file_version_info.txt
    with open(os.path.join(root, "packaging", "file_version_info.txt"), "r", encoding="utf-8") as f:
        fvi_content = f.read()
    assert f"({major}, {minor}, {patch + 1}, 0)" in fvi_content
    assert f"'{major}.{minor}.{patch + 1}.0'" in fvi_content

    # Check packaging/installer.iss
    with open(os.path.join(root, "packaging", "installer.iss"), "r", encoding="utf-8") as f:
        iss_content = f.read()
    assert f'#define MyAppVersion "{expected}"' in iss_content
