# SmartGestureOS Release Readiness

## Current status

The source tree has automated coverage for the camera pipeline, gesture classifier,
action routing, mouse control, and drawing. The runtime uses MediaPipe VIDEO mode
and a one-frame camera queue so stale frames do not build up. The camera and
landmark pipeline has been measured locally; physical gesture accuracy and the
installer still need human validation on the target Windows computer.

## Packaging status

- The application version is defined in `src/version.py` (`0.9.0`).
- The Windows installer is built from the PyInstaller ONEDIR output using Inno
  Setup; the configured output directory is `dist/release`.
- MSIX packaging uses `packaging/windows/msix/AppxManifest.xml` and
  `scripts/build_msix.ps1`.
- The MSIX build is intentionally blocked until real visual assets and exact
  Partner Center identity values are provided. No Store identity is assumed.
- Store signing, submission, and certification have not been performed.

## Validation still required

- Run the app and check every gesture in GENERAL, MEDIA, and DRAW modes with a
  physical webcam and verify the cursor and UI feedback.
- Verify camera unplug/reconnect and recovery from lighting or tracking loss.
- Build and install the Windows installer on a clean Windows 10/11 x64 machine.
- After supplying Partner Center identity and artwork, build, sign, and validate
  the MSIX package.

Automated test results and benchmark observations are recorded in
`docs/HARDWARE_VALIDATION_REPORT.md`. Do not treat manual checks as passed until
they are run on hardware.
