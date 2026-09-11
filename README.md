# Smart Gesture Operating System

A next-generation gesture-based operating system controller that allows you to control Windows entirely with your hands, using your webcam. No mouse, no keyboard—just natural hand movements.

## Project Overview

Smart Gesture OS harnesses the power of OpenCV and Google's MediaPipe Hand Landmarker to track 21 3D hand joints in real-time. It translates these landmarks into complex gestures (e.g., Pinch, Victory, Fist, Open Palm, Crossed Fingers) and maps them dynamically to system actions such as mouse movement, clicks, scrolling, media control, drawing on the screen, and managing windows.

### Recent Major Updates (V2 Architecture)
- **True Async ML Processing**: The application now utilizes MediaPipe's `LIVE_STREAM` API. The camera and drawing UI run completely unblocked at 60 FPS, while heavy ML inference is intelligently throttled to 30 FPS in a background thread.
- **Ultra-Low Latency (<20ms)**: By decoupling the rendering loop from the ML inference loop, input latency has been drastically reduced.
- **Buttery Smooth Cursor**: Integrated `OneEuroFilter` acting as a temporal interpolator between ML frames, completely eliminating cursor jitter and shaking.
- **High-Performance Drawing Engine**: Rebuilt the drawing mode to use high-frequency line interpolation at 60 FPS, eliminating jagged strokes and heavy CPU Bezier curve bottlenecks.
- **Optimized Resource Usage**: CPU utilization dropped to ~130% (approx 1 core) and RAM usage stabilized at <400 MB.
- **Enhanced Dashboard**: Real-time monitoring of FPS, Confidence, CPU, RAM, Camera State, Automation State, Voice Feedback, and Gesture History.

### Stability & Reliability
This version of SmartGestureOS has been rigorously stabilized for live demonstration purposes. The codebase features robust error handling, automated camera recovery, asynchronous TTS feedback, and strict gesture validation tests. 

## Running Tests
To verify system stability, a pytest suite is included. Run the tests via:
```bash
python -m pytest -q tests/
```
All tests should pass indicating proper geometric calculations and setting constraints.

## Requirements

* Python 3.8+
* A working webcam
* Windows OS (Required for pycaw, comtypes, screen-brightness-control, and keyboard hooks)

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/SmartGestureOS.git
   cd SmartGestureOS
   ```

2. **Create a virtual environment (Recommended):**
   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Project Structure

```text
SmartGestureOS/
├── src/
│   ├── camera.py              # Multithreaded 60 FPS camera capture
│   ├── gesture_detector.py    # MediaPipe LIVE_STREAM async integration
│   ├── gesture_classifier.py  # 3D vector math for robust gesture recognition
│   ├── gesture_mapper.py      # Logic connecting gestures to actions
│   ├── ui.py                  # CustomTkinter responsive dashboard
│   ├── drawing.py             # Canvas, strokes, undo/redo, eraser
│   ├── utils.py               # Math and OneEuroFilter utilities
│   └── *_controller.py        # System specific action controllers (mouse, media, etc.)
├── models/
│   └── hand_landmarker.task   # MediaPipe ML model
├── tests/                     # Pytest suite
├── main.py                    # Application entry point & thread orchestrator
├── config.py                  # Settings loader
├── GESTURES.md                # Strict 1-to-1 Gesture to Action mapping documentation
├── profiles/                  # Configuration profiles (default.json)
└── requirements.txt           # Python dependencies
```

## Features

- **General Mode:** Full mouse control (pointer, click, drag, scroll), volume/brightness adjustments, and OS shortcuts (calculator, VS Code, Task View).
- **Media Mode:** Control music playback (Play/Pause, Next Track, Prev Track, Mute).
- **Drawing Mode:** Draw anywhere on the screen! Includes stroke smoothing, color cycling, eraser, undo, redo, and screenshot saving.
- **Robust Classification:** Utilizes temporal smoothing and 3D vector checks so gestures are recognized accurately even if your hand is rotated.
- **Dynamic Continuous Controls:** Two-finger vertical scrolling and Middle-finger vertical brightness adjustments.

## Usage

Start the system by running:
```bash
python main.py
```
The OS starts in **GENERAL** mode by default.

### Gesture Mapping
Please refer to the [GESTURES.md](GESTURES.md) file for the complete, strict 1-to-1 gesture mapping table, including the new **Crossed Fingers** (Lock PC) and **Middle Finger** (Brightness) gestures, as well as support for **Custom Gestures**.

## Troubleshooting

- **No Camera Feed:** Ensure your camera is not being used by another application. Try changing `"index": 0` in `profiles/default.json` to `1` or `2`.
- **UI Lag / Low FPS:** Ensure you have adequate lighting. MediaPipe performs best with clear visibility of your hand.
- **Volume Control Not Working:** `pycaw` requires Windows. Make sure your default audio device is active.
- **"ModuleNotFoundError":** Ensure you've activated your virtual environment and installed all packages from `requirements.txt`.

## Performance Specifications

- **Target FPS:** 60 FPS UI / 30 FPS Inference
- **Target CPU:** < 30% System Usage (or ~130% process utilization across multi-cores)
- **Target RAM:** < 400 MB

## Contributing

Contributions are welcome! Please open an issue or submit a pull request. Make sure to run `pytest tests/` before submitting code to ensure no regressions.

