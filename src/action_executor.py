"""
action_executor — single-slot executor for slow, discrete Windows actions.

Why this exists
---------------
``ImageGrab.grab()`` (screenshot), ``subprocess.Popen`` (Chrome / VS Code),
pycaw brightness calls and ``keyboard.send`` desktop shortcuts can block for
hundreds of milliseconds. They used to run inline on the inference thread
while ``MainApp._automation_lock`` was held, which made the Tk UI thread
block on that same lock and made the whole application appear frozen. The
UI watchdog then observed a stale capture timestamp and force-invalidated
tracking, so the cursor visibly jumped after every screenshot.

What this preserves
-------------------
* **single-action semantics** — at most one action is queued; a new
  submission replaces the stale pending entry instead of piling up.
* **generation safety** — every submission is stamped with a generation. A
  pause, tracking reset, mode switch or shutdown bumps the generation, and
  the worker re-checks it *immediately before* running the callable, so a
  queued action can never fire after automation was paused or tracking was
  lost.
* **callable re-validation** — the submitter also passes ``is_valid``, a
  zero-argument predicate re-checked on the worker thread. This closes the
  window between queueing and execution.
* **safe shutdown** — ``stop()`` refuses new work, drops pending work and
  joins the worker with a bounded timeout.
"""

import queue
import threading
import time

from .logger import logger

_SENTINEL = object()


class _Job:
    __slots__ = ("name", "func", "generation", "is_valid", "submitted_at")

    def __init__(self, name, func, generation, is_valid, submitted_at):
        self.name = name
        self.func = func
        self.generation = generation
        self.is_valid = is_valid
        self.submitted_at = submitted_at


class ActionExecutor:
    """Run one slow discrete action at a time, off the inference thread."""

    def __init__(self, on_result=None, clock=time.perf_counter):
        self._clock = clock
        self._on_result = on_result
        self._queue: queue.Queue = queue.Queue(maxsize=1)
        self._lock = threading.Lock()
        self._generation = 0
        self._stopping = False
        self._started = False
        self._thread: threading.Thread | None = None
        self.dropped: int = 0
        self.executed: int = 0
        self.cancelled: int = 0

    # ── lifecycle ──────────────────────────────────────────────────────────

    def start(self) -> None:
        with self._lock:
            if self._started or self._stopping:
                return
            self._started = True
            self._thread = threading.Thread(
                target=self._worker, daemon=True, name="action-executor"
            )
            thread = self._thread
        thread.start()
        logger.info("ActionExecutor started (slow actions off the inference thread).")

    def stop(self, timeout: float = 2.0) -> None:
        """Refuse new work, drop pending work and join the worker."""
        with self._lock:
            if not self._started:
                return
            self._stopping = True
            thread = self._thread
        self.cancel("shutdown")
        self._put_sentinel()
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
            if thread.is_alive():
                logger.warning("ActionExecutor worker still stopping; pending work dropped.")
        logger.info("ActionExecutor stopped.")

    def _put_sentinel(self) -> None:
        try:
            self._queue.put_nowait(_SENTINEL)
            return
        except queue.Full:
            self._drain()
        try:
            self._queue.put_nowait(_SENTINEL)
        except queue.Full:
            pass

    # ── generation ─────────────────────────────────────────────────────────

    @property
    def generation(self) -> int:
        with self._lock:
            return self._generation

    @property
    def stopping(self) -> bool:
        with self._lock:
            return self._stopping

    def cancel(self, reason: str = "") -> None:
        """Invalidate every queued action.

        Called on pause, tracking reset, tracking generation bump, mode
        change and shutdown. A worker already inside a callable cannot be
        interrupted, which is why slow actions re-validate with ``is_valid``
        before touching the desktop.
        """
        with self._lock:
            self._generation += 1
            dropped = self._drain()
        if dropped:
            self.cancelled += dropped
        if reason:
            logger.debug(f"ActionExecutor cancelled pending actions ({reason}).")


    # ── submission ─────────────────────────────────────────────────────────

    def submit(self, name, func, is_valid=None) -> bool:
        """Queue one slow action. Returns False when it was refused.

        ``func`` runs on the worker thread and may return anything; its return
        value is handed to the ``on_result`` callback.
        """
        with self._lock:
            if self._stopping or not self._started:
                return False
            generation = self._generation

        job = _Job(name, func, generation, is_valid, self._clock())
        try:
            self._queue.put_nowait(job)
            return True
        except queue.Full:
            # Single-action semantics: the stale pending entry loses.
            replaced = self._drain()
            if replaced:
                self.dropped += replaced
        try:
            self._queue.put_nowait(job)
            return True
        except queue.Full:
            self.dropped += 1
            return False

    # ── worker ─────────────────────────────────────────────────────────────

    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            if item is _SENTINEL:
                self._queue.task_done()
                return
            try:
                self._run(item)
            except Exception:  # pragma: no cover - defensive
                logger.exception(f"ActionExecutor failed while running {item.name!r}.")
            finally:
                self._queue.task_done()

    def _run(self, job: _Job) -> None:
        with self._lock:
            generation = self._generation
            stopping = self._stopping
        if stopping or job.generation != generation:
            self.cancelled += 1
            logger.info(f"ActionExecutor dropped {job.name!r}: stale generation or shutdown.")
            return
        if job.is_valid is not None:
            try:
                still_valid = bool(job.is_valid())
            except Exception:
                logger.exception(f"ActionExecutor validity check failed for {job.name!r}.")
                return
            if not still_valid:
                self.cancelled += 1
                logger.info(f"ActionExecutor dropped {job.name!r}: invalidated before execution.")
                return

        started = self._clock()
        self.executed += 1
        result = job.func()
        if self._on_result is not None:
            try:
                self._on_result(job.name, result, self._clock() - started)
            except Exception:  # pragma: no cover - defensive
                logger.exception("ActionExecutor result callback failed.")

    def _drain(self) -> int:
        dropped = 0
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                return dropped
            dropped += 1

