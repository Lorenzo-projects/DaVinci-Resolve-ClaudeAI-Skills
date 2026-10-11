# DaVinci Resolve AI Skills

**A practical toolkit for turning an AI assistant into a sharper DaVinci Resolve
editing partner.** Choose a focused skill for the job, keep the creative work
editable in Resolve, and verify the result before calling it done.

This repository contains **11 independent skills** for editing, audio, color,
graphics, delivery, Resolve setup, troubleshooting, and hands-on training.

## Start here

### Claude.ai

Upload **one skill ZIP at a time** from Claude's Skills settings. Each archive
must contain that skill's `SKILL.md` at its root, together with any references
and scripts it uses. Do not upload the whole repository as one skill.

On Windows, create ready-to-upload archives for every skill:

```powershell
.\scripts\package-skills.ps1
```

The archives are written to `dist\skills\`. To package only one skill or choose
another output directory:

```powershell
.\scripts\package-skills.ps1 -Skill davinci-resolve-social-editor
.\scripts\package-skills.ps1 -OutputDirectory "$env:USERPROFILE\Desktop\resolve-skills"
```

### Claude Code

Copy the complete folder for each skill you want to use into either:

- **This project:** `.claude/skills/<skill-name>/`
- **Your user skills:** `~/.claude/skills/<skill-name>/`

Keep `SKILL.md`, `references/`, `scripts/`, and other included files together.
Claude Code can then load the skill when a task matches its description.

### Other assistants

The skill instructions are plain Markdown with YAML frontmatter and can be
adapted for other assistants that support skills. The
`davinci-resolve-social-editor/agents/openai.yaml` file is an optional
OpenAI-specific integration entry point; it is not required for Claude.

## Choose a skill

| Skill | Use it for |
|---|---|
| [`davinci-resolve-social-editor`](./davinci-resolve-social-editor/) | Story-first social edits, multicamera interviews, captions, B-roll, audio checks, and Resolve-ready handoffs. |
| [`social-video-folder-autocutter`](./social-video-folder-autocutter/) | Turning a media folder into a cut brief, story plan, and B-roll plan. |
| [`davinci-resolve-cut-screen-recording`](./davinci-resolve-cut-screen-recording/) | Tightening screen recordings, tutorials, demos, and talks by removing dead air and mistakes. |
| [`davinci-resolve-audio-cleanup-podcast`](./davinci-resolve-audio-cleanup-podcast/) | Cleaning dialogue, reducing noise and hum, and balancing music under speech. |
| [`davinci-resolve-color-grade-webcam`](./davinci-resolve-color-grade-webcam/) | Correcting exposure, white balance, skin tones, and talking-head shots. |
| [`davinci-resolve-titles-and-lower-thirds`](./davinci-resolve-titles-and-lower-thirds/) | Building branded titles, animated lower thirds, and reusable Fusion graphics. |
| [`davinci-resolve-export-multi-platform`](./davinci-resolve-export-multi-platform/) | Delivering one edit in platform-specific aspect ratios and formats. |
| [`davinci-resolve-setup`](./davinci-resolve-setup/) | Setting up Resolve, media storage, backups, proxies, and scripting preferences. |
| [`davinci-resolve-troubleshooting`](./davinci-resolve-troubleshooting/) | Diagnosing common media, playback, audio-sync, GPU, and render problems. |
| [`davinci-resolve-devrel-project-template`](./davinci-resolve-devrel-project-template/) | Creating a reusable, organized Resolve project structure for recurring videos. |
| [`davinci-resolve-computer-use-training`](./davinci-resolve-computer-use-training/) | Practicing Resolve workflows, recording evidence, and benchmarking a capstone. |

**Not sure where to begin?** Start with the Social Editor for a complete
speaker-led edit, or the Folder Autocutter when you first need to turn a drive
of source footage into a coherent plan.

## What makes this collection useful

- **Editorial judgement before automation:** protect story, context, and
  intelligibility instead of optimizing for cuts per minute.
- **Resolve-first handoffs:** favor editable timelines and review artifacts
  over a flattened render when the task calls for an ongoing project.
- **Quality gates:** inspect framing, captions, audio, exports, and timeline
  state instead of treating a successful render as proof of quality.
- **Focused modules:** install only the skill you need; its supporting
  references and scripts travel with it.
- **Practical tools:** selected skills include Python utilities and Resolve
  scripting helpers for repeatable media checks and workflows.

## Requirements and compatibility

The Markdown guidance can be used independently of the automation scripts.
Requirements vary by skill and task:

- **Resolve 21 scripting:** automation helpers use the platform-specific SDK
  locations for Windows, macOS, and Linux and the documented Resolve API names.
  Resolve must be running, external scripting enabled, and Python able to load
  the installed `fusionscript` library. Use the bundled launcher for
  diagnostics and repeatable setup.
- **Media tools:** install FFmpeg (including `ffprobe`) for media probing,
  duration/frame-rate checks, caption burn-in, and export verification. They
  are not bundled. In the environment used to maintain this repository,
  `ffmpeg`/`ffprobe` were not on `PATH`; those media-dependent flows therefore
  fail explicitly until installed.
- **AI/studio features:** native speech-to-text, Smart Reframe, and other AI
  functions depend on the installed Resolve edition, build, model downloads,
  and sometimes Blackmagic Extras. The native caption script uses
  `Timeline.CreateSubtitlesFromAudio`; it cannot guarantee transcript
  correctness and requires human review.
- **Python:** use a supported local Python installation and follow the
  relevant skill's SDK/environment instructions. Python API importability is
  not the same as a live Resolve connection or a verified edit/render.

**Compatibility evidence:** the maintained host has DaVinci Resolve
**21.0.0.48** and its Resolve 21 SDK. The SDK module imports and exposes the
documented scripting entry point. This verifies SDK discovery/import, not every
workflow against a running GUI session. No timeline staging or final render
was claimed as runtime-verified here. Run the diagnostic before production:

```powershell
.\davinci-resolve-computer-use-training\bin\resolve-kit.cmd doctor
```

```bash
./davinci-resolve-computer-use-training/bin/resolve-kit doctor
```

**Automation boundary:** this is an AI-assisted editing toolkit, not a
one-click autonomous editor. The folder timeline is only a time-based seed;
the semantic timeline script materializes reviewed edit-decision JSON. Story,
angle selection, reframing, captions, and final quality still need media-aware
planning and human approval. Native Resolve transcription can accelerate
caption creation but does not make the editorial decisions.

### Resolve 21 quick start (Windows)

1. Start Resolve and enable **Preferences > System > General > External
   scripting using: Local**.
2. Install FFmpeg and confirm both `ffmpeg` and `ffprobe` are available in
   PowerShell if you will probe media, burn in captions, or verify renders.
3. Run the diagnostic, then optionally install the Resolve menu helpers:

   ```powershell
   .\davinci-resolve-computer-use-training\bin\resolve-kit.cmd doctor
   .\davinci-resolve-computer-use-training\bin\resolve-kit.cmd install
   ```

4. Use a source-folder timeline only as a rough seed. For an edit with story
   decisions, create and review the JSON first, then run
   `davinci-resolve-computer-use-training/scripts/stage_edit_decisions.py`.
5. For editable captions from the selected timeline, run
   `davinci-resolve-social-editor/scripts/resolve_auto_captions.py`; inspect
   every caption in Resolve before export.

If the diagnostic cannot connect, check Resolve is open, local scripting is
enabled, and the SDK paths in
`davinci-resolve-computer-use-training/references/resolve-automation-stack.md`
match your installation. Do not proceed as if an edit or render succeeded
without reading back the resulting timeline or verifying the export.

## Repository layout

```text
.
├── davinci-resolve-*/          # Focused Resolve skills
├── social-video-folder-autocutter/
├── scripts/
│   └── package-skills.ps1      # Validate and package one ZIP per skill
└── README.md
```

Each skill folder contains its `SKILL.md` and any supporting
`references/`, `scripts/`, `agents/`, or `templates/` included in this
repository. Some workflows also expect separately installed software,
external source media, or locally available Resolve workbooks/wiki exports;
those external resources are not bundled here.

## Package and verify skills

The packager checks that each skill has a `SKILL.md` with matching `name` and
non-empty `description` frontmatter. It then creates and opens each ZIP to
verify that `SKILL.md` is at the archive root.

Package just the modules you want:

```powershell
.\scripts\package-skills.ps1 -Skill @(
    'davinci-resolve-social-editor',
    'davinci-resolve-setup'
)
```

PowerShell's built-in `Compress-Archive` is used; no package installation is
required. On macOS or Linux, create one ZIP per skill folder with that folder's
contents (not the parent folder) at the archive root.

## Contributing

When updating a skill:

1. Keep its `SKILL.md` focused on triggers, workflow, decisions, and verification.
2. Keep supporting material inside that skill's folder and use relative paths.
3. State platform, version, licensing, and feature limitations instead of
   implying that a workflow works everywhere.
4. Prefer measurable checks and editable handoffs over unsupported quality
   claims.
5. Run the ZIP packager for the changed skill before sharing it.

## License

No repository-wide license file is currently included. Check with the
repository owner before redistributing or using these materials in a way that
requires a specific license.

---

## 👤 Created by

* **Discord:** .lorenzo_.
* **Instagram:** [llorenzo\_exe](https://www.instagram.com/llorenzo.exe/)
* **Twitch:** [llorenzo\_exe](https://twitch.tv/llorenzo_exe)
