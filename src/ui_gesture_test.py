"""
GestureTestUI — live gesture recognition test screen.

Rules:
  - No OS actions execute inside this window (automation is paused on open).
  - Shows camera preview, detected gesture, confidence, mode.
  - A "RECOGNIZED" indicator flashes when a stable gesture is confirmed.
  - Tracks pass/fail counts per gesture for the current session.
"""
import customtkinter as ctk
from PIL import Image, ImageTk
import cv2
import time


# All gestures to display in the test list
ALL_GESTURES = [
    "Pointing",
    "Pinch",
    "Two Fingers",
    "Victory",
    "Three Fingers",
    "Four Fingers",
    "Open Palm",
    "Closed Fist",
    "Thumb Up",
    "Thumb Down",
    "Middle Finger",
    "Rock On",
    "Call Me",
    "Crossed Fingers",
]


class GestureTestUI(ctk.CTkToplevel):
    """Diagnostic gesture test window — safe to use during automation pause."""

    def __init__(self, parent, on_close_callback=None):
        super().__init__(parent)
        self.title("Gesture Test — SmartGestureOS")
        self.geometry("860x560")
        self.resizable(True, True)
        self.on_close_callback = on_close_callback
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        ctk.set_appearance_mode("dark")

        # ── Colors ─────────────────────────────────────────────────────────────
        self._bg = "#1a1a2e"
        self._card = "#16213e"
        self._accent = "#00d4ff"
        self._pass_col = "#2fa572"
        self._fail_col = "#d64545"
        self._muted = "#888888"

        self.configure(fg_color=self._bg)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)

        # ── Left: camera preview + live status ────────────────────────────────
        left = ctk.CTkFrame(self, fg_color=self._card, corner_radius=12)
        left.grid(row=0, column=0, padx=(12, 6), pady=12, sticky="nsew")
        left.grid_rowconfigure(0, weight=1)
        left.grid_columnconfigure(0, weight=1)

        self.preview_label = ctk.CTkLabel(left, text="")
        self.preview_label.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")

        # Status row
        status_frame = ctk.CTkFrame(left, fg_color="transparent")
        status_frame.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="ew")
        status_frame.grid_columnconfigure(0, weight=1)

        self.gesture_label = ctk.CTkLabel(
            status_frame, text="None",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=self._accent
        )
        self.gesture_label.grid(row=0, column=0, sticky="w")

        self.conf_label = ctk.CTkLabel(
            status_frame, text="0%",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=self._muted
        )
        self.conf_label.grid(row=0, column=1, sticky="e")

        self.recognized_label = ctk.CTkLabel(
            left, text="",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._pass_col
        )
        self.recognized_label.grid(row=2, column=0, pady=(0, 8))

        self._recognized_clear_id = None
        self._current_imgtk = None

        # ── Right: gesture checklist ───────────────────────────────────────────
        right = ctk.CTkScrollableFrame(self, width=200, fg_color=self._card, corner_radius=12)
        right.grid(row=0, column=1, padx=(6, 12), pady=12, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            right, text="GESTURES",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=self._muted
        ).grid(row=0, column=0, padx=12, pady=(10, 6), sticky="w")

        self._gesture_labels: dict[str, ctk.CTkLabel] = {}
        self._gesture_counts: dict[str, int] = {g: 0 for g in ALL_GESTURES}

        for i, gesture in enumerate(ALL_GESTURES):
            lbl = ctk.CTkLabel(
                right, text=f"○  {gesture}",
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color=self._muted, anchor="w"
            )
            lbl.grid(row=i + 1, column=0, padx=12, pady=2, sticky="ew")
            self._gesture_labels[gesture] = lbl

        reset_btn = ctk.CTkButton(
            right, text="Reset Counts",
            command=self._reset_counts,
            fg_color="#333355", hover_color="#444466",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            height=28
        )
        reset_btn.grid(row=len(ALL_GESTURES) + 1, column=0,
                       padx=12, pady=(12, 8), sticky="ew")

        # Note
        ctk.CTkLabel(
            right,
            text="No OS actions execute\nin test mode.",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=self._muted, justify="center"
        ).grid(row=len(ALL_GESTURES) + 2, column=0, padx=12, pady=(0, 10))

        # ── Poll loop ──────────────────────────────────────────────────────────
        self._last_gesture = ""
        self._prev_stable = ""
        self._poll()

    def _poll(self):
        """Pull the latest classification from the running backend (if any)."""
        try:
            import main as _main_module
            app = None
            for v in _main_module.__dict__.values():
                if hasattr(v, "classifier") and hasattr(v, "mapper"):
                    app = v
                    break

            if app is not None:
                # Read the latest data directly from the live classifier state
                stable = getattr(app.classifier, "last_stable_gesture", "None") or "None"
                raw = getattr(app.classifier, "last_raw_gesture", "None") or "None"
                conf = int(getattr(app.classifier, "confidence_ema", 0))
                frame_data = None
                try:
                    if not app.frame_queue.empty():
                        payload = app.frame_queue.queue[0]  # peek without consuming
                        if payload and len(payload) >= 2:
                            frame_data = payload[0]
                except Exception:
                    pass

                self._update_status(stable, raw, conf, frame_data)
        except Exception:
            pass

        if self.winfo_exists():
            self.after(100, self._poll)

    def _update_status(self, stable: str, raw: str, conf: int, frame=None):
        """Update all display elements for a new classification result."""
        if frame is not None:
            try:
                h = self.preview_label.winfo_height()
                w = self.preview_label.winfo_width()
                if w > 10 and h > 10:
                    resized = cv2.resize(frame, (w, h), interpolation=cv2.INTER_AREA)
                    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
                    self._current_imgtk = ImageTk.PhotoImage(image=Image.fromarray(rgb))
                    self.preview_label.configure(image=self._current_imgtk)
            except Exception:
                pass

        # Gesture + confidence
        display = stable if stable not in ("None", "Unknown", "") else raw
        if display in ("None", "Unknown", ""):
            display = "—"

        self.gesture_label.configure(text=display)
        self.conf_label.configure(text=f"{conf}%")

        # Flash RECOGNIZED when stable gesture changes to something real
        if (stable not in ("None", "Unknown", "")
                and stable != self._prev_stable
                and stable != self._last_gesture):
            self._flash_recognized(stable)
            self._prev_stable = stable
            self._record_recognition(stable)

        self._last_gesture = stable

    def _flash_recognized(self, gesture: str):
        """Flash the RECOGNIZED label."""
        try:
            self.recognized_label.configure(
                text=f"✓ RECOGNIZED: {gesture}",
                text_color=self._pass_col
            )
            if self._recognized_clear_id:
                self.after_cancel(self._recognized_clear_id)
            self._recognized_clear_id = self.after(
                1500, lambda: self.recognized_label.configure(text="")
            )
        except Exception:
            pass

    def _record_recognition(self, gesture: str):
        """Increment pass count and update checklist label."""
        if gesture not in self._gesture_counts:
            return
        self._gesture_counts[gesture] += 1
        count = self._gesture_counts[gesture]
        lbl = self._gesture_labels.get(gesture)
        if lbl is None:
            return
        try:
            lbl.configure(
                text=f"✓  {gesture}  ×{count}",
                text_color=self._pass_col if count > 0 else self._muted
            )
        except Exception:
            pass

    def _reset_counts(self):
        """Reset all recognition counts."""
        for gesture in ALL_GESTURES:
            self._gesture_counts[gesture] = 0
            lbl = self._gesture_labels.get(gesture)
            if lbl:
                try:
                    lbl.configure(text=f"○  {gesture}", text_color=self._muted)
                except Exception:
                    pass
        try:
            self.recognized_label.configure(text="")
        except Exception:
            pass

    def on_closing(self):
        if self.on_close_callback:
            self.on_close_callback()
        try:
            self.destroy()
        except Exception:
            pass
