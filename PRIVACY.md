# Privacy Policy — SmartGestureOS

**Effective Date:** 2025-01-01  
**Last Updated:** 2026-09-26
**Developer:** Sarvagya Birla  
**Contact:** [GitHub Issues](https://github.com/Sarvagyabirla/SmartGestureOS/issues)

---

## Overview

SmartGestureOS processes webcam frames locally for gesture recognition. The
application does not include an account, analytics, or telemetry feature. Review
the third-party library notices for the behavior and licenses of bundled
dependencies.

---

## Data We Collect

The app has no analytics or account system and does not send usage data to the
developer. Camera frames and landmarks are used in memory for gesture control.
The app can save screenshots, drawings, settings, custom gestures, and diagnostic
logs locally as described below.

| Category | Status |
|----------|--------|
| Camera images / video | Frames are processed in memory and are not saved by the capture pipeline. |
| Hand landmark coordinates | Used in memory for gesture recognition and control. |
| Gesture history | No history upload or analytics feature is implemented. |
| User identity / account | **No account required.** No login, no email, no name. |
| Usage analytics / telemetry | No application analytics or telemetry feature is implemented. |
| Crash reports | **Not automatically sent.** Log files are stored locally only (see below). |
| Network connections | The app has no account or cloud processing feature. Network behavior of third-party dependencies is governed by their own code and policies. |

---

## Local Storage Only

SmartGestureOS stores the following data **locally on your device only**:

| What | Where | Why |
|------|-------|-----|
| Application settings (JSON) | `%LOCALAPPDATA%\SmartGesture\settings.json` | Remember your preferences |
| Custom gesture models (JSON) | `%LOCALAPPDATA%\SmartGesture\custom_gestures\` | Store gestures you trained |
| Screenshots (PNG) | `%LOCALAPPDATA%\SmartGesture\screenshots\` | Saved when you use the screenshot action |
| Drawings (PNG) | `%LOCALAPPDATA%\SmartGesture\drawings\` | Saved when you use save-drawing in Draw mode |
| Log files | `%LOCALAPPDATA%\SmartGesture\logs\smart_gesture_os.log` | Local debugging |

All of this data is stored in the standard Windows per-user app data folder.
You can delete it at any time by removing that folder.

---

## Camera and Microphone Access

SmartGestureOS accesses your **camera** to detect hand gestures in real time.

- The application camera pipeline processes frames in memory and does not write
  them to disk or send them to the developer. See third-party library notices
  for information about bundled dependency behavior.
- No microphone access is required or requested.

---

## Third-Party Libraries

SmartGestureOS bundles several open-source libraries. See
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
