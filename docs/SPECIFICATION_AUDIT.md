# Specification audit and implementation plan

Audit date: 27 September 2026. Deadline: 30 September 2026.

The [user's specification](PRODUCT_SPECIFICATION.md) is authoritative. It is an
unchanged copy of the supplied attachment (SHA256
`8A34C511D55DC0BE8B91CF0539E3471C572548B83D332D8D93FE20CC1CFC0F83`). Historical
reports provide evidence, not alternative requirements. SmartGestureOS is a
Windows 10/11 x64 webcam utility, not an operating system or certified
accessibility solution. It supplements conventional input.

## Baseline verified before implementation

- The selected `SMART_GESTURE_OS` workspace was empty. The adjacent
  `SmartGestureOS` checkout was clean at `d4a8743` on
  `debug/phase1b-hand-detection`. An isolated worktree was created here on
  `feat/spec-product-readiness`; the existing checkout was preserved.
- Python 3.11.9, **356 tests passed in 8.34 seconds**; `pip check` passed.
- `main.py --self-check` loaded the bundled model and completed real native
  MediaPipe VIDEO inference on an artificial image. This does not prove hand
  recognition or physical input behavior.
- Historical evidence records webcam/21 landmarks and user-confirmed cursor
  movement. It does not establish the other mouse interactions or a sustained
  stability session. Preserve those distinctions.
- Public repository checks: latest release HTTP 404, Pages HTTP 404,
  `has_pages=false`. [Main CI succeeded](https://github.com/Sarvagyabirla/SmartGestureOS/actions/runs/36272237842),
  but [Windows build failed its frozen self-check](https://github.com/Sarvagyabirla/SmartGestureOS/actions/runs/36272237865).
  [Pages failed during configuration](https://github.com/Sarvagyabirla/SmartGestureOS/actions/runs/36272237835).

## Subsystem map at the start of this pass

“Complete in code” means the requirement is implemented and has relevant
automated evidence; physical requirements still need physical acceptance.
“Partial” records both existing working behavior and outstanding requirements.

| Specification | Subsystem and implementation | Baseline assessment / remaining work |
|---|---|---|
| 1–4 | Product, platform, user journey: README, site, Python 3.11 environment | Partial. Correct Windows utility concept; no validated public installer. README overstates replacing physical input. |
| 5–6 | Architecture: `main.py`, `src/camera.py`, detector, classifier, mapper, event engine, controllers, UI | Complete in code: layers are already separated; retain them. Main owns worker lifecycle, fresh observations, pause and UI scheduling. |
| 7 | Camera: newest-frame thread, timestamps, retry/reconnect, validation | Partial. Recovery covered; actual dimensions not exposed by Camera; late blocked read can republish after stop. Physical disconnect/reconnect pending. |
| 8–9 | Detector: `gesture_detector.py`, 7,819,105-byte `models/hand_landmarker.task` | Partial. VIDEO inference works, normalized/pixel/world landmarks and timestamp ordering exist. Handedness label omitted. Real inference in frozen build failing. |
| 10–11 | Classifier: geometry, 14 gestures, confidence EMA, history stabilization | Complete in code with tests. Recognition across actual users, distances and lighting remains hardware work. Confidence is heuristic, not a calibrated accuracy probability. |
| 12–13, 18 | Mapper: GENERAL/MEDIA/DRAW plus existing profiles | Complete mappings in code, including all specified system/media actions and Call Me cycling. Native action outcomes pending. |
| 14 | `mouse_controller.py`, `virtual_mouse.py`: active region, real frame dimensions, smoothing | Complete in code; prior cursor confirmation retained. Multi-display/edge comfort needs hardware acceptance. |
| 15 | `event_engine.py`: release-based single/double click, hold drag, drop | Complete in code with regressions; physical click, double-click and drag/drop unverified. Preserve recent raw/stable gating fixes. |
| 16–17 | Event engine scroll accumulator, rate limits, right-click release gate | Complete in code with tests; physical scroll and held right-click acceptance pending. |
| 19 | `drawing.py`: in-app canvas, stroke history, undo/redo, eraser/color, unique saves, resizing | Complete in code with tests; physical DRAW interaction and saved result review pending. This canvas does not draw on arbitrary applications. |
| 20, 29 | Separate mouse, keyboard, media, volume, brightness, desktop, shortcut, presentation controllers | Partial. Failure containment/returns implemented; actual hardware/app availability varies. Optional audio read previously succeeded. Global hotkey failure only logged, needs visible fallback. |
| 21 | Main pause state, hotkey, UI button, release/reset/watchdog/re-arm | Incorrect edge case reproduced: low-confidence raw Pinch with stable Unknown satisfies neutral re-arm. Require both raw and stable neutral. Other safety transitions already tested. |
| 22, 28, 52 | CustomTkinter dashboard: camera, landmarks, raw/stable, confidence, mode, status, actions, CPU/RAM/latency | Partial. Core dashboard exists. Sidebar exceeds default height; camera/detector rates not distinguished; inference latency only in logs. |
| 23 | First-use guidance and Coach | Partial. Coach exists; canonical gesture names inconsistent, Four Fingers missing, first-use instructions absent. |
| 24 | Settings validation, profiles, callbacks | Partial. Sensitivity/smoothing/cooldown/calibration implemented defensively; no camera selector. Add selection with explicit restart requirement. |
| 25 | `paths.py`, platformdirs; per-user settings/models/output | Incorrect product directory name: `SmartGesture` rather than `SmartGestureOS`. Migrate existing data without overwriting or deleting it. Bundled resources stay read-only. |
| 26–27 | In-memory camera processing, rotating local logs, privacy/security/notices | Partial. No app account/upload/recording pipeline. Preserve accurate MediaPipe metrics disclosure; do not promise zero network activity. Verify packaged notices. |
| 30 | 356 automated tests, hardware-free fixtures, diagnostics, compileall/pip check | Complete baseline software checks; add regressions for defects discovered here. No automated test substitutes for physical acceptance. |
| 31–32 | Hardware report, guided mouse tool, previous short logs | Partial. Hand/cursor evidence exists; full feature matrix and 20–30 minute session absent. |
| 33–34 | Canonical PyInstaller ONEDIR spec, frozen self-check | Broken distribution gate. Remote native inference probe failed; inspect bundle, correct native dependency collection, rebuild and execute locally. |
| 35–36 | Canonical Inno Setup script, installer helper | Partial. Source exists, no validated current installer; local compiler absent. Build and exercise install/start/uninstall in isolation; clean-machine camera acceptance remains separate. |
| 37 | `src/version.py` | Complete source authority at 0.9.0. Keep tag, installer, MSIX and website consistent; add executable metadata. |
| 38–40 | CI, Windows build, draft release workflow, GitHub history | Partial. CI runs; build currently fails. New branch filter needs coverage. No public release or checksum artifact yet. |
| 41–43 | Static `site/index.html`, hero, Pages workflow | Partial locally; public deployment broken/disabled. Expand required information and mobile navigation, keep release download absent until it exists. |
| 44–49 | Single MSIX manifest and builder | Partial source / Store NOT STARTED. Exact identity unavailable, visual assets absent, no package/certification/submission. Create artwork and listing draft; never invent identity. |
| 50–51 | README, gestures, changelog, privacy, security, support, notices, readiness | Partial. All required files exist; stale paths and validation claims must be reconciled. Keep old execution reports historical and link current audit. |
| 53–54 | Final report, presentation and demo backup | Partial. Existing academic report is not current acceptance evidence; missing verified installed demo and backup recording. Prepare a factual rehearsal/backup checklist. |
| 55–59 | Exact ten-step roadmap and definition of done | Not complete. Execute the following priorities, record evidence, preserve external gates. |

## Prioritized implementation plan — exact ten-step roadmap

| Order | Step and priority | Work and acceptance |
|---|---|---|
| 1 | Real hand tracking — P0 | Retain VIDEO/native model; fix camera stop race and missing structured metadata. Reconfirm packaged model inference. Existing real-hand evidence retained; new hardware check required for candidate. |
| 2 | Core mouse control — P0 | Fix neutral re-arm bypass; preserve tested temporal engine. Run focused and full tests; obtain single/double click, drag/drop, scroll/right-click observations with the guided target. |
| 3 | Complete gesture features — P1 | Preserve required GENERAL/MEDIA/DRAW mappings. Add visible hotkey failure, usable coach/onboarding, camera settings and accurate performance display. Validate native features physically. |
| 4 | Stability — P0/P1 | Reject late capture after stop, preserve user data during path migration, run regressions; perform 20–30 minute physical interaction/recovery session. |
| 5 | Standalone EXE — P0 | Repair frozen native dependency failure, add icon/version, build ONEDIR, run frozen native inference from outside source/venv. Exercise GUI/shutdown; record hardware limits. |
| 6 | Installer — P1 | Build canonical Inno installer, compute SHA256, test isolated install/start/uninstall/reinstall; validate camera and controls on a clean Windows machine. |
| 7 | GitHub Release — P1 | Push reviewable branch and obtain current CI/build evidence. Prepare release notes/checksum; publish v0.9.0 only after the physical and installer gates pass. |
| 8 | GitHub Pages — P1 | Complete responsive static product site, test local links/content, enable Pages account setting, deploy after source review, verify public URLs. Download links require a real release. |
| 9 | Microsoft Store — P1 | Produce valid PNG/ICO assets and listing draft; obtain exact Partner Center identity, then build/sign/validate MSIX and submit. Record real certification status. |
| 10 | Presentation freeze — P1 | Freeze a tested installed build, installer/checksum/source backups, actual screenshots/video, factual architecture and limitations, and rehearsed demo. |

Independent build, website and documentation preparation may proceed while
hardware acceptance is pending. Later steps are not marked accepted merely
because preparatory source changes exist.

## Execution evidence

Implementation and final verification results for this pass will be recorded in
[PRODUCT_EXECUTION_2026-09-27.md](PRODUCT_EXECUTION_2026-09-27.md).
