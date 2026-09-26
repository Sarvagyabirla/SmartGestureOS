# MSIX Packaging

This directory contains the single canonical MSIX manifest. Build the standard
PyInstaller ONEDIR output first, then run `scripts\build_msix.ps1` from the
repository root.

## Required inputs

- Windows 10/11 and the Windows SDK (`makeappx.exe`)
- `dist\SmartGestureOS\SmartGestureOS.exe` and the rest of the ONEDIR output
- Exact package identity, publisher, and publisher display name from Partner
  Center entered in `AppxManifest.xml`
- Real PNG files in `Assets\` with these exact dimensions:

| File | Dimensions |
|------|------------|
| `StoreLogo.png` | 50 × 50 |
| `Square44x44Logo.png` | 44 × 44 |
| `Square150x150Logo.png` | 150 × 150 |
| `Wide310x150Logo.png` | 310 × 150 |
| `Square310x310Logo.png` | 310 × 310 |
| `SplashScreen.png` | 620 × 300 |

The packaging script reads the version from `src/version.py`, validates the
identity, executable, and image files, then writes
`dist\release\SmartGestureOS_<version>_x64.msix`. It stops with an actionable
error when a required input is missing; it never creates placeholder artwork.

The manifest requests webcam access and `runFullTrust`, as required by the
camera-driven desktop app. Test signing is only for local sideloading. Store
submission requires the Partner Center identity and must follow Microsoft's
current submission and signing process.
