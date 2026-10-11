#!/usr/bin/env python3
"""Create a native, editable subtitle track from a Resolve timeline's audio."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from resolve_scripting import get_resolve


LANGUAGES = {
    "auto": "AUTO",
    "danish": "DANISH",
    "dutch": "DUTCH",
    "english": "ENGLISH",
    "french": "FRENCH",
    "german": "GERMAN",
    "italian": "ITALIAN",
    "japanese": "JAPANESE",
    "korean": "KOREAN",
    "mandarin-simplified": "MANDARIN_SIMPLIFIED",
    "mandarin-traditional": "MANDARIN_TRADITIONAL",
    "norwegian": "NORWEGIAN",
    "portuguese": "PORTUGUESE",
    "russian": "RUSSIAN",
    "spanish": "SPANISH",
    "swedish": "SWEDISH",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", help="Resolve project name. Defaults to the open project.")
    parser.add_argument("--timeline", help="Timeline name. Defaults to the current timeline.")
    parser.add_argument("--language", choices=sorted(LANGUAGES), default="auto")
    parser.add_argument("--style", choices=("default", "netflix", "teletext"), default="netflix")
    parser.add_argument("--chars-per-line", type=int, default=32)
    parser.add_argument("--gap", type=int, default=0)
    parser.add_argument("--single-line", action="store_true")
    parser.add_argument("--out", type=Path, help="Optional JSON report path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 1 <= args.chars_per_line <= 60:
        raise ValueError("--chars-per-line must be from 1 to 60.")
    if not 0 <= args.gap <= 10:
        raise ValueError("--gap must be from 0 to 10.")

    resolve = get_resolve()
    project_manager = resolve.GetProjectManager()
    project = project_manager.GetCurrentProject()
    if args.project and (not project or project.GetName() != args.project):
        project = project_manager.LoadProject(args.project)
    if not project:
        raise RuntimeError("No Resolve project is open or loadable.")
    timeline = None
    if args.timeline:
        for index in range(1, int(project.GetTimelineCount() or 0) + 1):
            candidate = project.GetTimelineByIndex(index)
            if candidate and candidate.GetName() == args.timeline:
                timeline = candidate
                break
        if timeline and not project.SetCurrentTimeline(timeline):
            raise RuntimeError(f"Could not select timeline {args.timeline!r}.")
    else:
        timeline = project.GetCurrentTimeline()
    if not timeline:
        raise RuntimeError("No Resolve timeline is current or loadable.")

    audio_clip_count = sum(
        len(timeline.GetItemListInTrack("audio", index) or [])
        for index in range(1, int(timeline.GetTrackCount("audio") or 0) + 1)
    )
    if audio_clip_count == 0:
        raise RuntimeError("The selected timeline has no audio clips to caption.")

    existing_subtitle_tracks = []
    for index in range(1, int(timeline.GetTrackCount("subtitle") or 0) + 1):
        items = timeline.GetItemListInTrack("subtitle", index) or []
        if items:
            existing_subtitle_tracks.append(index)
    if existing_subtitle_tracks:
        raise RuntimeError(
            "The timeline already contains subtitle clips on track(s) "
            f"{existing_subtitle_tracks}; remove or review them before generating another set."
        )

    preset_suffix = {
        "default": "SUBTITLE_DEFAULT",
        "netflix": "NETFLIX",
        "teletext": "TELETEXT",
    }[args.style]
    line_break_suffix = "SINGLE" if args.single_line else "DOUBLE"
    settings = {
        resolve.SUBTITLE_LANGUAGE: getattr(resolve, f"AUTO_CAPTION_{LANGUAGES[args.language]}"),
        resolve.SUBTITLE_CAPTION_PRESET: getattr(resolve, f"AUTO_CAPTION_{preset_suffix}"),
        resolve.SUBTITLE_CHARS_PER_LINE: args.chars_per_line,
        resolve.SUBTITLE_LINE_BREAK: getattr(resolve, f"AUTO_CAPTION_LINE_{line_break_suffix}"),
        resolve.SUBTITLE_GAP: args.gap,
    }
    if not timeline.CreateSubtitlesFromAudio(settings):
        raise RuntimeError(
            "Resolve could not create subtitles. Check that its speech-to-text model/required Extras "
            "are installed, the selected audio is usable, and the API is supported by this Resolve build."
        )

    subtitle_tracks = []
    for index in range(1, int(timeline.GetTrackCount("subtitle") or 0) + 1):
        items = timeline.GetItemListInTrack("subtitle", index) or []
        if items:
            subtitle_tracks.append(
                {
                    "index": index,
                    "name": timeline.GetTrackName("subtitle", index),
                    "clip_count": len(items),
                    "sample_text": [item.GetName() for item in items[:5]],
                }
            )
    if not subtitle_tracks:
        raise RuntimeError("Resolve returned success but no subtitle clips were readable afterward.")
    if not project_manager.SaveProject():
        raise RuntimeError("Subtitles were generated, but Resolve could not save the project.")

    report = {
        "project": project.GetName(),
        "timeline": timeline.GetName(),
        "resolve_version": resolve.GetVersionString(),
        "language": args.language,
        "style": args.style,
        "audio_clip_count": audio_clip_count,
        "subtitle_tracks": subtitle_tracks,
        "review_required": True,
        "notes": [
            "Resolve-generated captions are editable subtitles, not proofread copy.",
            "Check speaker names, punctuation, timing, line breaks, and safe areas before delivery.",
        ],
    }
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
