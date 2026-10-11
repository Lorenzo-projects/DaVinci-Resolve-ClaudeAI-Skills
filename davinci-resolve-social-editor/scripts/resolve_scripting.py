"""Locate and connect to the local DaVinci Resolve scripting API."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


def sdk_paths() -> tuple[Path, Path]:
    if sys.platform == "win32":
        root = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
        install = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
        api_default = root / "Blackmagic Design/DaVinci Resolve/Support/Developer/Scripting"
        library_default = install / "Blackmagic Design/DaVinci Resolve/fusionscript.dll"
    elif sys.platform == "darwin":
        api_default = Path("/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting")
        library_default = Path(
            "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"
        )
    else:
        api_default = Path("/opt/resolve/Developer/Scripting")
        library_default = Path("/opt/resolve/libs/Fusion/fusionscript.so")

    api = Path(os.environ.get("RESOLVE_SCRIPT_API", str(api_default))).expanduser()
    library = Path(os.environ.get("RESOLVE_SCRIPT_LIB", str(library_default))).expanduser()
    return api, library


def get_resolve() -> Any:
    api, library = sdk_paths()
    modules = api / "Modules"
    os.environ.setdefault("RESOLVE_SCRIPT_API", str(api))
    os.environ.setdefault("RESOLVE_SCRIPT_LIB", str(library))
    if str(modules) not in sys.path:
        sys.path.insert(0, str(modules))

    try:
        import DaVinciResolveScript as dvr  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Could not import DaVinciResolveScript. "
            f"Expected its module under {modules}; verify RESOLVE_SCRIPT_API and RESOLVE_SCRIPT_LIB."
        ) from exc

    resolve = dvr.scriptapp("Resolve")
    if resolve is None:
        raise RuntimeError(
            "DaVinci Resolve scripting API did not return an app. Start Resolve, "
            "open a project, and enable local external scripting."
        )
    return resolve
