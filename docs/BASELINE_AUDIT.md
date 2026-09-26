# SmartGestureOS Baseline Audit

> Historical snapshot from the pre-hardening baseline. Findings below describe
> that earlier tree and are not a current status report. See
> [`RELEASE_READINESS.md`](../RELEASE_READINESS.md) and
> [`HARDWARE_VALIDATION_REPORT.md`](HARDWARE_VALIDATION_REPORT.md) for the
> current state and validation results.

## 1. Current Git State
- **Branch**: `hardening/production-v1` (derived from `main`)
- **Untracked / Modified Files**: Numerous files were modified and untracked (including `.gitignore`, `GESTURES.md`, `main.py`, `src/*`, `tests/*`, etc.). These were preserved in the `backup/pre-production-YYYYMMDD-HHMM` branch and snapshotted.
- **Repository hygiene**: The current directory contains non-distribution files such as `.venv` (approx. 395MB), `.git` (approx. 6.5MB), `__pycache__`, `.pytest_cache`, `logs/`, `build/`, `dist/`.

## 2. Python Requirement and Environment
- **Target / Validated Runtime**: Python 3.11.x (specifically 3.11.9).
- **Discrepancy**: The README still claims Python 3.8+ support which is outdated.

## 3. Dependency Graph & Problems
- **OpenCV Conflict**: Both `opencv-python` and `opencv-contrib-python` are present. This needs to be validated and pinned to known-good versions.
- **Dependency Versioning**: Dependencies in `requirements.txt` currently use broad `>=` ranges instead of specific pinned versions.

## 4. Source Tree & Packaging Inventory
- **Model / Assets**: `Landmark` and `GestureResult` dataclasses exist.
- **Packaging**: Absent. No production `.spec`, MSIX project/template, installer definition, or Windows build scripts. `.gitignore` currently ignores `*.spec`.
- **Licensing**: README claims MIT License, but no `LICENSE` file actually exists in the ZIP.
- **Assets**: `assets/` lacks a production application icon (ICO/PNG) suitable for packaging.

## 5. Test Inventory
- **Current Suite**: 31 test functions present in the latest ZIP.
- **Hardware Coupling**: The camera test can accidentally touch real hardware during the ordinary CI suite.
- **UI Tests**: Test dependencies rely on real display/Tk instances, requiring headless isolation.

## 6. Known Runtime Issues
- **Unsafe Hand-Loss**: `GestureMapper.process()` returns immediately when no hands are present, bypassing the mouse controller and leaving drags stuck active.
- **State Confusion**: The drawing code's clear function executes repeatedly per frame on Pinch, contrary to the `GESTURES.md` stating it clears on Closed Fist.
- **Config & Storage**: Profiles, logs, screenshots, and custom gesture models use repo-relative paths (e.g., `profiles/`, `logs/`), making them incompatible with MSIX / read-only program files.

## 7. Unverified Claims
- **Latency & Performance**: Claims of `<20 ms` and `60 FPS` in README lack benchmark artifacts to support them.
- **Distance Benchmark**: The current `scripts/benchmark_distance.py` relies on an obsolete API and uses a hardcoded typical hand size to estimate distance rather than empirical measurement.

## 8. Architectural Risks
- **Confidence Model**: MediaPipe's *handedness* score is incorrectly mapped directly to `hands_data["score"]` and used as gesture recognition confidence.
- **Consensus & Temporality**: Classifier uses a weak 5-frame consensus (accepting 2/5).
- **Fragmented Logic**: Temporal filtering/holding logic is spread across the classifier, `GestureHoldTimer`, and the mouse controller.
- **Drawing Memory Bandwidth**: The drawing history clones the entire 1280x720 image instead of representing stroke objects.
- **MediaPipe Timing**: `time.time()` is incorrectly used as the timestamp source for `LIVE_STREAM` async processing instead of a monotonically increasing clock.
- **Stale Frame Re-use**: Up to 150ms of stale landmarks are reused without verifying age.

## 9. Security Risks
- **Command Execution**: `ShortcutController` uses `subprocess.Popen(..., shell=True)` (e.g., `start chrome`). This is highly fragile and presents a critical risk if a remote interface (Android) is exposed in the future.

## 10. Performance Risks
- **Telemetry Errors**: The UI FPS counter reports the processing-loop iteration rate rather than actual capture, inference, and UI rendering speeds separately.
