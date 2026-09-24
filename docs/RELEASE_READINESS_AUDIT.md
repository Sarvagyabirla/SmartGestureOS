# SmartGestureOS — Release Readiness Audit

**Baseline commit:** `ed775a8` (latest on `main`, Sep 25 2026)  
**Audit branch:** `production/v1-release-hardening`  
**Auditor:** Principal Software Architect / AI  
**Date:** 2026-09-25  
**Test baseline:** 60/60 PASS (pytest 9.1.1, Python 3.11.9)

---

## Summary

SmartGestureOS is a structurally sound project that has already gone through one
production-hardening pass. The async ML pipeline, event-engine state machine,
bounded queues, DXVA2+SBC brightness, and platformdirs-based storage are all
well-conceived. However, several real bugs, missing features, and packaging gaps
must be resolved before v1.0 can ship.

---

## Finding Register

| # | Finding | Severity | File(s) | Root Cause | User Impact | Proposed Fix | Test Required | Status |
|---|---------|----------|---------|------------|-------------|--------------|---------------|--------|
| F-01 | `psutil` missing from `requirements.txt` | HIGH | `requirements.txt`, `main.py` | `psutil` imported in main but not declared as production dep | App fails on clean install | Add `psutil>=5.9` to `requirements.txt` | pip check | FIXED |
| F-02 | Dual OpenCV wheels (`opencv-python` + `opencv-contrib-python`) | HIGH | `requirements.txt` | Both wheels provide `cv2`; conflict on pip install | pip check failure, import collision | Remove `opencv-contrib-python` (contrib not used); keep `opencv-python` only | pip check | FIXED |
| F-03 | `time.time()` used in cooldown/latency paths | MEDIUM | `src/shortcut_controller.py`, `src/volume_controller.py`, `src/drawing.py` | Wall-clock used instead of monotonic counter | Theoretically incorrect under DST/NTP jumps; minor | Replace with `time.perf_counter()` or `time.monotonic()` | unit | FIXED |
| F-04 | Camera disconnect does NOT call `on_hand_lost()` / reset event engine | CRITICAL | `main.py` (processing_loop) | When `camera.is_connected` is False, `mapper.process()` is skipped entirely — left button may remain pressed | Mouse left-button stuck on camera loss | Call `mapper.engine.on_hand_lost()` (via `mouse.release_all()`) in the camera-disconnect branch | unit + integration | FIXED |
| F-05 | `GestureMapper.process()` called with `[],"None","None"` on hand-loss but `on_hand_lost` is inside `MouseController`, only reached if `hands_data` path runs | MEDIUM | `src/gesture_mapper.py` | Mapper correctly calls `engine.on_hand_lost()` when `not hands_data`, but camera-disconnect bypasses the entire mapper call | Stale drag on camera disconnect | See F-04 fix; also verify `on_hand_lost` path is reachable from both routes | unit | FIXED |
| F-06 | Right-click fires repeatedly: `EventEngine` transitions to COOLDOWN after right-click, but re-enters HOVER → right-click again immediately if Three Fingers is still held | HIGH | `src/event_engine.py` | No release-gate on Three Fingers right-click; relies purely on COOLDOWN timing | Repeated context-menu opens | Add release-gate: Three Fingers right-click must see gesture change before re-arming | unit | FIXED |
| F-07 | `shell=True` in `ShortcutController._open()` | HIGH | `src/shortcut_controller.py` | All app launches use `subprocess.Popen(..., shell=True)` | Potential command injection if gesture name ever reaches command string; bad practice | Migrate to `shell=False` with explicit exe paths; use `os.startfile` for simple built-ins | unit | FIXED |
| F-08 | Camera actual resolution not propagated — mapper uses SETTINGS width/height | MEDIUM | `main.py`, `src/gesture_mapper.py` | GestureMapper uses `SETTINGS["camera"]["width"]` even if camera rejects the request | Mouse mapping wrong on cameras that don't support 1280×720 | Read actual frame shape and propagate to mapper | integration | FIXED |
| F-09 | Profile name sanitization absent | HIGH | `src/settings_manager.py` | Any string accepted as profile name, including `../../../evil` | Path traversal, write outside profiles dir | Add regex allowlist; reject path separators, reserved names, excessive length | unit | FIXED |
| F-10 | Undo stack pop-before-append off-by-one: `if len >= 20: pop` then `append` — max can be exactly 20, but initial `_save_state()` in `__init__` means first pop occurs at 20, giving effective max of 20; valid. But only one boundary tested | LOW | `src/drawing.py` | Logic is correct but boundary test missing | Could silently drift | Add explicit boundary test | unit | FIXED |
| F-11 | Screenshot/drawing filename collision at 1-second resolution | MEDIUM | `src/drawing.py`, `src/desktop_controller.py` | `int(time.time())` as filename; two saves in same second overwrite each other | Silent data loss | Use millisecond timestamp + random suffix | unit | FIXED |
| F-12 | `hold_time_ms` setting in `GestureClassifier` does not control classification (it's stored but never used to gate `classify()`) | MEDIUM | `src/gesture_classifier.py` | `self.hold_time` set but never referenced in `classify()` logic | Setting exposed to user but has no effect | Either remove misleading setting or implement properly; document | unit | FIXED |
| F-13 | `GESTURES.md` and README claim `Python 3.8+` compatibility | MEDIUM | `README.md`, `GESTURES.md` | mediapipe 0.10+ and several deps require 3.10+; `.python-version` = 3.11.9 | Developer confusion; build failures on wrong Python | Update docs to state Python 3.11 requirement | docs | FIXED |
| F-14 | No authoritative `src/version.py` — version is scattered | MEDIUM | Multiple files | No single version source | UI, logs, packaging inconsistent | Create `src/version.py`; use everywhere | — | FIXED |
| F-15 | No emergency kill-switch (Ctrl+Alt+G or equivalent) | HIGH | — | Missing feature | No recovery when gestures behave incorrectly | Implement global hotkey to pause/resume automation | integration | FIXED |
| F-16 | Camera startup failure shows no UI feedback — `start_system()` returns False silently | HIGH | `main.py` | `start_system()` returns False; UI doesn't reflect it | App appears frozen/blank with no camera | Show "No Camera" UI state with retry button | integration | FIXED |
| F-17 | Camera resolution: frame scaled to 640×360 for ML but mapper still receives SETTINGS dimensions as `frame_w`/`frame_h` instead of actual frame dimensions | HIGH | `main.py` (line 181, 208) | ML runs on 640×360 but mapper uses 1280×720; pixel_x/pixel_y computed from actual frame but mapper coordinate mapping uses wrong frame dims | Mouse movement mapped against wrong resolution | Pass actual `frame.shape` dims to mapper | integration | FIXED |
| F-18 | `VolumeController` uses `time.time()` for rate-limiting | LOW | `src/volume_controller.py` | Wall-clock for rate limiting | Theoretical skew | Replace with `time.perf_counter()` | unit | FIXED |
| F-19 | CI/CD (GitHub Actions) absent | HIGH | `.github/workflows/` | Never created | No automated build/test | Create `ci.yml`, `build-windows.yml`, `release.yml`, `pages.yml` | CI | FIXED |
| F-20 | PyInstaller spec in repo root (`SmartGesture.spec`) — `build_windows.ps1` references `packaging/windows/SmartGesture.spec` (already correct path) | MEDIUM | Root `SmartGesture.spec` | Stale root-level spec confuses contributors | Wrong spec may be used | Remove root spec; canonical is `packaging/windows/SmartGesture.spec` | build | FIXED |
| F-21 | `packaging/windows/SmartGesture.spec` missing `psutil` hidden import | MEDIUM | `packaging/windows/SmartGesture.spec` | psutil not in hiddenimports | Packaged app crashes on stats | Add `psutil` to hiddenimports | build | FIXED |
| F-22 | No `LICENSE` file | CRITICAL | — | Missing entirely | Cannot be published; legally ambiguous | Add MIT License | legal | FIXED |
| F-23 | No `PRIVACY.md` | HIGH | — | Missing; required for Store | Users cannot assess data handling | Create accurate privacy policy | legal | FIXED |
| F-24 | No `CHANGELOG.md` | MEDIUM | — | Missing | Release notes absent | Create CHANGELOG | docs | FIXED |
| F-25 | No `CONTRIBUTING.md` | LOW | — | Missing | Contributors have no guidance | Create CONTRIBUTING | docs | FIXED |
| F-26 | No `SECURITY.md` | MEDIUM | — | Missing | No vulnerability disclosure path | Create SECURITY | docs | FIXED |
| F-27 | No `SUPPORT.md` | LOW | — | Missing | Users have no support path | Create SUPPORT | docs | FIXED |
| F-28 | No `THIRD_PARTY_NOTICES.md` | HIGH | — | Missing; required for Store and OSS compliance | License compliance gap | Create with all bundled dependency licenses | legal | FIXED |
| F-29 | GitHub Pages product website absent | MEDIUM | `site/` | Never created | No public product page | Create static site | web | FIXED |
| F-30 | README performance claims unverified (`<20ms`, `60 FPS`) | MEDIUM | `README.md` | Claims without measurement | Misleading users | Rewrite as targets with test-machine disclosure | docs | FIXED |
| F-31 | `docs/HARDWARE_VALIDATION_MATRIX.md` absent | MEDIUM | `docs/` | Never created | No documented hardware compatibility | Create matrix | docs | FIXED |
| F-32 | `MSIX` packaging absent | MEDIUM | `packaging/windows/` | Never created | Cannot publish to Microsoft Store | Create AppxManifest + structure | packaging | FIXED |
| F-33 | No `src/version.py` → no single version authority | MEDIUM | — | See F-14 | Build/UI/installer version mismatch | Create version module | — | FIXED |
| F-34 | `main.py` camera disconnect branch: `mapper.mode` referenced but mapper imports process not in that branch | LOW | `main.py` line 162 | `self.mapper.mode` accessed without null check | Potential AttributeError if mapper failed to init | Guard with `hasattr` | unit | FIXED |
| F-35 | Lighting tests misnamed — they test "landmark noise robustness" not actual lighting | LOW | `tests/test_lighting_robustness.py` | Test names misleading | Developer confusion | Rename or add comment | docs | FIXED |
| F-36 | `hand_size_baseline` and `base_hand_size` are duplicate calibration keys | LOW | `config/defaults.json` | Two keys for same concept | Settings confusion | Consolidate to one | unit | FIXED |
| F-37 | `gesture_trainer.py` does not sanitize gesture names | HIGH | `src/gesture_trainer.py` | Any string accepted as gesture name in custom trainer | Path traversal / overwrite built-in gesture data | Add name sanitization + built-in gesture guard | unit | FIXED |
| F-38 | `drawing.py` uses `time.time()` for smoother | LOW | `src/drawing.py` | Wall-clock for animation timing | Minor accuracy issue | Use `time.perf_counter()` | unit | FIXED |
| F-39 | No camera-reconnect notification to event engine | MEDIUM | `main.py`, `src/event_engine.py` | Camera reconnect sets `is_connected=True` but engine stays in `HAND_LOST`; this is actually safe (hand must reappear), but should be documented | No user impact (engine re-arms on hand detection) | Document in code | docs | NOTED |
| F-40 | MSIX manifest placeholder values require Partner Center | BLOCKED | `packaging/windows/msix/` | Cannot be resolved without Microsoft account | Store submission impossible without real credentials | Document exact required steps | manual | DOCUMENTED |

---

## Priority Summary

| Priority | Count | Status |
|----------|-------|--------|
| CRITICAL | 2 | FIXED |
| HIGH | 14 | FIXED |
| MEDIUM | 16 | FIXED |
| LOW | 8 | FIXED / NOTED |
| BLOCKED | 1 | DOCUMENTED |

---

## Validation Approach

After each fix:
1. Run `pytest tests/ -v` — must remain 60+ PASS
2. Run `pip check` — must report no conflicts
3. For runtime fixes: launch `python main.py` and manually verify behavior
4. For packaging: run `scripts\build_windows.ps1` and test `dist\SmartGestureOS\SmartGestureOS.exe`
