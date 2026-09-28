"""
ui_commands — the only sanctioned way for a worker thread to reach Tk.

Why this module exists
----------------------
Tkinter is not thread-safe. A ``CTkLabel.configure()``, ``deiconify()`` or
``after()`` issued from the camera thread, the inference thread, the
ActionExecutor worker, the ``keyboard`` hotkey listener or the ``pystray``
menu thread can deadlock, raise ``RuntimeError: main thread is not in main
loop``, or corrupt Tk's internal state — the classic cause of a window that
"sticks" and never repaints.

The contract
------------
* Worker threads call :meth:`UiCommandQueue.post` and return immediately.
  ``post`` never blocks on a full queue: a stale UI request is worthless, so
  the oldest pending request is dropped rather than back-pressuring the
  control pipeline.
* The Tk thread calls :meth:`UiCommandQueue.drain` from its own ``after``
  loop and executes what it finds. That is the *only* place Tk is touched.

Latest-frame semantics
----------------------
:class:`PreviewBudget` is the preview-side companion. It answers two
questions without any Tk involvement: "may I render a preview frame right
now?" and "is this frame newer than the last one shown?". That keeps the
expensive ``cv2 -> PIL -> ImageTk`` pipeline off both the control path and,
while the dashboard is hidden, entirely off the machine.
"""

import threading
import time
from collections import deque

from .logger import logger

#: Preview frames per second. 20-30 is indistinguishable from the camera
#: cadence to a human eye and costs a fraction of the CPU that 60 Hz does.
DEFAULT_PREVIEW_FPS = 24.0


class UiCommandQueue:
    """A bounded, thread-safe mailbox of zero-argument callables for Tk."""

    def __init__(self, maxsize: int = 32):
        self._lock = threading.Lock()
        self._items: deque = deque()
        self._maxsize = max(1, int(maxsize))
        self.posted = 0
        self.dropped = 0
        self.executed = 0
        self.failed = 0

    def post(self, func, *args, **kwargs) -> bool:
        """Queue ``func(*args, **kwargs)`` for the Tk thread. Never blocks."""
        if not callable(func):
            return False
        call = (func, args, kwargs)
        with self._lock:
            if len(self._items) >= self._maxsize:
                # Drop the OLDEST request. A backlog of stale show/hide
                # intents is worse than losing one: the user would see the
                # dashboard do the wrong thing seconds after asking.
                self._items.popleft()
                self.dropped += 1
            self._items.append(call)
            self.posted += 1
        return True

    def drain(self, limit: int = 16) -> int:
        """Run queued commands. **Tk thread only.** Returns how many ran."""
        ran = 0
        while ran < max(0, int(limit)):
            with self._lock:
                if not self._items:
                    break
                func, args, kwargs = self._items.popleft()
            try:
                func(*args, **kwargs)
            except Exception:
                self.failed += 1
                logger.exception("UI command %r failed.", getattr(func, "__name__", func))
            self.executed += 1
            ran += 1
        return ran

    def clear(self) -> int:
        """Discard pending commands. Used on shutdown and when hiding."""
        with self._lock:
            count = len(self._items)
            self._items.clear()
        return count

    @property
    def pending(self) -> int:
        with self._lock:
            return len(self._items)

    def as_dict(self) -> dict:
        with self._lock:
            pending = len(self._items)
        return {
            "posted": self.posted,
            "executed": self.executed,
            "dropped": self.dropped,
            "failed": self.failed,
            "pending": pending,
        }


class PreviewBudget:
    """Rate limiter + latest-frame gate for dashboard preview rendering.

    ``should_render`` is the single decision point used by the UI thread. It
    is deliberately free of Tk and NumPy so it can be unit-tested directly
    and reused for the background-mode CPU budget.
    """

    def __init__(self, max_fps: float = DEFAULT_PREVIEW_FPS, clock=time.perf_counter):
        self._clock = clock
        self._max_fps = max(0.5, float(max_fps))
        self._interval = 1.0 / self._max_fps
        self._last_render_at: float | None = None
        self._last_frame_id: int | None = None
        self.rendered = 0
        self.throttled = 0
        self.duplicates = 0
        self.suppressed_hidden = 0

    @property
    def max_fps(self) -> float:
        return self._max_fps

    @property
    def last_frame_id(self):
        return self._last_frame_id

    def should_render(self, visible: bool, frame_id=None) -> bool:
        """True when a preview render is allowed right now.

        Three independent reasons to refuse, cheapest first:

        1. the dashboard is hidden — no conversion, no PhotoImage, no Tk;
        2. the frame is the one already on screen;
        3. the previous render was less than ``1/max_fps`` seconds ago.
        """
        if not visible:
            self.suppressed_hidden += 1
            return False
        if frame_id is not None and frame_id == self._last_frame_id:
            self.duplicates += 1
            return False
        now = self._clock()
        if self._last_render_at is not None and now - self._last_render_at < self._interval:
            self.throttled += 1
            return False
        return True

    def mark_rendered(self, frame_id=None, force=False) -> None:
        """Record that a render just happened, unblocking the next one.

        ``force`` (a synthetic status frame) leaves the rate limiter alone so
        a normal camera frame is not then blocked by an immediate update.
        """
        if not force:
            self._last_render_at = self._clock()
        if frame_id is not None:
            self._last_frame_id = frame_id
        self.rendered += 1

    def invalidate(self) -> None:
        """Forget the shown frame so the next one is always accepted."""
        self._last_frame_id = None
        self._last_render_at = None

    def reset(self) -> None:
        self.invalidate()
        self.rendered = 0
        self.throttled = 0
        self.duplicates = 0
        self.suppressed_hidden = 0

    def as_dict(self) -> dict:
        return {
            "preview_fps_target": self._max_fps,
            "preview_rendered": self.rendered,
            "preview_throttled": self.throttled,
            "preview_duplicate": self.duplicates,
            "preview_suppressed_hidden": self.suppressed_hidden,
        }

        """Discard pending commands. Used on shutdown and on hide."""
        with self._lock:
            count = len(self._items)
            self._items.clear()
        return count

    @property
    def pending(self) -> int:
        with self._lock:
            return len(self._items)

    def as_dict(self) -> dict:
        return {
            "posted": self.posted,
            "executed": self.executed,
            "dropped": self.dropped,
            "failed": self.failed,
            "pending": self.pending,
        }
