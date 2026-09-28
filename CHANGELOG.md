# Changelog

All notable changes to SmartGestureOS are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)  
and this project adheres to [Semantic Versioning](https://semver.org/).

---

## [0.9.0] — 2026-09-29

### Final Product Completion Pass — Physical Gesture Pipeline, Fluent UI & Clean Architecture

- **Eliminated Architectural Anti-Patterns**:
  - Removed all `import main` and `__dict__.values()` module global scanning across `src/ui.py` and `src/ui_gesture_test.py`.
  - Replaced ad-hoc discovery with an explicit, thread-safe UI ↔ Backend contract using explicit callbacks (`set_mode_callback`, `get_state_callback`, `get_latest_preview_callback`, `show_dashboard_callback`, `hide_dashboard_callback`, `quit_callback`).
  - Added an immutable `@dataclass(frozen=True) AppStateSnapshot` for safe, decoupling telemetry and state exchange between the backend engine and UI components.
  - Removed direct `Queue.queue[0]` inspection in `GestureTestUI`.

- **Wired Manual Mode Switch Buttons**:
  - `GENERAL`, `MEDIA`, and `DRAW` buttons now call `set_mode_callback(mode)` directly, invoking `GestureMapper.set_mode(mode)`.
  - State transitions atomically release active mouse states, reset temporal gesture timers, cancel pending async actions, and update the UI mode label immediately.
  - Zero dead or disconnected buttons remain on the main screen.

- **Rebuilt Live Gesture Validator (`scripts/validate_all_gestures.py`)**:
  - Replaced manual "Mark PASS/FAIL" mockup with a fully automated, real-time live grading tool.
  - Runs the authentic production pipeline (`Camera` -> `GestureDetector` -> `GestureClassifier`) with OS action execution strictly suppressed.
  - Auto-grades all 14 gestures based on sustained continuous recognition (350-500ms), outputting structured JSON metrics (`logs/gesture-validation-<timestamp>.json`) including median and p95 latency, confusion matrices, and confidence scores.

- **Gesture Recognition Pipeline & Geometry Overhaul**:
  - Rebuilt `fingers_up` with normalized, orientation-tolerant geometry combining MCP-PIP-DIP angles (`angle_pip`) and relative wrist-to-tip / wrist-to-MCP distances.
  - Eliminated deadbands between parallel two-finger scroll and divergent Victory gestures while preserving noise resilience against spurious activations.
  - Separated continuous gestures (Pointing, Pinch, Two Fingers) from discrete actions for near-instant latency and smooth cursor response.
  - Fixed rapid second-pinch rejection in `EventEngine` so physical double-clicking functions reliably without dropping the second tap.

- **Simplified Dashboard UI**:
  - Removed engineering metrics clutter (CPU, RAM, raw FPS counters) from the main user sidebar, keeping the interface beginner-friendly and focused.
  - Centralized advanced diagnostic and training tools in **Settings -> Advanced**.
  - Streamlined primary controls: Live Camera Preview, high-contrast Status Badge, Mode Selector, Gesture/Confidence Badge, Settings, Background Mode, and Pause/Resume.

- **Built & Verified Frozen Distribution**:
  - Built standalone PyInstaller distribution `dist/SmartGestureOS/SmartGestureOS.exe` with verified `--self-check` and `--ui-self-check` validation.
  - Built production Inno Setup installer `dist/release/SmartGestureOS-Setup-v0.9.0.exe` and verified matching `SHA256SUMS.txt`.
  - Created runtime performance diagnostic `scripts/measure_runtime_performance.py` recording measured 30.8 FPS camera throughput, 27.1 FPS detector rate, 9.8 ms median inference, and 13.6 ms Tk event-loop p95 latency.

---

## [0.8.0] — 2026-09-28

Root-cause analysis, with before/after measurements, is in
[`docs/UI_FREEZE_ROOT_CAUSE.md`](docs/UI_FREEZE_ROOT_CAUSE.md).

**Fixed — the window froze because the Tk event loop was 180 % over budget.**
`update_ui_loop()` runs on a 15 ms budget but measured 26.7 ms of work per
tick (`update_dashboard` 14.65 ms + `update_frame` 12.06 ms), so the Tcl/Tk
pump never idled and Windows marked the window "Not Responding". The
dashboard is now change-detected (zero `configure()` calls for a steady
gesture), the frame is downscaled with `cv2.INTER_AREA` before colour
conversion, preview is rate-limited to 24 FPS and label geometry is cached.
Measured Tk event-loop delay p95: **16.13 ms → 1.08 ms**.

**Fixed — the window could disappear with no way back.** `on_closing()`
unconditionally called `withdraw()`, so a tray failure left the user with no
window, no tray and no hotkey while the process kept holding the camera and
the global keyboard hook. The X button now honours an explicit
minimize-to-tray setting, and the dashboard can always be restored.

**Fixed — the pointer filter added ~290 ms of group delay.** The smoothing
slider mapped onto 2.0–0.55 Hz, and 0.55 Hz has a ~1/(2π·0.55) ≈ 290 ms
One Euro delay. The band is now 6.0–2.0 Hz (26–80 ms), and a test fails the
build if any slider position exceeds 100 ms.

**Added — Background Control Mode.** A *Run in Background* button, a system
tray menu (Open / Pause / Resume / Show Status / Exit) and the
**Ctrl+Alt+Shift+G** restore hotkey. Background mode is a view-only change:
camera, MediaPipe, classifier, pointer and event engine are untouched, while
preview rendering, canvas compositing and landmark drawing stop. Measured
**22 % lower CPU** and **0 preview renders** versus the visible dashboard.

**Fixed — Tk thread-safety.** Tray and hotkey callbacks previously called
`ui.after()` from the pystray and `keyboard` listener threads. All worker
threads now post to the new `UiCommandQueue`, drained only by the Tk thread.

**Fixed — packaging.** `pystray` was installed in the venv but missing from
`requirements.txt` and the PyInstaller spec, so a frozen build would have
shipped with no tray. It is now a pinned requirement with explicit hidden
imports, and the tray icon resolves in both source and frozen layouts. Both
hotkeys are now unregistered on exit.

**Added — diagnostics.** `scripts/diagnose_ui_freeze.py` (Tk cost breakdown,
no camera needed) and `scripts/diagnose_runtime.py` (full live pipeline,
visible vs background). Both report measured percentiles, never targets.

**Added — 48 regression tests** in `tests/test_background_mode.py` and
`tests/test_distribution_assets.py`.

### Product specification implementation — 27 September 2026

- Preserve the complete user specification and map every subsystem to the
  exact ten-step release plan, with software and hardware evidence separated.
- Require raw and stable neutral gestures before re-arming after pause; retain
  camera aspect ratio during inference and expose measured capture/detector rates.
- Discard queued/in-flight camera frames after stop and retain capture ownership
  until a native read finishes; expose observed resolution and handedness.
- Save drawings correctly under Unicode Windows paths and resize canvas/history
  transactionally when an allocation fails.
- Keep Pause/Resume visible, add first-use guidance and all 14 Coach gestures,
  expose hotkey failure, and add restart-applied camera selection.
- Remember the selected profile, provide Trainer save retry, and migrate legacy
  local data to `%LOCALAPPDATA%\SmartGestureOS` without deleting the originals.
- Bundle MediaPipe native resources explicitly, preserve runtime license texts,
  add application artwork/version metadata and a camera-free frozen UI probe.
- Prepare the static product site and Store listing; show the installer download
  only after a public release contains both installer and checksum.

Physical acceptance, public release, Pages deployment and Store submission are
tracked separately in `RELEASE_READINESS.md`; these changes do not establish
that the final product is fully validated or published.

### Documentation
- 2026-09-27: Updated privacy, security, support and website language using
  MediaPipe's published notice that Tasks APIs send performance and usage
  metrics to Google while processing input images on device.
- 2026-09-27: Corrected profile storage paths, team attribution, support routes,
  Trainer controls, VIDEO detector architecture, and pinned dependency notices.
- 2026-09-27: Disclosed observed MediaPipe 0.10.35 native Clearcut uploader
  activity in a physical diagnostic. The observed upload failed; payload and
  successful transmission status are unknown. Dependency behavior remains
  unresolved and prevents a verified zero-telemetry/no-network claim. See
  [PRIVACY.md](PRIVACY.md).

### Reliability and release validation
- Reject invalid camera frames and recover from driver open-state, mirror and
  release exceptions without losing the capture thread.
- Require raw/stable agreement before starting a pinch action; wait for the
  second pinch to release before deciding double click versus drag.
- Add a camera-free `--self-check` path for model loading and native VIDEO
  inference, and require it to pass in Windows build/release workflows.
- Correct the PyInstaller MediaPipe dependency exclusion and build-script path
  handling. Release workflow now creates a draft pending installer validation.

### Security
- F-07: Replaced `shell=True` subprocess launches with `shell=False` + explicit exe paths in `ShortcutController`. Chrome and VS Code paths now located via `shutil.which` + known env-var paths. `lock_pc` uses `ctypes.windll.user32.LockWorkStation()` directly.
- F-09: Added regex allowlist validation for profile names (`SettingsManager`). Rejects path separators, reserved Windows filenames, empty names, and names > 64 characters. Prevents path traversal attacks when loading/saving profiles.
- F-37: Added gesture name sanitization in `GestureTrainer`. Built-in gesture names (Pinch, Victory, etc.) cannot be overwritten by custom training. Max 50 samples per gesture enforced.

### Added
- F-14/F-33: `src/version.py` — single authoritative version source for UI, logs, packaging.
- F-19: GitHub Actions CI/CD workflows: `ci.yml` (test on PR), `build-windows.yml` (PyInstaller), `release.yml` (GitHub Release + installer), `pages.yml` (GitHub Pages).
- F-22: `LICENSE` (MIT).
- F-23: `PRIVACY.md` — full privacy policy. Required for Microsoft Store submission.
- F-24: `CHANGELOG.md` (this file).
- F-25: `CONTRIBUTING.md`.
- F-26: `SECURITY.md`.
- F-27: `SUPPORT.md`.
- F-28: `THIRD_PARTY_NOTICES.md`.
- F-29: GitHub Pages static website (`site/`).
- F-32: MSIX packaging structure (`packaging/windows/msix/`).
- Test: 13 new unit tests covering F-06, F-09, F-37 security fixes and F-12 classifier cleanup.

### Fixed
- F-01: Added `psutil>=5.9.0` to `requirements.txt` (was missing; caused import error on clean install).
- F-02: Use `opencv-contrib-python==5.0.0.93` as the single OpenCV wheel in `requirements.txt`; do not install `opencv-python` alongside it.
- F-03: Replaced `time.time()` with `time.perf_counter()` in `ShortcutController` rate-limiting.
- F-04: Camera disconnect in `main.py` now calls `mapper.mouse.release_all()` to release all desktop automation (drag, click, scroll) when the camera transitions from connected to disconnected.
- F-06: `EventEngine` right-click now uses a release gate (`_right_click_armed` flag). Right-click fires once per Three Fingers press, then requires gesture release before re-arming. Prevents repeated context-menu opens while Three Fingers is held.
- F-08/F-17: Actual camera frame dimensions (`frame.shape`) are propagated to `GestureMapper` after the first frame arrives, replacing the SETTINGS-based assumption. Mouse coordinates now correctly map to the camera's actual resolution.
- F-10: `DrawingCanvas._save_state()` now pops before appending, ensuring the undo stack is always capped at exactly `MAX_UNDO_STEPS = 20`.
- F-11: Screenshot and drawing filenames now use millisecond precision + 6-character UUID suffix to prevent collisions (`screen_<ts_ms>_<uuid>.png`, `drawing_<ts_ms>_<uuid>.png`).
- F-12: Removed misleading `hold_time_ms` parameter from `GestureClassifier.__init__()`. The classifier performs temporal stabilization via its history deque; action-intent hold timing is the responsibility of `GestureHoldTimer` in `GestureMapper`.
- F-13: Updated README and GESTURES.md to correctly state Python 3.11 requirement (was incorrectly "Python 3.8+").
- F-18: Replaced `time.time()` with `time.perf_counter()` in `VolumeController` rate-limiting.
- F-21: Added `psutil` to PyInstaller spec `hiddenimports`.
- F-35: Renamed `test_lighting_robustness.py` tests to `test_landmark_noise_robustness_*` to accurately reflect what is tested.
- F-38: Replaced `time.time()` with `time.perf_counter()` in `DrawingCanvas.draw()` for monotonic timing.

### Removed
- Stale root-level `SmartGesture.spec` (F-20). Canonical spec is `packaging/windows/SmartGesture.spec`.

---

## [0.8.0] — 2025-09-20 _(pre-production hardening)_

### Added
- Async MediaPipe hand detection pipeline with result TTL.
- Bounded `frame_queue` to prevent memory growth.
- `GestureClassifier` EMA confidence scoring.
- `FeedbackController` bounded TTS queue with duplicate suppression.
- `GestureTrainer` with landmark normalization (translation, rotation, scale).
- platformdirs-based storage architecture via `paths.py`.
- Camera reconnect logic in `Camera.read()`.
- `VirtualMouse` deadzone and 1€ filter smoothing.
- Initial 60 unit tests.

### Fixed
- DXVA2 + SBC brightness control on Windows 10/11.
- Pycaw volume endpoint initialization error handling.

---

## [0.7.0] — 2025-08-15 _(prototype)_

- Initial working prototype: camera → MediaPipe → gesture → mouse.
