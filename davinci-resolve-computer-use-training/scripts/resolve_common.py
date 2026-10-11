"""Shared helpers for DaVinci Resolve automation scripts."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any


def _resolve_paths() -> tuple[Path, Path, Path]:
    if sys.platform == "win32":
        script_api = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / (
            "Blackmagic Design/DaVinci Resolve/Support/Developer/Scripting"
        )
        script_lib = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / (
            "Blackmagic Design/DaVinci Resolve/fusionscript.dll"
        )
        user_scripts = Path(os.environ.get("APPDATA", str(Path.home() / "AppData/Roaming"))) / (
            "Blackmagic Design/DaVinci Resolve/Support/Fusion/Scripts"
        )
    elif sys.platform == "darwin":
        script_api = Path("/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting")
        script_lib = Path(
            "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"
        )
        user_scripts = Path.home() / "Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts"
    else:
        script_api = Path("/opt/resolve/Developer/Scripting")
        script_lib = Path("/opt/resolve/libs/Fusion/fusionscript.so")
        user_scripts = Path.home() / ".local/share/DaVinciResolve/Fusion/Scripts"
    return script_api, script_lib, user_scripts


_DEFAULT_SCRIPT_API, _DEFAULT_SCRIPT_LIB, USER_SCRIPTS = _resolve_paths()
SCRIPT_API = Path(os.environ.get("RESOLVE_SCRIPT_API", str(_DEFAULT_SCRIPT_API))).expanduser()
SCRIPT_LIB = Path(os.environ.get("RESOLVE_SCRIPT_LIB", str(_DEFAULT_SCRIPT_LIB))).expanduser()
MODULES = SCRIPT_API / "Modules"
DEFAULT_FPS = 24.0


def configure_env() -> None:
    os.environ.setdefault("RESOLVE_SCRIPT_API", str(SCRIPT_API))
    os.environ.setdefault("RESOLVE_SCRIPT_LIB", str(SCRIPT_LIB))
    if str(MODULES) not in sys.path:
        sys.path.insert(0, str(MODULES))


def get_resolve() -> Any:
    configure_env()
    try:
        import DaVinciResolveScript as dvr  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Could not import DaVinciResolveScript. "
            f"Expected module under {MODULES}; set RESOLVE_SCRIPT_API and "
            "RESOLVE_SCRIPT_LIB to match the installed Resolve SDK."
        ) from exc

    resolve = dvr.scriptapp("Resolve")
    if not resolve:
        raise RuntimeError("Could not connect to DaVinci Resolve. Start Resolve and enable local scripting.")
    return resolve


def project_by_name(project_manager, name: str):
    return project_manager.LoadProject(name) or project_manager.CreateProject(name)


def timeline_by_name(project, name: str):
    for index in range(1, int(project.GetTimelineCount() or 0) + 1):
        timeline = project.GetTimelineByIndex(index)
        if timeline and timeline.GetName() == name:
            return timeline
    return None


def get_or_create_bin(media_pool, parent, name: str):
    for folder in parent.GetSubFolderList():
        if folder.GetName() == name:
            return folder
    return media_pool.AddSubFolder(parent, name)


def append_to_timeline(media_pool, clip_infos: list[dict[str, Any]]) -> list[Any]:
    items = media_pool.AppendToTimeline(clip_infos)
    if not items or len(items) != len(clip_infos):
        raise RuntimeError(
            f"Resolve appended {len(items or [])} of {len(clip_infos)} requested timeline items."
        )
    return items


def seconds(value: float, fps: float = DEFAULT_FPS) -> int:
    return int(round(value * fps))


def json_dump(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def ffprobe_duration(path: Path) -> float | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe is required to determine source duration; install FFmpeg and retry.")
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    duration = result.stdout.strip()
    if not duration:
        return None
    return float(duration)


def ffprobe_video_fps(path: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe is required to read source frame rate; install FFmpeg and retry.")
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=avg_frame_rate,r_frame_rate",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    streams = payload.get("streams", [])
    if not streams:
        raise RuntimeError(f"No video stream found in {path}.")
    for key in ("avg_frame_rate", "r_frame_rate"):
        value = streams[0].get(key)
        if value:
            rate = float(Fraction(value))
            if rate > 0:
                return rate
    raise RuntimeError(f"Could not read a valid video frame rate from {path}.")


def media_files(folder: Path) -> list[Path]:
    exts = {".mp4", ".mov", ".m4v", ".wav", ".aif", ".aiff", ".mp3", ".m4a"}
    return sorted(
        path
        for path in folder.rglob("*")
        if path.is_file() and not path.name.startswith("._") and path.suffix.lower() in exts
    )


def classify_media(paths: list[Path]) -> dict[str, list[Path]]:
    classified = {"video": [], "audio": [], "other": []}
    for path in paths:
        suffix = path.suffix.lower()
        if suffix in {".mp4", ".mov", ".m4v"}:
            classified["video"].append(path)
        elif suffix in {".wav", ".aif", ".aiff", ".mp3", ".m4a"}:
            classified["audio"].append(path)
        else:
            classified["other"].append(path)
    return classified


def timeline_summary(project, timeline) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "project": project.GetName() if project else None,
        "timeline": timeline.GetName() if timeline else None,
        "start_frame": int(timeline.GetStartFrame()) if timeline else None,
        "markers": len(timeline.GetMarkers() or {}) if timeline else None,
        "tracks": {},
    }
    if not timeline:
        return summary
    for media_type in ("video", "audio"):
        tracks = {}
        for index in range(1, int(timeline.GetTrackCount(media_type) or 0) + 1):
            items = timeline.GetItemListInTrack(media_type, index) or []
            tracks[str(index)] = {
                "name": timeline.GetTrackName(media_type, index),
                "clip_count": len(items),
            }
        summary["tracks"][media_type] = tracks
    return summary
