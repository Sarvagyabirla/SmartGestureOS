# Support

## Getting Help

SmartGestureOS is a project by Sarvagya Birla, Uday Dangi, and Shantanu Yadav,
guided by Ms. Ankita Dubey. Use the following support channels:

| Issue Type | Where to Go |
| :--- | :--- |
| Bug report (camera not working, crash, wrong gesture) | [GitHub Issues](https://github.com/Sarvagyabirla/SmartGestureOS/issues) |
| Feature request | [GitHub Issues](https://github.com/Sarvagyabirla/SmartGestureOS/issues) — label `enhancement` |
| Question / usage help | [GitHub Issues](https://github.com/Sarvagyabirla/SmartGestureOS/issues) |
| Security vulnerability | See [SECURITY.md](SECURITY.md) — **do not open a public issue** |

## Before Reporting a Bug

1. Read [GESTURES.md](GESTURES.md) — make sure the gesture is supported.
2. Check [existing issues](https://github.com/Sarvagyabirla/SmartGestureOS/issues?q=is%3Aissue).
3. Collect your log file: `%LOCALAPPDATA%\SmartGestureOS\logs\smart_gesture_os.log`

## Information to Include in a Bug Report

```text
OS: Windows 11 22H2 / Windows 10 21H2
Python: (if running from source)
Camera: Logitech C920 / Built-in laptop webcam / etc.
Lighting: Good / Low / Mixed
Steps to reproduce:
  1.
  2.
Expected: ...
Actual: ...
Log snippet: (paste from smart_gesture_os.log)
```

## FAQ

**Q: The app can't find my camera.**  
A: Close other applications using the camera and check Windows camera permissions. In Settings, select the camera number (0 is usually the first camera), save, then restart SmartGestureOS. Camera changes apply on restart. Profiles live under `%LOCALAPPDATA%\SmartGestureOS\profiles\<name>.json`.

**Q: Gestures are detected but the mouse doesn't move.**  
A: Check that automation is enabled, GENERAL mode is selected, and a hand is tracked. After resuming, briefly remove your hand so the neutral re-arm can complete. Settings, Trainer, and Coach pause automation when opened; use Resume when ready. The physical mouse diagnostic additionally requires its target window to have focus.

**Q: The mouse clicks randomly.**  
A: Pause with Ctrl+Alt+G first. Use even, front-facing lighting and check that the intended gesture is shown before resuming. Report repeatable unintended clicks with the displayed raw/stable gesture and local log excerpt.

**Q: Can I add my own gestures?**  
A: Yes — click **Train Custom Gesture** to open the Trainer window. Automation pauses while it opens. See [GESTURES.md](GESTURES.md) for instructions.

**Q: Does SmartGestureOS upload any data?**  
A: The application code has no account or analytics service. [MediaPipe's privacy notice](https://github.com/google-ai-edge/mediapipe#privacy-notice) says its Tasks APIs send performance and usage metrics to Google and process input images on device. Its native uploader logged a failed attempt during a real run on 27 September 2026. We did not establish the payload or delivery status of that attempt. See [PRIVACY.md](PRIVACY.md).

**Q: What Python version is required?**  
A: Python 3.11 is the supported project environment. Check `requirements.txt` if you use a different Python version.
