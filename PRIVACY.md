# Privacy Policy — SmartGestureOS

**Effective Date:** 2025-01-01  
**Last Updated:** 2025-09-25  
**Developer:** Sarvagya Birla  
**Contact:** [GitHub Issues](https://github.com/Sarvagyabirla/SmartGestureOS/issues)

---

## Overview

SmartGestureOS is a **local-only** Windows desktop application. It runs entirely
on your device. No data ever leaves your computer.

---

## Data We Collect

**SmartGestureOS collects no data from you.**

More specifically:

| Category | Status |
|----------|--------|
| Camera images / video | **Never recorded or stored.** Processed in memory at runtime only. |
| Hand landmark coordinates | **Never stored or transmitted.** Processed in memory during each frame. |
| Gesture history | **Never logged or uploaded.** |
| User identity / account | **No account required.** No login, no email, no name. |
| Usage analytics / telemetry | **None.** Zero telemetry or analytics code. |
| Crash reports | **Not automatically sent.** Log files are stored locally only (see below). |
| Network connections | **None.** The app does not connect to the internet in any way. |

---

## Local Storage Only

SmartGestureOS stores the following data **locally on your device only**:

| What | Where | Why |
|------|-------|-----|
| Application settings (JSON) | `%LOCALAPPDATA%\SmartGestureOS\settings\` | Remember your preferences |
| Custom gesture models (JSON) | `%LOCALAPPDATA%\SmartGestureOS\models\` | Store gestures you trained |
| Screenshots (PNG) | `%LOCALAPPDATA%\SmartGestureOS\screenshots\` | Saved when you use the screenshot gesture |
| Drawings (PNG) | `%LOCALAPPDATA%\SmartGestureOS\drawings\` | Saved when you use save-drawing in Draw mode |
| Log files (TXT) | `%LOCALAPPDATA%\SmartGestureOS\logs\` | Local debugging only; not transmitted |

All of this data is stored in the standard Windows per-user app data folder.
You can delete it at any time by removing that folder.

---

## Camera and Microphone Access

SmartGestureOS accesses your **camera** to detect hand gestures in real time.

- Frames are processed in memory by the MediaPipe hand-tracking library.
- Frames are **never** written to disk, stored in a database, or transmitted.
- No microphone access is required or requested.

---

## Third-Party Libraries

SmartGestureOS bundles several open-source libraries. These libraries run locally
on your device and do not communicate with their authors' servers. See
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for a full list and their licenses.

---

## Children's Privacy

SmartGestureOS does not target children and does not collect any information from
any person of any age.

---

## Changes to This Policy

If this policy changes materially, the `Last Updated` date will be updated and
a note will be added to [CHANGELOG.md](CHANGELOG.md).

---

## Contact

If you have questions, open a [GitHub Issue](https://github.com/Sarvagyabirla/SmartGestureOS/issues).
