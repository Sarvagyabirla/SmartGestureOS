# SmartGestureOS

**Real-Time Hand Gesture Control System for Desktop Automation**

Computer Vision Based Touchless Human-Computer Interaction

[![Python](https://img.shields.io/badge/Python-3.11.x-blue)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-blue)](https://microsoft.com/windows)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

> **What is SmartGestureOS?**  
> SmartGestureOS is a Windows desktop utility that translates webcam hand gestures into desktop actions. It runs on top of Windows and adds touchless interaction alongside your mouse and keyboard. It is not a new operating system or a certified accessibility/medical solution.

The project explores whether a normal webcam can provide reliable, real-time
desktop control without specialized hardware. It combines computer vision,
geometric recognition, temporal input handling and Windows automation for a
B.Tech CSE (AI & ML) project, due 30 September 2026.

The [product specification](docs/PRODUCT_SPECIFICATION.md) is authoritative.
See the [subsystem audit and exact ten-step plan](docs/SPECIFICATION_AUDIT.md)
and [current implementation evidence](docs/PRODUCT_EXECUTION_2026-09-27.md).

---

## Features

**Release status (27 September 2026):** source and distribution validation is
in progress. Physical mouse/mode acceptance and clean-machine acceptance are pending;
see [release readiness](RELEASE_READINESS.md). The
[privacy policy](PRIVACY.md) explains MediaPipe's published metrics disclosure,
the observed native uploader activity, and the limits of local validation.

- **Three control modes** — GENERAL (mouse + OS), MEDIA, and DRAW
- **Real-time hand tracking** via MediaPipe Hand Landmarker (21 3D landmarks)
- **Animated RGB hand highlight** so a detected hand is easy to see in the camera view
- **14 built-in static gestures** — Pointing, Pinch, Victory, Rock On, Open Palm, Closed Fist, Thumb Up/Down, Two Fingers, Three Fingers, Four Fingers, Middle Finger, Call Me, and Crossed Fingers. Pinch hold/double-click are temporal actions.
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
| Python | Only for source development: 3.11.x (validated: 3.11.9). Packaged users do not need it. |
| Webcam | USB or integrated; 640×480 or higher recommended |
| RAM | ≥ 4 GB recommended |
| GPU | Not required |

---

## Installation (from source)

```bash
# Clone
git clone https://github.com/Sarvagyabirla/SmartGestureOS.git
cd SmartGestureOS

# Create virtual environment
py -3.11 -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run
python main.py
```

For installed users, the intended path is the product website → GitHub Release
→ `SmartGestureOS-Setup-v0.9.0.exe` → Start Menu. A public validated release is
not available yet; do not treat source archives as Windows installers.

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

Start with one clearly lit hand about 30–50 cm from the camera. Point to move
the cursor and briefly pinch thumb/index to click. Hold Pinch to drag; release
to drop. **Ctrl+Alt+G** and the fixed Pause/Resume button use the same automation
state. After resuming, remove your hand briefly to satisfy neutral re-arm.
Settings, Coach and Trainer pause automation while you configure or practice.
Camera selection is in Settings and applies after saving and restarting.

To inspect tracking without activating desktop actions, run
`python main.py --start-paused`.

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

## Architecture and Project Structure

```mermaid
flowchart LR
    Webcam --> Camera[Latest camera frame]
    Camera --> Detector[MediaPipe VIDEO: 21 landmarks]
    Detector --> Classifier[Raw and stable gesture]
    Classifier --> Mapper[GENERAL / MEDIA / DRAW]
    Mapper --> Events[Temporal event engine]
    Events --> Controllers[Windows controllers]
    Controllers --> Windows
    Camera --> UI[Dashboard and visual feedback]
    Detector --> UI
    Classifier --> UI
    Mapper --> UI
```

Camera capture and inference run on workers; Tk presentation stays on its UI
thread. Frames are processed locally in memory. The preview shows measured
camera/detector rates, inference latency and input age separately. Missing audio,
unsupported brightness or an absent target application should produce a local
error without crashing tracking.

```text
SmartGestureOS/
├── main.py                    # Entry point, thread orchestrator
├── config.py                  # Settings loader
├── src/
│   ├── camera.py              # Threaded camera capture with reconnect
│   ├── gesture_detector.py    # Synchronous MediaPipe VIDEO inference
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

# Step 2: Create installer (requires Inno Setup 6+ and ISCC.exe on PATH)
.\scripts\build_installer.ps1
```

Output: `dist\release\SmartGestureOS-Setup-v0.9.0.exe`

The ONEDIR executable supports `--self-check` for native model inference and
`--ui-self-check` for real dashboard/preview/auxiliary-window initialization.
Neither probe opens a webcam or proves gesture accuracy. The installer helper
also writes `SHA256SUMS.txt`. Build helpers accept `-PythonExe` for an explicit
Python 3.11 interpreter, and the installer accepts `-IsccPath`.

To build MSIX, first create the ONEDIR build, then supply exact Partner Center
identity values in the single `packaging/windows/msix/AppxManifest.xml`. Real
PNG assets are included in its `Assets` folder. Run `scripts/build_msix.ps1`;
it validates inputs and writes to `dist/release`. Microsoft Store status is
**NOT STARTED** until a valid identity/package and account submission exist.

---

## Team

Developed by **Sarvagya Birla**, **Uday Dangi**, and **Shantanu Yadav**

Under the guidance of **Ms. Ankita Dubey**

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| No camera feed | Close other camera apps; check Windows permission; select camera 0, 1 or 2 in Settings, save and restart |
| Volume not working | `pycaw` requires Windows with an active audio device |
| Brightness not working | External monitors use DXVA2; laptop panels use `screen-brightness-control` |
| `ModuleNotFoundError` | Ensure `.venv` is activated and `pip install -r requirements.txt` completed |
| Gestures not recognized | Ensure good lighting; keep hand within frame |

---

## License

MIT License — see [LICENSE](LICENSE)
