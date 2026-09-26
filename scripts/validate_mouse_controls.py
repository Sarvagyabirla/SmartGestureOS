"""Opt-in Windows hand-to-mouse check; importing this module starts nothing."""

import argparse
from collections import Counter, deque
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time


REPO_ROOT = Path(__file__).resolve().parent.parent
STEPS = (
    ("cursor", "Point with one finger and move the cursor across the target."),
    ("single_click", "Briefly pinch, then release. Expect one click after the short wait."),
    ("double_click", "Briefly pinch twice in quick succession. Expect one double click."),
    ("drag_release", "Hold a pinch, move at least 25 pixels, then release. The square must stop following."),
    ("scroll", "Show Two Fingers together and move vertically. Check both wheel directions."),
    ("right_click", "Show Three Fingers. Expect one right click; keep holding to check it does not repeat."),
)


def clamp_point(x, y, rectangle):
    """Clamp into a Windows client rectangle with exclusive right/bottom edges."""
    left, top, right, bottom = rectangle
    if right <= left or bottom <= top:
        raise ValueError("Target rectangle must have positive dimensions")
    return max(left, min(int(x), right - 1)), max(top, min(int(y), bottom - 1))


class TargetMouseAPI:
    """Per-instance Win32 boundary: reject new input outside the focused target.

    Button releases always pass through so focus loss cannot strand a drag.
    This does not clip or capture the user's physical mouse.
    """

    def __init__(self, backend, active_rectangle, owns_point):
        self.backend = backend
        self.active_rectangle = active_rectangle
        self.owns_point = owns_point
        self.blocked = 0

    def SetCursorPos(self, x, y):
        rectangle = self.active_rectangle()
        if rectangle is None:
            self.blocked += 1
            return 0
        return self.backend.SetCursorPos(*clamp_point(x, y, rectangle))

    def mouse_event(self, flags, dx, dy, data, extra):
        if flags not in (0x0004, 0x0010):  # LEFTUP / RIGHTUP are always safe to release.
            rectangle = self.active_rectangle()
            point = wintypes.POINT()
            inside = (rectangle is not None and self.backend.GetCursorPos(ctypes.byref(point))
                      and clamp_point(point.x, point.y, rectangle) == (point.x, point.y)
                      and self.owns_point(point))
            if not inside:
                self.blocked += 1
                return
        return self.backend.mouse_event(flags, dx, dy, data, extra)


class MouseTarget:
    def __init__(self, app, report_path):
        import tkinter as tk

        self.app = app
        self.report_path = report_path
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.counts = Counter()
        self.events = deque(maxlen=300)
        self.results = {}
        self.step = 0
        self.press_origin = None
        self.right_pressed = False
        self.dragged = False
        self.closed = False
        self._shown = False
        self.window = tk.Toplevel(app.ui)
        self.window.title("SmartGestureOS - physical mouse check")
        self.window.geometry("820x640")
        self.window.minsize(680, 580)
        self.window.protocol("WM_DELETE_WINDOW", app.ui.on_closing)
        self.window.bind("<Escape>", lambda _event: self.pause())

        tk.Label(self.window, text="Physical mouse check - GENERAL mode only",
                 font=("Segoe UI", 16, "bold")).pack(pady=(10, 3))
        tk.Label(self.window, text="Start each check, remove your hand briefly to re-arm, then use hand gestures.\n"
                 "Keep this window in front. Press Esc before using controls. Closing either window exits.",
                 font=("Segoe UI", 10)).pack()
        self.instruction = tk.Label(self.window, wraplength=760, font=("Segoe UI", 12, "bold"))
        self.instruction.pack(pady=8)
        row = tk.Frame(self.window)
        row.pack()
        tk.Button(row, text="Start / retry this check", command=self.start).pack(side="left", padx=4)
        tk.Button(row, text="Pause", command=self.pause).pack(side="left", padx=4)
        tk.Button(row, text="I observed it using my hand", command=lambda: self.finish_step(True)).pack(side="left", padx=4)
        tk.Button(row, text="Unclear / skip", command=lambda: self.finish_step(False)).pack(side="left", padx=4)
        self.status = tk.Label(self.window, text="PAUSED - press Start when ready", fg="#b33030")
        self.status.pack(pady=6)
        self.canvas = tk.Canvas(self.window, background="#182636", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=16, pady=4)
        self.canvas.create_text(20, 20, anchor="nw", fill="white", font=("Segoe UI", 11),
                                text="Move, click, drag and scroll anywhere inside this area.")
        self.square = self.canvas.create_rectangle(100, 100, 155, 155, fill="#44bd91", outline="white")
        self.receipts = tk.Label(self.window, text="Windows events: none received yet", wraplength=780)
        self.receipts.pack(pady=6)
        self.wheel_indicator = tk.Label(self.window, text="Wheel: waiting for scroll", font=("Segoe UI", 11, "bold"))
        self.wheel_indicator.pack()
        tk.Label(self.window, text="Use the physical mouse only for these controls. Event counts alone do not prove a hand test passed.",
                 wraplength=780).pack()
        tk.Button(self.window, text="Save report and close", command=app.ui.on_closing).pack(pady=8)

        self.canvas.bind("<Motion>", self.motion)
        self.canvas.bind("<ButtonPress-1>", self.down)
        self.canvas.bind("<Double-Button-1>", self.double)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", self.up)
        self.canvas.bind("<ButtonPress-3>", self.right_down)
        self.canvas.bind("<ButtonRelease-3>", self.right_up)
        self.canvas.bind("<MouseWheel>", self.wheel)
        self.window.update_idletasks()

        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32.GetForegroundWindow.restype = wintypes.HWND
        self.user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
        self.user32.GetAncestor.restype = wintypes.HWND
        self.user32.GetClientRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
        self.user32.ClientToScreen.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.POINT))
        self.user32.GetCursorPos.argtypes = (ctypes.POINTER(wintypes.POINT),)
        self.user32.WindowFromPoint.argtypes = (wintypes.POINT,)
        self.user32.WindowFromPoint.restype = wintypes.HWND
        self.canvas_hwnd = self.canvas.winfo_id()
        self.target_hwnd = self.user32.GetAncestor(self.canvas_hwnd, 2)  # GA_ROOT
        self.input_guard = TargetMouseAPI(self.user32, self.active_rectangle,
                                         lambda point: self.user32.WindowFromPoint(point) == self.canvas_hwnd)
        app.mapper.mouse.mouse.user32 = self.input_guard
        self.show_step()

    def rectangle(self):
        rectangle, origin = wintypes.RECT(), wintypes.POINT()
        if not self.user32.GetClientRect(self.canvas_hwnd, ctypes.byref(rectangle)):
            return None
        if not self.user32.ClientToScreen(self.canvas_hwnd, ctypes.byref(origin)):
            return None
        if rectangle.right <= 0 or rectangle.bottom <= 0:
            return None
        return origin.x, origin.y, origin.x + rectangle.right, origin.y + rectangle.bottom

    def focused(self):
        return not self.closed and self.user32.GetForegroundWindow() == self.target_hwnd

    def active_rectangle(self):
        # Called on the processing/hotkey threads: use Win32, never Tk here.
        return self.rectangle() if self.focused() and self.app.automation_enabled else None

    def show_step(self):
        if self.step < len(STEPS):
            self.instruction.config(text=f"{self.step + 1}/{len(STEPS)}: {STEPS[self.step][1]}")
        else:
            self.instruction.config(text="Checks recorded. Save the report and close; review any unclear results.")

    def show_once(self):
        # CTk deiconifies its root on first mainloop entry, after this target
        # was constructed. Reveal the target once after that startup work.
        if self.closed or not self.app.running or self._shown:
            return
        self._shown = True
        self.window.lift()
        self.window.focus_set()

    def start(self):
        if self.step >= len(STEPS):
            return
        self.pause()
        self.press_origin = None
        self.dragged = False
        self.counts.clear()
        self.wheel_indicator.config(text="Wheel: waiting for scroll")
        self.app.set_automation_enabled(True)

    def pause(self):
        self.app.set_automation_enabled(False)
        self.press_origin = None
        self.right_pressed = False
        self.dragged = False

    def finish_step(self, observed):
        self.pause()
        if self.step >= len(STEPS):
            return
        self.results[STEPS[self.step][0]] = {
            "human_observation": "observed_using_hand" if observed else "unclear_or_skipped",
            "windows_event_counts": dict(self.counts),
        }
        self.step += 1
        self.show_step()

    def record(self, kind, event=None):
        # Receipts include physical mouse input too; never infer a pass from them.
        if not self.app.automation_enabled or not self.focused():
            return
        self.counts[kind] += 1
        self.events.append({"time": round(time.monotonic(), 3), "step": self.step + 1,
                            "event": kind, "raw": self.app.ui.raw_gesture_label.cget("text"),
                            "stable": self.app.ui.gesture_label.cget("text")})

    def motion(self, event):
        self.record("motion", event)

    def down(self, event):
        self.press_origin = (event.x, event.y)
        self.dragged = False
        self.record("left_down", event)

    def double(self, event):
        self.down(event)
        self.record("double_click", event)

    def drag(self, event):
        if self.press_origin is None:
            return
        self.dragged |= ((event.x - self.press_origin[0]) ** 2
                         + (event.y - self.press_origin[1]) ** 2) >= 25 ** 2
        self.canvas.coords(self.square, event.x - 27, event.y - 27, event.x + 27, event.y + 27)
        self.record("drag_motion", event)

    def up(self, event):
        self.record("left_up", event)
        if self.press_origin is not None:
            self.record("drag_release" if self.dragged else "click_release", event)
        self.press_origin = None
        self.dragged = False

    def wheel(self, event):
        self.record("wheel_up" if event.delta > 0 else "wheel_down", event)
        self.wheel_indicator.config(text="Wheel: UP" if event.delta > 0 else "Wheel: DOWN")
        self.canvas.itemconfigure(self.square, fill="#f5b041" if event.delta > 0 else "#44bd91")

    def right_down(self, event):
        self.right_pressed = True
        self.record("right_down", event)

    def right_up(self, event):
        if self.right_pressed:
            self.record("right_click", event)
        self.right_pressed = False

    def poll(self):
        if self.closed or not self.app.running:
            return
        if self.app.automation_enabled and not self.focused():
            self.pause()
        with self.app._automation_lock:
            rectangle = self.rectangle()
            if rectangle is None:
                self.pause()
            else:
                mouse = self.app.mapper.mouse.mouse
                mouse.screen_x, mouse.screen_y = rectangle[:2]
                mouse.screen_w = rectangle[2] - rectangle[0]
                mouse.screen_h = rectangle[3] - rectangle[1]
        state = self.app._rearm_state.upper() if self.app.automation_enabled else "PAUSED"
        self.status.config(text=f"{state} - target must stay in front; Start to resume after focus loss")
        self.receipts.config(text="Windows events: " + (", ".join(f"{key}: {value}" for key, value in self.counts.items()) or "none received"))
        self.window.after(50, self.poll)

    def save(self):
        if self.closed:
            return
        self.closed = True
        report = {
            "started_utc": self.started_at,
            "ended_utc": datetime.now(timezone.utc).isoformat(),
            "automated_pass": False,
            "scope": "Production MainApp camera, detector, classifier, mapper, EventEngine and mouse; GENERAL only; cursor confined to target.",
            "evidence_limit": "Windows receipts also include physical mouse input. Only the user can confirm hand-only operation. No webcam images saved.",
            "results": {name: self.results.get(name, {"human_observation": "not_recorded"}) for name, _ in STEPS},
            "unrecorded_step_event_counts": dict(self.counts),
            "blocked_input_calls": self.input_guard.blocked,
            "recent_windows_events": list(self.events),
        }
        try:
            self.report_path.parent.mkdir(parents=True, exist_ok=True)
            self.report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"Could not save physical-check report to {self.report_path}: {exc}", file=sys.stderr)
        else:
            print(f"Local physical-check report: {self.report_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=REPO_ROOT / "logs" / (
        "mouse-validation-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".json"))
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("This physical check requires Windows 10/11 and a webcam.")
    sys.path.insert(0, str(REPO_ROOT))
    from main import MainApp

    class ValidationApp(MainApp):
        def start_system(self):
            # Install before production starts any camera or processing threads.
            # No SETTINGS edits and no save_profile/apply_settings calls.
            self.mapper.execute_action = lambda _name: None
            self.mapper.get_sleep_gesture = lambda _mappings: None
            self.mapper.set_mode = lambda _mode: None
            self.mapper.cycle_mode = lambda: None
            self.mapper.brightness.set_brightness_from_y = lambda _y: None
            self.ui.settings_btn.configure(state="disabled")
            self.ui.train_btn.configure(state="disabled")
            self.target = MouseTarget(self, args.report)
            super().start_system()
            self.target.poll()
            self.ui.after(250, self.target.show_once)

        def set_automation_enabled(self, enabled):
            target = getattr(self, "target", None)
            if enabled and (target is None or not target.focused() or target.step >= len(STEPS)):
                return
            super().set_automation_enabled(enabled)

        def stop_system(self):
            try:
                super().stop_system()
            finally:
                target = getattr(self, "target", None)
                if target is not None:
                    target.save()

    app = ValidationApp(start_paused=True)
    app.run()


if __name__ == "__main__":
    main()
