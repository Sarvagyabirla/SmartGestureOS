"""Measure live runtime performance metrics without webcam frame persistence.

Measures:
  - camera_fps
  - detector_fps
  - pointer_fps
  - preview_fps
  - inference_median_ms
  - inference_p95_ms
  - capture_to_pointer_median_ms
  - capture_to_pointer_p95_ms
  - tk_loop_p95_ms
  - CPU average / peak
  - RAM start / end
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import statistics
import sys
import time
from collections import deque
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _stub_win32():
    """Stub virtual mouse input so the operator's real desktop cursor is untouched."""
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


def get_process_rss():
    import psutil
    return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)


def measure_runtime(seconds: float = 10.0, output_path: Path = None, mock: bool = False):
    if mock:
        # Fast mock path for automated testing
        result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_s": seconds,
            "camera_fps": 30.0,
            "detector_fps": 27.5,
            "pointer_fps": 26.8,
            "preview_fps": 24.0,
            "inference_median_ms": 14.2,
            "inference_p95_ms": 18.5,
            "capture_to_pointer_median_ms": 32.0,
            "capture_to_pointer_p95_ms": 48.0,
            "tk_loop_p95_ms": 6.4,
            "cpu_average": 15.2,
            "cpu_peak": 24.5,
            "ram_start_mb": 140.0,
            "ram_end_mb": 155.0,
        }
        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
        return result

    _stub_win32()
    import psutil
    import main as main_module

    app = main_module.MainApp(start_paused=False)
    app.ui.withdraw()  # Hidden for non-invasive profiling

    loop_delays = deque(maxlen=2000)
    schedule = {"next": time.perf_counter() + 0.05}

    def tick():
        now = time.perf_counter()
        loop_delays.append((now - schedule["next"]) * 1000.0)
        schedule["next"] = now + 0.05
        if app.ui.winfo_exists():
            app.ui.after(50, tick)

    app.ui.after(50, tick)

    cpu_samples = []
    fps_samples = []
    detector_samples = []
    process = psutil.Process(os.getpid())
    process.cpu_percent()
    ram_start = get_process_rss()

    def sample_metrics():
        if getattr(app, "camera", None):
            fps_samples.append(float(getattr(app.camera, "measured_fps", 0.0)))
        detector_samples.append(float(getattr(app, "detector_fps", 0.0)))
        cpu_samples.append(process.cpu_percent())
        if app.ui.winfo_exists():
            app.ui.after(250, sample_metrics)

    def stop():
        app.ui.after(0, app.ui.force_quit)

    app.ui.after(500, sample_metrics)
    app.ui.after(int(seconds * 1000), stop)
    app.run()

    ram_end = get_process_rss()

    inf_samples = list(getattr(app.detector, "_latency_samples", []))
    inf_median = pct(inf_samples, 0.50) if inf_samples else None
    inf_p95 = pct(inf_samples, 0.95) if inf_samples else None

    pointer = app._pointer_metrics_snapshot() if hasattr(app, "_pointer_metrics_snapshot") else {}
    c2p_raw = pointer.get("capture_to_pointer_ms")
    c2p_p95_raw = pointer.get("capture_to_pointer_p95_ms")
    has_pointer_events = pointer.get("pointer_samples", 0) > 0 and c2p_raw is not None

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "duration_s": seconds,
        "camera_fps": round(statistics.fmean(fps_samples) if fps_samples else 0.0, 1),
        "detector_fps": round(statistics.fmean(detector_samples) if detector_samples else 0.0, 1),
        "pointer_fps": round(float(pointer.get("pointer_fps", 0.0)), 1),
        "preview_fps": round(float(app.ui.frames_rendered / seconds if seconds > 0 else 0.0), 1),
        "inference_median_ms": round(inf_median, 1) if inf_median is not None else None,
        "inference_p95_ms": round(inf_p95, 1) if inf_p95 is not None else None,
        "capture_to_pointer_median_ms": round(c2p_raw, 1) if has_pointer_events else None,
        "capture_to_pointer_p95_ms": round(c2p_p95_raw, 1) if has_pointer_events and c2p_p95_raw is not None else None,
        "tk_loop_p95_ms": round(pct(list(loop_delays), 0.95), 1),
        "cpu_average": round(statistics.fmean(cpu_samples) if cpu_samples else 0.0, 1),
        "cpu_peak": round(max(cpu_samples) if cpu_samples else 0.0, 1),
        "ram_start_mb": round(ram_start, 1),
        "ram_end_mb": round(ram_end, 1),
    }

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)

    return result


def main():
    parser = argparse.ArgumentParser(description="Measure runtime performance metrics.")
    parser.add_argument("--seconds", type=float, default=10.0, help="Measurement duration in seconds")
    parser.add_argument("--output", "-o", type=Path, default=REPO_ROOT / "logs" / "runtime-performance.json",
                        help="Output JSON path")
    parser.add_argument("--mock", action="store_true", help="Run with mock data for rapid self-testing")
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    res = measure_runtime(seconds=args.seconds, output_path=args.output, mock=args.mock)

    print("\n" + "=" * 50)
    print("SMARTGESTUREOS RUNTIME PERFORMANCE SUMMARY")
    print("=" * 50)
    for k, v in res.items():
        if k != "timestamp":
            print(f"  {k:30}: {v}")
    print("=" * 50)
    print(f"Report saved to: {args.output}")


if __name__ == "__main__":
    main()
