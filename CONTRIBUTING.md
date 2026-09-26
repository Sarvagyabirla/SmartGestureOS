# Contributing to SmartGestureOS

SmartGestureOS is a Windows gesture control application built with Python,
MediaPipe, and CustomTkinter. Hand inference runs on the device; unresolved
dependency uploader activity is documented in [PRIVACY.md](PRIVACY.md).

## Quick Start

### Prerequisites

- Windows 10 or 11 (64-bit)
- Python 3.11 (exact version; use [pyenv-win](https://github.com/pyenv-win/pyenv-win) or python.org installer)
- A USB or built-in webcam

### Setup

```powershell
# Clone
git clone https://github.com/Sarvagyabirla/SmartGestureOS.git
cd SmartGestureOS

# Create virtual environment
python -m venv .venv
.\.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run the app
python main.py

# Run tests
python -m pytest tests/ -v
```

## Development Workflow

1. **Fork** the repository and **create a branch** from `main`.
   - Feature: `feature/<short-description>`
   - Bug fix: `fix/<issue-number>-short-description`

2. **Write tests first** for any new behaviour or bug fix.
   - All bug fixes must have a regression test that fails before the fix.
   - Minimum test file: `tests/test_<module>.py`.

3. **Run the full test suite** before pushing:
   ```powershell
   python -m pytest tests/ -v
   ```
   All tests must pass. Record the current count and any skips from the run;
   automated results do not establish physical gesture or installer readiness.

4. **Open a Pull Request** against `main`. PR description must include:
   - What the change does
   - Test evidence (paste the last line of pytest output)
   - Any hardware/camera tested on (if a camera-path change)

## Coding Standards

| Standard | Rule |
|----------|------|
| Python version | 3.11 only |
| Timing | Always use `time.perf_counter()`, never `time.time()` for durations |
| File paths | Always use `pathlib.Path`; never string concatenation |
| User-supplied strings used as paths | Always validate with `validate_profile_name()` or `validate_gesture_name()` before use |
| Shell commands | `shell=False` only. No `shell=True`. No user-supplied strings in `Popen` args |
| Mouse safety | Any code path that performs desktop automation **must** call `mouse.release_all()` before terminating or on exception |
| Tests | Use `unittest.mock` / `pytest-mock` — no real camera, no real WinAPI in unit tests |

## Architecture Overview

```
main.py                  # MainApp orchestrator (camera → detector → classifier → mapper)
src/
  camera.py              # OpenCV capture + reconnect
  gesture_detector.py    # Synchronous MediaPipe VIDEO inference on the processing worker
  gesture_classifier.py  # Geometry → gesture name (stateless per-frame; history deque for temporal)
  event_engine.py        # Deterministic mouse state machine (CRITICAL: safety contract)
  gesture_mapper.py      # Action dispatcher + mode management
  virtual_mouse.py       # Windows API wrapper
  mouse_controller.py    # Owns EventEngine; calls release_all on cleanup
  settings_manager.py    # Profile CRUD with name sanitization
  gesture_trainer.py     # Custom gesture training + classification
  drawing.py             # In-memory canvas for DRAW mode
  feedback_controller.py # Async TTS with bounded queue
  version.py             # Single version authority
config/
  defaults.json          # Factory defaults (read-only)
packaging/windows/
  SmartGesture.spec      # PyInstaller spec
  SmartGestureOS.iss     # Inno Setup installer script
  msix/                  # MSIX packaging for Microsoft Store
```

## Safety Contract (Critical)

If you touch **any code** that controls the mouse or keyboard:

> All active desktop automation (left button held, drag in progress) **MUST** be
> released via `mouse.release_all()` before:
> - The app exits
> - An exception propagates out of the processing loop
> - The camera disconnects
> - MediaPipe result TTL expires
> - The mode changes

Violations of this contract are **P0 bugs**.

## Commit Message Format

```
type(scope): Short description (max 72 chars)

Optional body explaining the why, not the what.

Refs: #123
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `build`, `ci`, `chore`

## Reporting Bugs

Open a [GitHub Issue](https://github.com/Sarvagyabirla/SmartGestureOS/issues/new)
with:
- Windows version
- Python version (`python --version`)
- Camera make/model
- Steps to reproduce
- Log output from `%LOCALAPPDATA%\SmartGesture\logs\smart_gesture_os.log`

## Security Issues

**Do not open public issues for security vulnerabilities.** See [SECURITY.md](SECURITY.md).
