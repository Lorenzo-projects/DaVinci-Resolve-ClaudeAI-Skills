#!/usr/bin/env python3
"""
multi_platform_render.py — Queue and render every timeline in the current
DaVinci Resolve project against a matching platform preset, based on the
timeline's aspect ratio.

This script:
  1. Walks every timeline in the current project.
  2. Determines each timeline's aspect ratio (16:9, 1:1, or 9:16).
  3. Loads the matching render preset by name.
  4. Adds a render job to the Render Queue.
  5. Asks for stdin confirmation before starting the actual render.
  6. Calls StartRendering() and reports progress.

Required preset names (rename in PRESET_BY_ASPECT below if yours differ):
  - "DEVREL_YOUTUBE_1080"   for 16:9 (1920x1080)
  - "DEVREL_LINKEDIN_1080"  for 1:1  (1080x1080)
  - "DEVREL_SHORTS_1080"    for 9:16 (1080x1920)

Requirements:
  - DaVinci Resolve 21 (free or Studio) running with a project open.
  - The three render presets above must already exist. Create them by
    following the steps in SKILL.md (Phase 3 — Build the three render
    presets).
  - External scripting enabled: Preferences > System > General >
    External scripting using = Local.
  - Python 3.9+.

The helper resolves the platform-specific SDK paths documented by Blackmagic.
Set RESOLVE_SCRIPT_API and RESOLVE_SCRIPT_LIB manually only for custom installs.

API surface used (all documented in Reference Manual and Developer/Scripting/README.txt):
  Resolve.GetProjectManager()
  ProjectManager.GetCurrentProject()
  Project.GetTimelineCount()
  Project.GetTimelineByIndex(idx)
  Project.SetCurrentTimeline(timeline)
  Project.LoadRenderPreset(presetName)
  Project.SetRenderSettings(settings_dict)
  Project.AddRenderJob()
  Project.StartRendering()
  Project.IsRenderingInProgress()
  Project.GetRenderJobStatus(jobId)
  Timeline.GetName()
  Timeline.GetSetting(setting_name)
"""

import argparse
import sys
import time
from pathlib import Path

from resolve_scripting import get_resolve as get_resolve_from_sdk


# Map aspect ratio (width:height ratio rounded to 2 decimals) to preset name.
PRESET_BY_ASPECT = {
    1.78: "DEVREL_YOUTUBE_1080",   # 1920x1080 = 16:9
    1.00: "DEVREL_LINKEDIN_1080",  # 1080x1080 = 1:1
    0.56: "DEVREL_SHORTS_1080",    # 1080x1920 = 9:16
}


def get_resolve():
    try:
        return get_resolve_from_sdk()
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc


def get_timeline_aspect(timeline):
    """
    Return (width, height, aspect) for a timeline. Aspect is rounded to
    2 decimal places so we can dict-lookup the preset.
    """
    try:
        width = int(timeline.GetSetting("timelineResolutionWidth"))
        height = int(timeline.GetSetting("timelineResolutionHeight"))
    except (TypeError, ValueError):
        return None, None, None
    if height == 0:
        return width, height, None
    return width, height, round(width / height, 2)


def plan_render_jobs(project):
    """
    Walk every timeline in the project and return a list of
    (timeline, preset_name, width, height) tuples that should be rendered.
    """
    plan = []
    count = project.GetTimelineCount()
    if count == 0:
        print("ERROR: Project has no timelines.")
        sys.exit(1)

    for i in range(1, count + 1):
        timeline = project.GetTimelineByIndex(i)
        if timeline is None:
            continue
        name = timeline.GetName()
        width, height, aspect = get_timeline_aspect(timeline)
        if aspect is None:
            print(f"  Skipping '{name}' (could not read resolution)")
            continue
        preset = PRESET_BY_ASPECT.get(aspect)
        if preset is None:
            print(
                f"  Skipping '{name}' ({width}x{height}, aspect {aspect})"
                f" — no preset mapped for this aspect ratio"
            )
            continue
        plan.append((timeline, preset, width, height))
    return plan


def confirm(prompt):
    try:
        answer = input(f"{prompt} [y/N]: ").strip().lower()
    except EOFError:
        return False
    return answer == "y"


def queue_render_jobs(project, plan, output_dir):
    """Add a render job to the queue for each timeline in the plan."""
    queued = []
    original_timeline = project.GetCurrentTimeline()
    try:
        for timeline, preset, width, height in plan:
            name = timeline.GetName()
            print(f"\nQueueing: {name} ({width}x{height}) -> preset '{preset}'")

            if not project.SetCurrentTimeline(timeline):
                print(f"  WARNING: Could not set current timeline to '{name}'")
                continue

            if not project.LoadRenderPreset(preset):
                print(
                    f"  WARNING: Could not load preset '{preset}'. Does it exist?\n"
                    f"           Create it via SKILL.md Phase 3 first."
                )
                continue

            settings = {"TargetDir": str(output_dir)}
            if not project.SetRenderSettings(settings):
                print("  WARNING: Could not set render settings (TargetDir).")
                continue

            job_id = project.AddRenderJob()
            if not job_id:
                print("  WARNING: AddRenderJob() returned no id.")
                continue
            print(f"  Queued job id: {job_id}")
            queued.append(job_id)
    finally:
        if original_timeline:
            project.SetCurrentTimeline(original_timeline)
    return queued


def render_all_and_wait(project, job_ids):
    """Start rendering and poll until the queue completes."""
    if not project.StartRendering(job_ids):
        print("ERROR: StartRendering() returned False.")
        return False

    print(f"\nRendering {len(job_ids)} requested jobs. Polling every 5 seconds...")
    while project.IsRenderingInProgress():
        time.sleep(5)
        for job_id in job_ids:
            status = project.GetRenderJobStatus(job_id) or {}
            state = status.get("JobStatus", "unknown")
            percentage = status.get("CompletionPercentage", "unknown")
            print(f"  {job_id}: {state} ({percentage}%)")

    unsuccessful = []
    for job_id in job_ids:
        status = project.GetRenderJobStatus(job_id) or {}
        state = status.get("JobStatus", "unknown")
        if state not in {"Complete", "Completed"}:
            unsuccessful.append({"job_id": job_id, "status": status})

    if unsuccessful:
        print(f"ERROR: {len(unsuccessful)} render job(s) did not report completion:")
        for result in unsuccessful:
            print(f"  {result}")
        return False

    print("All requested renders completed.")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, help="Render destination. Prompts when omitted.")
    parser.add_argument("--yes", action="store_true", help="Queue and render the planned timelines without prompts.")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan without queueing or rendering.")
    args = parser.parse_args()

    resolve = get_resolve()
    pm = resolve.GetProjectManager()
    project = pm.GetCurrentProject()
    if project is None:
        print("ERROR: No project is currently open.")
        sys.exit(1)

    print(f"\nProject: {project.GetName()}")
    print("Planning render jobs based on timeline aspect ratios...\n")
    plan = plan_render_jobs(project)
    if not plan:
        print("\nNothing to render. Exiting.")
        return

    print(f"\nPlanned {len(plan)} render jobs:")
    for timeline, preset, width, height in plan:
        print(f"  - {timeline.GetName()} ({width}x{height}) -> {preset}")

    if args.dry_run:
        print("\nDry run complete. No render jobs were queued.")
        return

    default_dir = Path.home() / ("Movies" if sys.platform == "darwin" else "Videos") / "Resolve_Renders"
    output_dir = args.output_dir
    if output_dir is None:
        output_text = input(f"\nOutput directory [default: {default_dir}]: ").strip()
        output_dir = Path(output_text).expanduser() if output_text else default_dir
    output_dir = output_dir.expanduser().resolve()

    if not args.yes and not confirm(f"\nProceed to queue {len(plan)} jobs?"):
        print("Cancelled. No jobs queued.")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    queued = queue_render_jobs(project, plan, output_dir)
    if not queued:
        print("\nNo jobs queued successfully. Exiting.")
        raise SystemExit(1)

    if not args.yes and not confirm(f"\n{len(queued)} jobs queued. Start rendering?"):
        print("Jobs are queued in Resolve. You can render them manually from the Deliver page.")
        return

    if not render_all_and_wait(project, queued):
        raise SystemExit(2)
    print(f"\nOutput files should be in: {output_dir}")


if __name__ == "__main__":
    main()
