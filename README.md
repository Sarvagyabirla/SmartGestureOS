# SmartGestureOS

**Real-Time Hand Gesture Control System for Desktop Automation**

Computer Vision Based Touchless Human-Computer Interaction

[![Python](https://img.shields.io/badge/Python-3.11.x-blue)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-blue)](https://microsoft.com/windows)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

> **What is SmartGestureOS?**  
> SmartGestureOS is a Windows desktop automation application that lets you control your PC using webcam-based hand gestures — no mouse or keyboard required. It is **not** a real operating system. It runs *on top of* Windows.

---

## Features

- **Three control modes** — GENERAL (mouse + OS), MEDIA, and DRAW
- **Real-time hand tracking** via MediaPipe Hand Landmarker (21 3D landmarks)
- **16 built-in gestures** — Pointing, Pinch, Victory, Rock On, Open Palm, Closed Fist, Thumb Up/Down, Two Fingers, Three Fingers, Four Fingers, Middle Finger, Call Me, Crossed Fingers, and more
- **Temporal event engine** — single/double click, drag, and scroll are temporal events, not static poses
- **Custom gesture training** — record and match your own gestures (nearest-sample matching)
- **Automatic camera recovery** — reconnects if webcam is unplugged
- **Hand-loss safety** — mouse is released immediately if hand disappears mid-drag
- **Async TTS feedback** — bounded queue, duplicate suppression
- **Professional CustomTkinter dashboard** — mode, gesture, confidence, CPU, RAM, latency

---

## Requirements

| Component | Requirement |
|-----------|------------|
| OS | Windows 10 or Windows 11 (x64) |
| Python | 3.11.x (validated: 3.11.9) |
| Webcam | USB or integrated, 640×480 minimum |
| RAM | ≥ 4 GB recommended |
| GPU | Not required |

---

## Installation (from source)

```bash
# Clone
git clone https://github.com/Sarvagyabirla/SmartGestureOS.git
cd SmartGestureOS

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run
python main.py
```

---

## Usage

Launch the application:

```bash
python main.py
```

The app starts in **GENERAL** mode. Use the **Call Me** gesture (Thumb + Pinky) to cycle through:

```
GENERAL → MEDIA → DRAW → GENERAL
```

Refer to [GESTURES.md](GESTURES.md) for the complete gesture reference.

---

## Gesture Modes

### GENERAL Mode
Full mouse control, OS shortcuts, volume, brightness, and discrete actions.

### MEDIA Mode
Control music playback: Play/Pause, Next Track, Previous Track, Mute.

### DRAW Mode
Draw on a canvas overlay. Undo, redo, color cycle, eraser, save drawing.

> **Note:** Draw mode draws on an in-app canvas overlay displayed in the SmartGestureOS window. It does not draw over arbitrary Windows applications.

---

## Running Tests

```bash
python -m pytest -q tests/
```

All automated tests should pass. Tests use mocks — no physical webcam or mouse required.

---

## Project Structure

```
SmartGestureOS/
├── main.py                    # Entry point, thread orchestrator
├── config.py                  # Settings loader
├── src/
│   ├── camera.py              # Threaded camera capture with reconnect
│   ├── gesture_detector.py    # MediaPipe LIVE_STREAM integration
│   ├── gesture_classifier.py  # Geometric gesture recognition
│   ├── event_engine.py        # Temporal state machine (click/drag/scroll)
│   ├── gesture_mapper.py      # Mode-aware action routing
│   ├── mouse_controller.py    # Cursor movement + EventEngine bridge
│   ├── virtual_mouse.py       # Win32 API mouse input
│   ├── drawing.py             # Canvas with undo/redo/save
│   ├── ui.py                  # CustomTkinter dashboard
│   └── *_controller.py        # Volume, brightness, media, desktop, etc.
├── models/
│   └── hand_landmarker.task   # MediaPipe model (bundled)
├── config/
│   └── defaults.json          # Default settings
├── packaging/
│   └── windows/
│       ├── SmartGesture.spec  # PyInstaller ONEDIR spec
│       └── SmartGestureOS.iss # Inno Setup installer script
├── scripts/
│   └── build_windows.ps1      # Build automation
├── tests/                     # Pytest test suite (mocked)
├── GESTURES.md                # Complete gesture reference
└── requirements.txt
```

---

## Performance

These are **targets**, not guaranteed values. Actual performance depends on hardware.

| Metric | Target |
|--------|--------|
| Processing rate | ~30 fps |
| Inference result age | < 100 ms typical |
| RAM usage | < 500 MB |
| CPU usage | < 2 cores |

---

## Packaging

Build a Windows installer:

```powershell
# Step 1: Build ONEDIR executable
.\scripts\build_windows.ps1

# Step 2: Create installer (requires Inno Setup 6+)
iscc packaging\windows\SmartGestureOS.iss
```

Output: `release\SmartGestureOS-Setup-v1.0.0.exe`

---

## Team

Developed by **Sarvagya Birla**, **Uday Dangi**, and **Shantanu Yadav**

Under the guidance of **Ms. Ankita Dubey**

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| No camera feed | Change `"index": 0` in `config/defaults.json` to `1` or `2` |
| Volume not working | `pycaw` requires Windows with an active audio device |
| Brightness not working | External monitors use DXVA2; laptop panels use `screen-brightness-control` |
| `ModuleNotFoundError` | Ensure `.venv` is activated and `pip install -r requirements.txt` completed |
| Gestures not recognized | Ensure good lighting; keep hand within frame |

---

## License

MIT License — see [LICENSE](LICENSE)
