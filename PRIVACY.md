# Privacy Policy — SmartGestureOS

**Effective Date:** 2025-01-01\
**Last Updated:** 2026-09-27
**Project team:** Sarvagya Birla, Uday Dangi, Shantanu Yadav\
**Guide:** Ms. Ankita Dubey\
**Contact:** [GitHub Issues](https://github.com/Sarvagyabirla/SmartGestureOS/issues)

---

## Overview

SmartGestureOS processes webcam frames locally for gesture recognition. Its
application code has no account system or analytics service. The bundled
MediaPipe Tasks dependency [states that it sends API performance and usage
metrics to Google](https://github.com/google-ai-edge/mediapipe#privacy-notice).
MediaPipe also states that input data such as images is processed on device and
is not sent to Google. A native uploader error was observed during a real run;
the exact payload and successful transmission status of that run are unknown.

---

## Data We Collect

The application code has no analytics or account system. Camera frames and
landmarks are used in memory for gesture control.
The app can save screenshots, drawings, settings, custom gestures, and diagnostic
logs locally as described below.

| Category | Status |
|----------|--------|
| Camera images / video | Frames are processed in memory and are not saved by the capture pipeline. |
| Hand landmark coordinates | Used in memory for gesture recognition and control. |
| Gesture history | No history upload or analytics feature is implemented. |
| User identity / account | **No account required.** No login, no email, no name. |
| Usage analytics / telemetry | No analytics service is implemented in the application code. MediaPipe states that its Tasks APIs send performance and usage metrics to Google; see below. |
| Crash reports | The application writes local diagnostic logs and has no automatic crash-report submission feature. The content of MediaPipe metrics has not been independently inspected. |
| Network connections | MediaPipe states that its Tasks APIs send metrics to Google. In one local run, its native uploader logged a failed Clearcut upload. |

## Observed MediaPipe uploader activity

On 27 September 2026 at about 00:44:25 IST, a physical diagnostic run using
MediaPipe 0.10.35 logged `portable_clearcut_uploader.cc` reporting a failed
Clearcut upload. The local evidence is in
`logs/mouse-check-errors-20260927.txt` (a local diagnostic file, excluded from
Git). [MediaPipe issue #6291](https://github.com/google-ai-edge/mediapipe/issues/6291)
reports a matching native uploader message with this dependency version.

The observed log does not reveal the payload or establish a successful transfer.
It does not establish that camera frames were transmitted. The dependency's
[privacy notice](https://github.com/google-ai-edge/mediapipe#privacy-notice)
states that Tasks APIs send performance and usage metrics to Google and do not
send input images or video. We have not independently inspected the network
payload or verified which metrics this build sends. A zero-telemetry or
no-network guarantee would be inaccurate.

---

## Files Saved on This Device

The application writes the following files on your device:

| What | Where | Why |
|------|-------|-----|
| Application profiles (JSON) | `%LOCALAPPDATA%\SmartGesture\profiles\<name>.json` | Remember your preferences |
| Custom gesture models (JSON) | `%LOCALAPPDATA%\SmartGesture\custom_gestures\custom_gestures.json` | Store gestures you trained |
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
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for the pinned direct dependencies
and their licenses. Distribution notices also need to cover bundled transitive
components.

---

## Children's Privacy

SmartGestureOS does not target children or request personal account details.
The unresolved dependency behavior described above applies to all users.

---

## Changes to This Policy

If this policy changes materially, the `Last Updated` date will be updated and
a note will be added to [CHANGELOG.md](CHANGELOG.md).

---

## Contact

If you have questions, open a [GitHub Issue](https://github.com/Sarvagyabirla/SmartGestureOS/issues).
