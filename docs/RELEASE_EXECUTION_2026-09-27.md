# Release execution — 27 September 2026

Deadline: **30 September 2026**. This continues the [26 September report](RELEASE_EXECUTION_2026-09-26.md)
and the user's updated ten-step brief. Hardware acceptance is separate from
implementation and automated tests. No release or Store publication is claimed.

## Current repository audit

| Item | Evidence |
|---|---|
| Branch | `debug/phase1b-hand-detection` |
| Starting local and remote debug HEAD | `28f7f2d`; clean tree; no unpushed commits |
| Fetched `origin/main` | `fb70efcee0b30204f06ca3fff0d6d7477fff6ad8` |
| Fresh baseline | Python 3.11.9; **223 passed in 6.65 s** |
| After runtime fixes | **346 passed in 7.08 s**; compileall and pip check passed |
| Detector | MediaPipe VIDEO, one newest camera frame, worker inference |
| Camera and landmarks | Actual camera 0 returned a moving 21-point hand in the guided run |
| Cursor/click/drag/scroll/right-click | Automated regressions pass; physical acceptance remains NOT TESTED |
| Pause | Automated release/re-arm tests pass; live guide resumed, armed, paused and shut down |
| DRAW | History, resize and gesture-release defects fixed in code; physical drawing pending |
| Media/audio | Action results and holds fixed; real audio endpoint read succeeded; gesture-driven audio pending |
| EXE/installer | Old September 25 bundle remains; no validated current installer |
| Main CI/build | Successful runs linked below; debug branch previously excluded from push CI |
| GitHub Release | No published release at audit time |
| Pages | Repository reports disabled; public URL returns 404 |
| MSIX/Store | Placeholder identity, no assets/package/submission evidence |
| Top runtime blockers found | Unsafe profile data could prevent startup; configuration/practice windows left actions active |
| Current acceptance blocker | Physical core-input outcomes have not been recorded |

Remote evidence: [main CI](https://github.com/Sarvagyabirla/SmartGestureOS/actions/runs/36257216602),
[main installer build](https://github.com/Sarvagyabirla/SmartGestureOS/actions/runs/36257216605),
[failed Pages run](https://github.com/Sarvagyabirla/SmartGestureOS/actions/runs/36250268367),
[Releases](https://github.com/Sarvagyabirla/SmartGestureOS/releases).

## Exact ten-step status

| Step | Status | Acceptance still needed |
|---|---|---|
| 1 — Working hand tracking | DONE | Prior physical evidence retained; current run reconfirms camera and 21 landmarks |
| 2 — Core input control | PARTIAL | Explicit hand-only cursor, click, double-click, drag/drop, both scroll directions and right-click results |
| 3 — Complete feature set | PARTIAL | Source fixes and tests below; physical GENERAL/MEDIA/DRAW, system actions, pause/resume |
| 4 — Stability | PARTIAL | Configuration recovery hardened; 20–30 minute interaction/reconnect session pending |
| 5 — Standalone EXE | NOT STARTED | Correct dependency exclusion, rebuild, then startup and physical checks |
| 6 — Installer | NOT STARTED | Current installer and install/restart/uninstall/reinstall validation |
| 7 — GitHub Release | NOT STARTED | Validated v0.9.0 installer, checksum and public download |
| 8 — GitHub Pages | NOT STARTED | Accurate site, enabled deployment and verified public links |
| 9 — Microsoft Store | NOT STARTED | Exact Partner Center identity, real assets, valid package/listing and submission |
| 10 — Presentation freeze | NOT STARTED | Installed presentation build, rehearsal, backup video and final documentation |

Normal runtime fixes continued while the physical Step 2 gate was pending.
Later acceptance gates are not marked passed by this software work. Main was
not merged, and no release tag, installer publication or Store submission was made.

## Step 2 — core input control

**STATUS: PARTIAL.** Existing mouse fixes remain covered by automated regressions.

The user requested another run. The guided diagnostic ran from **00:43:05 to
00:44:26 IST**. The target was visible and in front. Camera 0 detected 21
landmarks; sampled preview cadence was about 19–29 FPS with roughly 7.7–9.7 ms
inference latency. These are short observations, not performance guarantees.

It resumed at 00:43:51, armed after neutral at 00:44:12, paused at 00:44:13,
and closed cleanly at 00:44:26. Camera and global hotkey were released.
The local JSON report contains **78 motion receipts, one blocked input call,
no button/wheel receipts, and all six human observations `not_recorded`**.
Those motion receipts also include physical mouse movement and do not prove
gesture-driven cursor operation. No webcam images were saved.

**Manual action required:** report what happened during the cursor attempt,
then complete the [guided physical check](MOUSE_HARDWARE_CHECK.md):

```powershell
.\.venv\Scripts\python.exe scripts\validate_mouse_controls.py
```

**Expected:** each requested interaction occurs once or continuously as directed;
drag releases, scroll stops on release, right-click does not repeat while held.
Press Esc before using the result controls. Record only hand-observed results.

**Next step:** resolve any reported physical failure and complete all six checks.

## Step 3 — complete feature set

**STATUS: PARTIAL.** Source corrections are committed as `96e6bc7`.

| Priority / issue | Root cause and fix | Files |
|---|---|---|
| P1 volume unavailable | Obsolete `AudioDevice.Activate` call replaced with supported `EndpointVolume`; acquire/release COM on processing worker | `src/volume_controller.py`, `main.py` |
| P1 brightness falsely reported success | Check native results, use pointer-sized handles and monitor range, release handles, fall back to laptop backend; update applied state only after success | `src/brightness_controller.py`, `src/gesture_mapper.py` |
| P1 unwanted strokes/history | End strokes on raw release, clear, undo/redo and resize; clear redo on new branch; preserve dimensions when resize fails | `src/drawing.py`, `src/gesture_mapper.py` |
| P1 action after gesture release | Require fresh raw/stable agreement for unfinished holds; retain consumed one-shot state through confidence gaps | `src/gesture_mapper.py` |
| P1 repeated mode switch | Reset temporal state on switch and require release of an already-consumed switch gesture | `src/gesture_mapper.py` |
| P1 false/missing action result | Return failures from desktop/presentation shortcuts, use monotonic cooldown, resolve normal VS Code `bin/code.cmd` parent layout | Desktop, presentation and shortcut controllers |

New regression files: `test_volume_endpoint.py`, `test_brightness_regression.py`,
`test_desktop_presentation_launch_regression.py`, and `test_drawing_mapper_transitions.py`.
Processing-worker cleanup tests and the diagnostic brightness stub were updated.
Controllers are mocked in action tests; no test changes system volume/brightness,
locks Windows, or launches desktop applications.

**Hardware result:** a separate read-only audio probe acquired the real endpoint
on a worker, read **40.1%** with a **−96 to 0 dB** range, then exited cleanly.
The live application's worker also acquired the endpoint. Volume changes and
brightness behavior have **not** been physically validated.

**Next step / manual action:** validate actual GENERAL/MEDIA/DRAW behavior after
the core input gate. Source command: `.\.venv\Scripts\python.exe main.py --start-paused`.
No packaging/deployment result is claimed for this step.

## Step 4 — stability groundwork

**STATUS: PARTIAL.** Source corrections are committed as `58716b1`.

- **P0/P1 causes:** profile merging accepted invalid sections/numbers; malformed
  custom samples could crash classification; opening Settings, Trainer or Coach
  left desktop actions active while users practiced gestures.
- **Fixes:** validate types, finite values, ranges and threshold relationships;
  preserve invalid files and existing valid settings on failed load; keep safe
  startup defaults in memory. Accept bounded finite 63-coordinate samples;
  report and roll back failed saves/deletes. Pause via the authoritative callback
  before opening practice/configuration windows; keep resuming explicit.
- **Files:** `config.py`, settings manager, gesture trainer, main UI, settings UI,
  trainer UI, and `tests/test_profile_trainer_ui_regression.py`.
- **Automated result:** 52 isolated regressions passed; included in the full
  **346 passing tests**. UI methods use mock widgets; files use temporary folders.
- **Hardware result:** no sustained stability or camera-unplug test completed.
- **Manual action / next step:** 20–30 minute session with hand loss, rapid pose
  changes, pause during drag, camera disconnect/reconnect and clean restart.

## Dependency privacy finding

At **00:44:25** the installed MediaPipe 0.10.35 native library logged a failed
Clearcut uploader attempt. No successful transfer or payload content was
established. The application camera code processes frames in memory; that does
not establish that all dependency code makes no network requests.

The same behavior has an [upstream report](https://github.com/google-ai-edge/mediapipe/issues/6291).
Privacy/notices are corrected to disclose this observed limitation. A validated
dependency configuration is still needed before claiming zero telemetry or
zero network activity. No dependency downgrade, firewall change or silent log
suppression was performed.

## Reproduction commands

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -v --tb=short
.\.venv\Scripts\python.exe -m compileall -q main.py config.py src tests scripts
.\.venv\Scripts\python.exe -m pip check
```

Results: **346 passed in 7.08 seconds**, compilation passed, no broken requirements.
The CI push filter now includes `debug/**` and compiles tests/scripts as well as
application code so these checkpoints receive automated remote validation.
