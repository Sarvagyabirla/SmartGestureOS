# MSIX Packaging Guide

## Overview

This directory contains the MSIX manifest for Microsoft Store submission.
MSIX wraps the PyInstaller ONEDIR output into a store-deployable package.

## Prerequisites

- Windows 10/11 with **Windows SDK** installed (for `makeappx.exe`, `signtool.exe`)
- PyInstaller build completed (`dist\SmartGestureOS\` folder exists)
- Microsoft Partner Center account: https://partner.microsoft.com

## Step-by-Step: First Store Submission

### 1. Reserve the app name in Partner Center

1. Log in to https://partner.microsoft.com/en-us/dashboard
2. Click **"New product"** → **"MSIX or PWA app"**
3. Enter the product name: `SmartGestureOS`
4. On the **Product Identity** page, note down:
   - **Package/Identity Name** (e.g., `12345YourPublisherName.SmartGestureOS`)
   - **Publisher** (e.g., `CN=XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX`)
   - **Publisher Display Name** (your display name)

### 2. Update AppxManifest.xml

Replace the placeholder values in `AppxManifest.xml`:

```xml
<Identity
  Name="12345YourPublisherName.SmartGestureOS"
  Publisher="CN=XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX"
  Version="0.9.0.0"
  ... />
<PublisherDisplayName>Your Publisher Display Name</PublisherDisplayName>
```

Also update `src/version.py` to match the version.

### 3. Create visual assets

Required sizes (PNG with transparent background):

| File | Size |
|------|------|
| `Assets\Square44x44Logo.png` | 44×44 px |
| `Assets\Square44x44Logo.targetsize-16.png` | 16×16 px |
| `Assets\Square44x44Logo.targetsize-32.png` | 32×32 px |
| `Assets\Square150x150Logo.png` | 150×150 px |
| `Assets\Wide310x150Logo.png` | 310×150 px |
| `Assets\Square310x310Logo.png` | 310×310 px |
| `Assets\SplashScreen.png` | 620×300 px |

Use the Partner Center visual assets tool or create them manually.

### 4. Build the MSIX

```powershell
# Build PyInstaller output first
python -m PyInstaller --noconfirm --clean packaging\windows\SmartGesture.spec

# Create mapping file
$mappingContent = @"
[Files]
"dist\SmartGestureOS\SmartGestureOS.exe" "SmartGestureOS.exe"
"packaging\windows\msix\AppxManifest.xml" "AppxManifest.xml"
"packaging\windows\msix\Assets\Square150x150Logo.png" "Assets\Square150x150Logo.png"
"packaging\windows\msix\Assets\Square44x44Logo.png" "Assets\Square44x44Logo.png"
"packaging\windows\msix\Assets\Wide310x150Logo.png" "Assets\Wide310x150Logo.png"
"packaging\windows\msix\Assets\Square310x310Logo.png" "Assets\Square310x310Logo.png"
"packaging\windows\msix\Assets\SplashScreen.png" "Assets\SplashScreen.png"
[ResourceMetadata]
"ResourceDimensions" "language-en-US"
"@
$mappingContent | Out-File -FilePath dist\msix_mapping.txt -Encoding UTF8

# Build MSIX
makeappx.exe pack /m packaging\windows\msix\AppxManifest.xml /f dist\msix_mapping.txt /p dist\SmartGestureOS.msix /o
```

### 5. Sign the MSIX (for sideloading / testing only)

For Store submission, Microsoft signs the package. For local testing:

```powershell
# Create self-signed cert (testing only)
New-SelfSignedCertificate -Type Custom -Subject "CN=SmartGestureOS Test" `
  -KeyUsage DigitalSignature -FriendlyName "SmartGestureOS Test" `
  -CertStoreLocation "Cert:\CurrentUser\My" `
  -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3", "2.5.29.19={text}")

# Sign
signtool.exe sign /fd SHA256 /a dist\SmartGestureOS.msix
```

### 6. Submit to Partner Center

1. Upload `SmartGestureOS.msix` on the submission page.
2. Complete all required metadata (categories, age rating, description, screenshots).
3. Add the Privacy Policy URL (your GitHub Pages site `/privacy`).
4. Submit for certification.

## Important Notes

- **runFullTrust capability**: Required for all PyInstaller/desktop bridge apps.
  This requires Microsoft approval in the Store.
- **webcam capability**: Declared and required. Will appear in Windows permission dialog.
- **Version must increment**: Every Store submission needs a higher `Version` in the manifest.
