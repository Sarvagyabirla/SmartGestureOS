# Changelog

All notable changes to SmartGestureOS are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)  
and this project adheres to [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

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
- F-02: Removed duplicate `opencv-contrib-python` from `requirements.txt`. Only `opencv-python` is kept (no contrib features are used).
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
