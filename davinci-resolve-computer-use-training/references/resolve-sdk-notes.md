# Resolve SDK Notes

These notes are aligned with the Resolve 21 scripting API and a locally
installed Resolve 21 SDK. Resolve ships the authoritative README and examples;
check those against the exact build installed on the target machine before
depending on a version-specific operation.

## Supported Invocation

- Python and Lua scripts are supported.
- Resolve must be running for normal external scripting.
- Scripts can be run from the Fusion console, from the command line, or from Resolve's Workspace > Scripts menu.
- External scripting access is controlled in Resolve Preferences. Use local access for AI-assisted workflows unless a network workflow is explicitly required.

## Default SDK Locations

Windows:

```text
RESOLVE_SCRIPT_API=%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting
RESOLVE_SCRIPT_LIB=%PROGRAMFILES%\Blackmagic Design\DaVinci Resolve\fusionscript.dll
Modules=%RESOLVE_SCRIPT_API%\Modules
User scripts=%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts
```

macOS:

```bash
export RESOLVE_SCRIPT_API="/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
export RESOLVE_SCRIPT_LIB="/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"
export PYTHONPATH="$PYTHONPATH:$RESOLVE_SCRIPT_API/Modules/"
```

Linux default locations used by the helpers:

```text
RESOLVE_SCRIPT_API=/opt/resolve/Developer/Scripting
RESOLVE_SCRIPT_LIB=/opt/resolve/libs/Fusion/fusionscript.so
Modules=$RESOLVE_SCRIPT_API/Modules
User scripts=~/.local/share/DaVinciResolve/Fusion/Scripts
```

Set `RESOLVE_SCRIPT_API` and `RESOLVE_SCRIPT_LIB` explicitly for custom
installations. The Resolve scripting API must be enabled in Preferences and
Resolve must be running for normal external scripting.

## Script Menu Install Paths

Windows:

```text
%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts
```

macOS:

```text
/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts
~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts
```

Linux:

```text
~/.local/share/DaVinciResolve/Fusion/Scripts
```

Place scripts under:

- `Utility` for all pages
- page folders such as `Edit`, `Color`, or `Deliver` for page-specific actions
- `Deliver` when render-job menu availability is useful

## APIs We Should Prefer

- `resolve.OpenPage("media" | "cut" | "edit" | "fusion" | "color" | "fairlight" | "deliver")`
- `resolve.GetCurrentPage()`
- `resolve.LoadLayoutPreset`, `SaveLayoutPreset`, `ImportLayoutPreset`, `ExportLayoutPreset`
- `resolve.ImportRenderPreset`, `ExportRenderPreset`
- `resolve.ImportBurnInPreset`, `ExportBurnInPreset`
- `ProjectManager.CreateProject`, `LoadProject`, `SaveProject`, `ExportProject`, `ArchiveProject`
- `Project.GetCurrentTimeline`, `GetTimelineByIndex`, `SetCurrentTimeline`
- `Project.SetRenderSettings`, `AddRenderJob`, `StartRendering`, `GetRenderJobStatus`
- `MediaStorage.AddItemListToMediaPool`
- `MediaPool.CreateEmptyTimeline`, `AppendToTimeline`, `CreateTimelineFromClips`
- `Timeline.GetItemListInTrack` (use this documented method, not the legacy appendix entry `GetItemsInTrack`)
- `MediaPoolItem.TranscribeAudio` and `Timeline.CreateSubtitlesFromAudio` for supported transcription/caption workflows
- `Timeline.InsertFusionTitleIntoTimeline`, `InsertFusionCompositionIntoTimeline`, `InsertFusionGeneratorIntoTimeline`
- `TimelineItem.ImportFusionComp`, `ExportFusionComp`, `LoadBurnInPreset`

## Practical Implication

Successful module import only proves the Python bridge can be found. A live
connection additionally requires Resolve to be running with external scripting
enabled; timeline mutation and rendering need separate runtime validation.
Most production work should be script-first. UI automation is for proving
manual workflows, catching screenshots, and operating non-scriptable controls.
