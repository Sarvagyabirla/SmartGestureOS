# Product execution — 27 September 2026

This records work against the unchanged [master specification](PRODUCT_SPECIFICATION.md).
See [the baseline subsystem map and priorities](SPECIFICATION_AUDIT.md).
The project is **not yet fully accepted for public distribution**.

## Completed implementation

Working detector, classifier, event engine, three modes and Windows controllers
were retained. Changes address reproduced gaps rather than replacing those layers.

| Priority | Finding and resulting behavior | Verification |
|---|---|---|
| P0 | A low-confidence held Pinch produced stable Unknown and incorrectly re-armed after resume. Both raw and stable gestures must now be neutral. | Production-loop regression failed before fix, passes afterward; pause/hand-loss/watchdog tests retained. |
| P0 | Camera stop retained queued frames and could release a capture during a native read. Stop invalidates queued/in-flight frames; the worker owns delayed cleanup and restart waits for it. | Deterministic blocked-driver shutdown regressions; no native camera used in these tests. |
| P0 | Main Windows build's EXE failed native inference despite PyInstaller success. Bundle MediaPipe resources, dynamic C API package and DLL explicitly. | Fresh local ONEDIR native inference and UI probes both exited 0 from outside the repository. |
| P1 | Fixed 640×360 inference stretched non-16:9 cameras. Downscaling now preserves source aspect ratio. | 4:3 production-loop regression. |
| P1 | Detector omitted handedness and camera did not expose observed resolution/rate. Add structured labels and independently measured camera/detector FPS and inference time to dashboard. | Conversion, timing and fresh-inference regressions; no benchmark guarantees. |
| P1 | Drawing save failed under Unicode Windows paths; failed history resize could partly mutate the canvas. Use PNG encoding plus Unicode-safe file writes and transactional resize. | Reproduced Windows path failure; save/readback and allocation-failure regressions. |
| P1 | Sidebar exceeded default height, hiding controls. Scroll content while keeping Pause/Resume fixed; expose failed hotkey fallback and first-use instructions. | Mocked behavior and real Windows Tk geometry at 125% scaling; real auxiliary UI startup passed. |
| P1 | Coach names drifted and omitted Four Fingers. All 14 canonical gestures now appear. | Coach reference checks. |
| P1 | Camera selection was absent and selected profiles were forgotten at restart. Add validated camera index with restart guidance and saved active-profile preference. | Save/restart/fallback tests with temporary profiles. |
| P1 | Runtime data used `SmartGesture`. Copy existing data once into `SmartGestureOS` without deleting originals or replacing existing destination files. | Migration, failure/retry, no-overwrite and unavailable-storage tests. |
| P1 | Trainer's failed-save guidance did not provide a real retry. Retain samples and offer Retry Save; contain optional style/log failures. | Failed persistence retry and UI fallback regressions. |
| P1 | Controller failure explanations were discarded. Recent Actions now includes unavailable browser/audio messages. | Simulated unavailable native endpoint/browser tests. |
| P1 | Distribution lacked original artwork/version metadata and complete installed notice material. Add PNG/ICO artwork, source-derived executable version and collected runtime metadata/license texts. | Decode/dimension/icon/reference tests and actual bundle construction. |
| P1 | Product site omitted required information. Add requirements, mode mappings, architecture and onboarding; enable download only when a public release contains nonempty matching installer and checksum. | Eight JavaScript cases plus browser checks at 390px and 1365px: no horizontal overflow, broken images or anchor targets. |

## Acceptance and execution status

| Exact roadmap step | Current state | Remaining gate |
|---|---|---|
| 1. Real hand tracking | PARTIAL acceptance; implemented | Historical 21-landmark evidence retained; current candidate hand recognition check. |
| 2. Core mouse control | PARTIAL | Guided physical check underway; do not infer a pass from mocked tests or raw Windows event receipts. |
| 3. Complete gesture features | PARTIAL | GENERAL/MEDIA/DRAW native outcomes and physical settings/pause checks. |
| 4. Stability | PARTIAL | 20–30 minute physical interaction, camera unplug/reconnect and restart session. |
| 5. Standalone EXE | PARTIAL | Native/UI probes pass; full packaged camera and desktop actions remain unaccepted. |
| 6. Installer | IN PROGRESS | Build, isolated lifecycle smoke and clean-machine hardware acceptance. |
| 7. GitHub Release | NOT STARTED | Draft preparation only until physical/release gates pass; no public v0.9.0 release. |
| 8. GitHub Pages | LOCAL SITE READY | Account setting remains disabled at last verification; deployment/public link checks pending. |
| 9. Microsoft Store | NOT STARTED | Assets/listing draft ready; exact Partner Center identity, signed/validated package, screenshots and submission absent. |
| 10. Presentation freeze | PARTIAL preparation | [Runbook](PRESENTATION_RUNBOOK.md) ready; validated installed demo, actual screenshots/recording, backups and rehearsal pending. |

## Verification record

- Baseline: **356 passed**, Python 3.11.9, dependency check and native VIDEO probe passed.
- Integrated checkpoint: **394 passed in 7.26 seconds**, compileall and pip check passed.
- Website release gating: **8 Node tests passed**.
- First corrected ONEDIR build: PyInstaller 6.22.2 completed; `--self-check` and
  `--ui-self-check` each exited **0**, working directory outside source tree.
- Final build, installer, commit/CI and physical observations are recorded below
  as they complete. No installer or Store acceptance is implied by these probes.

## Known limits

Native camera drivers can block indefinitely. Shutdown invalidates input and
waits only a bounded interval; it cannot safely terminate an arbitrary native
driver call. Brightness depends on display support; media/audio requires an
available endpoint, and application launchers require installed applications.
Custom gesture matching is experimental. MediaPipe's published metrics
disclosure remains in [privacy](../PRIVACY.md); no zero-network claim is made.

## Reproduction

Standard development environment:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -q --tb=short
.\.venv\Scripts\python.exe -m compileall -q main.py config.py src tests scripts
.\.venv\Scripts\python.exe -m pip check
node --test tests/test_site_release.js
.\scripts\build_windows.ps1
.\scripts\build_installer.ps1
```

This isolated worktree reuses the adjacent checkout's Python 3.11.9 interpreter
via build helpers' `-PythonExe` option. Inno Setup 6.7.3 was downloaded from its
official immutable release, Authenticode verified as valid, and extracted in
portable mode under ignored `build/tools/InnoSetup`; `-IsccPath` selects it.
The [official portable-mode documentation](https://jrsoftware.org/ishelp/topic_technotes.htm)
describes this build-tool setup. No developer tool is needed by packaged users.
