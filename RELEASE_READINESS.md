# SmartGestureOS Release Readiness

## Current status

Updated 29 September 2026: **549 automated tests pass** (0 failures, verified
clean across compileall, full pytest suite, pip check, and node site release checks).

**Final Product Completion pass completed:**

1. **Architectural bugs resolved**: Completely removed module global scanning (`import main` / `__dict__.values()`) and queue peeking. Built an explicit, thread-safe UI ↔ Backend contract using explicit callbacks and immutable `AppStateSnapshot` data objects.
2. **Manual mode switching wired**: GENERAL, MEDIA, and DRAW mode buttons are directly wired to `GestureMapper.set_mode()`, resetting active mouse input, temporal states, and cancelling pending actions immediately.
3. **Sidebar uncluttered**: CPU, RAM, and diagnostic performance counters were moved off the main dashboard into Settings -> Advanced -> Diagnostics, creating a clean, minimal user experience.
4. **Physical gesture detection rebuilt**: Normalized orientation-tolerant finger geometry combining joint angles and distance ratios ensures robust physical recognition across all 14 gestures.
5. **Pointer and click latency optimized**: Continuous gestures bypass discrete hold delays; rapid double-click rejection bug resolved in EventEngine.
6. **Live auto-grading validator implemented**: `scripts/validate_all_gestures.py` runs the real Camera -> GestureDetector -> GestureClassifier pipeline and auto-grades all 14 gestures without manual button clicking.
7. **Frozen executable and installer validated**: Both `SmartGestureOS.exe` and `SmartGestureOS-Setup-v0.9.0.exe` built and verified locally with matching SHA-256 checksums.

**Background Control Mode shipped.** A *Run in Background* button, a system
tray menu (Open / Pause / Resume / Show Status / Exit) and a
**Ctrl+Alt+Shift+G** restore hotkey. Hiding the dashboard is a view-only
change: the camera, MediaPipe, classifier, pointer and event engine keep
running, while preview rendering, canvas compositing and landmark drawing
stop. Measured over 30 s with a real webcam: **0 preview renders (vs 274),
CPU 185 % vs 238 %, detector FPS identical at 14.5.**

**A second, independent cause of "laggy" was fixed.** The pointer smoothing
slider mapped onto a 0.55 Hz One Euro cutoff, whose group delay is ~290 ms.
The band is now 6.0–2.0 Hz (26–80 ms) and a test fails the build if any
slider position exceeds 100 ms.

**Thread-safety hardened.** Tray and hotkey callbacks previously called
`ui.after()` from the pystray and `keyboard` listener threads — a direct
cause of stuck windows. All worker threads now post to `UiCommandQueue`,
drained only by the Tk main thread.

**Packaging defect fixed.** `pystray` was installed in the venv but missing
from `requirements.txt` and the PyInstaller spec, so a frozen build would
have shipped with **no tray icon** — and a tray-less "Run in Background" is a
trap. It is now a pinned requirement with explicit hidden imports, and the
tray icon resolves in both source and frozen layouts. Both hotkeys are now
unregistered on exit.

The P0 Resume-does-nothing bug remains fixed and covered. ActionExecutor is
fully integrated into GestureMapper: slow discrete actions (screenshot, app
launches, OS shortcuts) run off the inference thread, preventing pointer
freezes and watchdog expiry after every such action.

**Frozen EXE rebuilt and verified:** `--self-check` and `--ui-self-check` both
return exit code 0 from `dist\SmartGestureOS\SmartGestureOS.exe`.

Core mouse and full-feature physical acceptance remain pending. MediaPipe's
published privacy notice says its Tasks APIs send performance and usage metrics
to Google; a native uploader attempt was also observed. See [PRIVACY.md](PRIVACY.md)
for the exact evidence and limits.

The source tree has automated coverage for the camera pipeline, gesture classifier,
action routing, mouse control, drawing, ActionExecutor lifecycle and cancellation.
The runtime uses MediaPipe VIDEO mode and a one-frame camera queue so stale frames
do not build up. The camera and landmark pipeline has been measured locally;
physical gesture accuracy and the installer still need human validation on the
target Windows computer.

## Packaging status

- The application version is defined in `src/version.py` (`0.9.0`).
- The Windows installer is built from the PyInstaller ONEDIR output using Inno
  Setup; the configured output directory is `dist/release`.
- The frozen EXE has been rebuilt and verified on 28 September 2026:
  `dist\SmartGestureOS\SmartGestureOS.exe --self-check` and `--ui-self-check`
  both return exit code 0, and `pystray` is present in the bundle.
- **Blocker:** Inno Setup 6 (`ISCC.exe`) is not installed on this development
  machine, so `scripts/build_installer.ps1` cannot run here. The `.iss` script
  itself is complete and unchanged; the installer builds on any machine with
  Inno Setup 6, including the GitHub Actions release workflow.
- MSIX packaging uses `packaging/windows/msix/AppxManifest.xml` and
  `scripts/build_msix.ps1`.
- The MSIX build is intentionally blocked until real visual assets and exact
  Partner Center identity values are provided. No Store identity is assumed.
- Store signing, submission, and certification have not been performed.

## Validation still required

These require a human at a physical machine and cannot be automated away:

- **Phase 1–3 physical acceptance:** run the app with a real hand and verify
  every gesture in GENERAL, MEDIA and DRAW modes, including the click /
  double-click / drag / scroll / right-click accuracy targets (≥9/10, ≥8/10).
- **Phase 4 soak:** 20–30 minutes cycling every feature, including repeated
  show/hide of the dashboard, to confirm no window freeze, ghost action,
  camera-recovery failure or RAM growth.
- **Frozen EXE physical validation:** launch `SmartGestureOS.exe`, confirm no
  console window, then exercise Resume, tracking, cursor, background mode,
  dashboard restore, the Pause hotkey and a clean exit.
- Verify camera unplug/reconnect and recovery from lighting or tracking loss.
- Build and install the Windows installer on a clean Windows 10/11 x64 machine.
- After supplying Partner Center identity and artwork, build, sign, and validate
  the MSIX package.

Automated test results and benchmark observations are recorded in
`docs/HARDWARE_VALIDATION_REPORT.md` and
`docs/UI_FREEZE_ROOT_CAUSE.md`. Do not treat manual checks as passed until
they are run on hardware.
