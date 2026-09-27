# MSIX Packaging

This directory contains the single canonical MSIX manifest. Build the standard
PyInstaller ONEDIR output first, then run `scripts\build_msix.ps1` from the
repository root. Use `-PythonExe 'C:\path\to\python.exe'` when the Python 3.11
environment is outside the checkout.

**Store status: NOT STARTED.** The manifest still intentionally contains the
Partner Center identity placeholders. No package or submission is claimed.
Listing copy is prepared in [STORE_LISTING.md](STORE_LISTING.md).

## Required inputs

- Windows 10/11 and the Windows SDK (`makeappx.exe`)
- `dist\SmartGestureOS\SmartGestureOS.exe` and the rest of the ONEDIR output
- Exact package identity, publisher, and publisher display name from Partner
  Center entered in `AppxManifest.xml`
- Real PNG files are already provided in `Assets\` with these exact dimensions:

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

The original 21-landmark hand mark is rendered by
`scripts\generate_brand_assets.ps1` using Windows GDI+ vector primitives. That
script regenerates all six PNGs and the multi-resolution desktop ICO without
external artwork or image downloads. Keep the generated resources committed.

The manifest requests webcam access and `runFullTrust`, as required by the
camera-driven desktop app. Test signing is only for local sideloading. Store
submission requires the Partner Center identity and must follow Microsoft's
current submission and signing process.

Before uploading, replace all three identity fields with the exact values from
the Partner Center Product Identity page, build the package, test installation
and the complete hardware checklist, and complete the listing screenshots and
age-rating questionnaire. Microsoft performs certification after submission;
its status must be recorded separately from a successful local build.
