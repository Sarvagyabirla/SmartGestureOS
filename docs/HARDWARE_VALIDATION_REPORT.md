# Hardware and Automated Validation

**Updated:** 2026-09-26

## Automated checks

- Python 3.11.9: `python -m pytest tests/ -v --tb=short`: **181 passed**.
- `python -m compileall -q main.py config.py src tests scripts`: passed.
- `python -m pip check`: passed, no broken requirements.
- RGB skeleton drawing is covered with deterministic red and green color-phase
  assertions. Gesture classifier tests cover the built-in pose patterns and
  input-control regressions cover click, double-click, drag, scroll, and
  right-click behavior.

## Camera pipeline samples

Measured with `scripts/diagnose_hand_pipeline.py` on the current Windows machine.
These short runs are observations, not controlled performance guarantees.

| Inference input | Inference rate | Detector latency | Camera-to-landmark | Hand frames |
|---|---:|---:|---:|---:|
| 640 × 360 | 20.42 FPS | 23.20 ms | 33.48 ms | 0 / 123 |
| 480 × 270 | 11.17 FPS | 77.97 ms | 116.10 ms | 0 / 67 |
| 320 × 180 | 19.63 FPS | 20.69 ms | 28.49 ms | 2 / 118 |

The results varied substantially between runs. The 640 × 360 setting remains
the application default because the smaller input did not show a consistent
throughput improvement, and the brief samples did not include a controlled
gesture-recognition comparison. For faster pointer response, the default
One-Euro filter setting was reduced; the Settings slider can trade smoothness
for responsiveness.

## Controlled hardware validation (2026-09-26)

Validated on the development Windows machine using camera 0, model
`models/hand_landmarker.task` (7,819,105 bytes; SHA-256
`fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1`), and a
physical hand in front of the webcam.

| Check | Result |
|---|---|
| IMAGE mode, original frame | 1 hand; 21 landmarks; 99.7% confidence |
| IMAGE mode, mirrored / 640x360 / padded 640x640 | 1 hand in each case |
| IMAGE thresholds 0.5 / 0.4 / 0.3 | 1 hand at each threshold |
| VIDEO mode, sequential webcam frames | 48 / 48 frames with a hand |
| LIVE_STREAM, original / 640x360 | 59 / 59 callbacks; 55 / 58 callbacks with a hand |
| `main.py --start-paused` live preview | 21 landmarks displayed; fingertip coordinates changed as the hand moved |
| Hand loss and reacquisition in the app | Landmarks cleared on loss, then returned as 21 points after re-entry |
| App session | Remained responsive for over 2 minutes and shut down without a crash |

During the live application run, preview cadence was approximately 22-31 FPS
and detector latency approximately 7.6-9.7 ms. Automation stayed paused during
this check. One initial 10-second standalone production-pipeline sample
reported 0/149 hand frames; a subsequent controlled mode matrix and the live
application check detected and tracked the hand. Treat the initial result as a
non-repeatable sample, not evidence of a persistent VIDEO-mode failure.

The application also logged that its pycaw audio endpoint could not initialize
(`AudioDevice` has no `Activate` attribute), so volume control was disabled on
this machine during the tracking check. Volume behavior still needs separate
investigation and validation.

## Manual checks still needed

- Present each gesture deliberately and verify the expected action in all three
  modes with a person operating the app.
- Verify RGB hand highlighting in the live UI and check sustained tracking under
  different lighting and hand distances.
- Test camera disconnect/reconnect, cursor feel, and high system load while the
  app window is open.
- Build and install the Windows installer on a clean Windows 10/11 x64 machine.
- Build and sign MSIX only after real artwork and Partner Center identity values
  have been supplied.

Automated simulation does not certify gesture accuracy or safety of desktop
actions on a person's machine. The physical tracking check does not validate
all gesture-to-action mappings. No installer or signed MSIX was built in this
validation pass.
