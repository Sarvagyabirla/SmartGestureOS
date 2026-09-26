# Hardware and Automated Validation

**Updated:** 2026-09-26

## Automated checks

- `python -m pytest -q tests`: **150 passed**.
- `python -m compileall -q main.py config.py src tests`: passed.
- MSIX manifest XML and PowerShell build script syntax: parsed successfully.
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

Automated simulation does not certify camera accuracy or safety of desktop
actions on a person's machine. No installer or signed MSIX was built in this
validation pass.
