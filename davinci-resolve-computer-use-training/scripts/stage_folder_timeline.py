#!/usr/bin/env python3
"""Stage a local media folder into an editable Resolve timeline."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from resolve_common import (
    DEFAULT_FPS,
    append_to_timeline,
    classify_media,
    ffprobe_duration,
    ffprobe_video_fps,
    get_or_create_bin,
    get_resolve,
    json_dump,
    media_files,
    project_by_name,
    seconds,
    timeline_by_name,
    timeline_summary,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("--project", default="Resolve Kit Autocut")
    parser.add_argument("--timeline", default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--fps", type=float, default=DEFAULT_FPS)
    parser.add_argument("--max-seconds", type=float, default=180.0)
    parser.add_argument("--replace", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    folder = args.folder.expanduser().resolve()
    if not folder.exists():
        raise FileNotFoundError(folder)
    if not folder.is_dir():
        raise NotADirectoryError(folder)
    if not math.isfinite(args.fps) or args.fps <= 0:
        raise ValueError("--fps must be greater than zero.")
    if not math.isfinite(args.max_seconds) or args.max_seconds <= 0:
        raise ValueError("--max-seconds must be greater than zero.")

    timeline_name = args.timeline or f"{folder.name} - Layered Rough Cut"
    output = args.output or folder / "work" / "resolve_stage_report.json"

    paths = media_files(folder)
    classified = classify_media(paths)
    if not classified["video"]:
        raise RuntimeError(f"No video files found in {folder}")

    videos = classified["video"]
    audios = classified["audio"]
    primary_video = next((p for p in videos if "cam 2" in p.name.lower()), videos[0])
    clean_audio = next((p for p in audios if "mic 1" in p.name.lower()), audios[0] if audios else None)
    duration = ffprobe_duration(primary_video)
    if duration is None or duration <= 0:
        raise RuntimeError(f"Could not determine a positive duration for {primary_video}.")
    total = min(duration, args.max_seconds)
    source_fps = ffprobe_video_fps(primary_video)

    resolve = get_resolve()
    project_manager = resolve.GetProjectManager()
    project = project_by_name(project_manager, args.project)
    if not project:
        raise RuntimeError(f"Could not load/create project {args.project!r}")

    old = timeline_by_name(project, timeline_name)
    if old and not args.replace:
        report = timeline_summary(project, old)
        report["status"] = "existing timeline left unchanged; pass --replace to rebuild"
        json_dump(output, report)
        print(output)
        return 0

    media_storage = resolve.GetMediaStorage()
    media_pool = project.GetMediaPool()
    root = media_pool.GetRootFolder()
    source_bin = get_or_create_bin(media_pool, root, f"{folder.name} Source")
    if not source_bin or not media_pool.SetCurrentFolder(source_bin):
        raise RuntimeError("Resolve could not select the source bin.")

    imported = {}
    existing_by_path = {}
    for item in source_bin.GetClipList() or []:
        properties = item.GetClipProperty() or {}
        source_path = properties.get("File Path")
        if source_path:
            existing_by_path[str(Path(source_path).resolve()).casefold()] = item
    for path in classified["video"] + classified["audio"]:
        item = existing_by_path.get(str(path.resolve()).casefold())
        if not item:
            added = media_storage.AddItemListToMediaPool([str(path)])
            if not added:
                raise RuntimeError(f"Resolve could not import {path}.")
            item = added[0]
            existing_by_path[str(path.resolve()).casefold()] = item
        imported[str(path)] = item

    if not project.SetSetting("timelineFrameRate", str(args.fps)):
        raise RuntimeError(f"Resolve rejected project timeline frame rate {args.fps}.")
    if old and args.replace:
        if not media_pool.DeleteTimelines([old]):
            raise RuntimeError(f"Resolve could not delete timeline {timeline_name!r} for replacement.")
        old = None

    timeline = old or media_pool.CreateEmptyTimeline(timeline_name)
    if not timeline:
        raise RuntimeError(f"Could not create timeline {timeline_name!r}")

    if not project.SetCurrentTimeline(timeline):
        raise RuntimeError(f"Could not make timeline {timeline_name!r} current.")
    if not resolve.OpenPage("edit"):
        raise RuntimeError("Resolve could not open the Edit page.")

    while int(timeline.GetTrackCount("video") or 0) < 4:
        if not timeline.AddTrack("video"):
            raise RuntimeError("Resolve failed to add a video track.")
    while int(timeline.GetTrackCount("audio") or 0) < 4:
        if not timeline.AddTrack("audio"):
            raise RuntimeError("Resolve failed to add an audio track.")

    track_names = [
        ("video", 1, "V1 Primary A-roll"),
        ("video", 2, "V2 B-roll / Whiteboard / Cutaways"),
        ("video", 3, "V3 Alternate Angle"),
        ("video", 4, "V4 Captions / Titles / Graphics"),
        ("audio", 1, "A1 Clean Dialogue"),
        ("audio", 2, "A2 Scratch / Camera Audio"),
        ("audio", 3, "A3 Music / Ambience"),
        ("audio", 4, "A4 SFX / Bumpers"),
    ]
    for media_type, index, name in track_names:
        if not timeline.SetTrackName(media_type, index, name):
            raise RuntimeError(f"Resolve failed to name {media_type} track {index} '{name}'.")

    beat_count = 6
    beat_len = total / beat_count
    start_frame = int(timeline.GetStartFrame())
    record = 0
    beats = []

    for idx in range(beat_count):
        src_in = idx * beat_len
        src_out = min(src_in + beat_len, duration)
        if src_out <= src_in:
            break
        source_start = seconds(src_in, source_fps)
        source_end = seconds(src_out, source_fps) - 1
        duration_frames = seconds(src_out - src_in, args.fps)
        if source_end < source_start or duration_frames < 1:
            raise RuntimeError(f"Calculated an invalid frame range for rough-cut beat {idx + 1}.")
        rec = start_frame + record
        clip_infos = [
            {
                "mediaPoolItem": imported[str(primary_video)],
                "startFrame": source_start,
                "endFrame": source_end,
                "recordFrame": rec,
                "mediaType": 1,
                "trackIndex": 1,
            }
        ]
        if clean_audio:
            clip_infos.append(
                {
                    "mediaPoolItem": imported[str(clean_audio)],
                    "startFrame": seconds(src_in, args.fps),
                    "endFrame": seconds(src_out, args.fps) - 1,
                    "recordFrame": rec,
                    "mediaType": 2,
                    "trackIndex": 1,
                }
            )
        append_to_timeline(media_pool, clip_infos)

        marker_name = f"{idx + 1}. Rough slice {idx + 1}"
        note = "Equal-duration source slice; not a transcript-confirmed story beat."
        if not timeline.AddMarker(rec, "Blue", marker_name, note, duration_frames, f"rough_slice_{idx + 1}"):
            raise RuntimeError(f"Resolve failed to add marker for rough-cut slice {idx + 1}.")
        beats.append({"name": marker_name, "source_seconds": [src_in, src_out], "record_frame": rec})
        record += duration_frames

    if not project_manager.SaveProject():
        raise RuntimeError("Resolve could not save the staged project.")

    report = timeline_summary(project, timeline)
    report.update(
        {
            "status": "timed_rough_cut_seed_not_semantic_edit",
            "folder": str(folder),
            "primary_video": str(primary_video),
            "clean_audio": str(clean_audio) if clean_audio else None,
            "source_frame_rate": source_fps,
            "beats": beats,
            "warnings": [
                "Six equal time slices are only a rough-cut seed; they do not represent transcript-verified story beats.",
                "Camera angles were not auto-switched; review and rebuild from semantic edit decisions.",
            ],
        }
    )
    json_dump(output, report)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
