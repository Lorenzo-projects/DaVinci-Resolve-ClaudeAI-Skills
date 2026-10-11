#!/usr/bin/env python3
"""Audit a DaVinci Resolve timeline for editable social-video handoff issues."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from resolve_scripting import get_resolve


def tc_to_frames(tc: str, fps: float) -> int | None:
    try:
        hh, mm, ss, ff = [int(part) for part in tc.split(":")]
    except Exception:
        return None
    return int(round(((hh * 3600) + (mm * 60) + ss) * fps + ff))


def item_payload(item, fps: float) -> dict:
    start = int(item.GetStart())
    end = int(item.GetEnd())
    name = item.GetName() or ""
    source = ""
    media = item.GetMediaPoolItem()
    if media:
        props = media.GetClipProperty() or {}
        source = props.get("File Path") or props.get("Filename") or ""
    return {
        "name": name,
        "source": source,
        "start_frame": start,
        "end_frame": end,
        "start_timecode": frames_to_tc(start, fps),
        "end_timecode": frames_to_tc(end, fps),
        "enabled": bool(item.GetClipEnabled()),
    }


def is_caption_like(item: dict) -> bool:
    haystack = f"{item.get('name', '')} {item.get('source', '')}".lower()
    return any(token in haystack for token in ("caption", "subtitle", "/cap_", "cap_"))


def frames_to_tc(frame: int, fps: float) -> str:
    fps_i = int(round(fps)) or 24
    total_seconds, ff = divmod(max(frame, 0), fps_i)
    hh, rem = divmod(total_seconds, 3600)
    mm, ss = divmod(rem, 60)
    return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"


def get_project(pm, name: str | None):
    if not name:
        project = pm.GetCurrentProject()
        if project:
            return project
        raise SystemExit("No current Resolve project.")
    current = pm.GetCurrentProject()
    if current and current.GetName() == name:
        return current
    project = pm.LoadProject(name)
    if project:
        return project
    raise SystemExit(f"Could not load Resolve project: {name}")


def get_timeline(project, name: str | None):
    if not name:
        timeline = project.GetCurrentTimeline()
        if timeline:
            return timeline
        raise SystemExit("No current Resolve timeline.")
    for idx in range(1, int(project.GetTimelineCount()) + 1):
        timeline = project.GetTimelineByIndex(idx)
        if timeline and timeline.GetName() == name:
            if not project.SetCurrentTimeline(timeline):
                raise SystemExit(f"Could not select Resolve timeline: {name}")
            return timeline
    raise SystemExit(f"Could not find timeline: {name}")


def audit(project_name: str | None, timeline_name: str | None) -> dict:
    resolve = get_resolve()
    pm = resolve.GetProjectManager()
    project = get_project(pm, project_name)
    timeline = get_timeline(project, timeline_name)

    fps = float(timeline.GetSetting("timelineFrameRate") or 24)
    start_frame = int(timeline.GetStartFrame())
    end_frame = int(timeline.GetEndFrame())
    current_tc = timeline.GetCurrentTimecode()
    current_frame = tc_to_frames(current_tc, fps)

    tracks: list[dict] = []
    warnings: list[str] = []
    min_clip_start: int | None = None
    max_video_end: int | None = None
    max_audio_end: int | None = None
    enabled_audio = 0
    caption_like_items = 0
    video_items = 0

    for media_type in ("video", "audio", "subtitle"):
        count = int(timeline.GetTrackCount(media_type))
        for track_index in range(1, count + 1):
            items = [item_payload(item, fps) for item in timeline.GetItemListInTrack(media_type, track_index)]
            for item in items:
                min_clip_start = item["start_frame"] if min_clip_start is None else min(min_clip_start, item["start_frame"])
                if item["start_frame"] < start_frame:
                    warnings.append(
                        f"{media_type.upper()} track {track_index} item '{item['name']}' starts before timeline start "
                        f"({item['start_frame']} < {start_frame})."
                    )
                if media_type == "video":
                    video_items += 1
                    max_video_end = item["end_frame"] if max_video_end is None else max(max_video_end, item["end_frame"])
                    if is_caption_like(item):
                        caption_like_items += 1
                elif media_type == "subtitle":
                    caption_like_items += 1
                else:
                    max_audio_end = item["end_frame"] if max_audio_end is None else max(max_audio_end, item["end_frame"])
                    if item["enabled"]:
                        enabled_audio += 1
            tracks.append({"type": media_type, "index": track_index, "items": items})

    markers = timeline.GetMarkers() or {}
    marker_payload = []
    for frame, marker in markers.items():
        marker_payload.append({"frame": int(frame), **marker})

    if video_items == 0:
        warnings.append("Timeline has no video items.")
    if enabled_audio == 0:
        warnings.append("Timeline has no enabled audio items.")
    if caption_like_items == 0:
        warnings.append("No subtitle-track or caption-like video items were found.")
    if max_video_end and max_audio_end and max_audio_end - max_video_end > int(round(fps)):
        warnings.append("Audio extends more than one second past the video tail.")
    if current_frame is not None and max_video_end and not (start_frame <= current_frame <= max_video_end):
        warnings.append(
            f"Current playhead {current_tc} is outside visible picture range "
            f"{frames_to_tc(start_frame, fps)}-{frames_to_tc(max_video_end, fps)}."
        )
    if min_clip_start is not None and min_clip_start < start_frame:
        warnings.append("At least one clip is before Resolve's visible timeline start; this can make the UI look empty.")

    return {
        "project": project.GetName(),
        "timeline": timeline.GetName(),
        "fps": fps,
        "start_frame": start_frame,
        "end_frame": end_frame,
        "start_timecode": timeline.GetStartTimecode(),
        "current_timecode": current_tc,
        "tracks": tracks,
        "markers": sorted(marker_payload, key=lambda row: row["frame"]),
        "warnings": warnings,
        "pass": not warnings,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", help="Resolve project name. Defaults to current project.")
    parser.add_argument("--timeline", help="Timeline name. Defaults to current timeline.")
    parser.add_argument("--out", help="Write JSON audit to this path.")
    args = parser.parse_args()

    result = audit(args.project, args.timeline)
    payload = json.dumps(result, indent=2)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    if result["warnings"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
