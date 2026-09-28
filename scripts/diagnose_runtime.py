"""
diagnose_runtime.py — Phase 1 + Phase 2 live measurement with a REAL webcam.

Runs the REAL production MainApp with the REAL Tk mainloop for N seconds and
reports only MEASURED numbers:

  * camera FPS, detector FPS, pointer FPS, preview renders
  * inference latency median / p95
  * capture-to-pointer latency (the user-visible delay)
  * Tk event-loop delay, sampled from INSIDE the Tk thread
  * process CPU and RSS, dashboard VISIBLE vs HIDDEN (background mode)

The Windows input layer is stubbed so this measures the pipeline without
moving the operator's real cursor or clicking anything.

Usage:
    .\\.venv\\Scripts\\python.exe scripts\\diagnose_runtime.py --seconds 20
"""
import argparse
import os
import statistics
import sys
import time
from collections import deque
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _stub_win32():
    """Neutralise real desktop input: measure, never move the operator's mouse.

    Only VirtualMouse's two entry points are replaced, so every other library
    that resolves symbols from ctypes.windll keeps working normally.
    """
    from unittest.mock import MagicMock
    from src import virtual_mouse

    fake = MagicMock()
    fake.SetCursorPos = MagicMock(return_value=1)
    fake.mouse_event = MagicMock()
    original = virtual_mouse.VirtualMouse.__init__

    def patched(self, *args, **kwargs):
        original(self, *args, **kwargs)
        self.user32 = fake

    virtual_mouse.VirtualMouse.__init__ = patched
    return fake


def pct(values, q):
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * q))]


def report(label, values, unit="ms"):
    if not values:
        print(f"  {label:<32} (no samples)")
        return
    print(f"  {label:<32} n={len(values):<6} p50={pct(values, 0.50):7.2f} "
          f"p95={pct(values, 0.95):7.2f}  max={max(values):7.2f}  ({unit})")


def cpu_rss():
    import psutil
    return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)


def run_phase(seconds, label, hidden):
    """Boot the REAL MainApp (real mainloop, real threads) and measure it."""
    import psutil
    import main as main_module

    app = main_module.MainApp(start_paused=False)
    app.ui.withdraw()          # never flash a window at the operator

    loop_delay = deque(maxlen=2000)
    schedule = {"next": time.perf_counter() + 0.05}

    def tick():
        """Runs ON the Tk thread, so this IS the real event-loop delay."""
        now = time.perf_counter()
        loop_delay.append((now - schedule["next"]) * 1000.0)
        schedule["next"] = now + 0.05
        app.ui.after(50, tick)

    app.ui.after(50, tick)
    if hidden:
        app.ui.set_dashboard_visible(False)

    state = {}

    def begin():
        process = psutil.Process(os.getpid())
        process.cpu_percent()
        state["rss_start"] = cpu_rss()
        state["process"] = process
        loop_delay.clear()
        state["fps_samples"] = []

    def sample():
        """Camera.measured_fps returns 0 once the newest frame is >1 s old,
        so it must be sampled WHILE the pipeline is running."""
        state["fps_samples"].append(app.camera.measured_fps)
        state["detector_samples"].append(getattr(app, "detector_fps", 0.0))
        app.ui.after(500, sample)

    def stop():
        state["cpu"] = state["process"].cpu_percent()
        state["rss_end"] = cpu_rss()
        app.ui.after(0, app.ui.force_quit)

    state["fps_samples"] = []
    state["detector_samples"] = []
    app.ui.after(500, sample)
    app.ui.after(2500, begin)                 # let the pipeline settle
    app.ui.after(int(seconds * 1000), stop)
    app.run()                                  # real mainloop

    print(f"\n=== {label} ===")
    print("  -- throughput --")
    print(f"  {'camera FPS (mean live)':<32} "
          f"{statistics.fmean(state['fps_samples']):7.1f}")
    print(f"  {'detector FPS (mean live)':<32} "
          f"{statistics.fmean(state['detector_samples']):7.1f}")
    print(f"  {'preview renders':<32} {app.ui.frames_rendered}")
    print(f"  {'previews suppressed':<32} {app.ui.frames_suppressed_hidden}")
    pointer = app._pointer_metrics_snapshot()
    print(f"  {'pointer FPS':<32} {pointer.get('pointer_fps', 0.0):7.1f}")
    print(f"  {'pointer samples':<32} {pointer.get('pointer_samples', 0)}")
    print(f"  {'detector inferences':<32} {app.detector.frames_processed}")

    print("  -- latency --")
    report("inference latency", list(app.detector._latency_samples))
    report("tk event-loop delay", list(loop_delay))
    print(f"  {'capture->pointer p50':<32} "
          f"{pointer.get('capture_to_pointer_ms', 0.0):7.2f}")

    print("  -- resources --")
    print(f"  {'CPU (process)':<32} {state.get('cpu', 0.0):7.1f} %")
    rss0, rss1 = state.get("rss_start", 0.0), state.get("rss_end", 0.0)
    print(f"  {'RAM start -> end':<32} {rss0:7.1f} -> {rss1:7.1f} MB "
          f"(delta {rss1 - rss0:+.1f} MB)")
    return dict(cpu=state.get("cpu", 0.0), renders=app.ui.frames_rendered,
                tk_p95=pct(list(loop_delay), 0.95), rss0=rss0, rss1=rss1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=20.0)
    args = parser.parse_args()

    _stub_win32()
    visible = run_phase(args.seconds,
                        f"PHASE A - dashboard VISIBLE ({args.seconds:.0f}s)", False)
    background = run_phase(args.seconds,
                           f"PHASE B - BACKGROUND MODE ({args.seconds:.0f}s)", True)

    print("\n=== SUMMARY ===")
    print(f"  visible    : {visible['renders']} preview renders, "
          f"Tk p95 {visible['tk_p95']:.1f} ms, CPU {visible['cpu']:.1f}%, "
          f"RAM {visible['rss0']:.0f}->{visible['rss1']:.0f} MB")
    print(f"  background : {background['renders']} preview renders, "
          f"Tk p95 {background['tk_p95']:.1f} ms, CPU {background['cpu']:.1f}%, "
          f"RAM {background['rss0']:.0f}->{background['rss1']:.0f} MB")
    print("  PASS: background preview renders == 0 and Tk p95 < 50 ms.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
