"""
DrawingCanvas — in-memory drawing engine for DRAW mode.

Uses time.perf_counter() throughout for monotonic timing (F-38 fix).
Filenames use millisecond precision + random suffix to prevent collision (F-11 fix).
Undo stack capped at 20 snapshots (the initial blank state counts as slot 0).
"""

import cv2
import numpy as np
import os
import time
import uuid
from .utils import PointSmoother, cubic_bezier_interpolation


class DrawingCanvas:
    MAX_UNDO_STEPS = 20

    def __init__(self, width=1280, height=720):
        self.width = width
        self.height = height
        self.canvas = np.zeros((height, width, 3), np.uint8)

        self.colors = [
            (255, 0, 255),   # Magenta
            (255, 0, 0),     # Blue (BGR)
            (0, 255, 0),     # Green
            (0, 0, 255),     # Red (BGR)
            (0, 255, 255),   # Yellow (BGR)
        ]
        self.color_idx = 0
        self.color = self.colors[self.color_idx]

        self.brush_size = 8
        self.eraser_size = 50
        self.is_eraser = False

        # F-38 FIX: use perf_counter for timing
        self.smoother = PointSmoother(min_cutoff=0.5, beta=0.8)
        self.hover_smoother = PointSmoother(min_cutoff=0.1, beta=0.1)

        self.last_point = None
        self.is_drawing = False

        # Undo/redo stacks hold canvas snapshots
        self.undo_stack = []
        self.redo_stack = []

        # Save initial blank state as slot 0
        self._save_state()

    # ── State management ──────────────────────────────────────────────────────

    def _save_state(self) -> None:
        """Push current canvas to undo stack; enforce MAX_UNDO_STEPS limit."""
        # F-10 FIX: pop the oldest entry BEFORE appending to guarantee max == MAX_UNDO_STEPS
        if len(self.undo_stack) >= self.MAX_UNDO_STEPS:
            self.undo_stack.pop(0)
        self.undo_stack.append(self.canvas.copy())

    # ── Drawing ───────────────────────────────────────────────────────────────

    def end_stroke(self) -> None:
        """Forget tracking coordinates without changing the drawing or history."""
        self.is_drawing = False
        self.last_point = None
        self.smoother.reset()
        self.hover_smoother.reset()

    def resize(self, new_width: int, new_height: int) -> "ActionResult":
        from src.models import ActionResult
        import time
        import cv2
        t = time.perf_counter()
        
        if new_width <= 0 or new_height <= 0:
            return ActionResult(False, "resize_canvas", "Invalid dimensions", "Width/height <= 0", t)
            
        if new_width == self.width and new_height == self.height:
            return ActionResult(True, "resize_canvas", "No resize needed", None, t)
            
        try:
            self.canvas = cv2.resize(self.canvas, (new_width, new_height), interpolation=cv2.INTER_NEAREST)
            self.width = new_width
            self.height = new_height
            
            self.undo_stack = [cv2.resize(s, (new_width, new_height), interpolation=cv2.INTER_NEAREST) for s in self.undo_stack]
            self.redo_stack = [cv2.resize(s, (new_width, new_height), interpolation=cv2.INTER_NEAREST) for s in self.redo_stack]
            self.end_stroke()
            
            return ActionResult(True, "resize_canvas", f"Resized to {new_width}x{new_height}", None, t)
        except Exception as e:
            return ActionResult(False, "resize_canvas", "Resize failed", str(e), t)

    def draw(self, x: int, y: int, draw_mode: bool = True) -> tuple[int, int]:
        t = time.perf_counter()  # F-38 FIX

        if draw_mode:
            self.hover_smoother.reset()
            smooth_x, smooth_y = self.smoother.update(t, x, y)
            sx, sy = int(smooth_x), int(smooth_y)

            if not self.is_drawing:
                self.is_drawing = True
                self.last_point = (sx, sy)
                self._save_state()
                self.redo_stack.clear()

            if self.last_point:
                if self.is_eraser:
                    cv2.circle(self.canvas, (sx, sy), self.eraser_size // 2, (0, 0, 0), cv2.FILLED)
                    cv2.line(self.canvas, self.last_point, (sx, sy), (0, 0, 0), self.eraser_size)
                else:
                    cv2.line(
                        self.canvas, self.last_point, (sx, sy),
                        self.color, self.brush_size, cv2.LINE_AA,
                    )
                    cv2.circle(
                        self.canvas, (sx, sy),
                        self.brush_size // 2, self.color, cv2.FILLED, cv2.LINE_AA,
                    )
                self.last_point = (sx, sy)
            return sx, sy
        else:
            self.smoother.reset()
            self.is_drawing = False
            self.last_point = None
            smooth_x, smooth_y = self.hover_smoother.update(t, x, y)
            return int(smooth_x), int(smooth_y)

    # ── Tools ─────────────────────────────────────────────────────────────────

    def toggle_eraser(self) -> "ActionResult":
        from src.models import ActionResult
        import time
        self.is_eraser = not self.is_eraser
        return ActionResult(True, "toggle_eraser", f"Eraser {'On' if self.is_eraser else 'Off'}", None, time.perf_counter())

    def cycle_color(self) -> "ActionResult":
        from src.models import ActionResult
        import time
        self.is_eraser = False
        self.color_idx = (self.color_idx + 1) % len(self.colors)
        self.color = self.colors[self.color_idx]
        return ActionResult(True, "cycle_color", "Color cycled", None, time.perf_counter())

    def clear(self) -> "ActionResult":
        from src.models import ActionResult
        import time
        self.end_stroke()
        self._save_state()
        self.redo_stack.clear()
        self.canvas = np.zeros((self.height, self.width, 3), np.uint8)
        return ActionResult(True, "clear_canvas", "Canvas cleared", None, time.perf_counter())

    # ── Undo / Redo ───────────────────────────────────────────────────────────

    def undo(self) -> "ActionResult":
        from src.models import ActionResult
        import time
        if not self.undo_stack:
            return ActionResult(False, "undo", "Undo stack empty", None, time.perf_counter())
        if len(self.undo_stack) > 1 or np.count_nonzero(self.canvas) > 0:
            self.end_stroke()
            self.redo_stack.append(self.canvas.copy())
            self.canvas = self.undo_stack.pop()
            return ActionResult(True, "undo", "Undo successful", None, time.perf_counter())
        return ActionResult(False, "undo", "No state to undo", None, time.perf_counter())

    def redo(self) -> "ActionResult":
        from src.models import ActionResult
        import time
        if self.redo_stack:
            self.end_stroke()
            self._save_state()
            self.canvas = self.redo_stack.pop()
            return ActionResult(True, "redo", "Redo successful", None, time.perf_counter())
        return ActionResult(False, "redo", "No state to redo", None, time.perf_counter())

    # ── Save ──────────────────────────────────────────────────────────────────

    def save_image(self) -> "ActionResult":
        """
        F-11 FIX: use millisecond timestamp + UUID suffix to prevent filename collisions.
        """
        from src.paths import DRAWINGS_DIR
        from src.models import ActionResult

        ts_ms = int(time.perf_counter() * 1000)
        suffix = uuid.uuid4().hex[:6]
        filename = DRAWINGS_DIR / f"drawing_{ts_ms}_{suffix}.png"

        success = cv2.imwrite(str(filename), self.canvas)
        if success and os.path.exists(str(filename)):
            return ActionResult(
                True, "save_drawing",
                f"Saved {filename.name}",
                None,
                time.perf_counter(),
            )
        return ActionResult(
            False, "save_drawing",
            "Failed to save drawing.",
            "cv2.imwrite failed or file missing",
            time.perf_counter(),
        )

    # ── Overlay ───────────────────────────────────────────────────────────────

    def get_overlay(self, frame: np.ndarray) -> np.ndarray:
        """Composite drawing canvas over camera frame."""
        gray = cv2.cvtColor(self.canvas, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray, 1, 255, cv2.THRESH_BINARY)
        mask_inv = cv2.bitwise_not(mask)
        frame_bg = cv2.bitwise_and(frame, frame, mask=mask_inv)
        canvas_fg = cv2.bitwise_and(self.canvas, self.canvas, mask=mask)
        return cv2.add(frame_bg, canvas_fg)
