# SmartGestureOS release execution — 26 September 2026

This report records the initial audit for the user's exact ten-step completion
sequence. Findings describe the baseline below, before the current Step 1
changes. Automated checks and successful builds do not establish physical
gesture operation, installation readiness, or Store publication.

## CURRENT REPOSITORY AUDIT

| Item | Observed baseline |
|---|---|
| Current branch | `debug/phase1b-hand-detection` |
| Local HEAD after Step 1 evidence commit | `6c38ca5` (`docs: record real hand tracking validation`) |
| Remote debug HEAD | `b2a7b6415ffcf9ffd8b55682c6b95cafc4b1abb8` |
| `origin/main` | `35539ed31b4115d91f5c70e81601ad9cc6a5897c`; PR #3 already merged |
| Working tree at audit start | Dirty; existing Phase 1–3 and tracking work preserved |
| Development Python | 3.11.9 |
| Fresh automated baseline | **181 passed in 6.61 seconds**; 182 pass after the Step 2 regression test and fix |
| Syntax check | `compileall` passed for `main.py`, `config.py`, `src`, `tests`, and `scripts` |
| Dependencies | `pip check`: no broken requirements |
| Detector architecture | Camera capture thread with a newest-frame queue; synchronous MediaPipe VIDEO inference through `process_frame`; classifier, mapper, and dedicated Windows controllers |
| Model | `models/hand_landmarker.task`, 7,819,105 bytes |
| Model SHA-256 | `fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1` |
| Top P0 gate | Cleared on 2026-09-26: actual `main.py` showed a moving 21-point hand, handled loss/re-entry, and shut down cleanly |

Baseline commands:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -v --tb=short
.\.venv\Scripts\python.exe -m compileall -q main.py config.py src tests scripts
.\.venv\Scripts\python.exe -m pip check
```

Confirmed automated coverage includes camera behavior, gesture geometry,
temporal mouse events, action routing, drawing, and RGB overlay rendering.
Earlier camera diagnostics demonstrate that the model can return real hand
landmarks using VIDEO mode. Those observations do **not** complete the actual
application's physical tracking acceptance test or certify every gesture.

## Distribution and deployment snapshot

| Area | Status | Evidence and limitation |
|---|---|---|
| Windows packaging | PARTIAL | Main installer workflow succeeded and uploaded a 67,873,126-byte build artifact; packaged startup and installation remain unverified. The spec excludes a required MediaPipe dependency. |
| Local packaging environment | PARTIAL | An older ONEDIR executable exists, dated 25 September. No `dist/release` directory, Inno compiler on PATH, or Windows SDK `Windows Kits/10/bin` was found. |
| GitHub deployment | PARTIAL | Main and debug PR CI passed; main installer build passed. Pages deployment failed. |
| Public GitHub Release | NOT STARTED | Public releases API returned zero releases. No published installer download or release checksum was established. |
| GitHub Pages | PARTIAL | Static site and workflow exist. Repository reports `has_pages=false`; the public URL returns 404. Deployment failed during Setup Pages. |
| Microsoft Store | NOT STARTED | Canonical manifest exists, but identity is placeholder and artwork folder is absent. No valid MSIX, submission, or certification evidence. |

Remote evidence:

- [Merged PR #3](https://github.com/Sarvagyabirla/SmartGestureOS/pull/3).
- [Successful main CI](https://github.com/Sarvagyabirla/SmartGestureOS/actions/runs/36250268368).
- [Successful debug PR CI](https://github.com/Sarvagyabirla/SmartGestureOS/actions/runs/36250261968).
- [Successful main installer build](https://github.com/Sarvagyabirla/SmartGestureOS/actions/runs/36250268358).
- [Failed Pages deployment](https://github.com/Sarvagyabirla/SmartGestureOS/actions/runs/36250268367): its annotation says Pages must be enabled and configured for GitHub Actions.
- [Intended public website](https://sarvagyabirla.github.io/SmartGestureOS/) returned 404 during this audit.

## Exact ten-step execution status

Status below describes this execution sequence. Existing code and historical
checks are inputs to each step; they do not bypass the physical acceptance gates.

| Step | Name | Status | Acceptance still required |
|---|---|---|---|
| 1 | Real hand tracking | DONE | Actual application displays moving 21-point landmarks, handles hand exit/re-entry, and remains responsive without crashing. |
| 2 | Core mouse controls | PARTIAL | Pinch transitions, click targeting, scroll limits and cursor reset fixed; automated regressions pass. Physical cursor, click, double-click, drag/drop, scroll, and right-click results are still pending. |
| 3 | Full feature set | NOT STARTED | GENERAL, MEDIA, DRAW, system actions, mode switching, and pause/resume work or have accurate limitations. |
| 4 | Stability | NOT STARTED | 20–30 minute session, hand loss, camera reconnect, pause during drag, rapid changes, and safe shutdown. |
| 5 | Packaged desktop EXE | NOT STARTED | Rebuild ONEDIR and repeat core physical checks in the executable. |
| 6 | Installer | NOT STARTED | Install, launch, restart, uninstall, reinstall, and preferably validate on a clean Windows computer without Python. |
| 7 | GitHub Release | NOT STARTED | Publish v0.9.0 with validated installer and SHA256SUMS; verify public download. |
| 8 | GitHub Pages | NOT STARTED | Deploy `site/`; verify public rendering, assets, download, privacy, and support links. |
| 9 | Microsoft Store | NOT STARTED | Real Partner Center identity, artwork, valid MSIX, listing, and successful submission. |
| 10 | Presentation freeze | NOT STARTED | Final documentation, installer, known limitations, architecture, demo checklist, backups, and rehearsal. |

Do not begin a later step until the current acceptance criteria pass, except for
the external dependency exception explicitly permitted by the user. Physical
hand interaction, another computer, and Partner Center inputs must be recorded
honestly when they require the user's participation. Store status remains
NOT STARTED until supported by actual evidence.

## Deferred findings for the appropriate steps

These are audit findings to reproduce, fix, and validate at their assigned step.
They are **not** claims that the work has been completed in this sequence.

| Step | Finding | Required follow-up |
|---|---|---|
| 2 | Late second pinch was treated as a double-click outside the intended window. | FIXED in `src/event_engine.py`; regression fails before and passes after the fix. Physical gesture validation remains pending. |
| 3 | Current pycaw speaker endpoint exposes `EndpointVolume`; the controller expects an `Activate` path that is absent on that object. | Use the supported endpoint interface and validate real volume control with an active audio device. |
| 3 | Brightness failures do not reliably propagate to the displayed action result. | Report unsupported hardware and controller errors accurately; test supported hardware when available. |
| 3 | DRAW undo/redo history needs correction and behavior validation. | Validate complete strokes, redo, bounded history, resize, and save before claiming drawing ready. |
| 4 | Malformed saved profiles and custom gesture data can reach insufficiently validated runtime paths. | Harden configuration/data loading and verify recovery without losing valid user data. |
| 5 | `packaging/windows/SmartGesture.spec` excludes `matplotlib`, although MediaPipe 0.10.35 imports `matplotlib.pyplot` during normal import. | Remove the invalid exclusion, rebuild, and validate packaged startup. |
| 5 | Build scripts depend on the caller's working directory. | Resolve paths consistently from the repository root; read `src.version` after establishing its import path. |
| 5–6 | Executable icon/version metadata are unset; distributed license/notices coverage needs review. | Add legitimate metadata/artwork and inspect the actual packaged distribution. |
| 7 | CI push patterns omit `debug/**`; current debug success came from its PR. | Ensure subsequent work receives CI coverage through a new PR or an appropriate trigger. |
| 8 | Pages is not enabled for GitHub Actions. | Configure repository Pages at the deployment step and rerun the workflow. |
| 8 | Website download buttons currently lead to source setup; it has a premature Live badge, no Support link, and incomplete team attribution. | Link the validated published installer and correct claims, support, team, and guide information. |
| 9 | Store identity values and real PNG artwork are missing. | Obtain exact Partner Center values and legitimate assets; never invent identity or fabricate empty assets. |
| 9 | Manifest lists `DeviceCapability` before `rescap:Capability`. | Correct schema ordering and validate with packaging tools; XML well-formedness alone is insufficient. |
| 9 | MSIX PNG checks only inspect signature, IHDR, and dimensions. | Decode and verify image integrity so a truncated header cannot pass as a real asset. |

The packaging dependency finding was confirmed without launching the app:
inspection of the existing executable's PYZ found MediaPipe and its
`drawing_utils`, but no matplotlib; the bundle also contains no matplotlib
paths. A fresh source import with that dependency unavailable fails at
`mediapipe/tasks/python/vision/drawing_utils.py:21`. The successful installer
workflow currently checks executable existence, so it does not rule out this
startup failure.

Microsoft's [Capabilities schema](https://learn.microsoft.com/en-us/uwp/schemas/appxpackage/uapmanifestschema/element-f-capabilities)
places capability groups before device capabilities; this is the basis for the
deferred manifest ordering correction.

## Documentation conflicts to reconcile before release

- `CHANGELOG.md` says `opencv-python` is retained, while current requirements
  retain `opencv-contrib-python==5.0.0.93`.
- `THIRD_PARTY_NOTICES.md` names the wrong OpenCV distribution and stale Pillow
  and CustomTkinter versions, and overstates dependency network guarantees.
- `CONTRIBUTING.md` retains a 73-test reference and describes the detector as
  asynchronous; production now uses synchronous VIDEO inference.
- `SUPPORT.md` calls this a solo project, links to disabled GitHub Discussions,
  and calls the Trainer a tab.
- `PRIVACY.md` describes settings at `settings.json`, while `SettingsManager`
  persists active profiles under `profiles/<profile>.json`.
- `docs/PRODUCTION_AUDIT.md` uses RESOLVED/“None identified” for areas whose
  physical checks are still pending. Separate implementation/test evidence from
  hardware acceptance.
- README needs a validated normal-user download/install path and a clear
  distinction between development Python requirements and the standalone
  installed application.
- Historical audit documents are labeled historical. Preserve their context;
  their old test counts and findings are not the current release status.

## Step 1 results — REAL HAND TRACKING

**STATUS: DONE**

- **What was wrong:** Previous hardware reports were inconsistent; a 10-second standalone production sample returned 0/149 hand frames.
- **Root cause:** No persistent detector or preprocessing failure reproduced. In a subsequent controlled camera probe, IMAGE detected 1 hand at 99.7%, VIDEO detected a hand in 48/48 frames, and LIVE_STREAM detected one in 59/59 original-resolution callbacks. Treat the earlier zero-hand sample as non-repeatable; its specific cause was not established.
- **What was changed:** No detector implementation changes were needed during this step. Existing dirty-worktree changes already selected MediaPipe VIDEO mode and provided safe tracking invalidation; they were preserved.
- **Files changed for this step:** `docs/HARDWARE_VALIDATION_REPORT.md` only; committed as `6c38ca5`. Generated diagnostic stills from this run were removed. A separate pre-existing `real_room_with_hand.png` was preserved.
- **Automated results:** 181 passed before Step 2 test addition; compileall and `pip check` passed.
- **Manual test:** Launched `main.py --start-paused` on camera 0. Live UI preview reported 21 landmarks and changing fingertip coordinates at about 22–31 FPS, with 7.6–9.7 ms detector latency. Landmarks cleared on hand loss and reacquired as 21 points. The application ran for over two minutes and closed normally.
- **Remaining blockers:** None for Step 1. The machine's pycaw audio endpoint failed initialization; that is tracked under Step 3.
- **Next step:** Validate core mouse controls, including the fixed double-click timing boundary.

## Resumed repository audit

The next development pass began with a clean working tree at `6eb6a52` on
`debug/phase1b-hand-detection`, matching its remote branch. After fetching,
`origin/main` was `fb70efc` (merged PR #4) and its tree matched that debug HEAD.
No main merge or history rewrite was performed in this pass. The fresh baseline
was **182 passed in 6.73 seconds**; compileall and `pip check` also passed.

## Step 2 results — CORE MOUSE CONTROLS

**STATUS: PARTIAL — PHYSICAL GESTURES PENDING**

- **What was wrong:** The original late second-pinch bug was fixed in `d58b224`.
  Further deterministic checks reproduced delayed drag release, a short pinch
  becoming a drag because the stable label lagged, repeated input from a held
  second pinch, cursor drift before delayed click dispatch, excessive scroll,
  and stale pointing coordinates after tracking reset. A release sampled just
  beyond the drag deadline could also disappear without a click or drag.
- **Root cause:** Stable gesture history was treated as a still-held pose;
  double-click consumption was not retained until release; movement continued
  during pending clicks; an unbounded loop emitted every accumulated wheel tick;
  the legacy uncalibrated hand-size placeholder `1.0` became an actual scaling
  measurement; reset left smoothing and deadzone coordinates intact.
- **What was changed:** Use raw geometry for release while retaining confidence
  checks at action entry. Keep click targets fixed, consume a double pinch until
  released, and retain a pending click when no drag press actually occurred.
  Reject invalid scroll samples, bound calibrated scale to 0.25–4, emit at most
  one wheel event of three ticks per frame, and discard excess whole ticks.
  Treat the legacy placeholder as uncalibrated. Release input on missing hand
  data and reset cursor smoothing on release. Added an opt-in physical guide with
  production camera/classifier/input logic and input confined to its target.
- **Files changed:** `src/event_engine.py`, `src/mouse_controller.py`,
  `src/virtual_mouse.py`; regression tests for temporal transitions, scaling and
  mouse reset; `scripts/validate_mouse_controls.py` and
  `docs/MOUSE_HARDWARE_CHECK.md`. Existing automated fixtures were also corrected
  to mock desktop input for their full lifetime.
- **Automated results:** The new regressions reproduced the defects before
  correction. The targeted event/input suite passed **34 tests**; the scaling
  checks passed **11 tests**. Diagnostic boundary and UI behavior checks passed
  **13 tests**. Full suite: **223 passed in 6.60 seconds**. Syntax compilation and dependency
  checks passed. Runtime fixes and their regressions are committed as `d544370`.
- **Manual test required:** Physically validate Pointing, single Pinch, double
  Pinch, held Pinch drag/drop, Two Fingers scrolling in both directions, and
  Three Fingers right-click. Follow [the guide](MOUSE_HARDWARE_CHECK.md).
- **Exact command:** `.\.venv\Scripts\python.exe scripts\validate_mouse_controls.py`
- **Expected result:** Start each check in the target window, briefly remove the
  hand for neutral re-arm, and verify the requested Windows interaction. Esc
  pauses; focus loss also pauses. Record explicit human observations and save
  the report. Event counts alone are not proof of physical gesture operation.
- **Hardware attempt:** The guided process ran on 26 September from 23:51:48
  to 23:52:01 local time. Camera 0 detected a real hand with 21 landmarks while
  automation remained paused. Shutdown saved a local report with all six results
  `not_recorded`, no input receipts, and no blocked calls. This does not establish
  a mouse-control pass. No camera images were saved. The diagnostic now raises
  its target once after application startup so the preview cannot hide the
  guide at launch; wheel direction is also displayed explicitly. Those changes
  have mocked checks but have not yet had a second physical run.
- **Remaining blockers:** The six interactions still need explicit physical
  results. Normal desktop use and later stability/packaged checks remain pending.
- **Next step:** Complete this physical check before starting Step 3.
