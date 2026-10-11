#!/usr/bin/env python3
"""Stage transcript/story edit decisions into layered Resolve timelines."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path

from resolve_common import (
    DEFAULT_FPS,
    append_to_timeline,
    ffprobe_duration,
    ffprobe_video_fps,
    get_or_create_bin,
    get_resolve,
    json_dump,
    project_by_name,
    seconds,
    timeline_by_name,
    timeline_summary,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("decisions", type=Path)
    parser.add_argument("--project", default="Resolve Kit ChaiWithJai Capstone")
    parser.add_argument("--audio", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=Path(os.environ.get("RESOLVE_KIT_STATUS_DIR", "resolve_kit/status")))
    parser.add_argument("--replace", action="store_true")
    return parser.parse_args()


def ensure_tracks(timeline) -> None:
    while int(timeline.GetTrackCount("video") or 0) < 5:
        if not timeline.AddTrack("video"):
            raise RuntimeError("Resolve failed to add a video track.")
    while int(timeline.GetTrackCount("audio") or 0) < 4:
        if not timeline.AddTrack("audio"):
            raise RuntimeError("Resolve failed to add an audio track.")
    names = [
        ("video", 1, "V1 Semantic A-roll"),
        ("video", 2, "V2 B-roll / Whiteboard"),
        ("video", 3, "V3 Alternate Angle"),
        ("video", 4, "V4 Captions / Titles"),
        ("video", 5, "V5 Rendered Segment Reference"),
        ("audio", 1, "A1 Dialogue Source"),
        ("audio", 2, "A2 Dialogue Processed"),
        ("audio", 3, "A3 Music / Ambience"),
        ("audio", 4, "A4 SFX / Bumpers"),
    ]
    for media_type, index, name in names:
        if not timeline.SetTrackName(media_type, index, name):
            raise RuntimeError(f"Resolve failed to name {media_type} track {index} '{name}'.")


def required_file(value: str, base: Path, field: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(f"{field} does not exist or is not a file: {path}")
    return path


def validate_decisions(data: dict, base: Path) -> dict:
    normalized = dict(data)
    media_info: dict[str, tuple[float, float]] = {}
    for key in ("reel_segments", "youtube_segments"):
        segments = data.get(key)
        if not isinstance(segments, list) or not segments:
            raise ValueError(f"Decision file must contain a non-empty '{key}' list.")
        normalized_segments = []
        for index, segment in enumerate(segments, start=1):
            if not isinstance(segment, dict):
                raise ValueError(f"{key}[{index}] must be an object.")
            if "video" not in segment or "start" not in segment or "end" not in segment:
                raise ValueError(f"{key}[{index}] must include video, start, and end.")
            item = dict(segment)
            item["video"] = str(required_file(str(segment["video"]), base, f"{key}[{index}].video"))
            try:
                start = float(segment["start"])
                end = float(segment["end"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{key}[{index}] start/end must be numeric seconds.") from exc
            if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
                raise ValueError(f"{key}[{index}] must have start >= 0 and end > start.")
            media_path = item["video"]
            if media_path not in media_info:
                media_duration = ffprobe_duration(Path(media_path))
                if media_duration is None or media_duration <= 0:
                    raise RuntimeError(f"Could not read a positive duration for {media_path}.")
                media_info[media_path] = (media_duration, ffprobe_video_fps(Path(media_path)))
            if end > media_info[media_path][0]:
                raise ValueError(
                    f"{key}[{index}] ends at {end:.3f}s, beyond source duration "
                    f"{media_info[media_path][0]:.3f}s: {media_path}"
                )
            item["start"] = start
            item["end"] = end
            for optional_path in ("processed_video", "caption_image"):
                if segment.get(optional_path):
                    item[optional_path] = str(
                        required_file(str(segment[optional_path]), base, f"{key}[{index}].{optional_path}")
                    )
                    if optional_path == "processed_video":
                        processed_path = item[optional_path]
                        processed_duration = ffprobe_duration(Path(processed_path))
                        try:
                            expected_duration = float(segment.get("output_duration_seconds", end - start))
                        except (TypeError, ValueError) as exc:
                            raise ValueError(
                                f"{key}[{index}].output_duration_seconds must be numeric."
                            ) from exc
                        if (
                            not math.isfinite(expected_duration)
                            or expected_duration <= 0
                            or processed_duration is None
                            or processed_duration < expected_duration
                        ):
                            raise ValueError(
                                f"{key}[{index}].processed_video is shorter than its declared output duration."
                            )
                        media_info[processed_path] = (
                            processed_duration,
                            ffprobe_video_fps(Path(processed_path)),
                        )
            normalized_segments.append(item)
        normalized[key] = normalized_segments

    if data.get("audio_source"):
        normalized["audio_source"] = str(required_file(str(data["audio_source"]), base, "audio_source"))
    return normalized


def stage_timeline(
    project,
    media_pool,
    media_storage,
    bin_folder,
    name: str,
    segments: list[dict],
    audio_path: Path | None,
    replace: bool,
):
    old = timeline_by_name(project, name)
    if old and not replace:
        return timeline_summary(project, old)
    if old and replace:
        if not media_pool.DeleteTimelines([old]):
            raise RuntimeError(f"Resolve could not delete timeline {name!r} for replacement.")
        old = None
    timeline = old or media_pool.CreateEmptyTimeline(name)
    if not timeline:
        raise RuntimeError(f"Could not create timeline {name!r}.")
    if not project.SetCurrentTimeline(timeline):
        raise RuntimeError(f"Could not make timeline {name!r} current.")
    ensure_tracks(timeline)

    imported = {}
    for item in bin_folder.GetClipList() or []:
        properties = item.GetClipProperty() or {}
        source_path = properties.get("File Path")
        if source_path:
            imported[str(Path(source_path).resolve()).casefold()] = item

    def import_item(path: Path):
        key = str(path.resolve()).casefold()
        item = imported.get(key)
        if not item:
            added = media_storage.AddItemListToMediaPool([str(path)])
            if not added:
                raise RuntimeError(f"Could not import {path}")
            item = added[0]
            imported[key] = item
        return item

    start_frame = int(timeline.GetStartFrame())
    timeline_fps = float(timeline.GetSetting("timelineFrameRate") or DEFAULT_FPS)
    if timeline_fps <= 0:
        raise RuntimeError(f"Resolve returned invalid timeline frame rate {timeline_fps}.")
    record = 0
    staged = []
    source_frame_rates: dict[str, float] = {}
    audio_item = import_item(audio_path) if audio_path else None

    for idx, segment in enumerate(segments, start=1):
        src_video = Path(segment["video"])
        video_item = import_item(src_video)
        src_in = float(segment["start"])
        src_out = float(segment["end"])
        duration_frames = seconds(src_out - src_in, timeline_fps)
        if duration_frames < 1:
            raise ValueError(f"Segment {idx} is shorter than one timeline frame.")
        source_key = str(src_video)
        source_fps = source_frame_rates.get(source_key)
        if source_fps is None:
            source_fps = ffprobe_video_fps(src_video)
            source_frame_rates[source_key] = source_fps
        source_start = seconds(src_in, source_fps)
        source_end = seconds(src_out, source_fps) - 1
        if source_end < source_start:
            raise ValueError(f"Segment {idx} produced an invalid source-frame range.")
        rec = start_frame + record
        mode = segment.get("mode", "")
        track = 1
        if "board" in mode:
            track = 2
        elif "wide" in mode:
            track = 3

        append_to_timeline(
            media_pool,
            [
                {
                    "mediaPoolItem": video_item,
                    "startFrame": source_start,
                    "endFrame": source_end,
                    "recordFrame": rec,
                    "mediaType": 1,
                    "trackIndex": track,
                }
            ]
        )
        if audio_item:
            append_to_timeline(
                media_pool,
                [
                    {
                        "mediaPoolItem": audio_item,
                        "startFrame": seconds(src_in, timeline_fps),
                        "endFrame": seconds(src_out, timeline_fps) - 1,
                        "recordFrame": rec,
                        "mediaType": 2,
                        "trackIndex": 1,
                    }
                ]
            )
        processed = segment.get("processed_video")
        if processed:
            ref_item = import_item(Path(processed))
            processed_fps = ffprobe_video_fps(Path(processed))
            processed_end = seconds(
                float(segment.get("output_duration_seconds", src_out - src_in)),
                processed_fps,
            ) - 1
            append_to_timeline(
                media_pool,
                [
                    {
                        "mediaPoolItem": ref_item,
                        "startFrame": 0,
                        "endFrame": processed_end,
                        "recordFrame": rec,
                        "mediaType": 1,
                        "trackIndex": 5,
                    }
                ]
            )
            append_to_timeline(
                media_pool,
                [
                    {
                        "mediaPoolItem": ref_item,
                        "startFrame": 0,
                        "endFrame": processed_end,
                        "recordFrame": rec,
                        "mediaType": 2,
                        "trackIndex": 2,
                    }
                ]
            )

        caption_image = segment.get("caption_image")
        if caption_image:
            caption_item = import_item(Path(caption_image))
            append_to_timeline(
                media_pool,
                [
                    {
                        "mediaPoolItem": caption_item,
                        "startFrame": 0,
                        "endFrame": duration_frames - 1,
                        "recordFrame": rec,
                        "mediaType": 1,
                        "trackIndex": 4,
                    }
                ]
            )

        label = segment.get("label") or segment.get("name") or f"Segment {idx}"
        note = f"{segment.get('name', '')} | {segment.get('reason', '')}".strip()
        if not timeline.AddMarker(rec, "Blue", f"{idx}. {label}", note, duration_frames, f"semantic_{idx}"):
            raise RuntimeError(f"Resolve failed to add marker for segment {idx}.")
        staged.append(
            {
                "index": idx,
                "label": label,
                "source": str(src_video),
                "source_seconds": [src_in, src_out],
                "record_frame": rec,
                "track": track,
                "caption_text": segment.get("caption_text"),
                "caption_image": caption_image,
            }
        )
        record += duration_frames + seconds(0.25, timeline_fps)

    for media_type, index, enabled in (("audio", 1, False), ("audio", 2, True), ("video", 5, False)):
        if not timeline.SetTrackEnable(media_type, index, enabled):
            raise RuntimeError(f"Resolve failed to set enabled state for {media_type} track {index}.")

    report = timeline_summary(project, timeline)
    report["segments"] = staged
    return report


def main() -> int:
    args = parse_args()
    decisions_path = args.decisions.expanduser().resolve()
    data = json.loads(decisions_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Decision file root must be a JSON object.")
    data = validate_decisions(data, decisions_path.parent)
    audio_path = args.audio.expanduser().resolve() if args.audio else (
        Path(data["audio_source"]) if data.get("audio_source") else None
    )
    if audio_path and not audio_path.is_file():
        raise FileNotFoundError(f"Audio source does not exist or is not a file: {audio_path}")
    if audio_path:
        audio_duration = ffprobe_duration(audio_path)
        last_source_time = max(
            float(segment["end"])
            for key in ("reel_segments", "youtube_segments")
            for segment in data[key]
        )
        if (
            audio_duration is None
            or not math.isfinite(audio_duration)
            or audio_duration < last_source_time
        ):
            raise ValueError(
                f"Audio source duration ({audio_duration or 0:.3f}s) is shorter than "
                f"the latest selected source time ({last_source_time:.3f}s): {audio_path}"
            )

    resolve = get_resolve()
    project_manager = resolve.GetProjectManager()
    project = project_by_name(project_manager, args.project)
    media_pool = project.GetMediaPool()
    media_storage = resolve.GetMediaStorage()
    root = media_pool.GetRootFolder()
    bin_folder = get_or_create_bin(media_pool, root, "Capstone Semantic Sources")
    if not bin_folder or not media_pool.SetCurrentFolder(bin_folder):
        raise RuntimeError("Resolve could not select the semantic source bin.")

    reports = {}
    for key, timeline_name, segments in [
        ("reel", "CAPSTONE Instagram Semantic Cut", data["reel_segments"]),
        ("youtube", "CAPSTONE YouTube Semantic Cut", data["youtube_segments"]),
    ]:
        reports[key] = stage_timeline(
            project,
            media_pool,
            media_storage,
            bin_folder,
            timeline_name,
            segments,
            audio_path,
            args.replace,
        )

    if not resolve.OpenPage("edit"):
        raise RuntimeError("Resolve could not open the Edit page.")
    if not project_manager.SaveProject():
        raise RuntimeError("Resolve could not save the semantic edit timeline.")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out = args.output_dir / "kvibe3_semantic_capstone_resolve_report.json"
    json_dump(out, {"project": args.project, "reports": reports})
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
