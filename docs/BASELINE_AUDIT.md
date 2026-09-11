# SmartGestureOS Baseline Audit

This document summarizes the current state of the SmartGestureOS project, detailing existing bugs, architectural issues, configuration conflicts, and performance bottlenecks as discovered during Phase 0 of the production upgrade.

## 1. Bugs
- **Custom Gesture Normalization:** `gesture_trainer.py` uses pixel x/y or a mix of normalized and pixel values depending on dictionary/list format. It does not consistently use normalized coordinates for robust 3D shape comparison.
- **Victory Sleep Conflict:** The "Victory" gesture is mapped to both "open_vscode" (or "undo" in DRAW mode) and hardcoded as `toggle_sleep` in the codebase.
- **Classifier Lag:** Action gestures are evaluated using simple EMA smoothing but apply `hold_time_ms` for everything, causing lag for continuous movements.
- **Pinch State Machine:** `MouseController` implements a brittle pinch state machine with timeouts that conflict with continuous tracking.
- **Unverified Statuses:** The UI simply reads `self.camera.is_connected` and hardcoded flags rather than using a true robust status system.

## 2. Architecture Issues
- **Configuration Fragmentation:** Configuration is split between `config.py` (which loads from `settings_manager`), `profiles/default.json`, `settings.json` (if present), and hardcoded defaults in `settings_manager.py`.
- **Missing Action Results:** Controllers execute actions but do not return an `ActionResult` with success/failure data. `gesture_mapper.py` simply returns "Executed" blindly.
- **Gesture Confidence:** The classifier returns `self.confidence_ema`, which is derived from geometric matches and handedness probability, rather than a genuine stability and shape confidence metric.
- **Timer Duplication:** `GestureMapper` has its own `GestureHoldTimer`, `GestureClassifier` has `hold_time`, and `MouseController` tracks `gesture_start_time`. This causes overlapping state tracking.
- **App Launching:** `ShortcutController` likely uses fragile subprocess launching without robust path resolution.

## 3. Configuration & Mapping Conflicts
- **Strict Mapping Violations:** The `Victory` gesture is overloaded. `settings_manager.py` defines defaults that may conflict with `GESTURES.md`.
- **Missing Mappings:** The newer `Crossed Fingers` and `Middle Finger` (brightness) are implemented, but need to be cleaned up regarding mirrored camera output and strict 1-to-1 enforcement.

## 4. Performance Problems
- **Inference Pacing:** `main.py` manually paces the inference loop to 30 FPS and rendering to 60 FPS using `time.sleep()`. While it attempts decoupling, thread synchronization via a size-1 queue drops frames inefficiently.
- **Drawing Engine:** Recreates overlays on the frame per-tick instead of efficiently maintaining stroke history.
- **Metrics:** Displayed FPS is computed using a simple EMA of loop time instead of discrete capture/inference/UI timestamps.

## 5. Unsafe Code
- The use of subprocess without paths or argument sanitization poses a risk for remote-execution features on Android.

## 6. Incorrect Tests
- Tests currently access `cv2.VideoCapture` directly in standard runs, failing in CI or environments without physical cameras.

## 7. Next Steps
The project requires a comprehensive cleanup (Phase 1), unifying the configuration system (Phase 2), and migrating to a robust single-event engine and typed data model (Phases 4-10) before expanding Android features.
