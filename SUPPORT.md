# Support

## Getting Help

SmartGestureOS is maintained by a solo developer. Please use the appropriate
channel for your issue type:

| Issue Type | Where to Go |
|------------|-------------|
| Bug report (camera not working, crash, wrong gesture) | [GitHub Issues](https://github.com/Sarvagyabirla/SmartGestureOS/issues) |
| Feature request | [GitHub Issues](https://github.com/Sarvagyabirla/SmartGestureOS/issues) — label `enhancement` |
| Question / usage help | [GitHub Discussions](https://github.com/Sarvagyabirla/SmartGestureOS/discussions) |
| Security vulnerability | See [SECURITY.md](SECURITY.md) — **do not open a public issue** |

## Before Reporting a Bug

1. Read [GESTURES.md](GESTURES.md) — make sure the gesture is supported.
2. Check [existing issues](https://github.com/Sarvagyabirla/SmartGestureOS/issues?q=is%3Aissue).
3. Collect your log file: `%LOCALAPPDATA%\SmartGestureOS\logs\latest.log`

## Information to Include in a Bug Report

```
OS: Windows 11 22H2 / Windows 10 21H2
Python: (if running from source)
Camera: Logitech C920 / Built-in laptop webcam / etc.
Lighting: Good / Low / Mixed
Steps to reproduce:
  1.
  2.
Expected: ...
Actual: ...
Log snippet: (paste from latest.log)
```

## FAQ

**Q: The app can't find my camera.**  
A: Check that no other application (Teams, Zoom) is using the camera. Try changing the camera index in Settings.

**Q: Gestures are detected but the mouse doesn't move.**  
A: Ensure the SmartGestureOS window is focused when you start. On some systems, camera must be open before starting the gesture engine.

**Q: The mouse clicks randomly.**  
A: Lighting conditions affect hand tracking. Ensure you have even, front-facing lighting and no strong backlighting.

**Q: Can I add my own gestures?**  
A: Yes — use the **Trainer** tab in the UI. See [GESTURES.md](GESTURES.md) for instructions.

**Q: Does SmartGestureOS upload any data?**  
A: No. See [PRIVACY.md](PRIVACY.md).

**Q: What Python version is required?**  
A: Python 3.11 exactly. MediaPipe and several other dependencies require 3.11+.
