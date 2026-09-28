"""
diagnose_ui_freeze — MEASURE, do not guess, where dashboard time is spent.

Answers the Phase-0 audit questions with real numbers on this machine:

  * Tk event-loop delay (how long a no-op ``after(0)`` round trip takes while
    the update loop runs) — this is what the user perceives as "frozen".
  * ``update_dashboard()`` cost (the CTk ``configure()`` storm).
  * ``update_frame()`` cost, split into cvtColor / fromarray / resize /
    ImageTk.PhotoImage.
  * Preview backlog: published vs displayed frames.

Usage:
    .\\.venv\\Scripts\\python.exe scripts\\diagnose_ui_freeze.py --seconds 6
"""

import argparse
import sys
import time
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np
from PIL import Image, ImageTk

FRAME_W, FRAME_H = 1280, 720
SAMPLE = np.zeros((FRAME_H, FRAME_W, 3), dtype=np.uint8)

_PIL = {}


class Stats:
    """Percentile helper - reports p50/p95/max rather than a single mean."""

    def __init__(self):
        self.samples = deque(maxlen=4000)

    def add(self, seconds):
        self.samples.append(seconds * 1000.0)

    def report(self, label, indent="  "):
        if not self.samples:
            print(f"{indent}{label:<26} (no samples)")
            return
        ordered = sorted(self.samples)
        p50 = ordered[len(ordered) // 2]
        p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
        print(f"{indent}{label:<24} n={len(ordered):<5} "
              f"p50={p50:7.2f}  p95={p95:7.2f}  max={ordered[-1]:7.2f}  (ms)")


def _timed(ui, frame, frame_stats):
    """Break one dashboard frame into its measurable stages."""
    t0 = time.perf_counter()
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    t1 = time.perf_counter()
    image = Image.fromarray(rgb)
    t2 = time.perf_counter()
    image = image.resize((ui.frame_width, ui.frame_height))
    t3 = time.perf_counter()
    photo = ImageTk.PhotoImage(image=image)
    t4 = time.perf_counter()
    ui.video_label.configure(image=photo)
    t5 = time.perf_counter()
    frame_stats.add(t5 - t0)
    for key, value in (("fromarray", t2 - t1), ("resize", t3 - t2),
                       ("ImageTk.PhotoImage", t4 - t3),
                       ("label.configure", t5 - t4)):
        _PIL.setdefault(key, deque(maxlen=4000)).append(value * 1000.0)
    return photo


def measure_phase(ui, seconds, hidden, label):
    """Drive the real UI at the real 15 ms tick cadence main.py uses."""
    loop_delay, dashboard, frame_total = Stats(), Stats(), Stats()
    published = displayed = 0
    backlog = deque(maxlen=1)

    if hidden:
        ui.set_dashboard_visible(False)
    else:
        ui.set_dashboard_visible(True)
    ui.update_idletasks()

    frame = SAMPLE.copy()
    deadline = time.perf_counter() + seconds
    next_tick = time.perf_counter()
    while time.perf_counter() < deadline:
        next_tick += 0.015
        spin = time.perf_counter()
        published += 1
        backlog.clear()
        backlog.append(time.perf_counter())

        t0 = time.perf_counter()
        try:
            if backlog:
                displayed += 1
            if not hidden:
                frame_total.add(t0 - spin)
                t0 = time.perf_counter()
                ui.update_frame(frame)
                frame_total.add(time.perf_counter() - t0)
                t0 = time.perf_counter()
            ui.update_dashboard("GENERAL", "Pointing", "Pointing", 87,
                                "Executed: screenshot", 29, 21.5, 412.0,
                                True, False, 41, True)
            ui.update_performance(29.8, 27.1, 12.4)
        except Exception as exc:
            print("  UI error:", exc)
        dashboard.add(time.perf_counter() - t0)

        marker = []
        ui.after(0, lambda: marker.append(time.perf_counter()))
        waited = time.perf_counter()
        while not marker and time.perf_counter() - waited < 0.5:
            ui.update()
        if marker:
            loop_delay.add(marker[0] - spin)

        sleep_for = next_tick - time.perf_counter()
        if sleep_for > 0:
            time.sleep(sleep_for)
        else:
            next_tick = time.perf_counter()

    print(f"\n=== {label} (dashboard {'HIDDEN' if hidden else 'VISIBLE'}) ===")
    print(f"  published={published}  displayed={displayed}")
    loop_delay.report("Tk event-loop delay")
    dashboard.report("update_dashboard")
    frame_total.report("update_frame (total)")
    for key in ("fromarray", "resize", "ImageTk.PhotoImage", "label.configure"):
        bucket = _PIL.get(key)
        if bucket:
            ordered = sorted(bucket)
            print(f"    {key:<22} p50={ordered[len(ordered)//2]:6.2f}  "
                  f"p95={ordered[int(len(ordered)*0.95)]:6.2f}  (ms)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=6.0)
    args = parser.parse_args()

    from src.ui import SmartGestureApp

    ui = SmartGestureApp(set_automation_callback=lambda enabled: None)
    ui.geometry("1100x700")
    ui.update_idletasks()
    ui.update_idletasks()
    print(f"video_label geometry: {ui.video_label.winfo_width()}x"
          f"{ui.video_label.winfo_height()}")
    ui.frame_width, ui.frame_height = 750, 500
    try:
        measure_phase(ui, args.seconds, hidden=False, label="VISIBLE DASHBOARD")
        _PIL.clear()
        measure_phase(ui, args.seconds, hidden=True, label="BACKGROUND MODE")
    finally:
        try:
            ui.destroy()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


    def __init__(self):
        self.samples = deque(maxlen=4000)

    def add(self, seconds):
        self.samples.append(seconds * 1000.0)

    def report(self, label, indent="  "):
        if not self.samples:
            print(f"{indent}{label:<26} (no samples)")
            return
        ordered = sorted(self.samples)
        p50 = ordered[len(ordered) // 2]
        p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
        print(f"{indent}{label:<24} n={len(ordered):<5} "
              f"p50={p50:7.2f}  p95={p95:7.2f}  max={ordered[-1]:7.2f}  (ms)")
