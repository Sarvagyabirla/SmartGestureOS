# UI Freeze & Window Stability — Root Cause Analysis

Status: **FIXED** — verified by measurement before and after.
Machine: Windows 11 x64, Python 3.11.9, CustomTkinter 6.0.0.
Reproduce: `.\.venv\Scripts\python.exe scripts\diagnose_ui_freeze.py --seconds 6`
and `.\.venv\Scripts\python.exe scripts\diagnose_runtime.py --seconds 30`.

---

## 1. The reported symptom

> "While controlling the computer through hand gestures, the SmartGestureOS
> window sometimes appears/stays on screen and becomes stuck/frozen."

Two distinct failures were behind that single report:

| # | Symptom | Cause | Status |
|---|---------|-------|--------|
| **A** | Window "freezes" / "Not Responding" | Tk event loop 180 % over budget | **Fixed** |
| **B** | Window disappears, app unreachable | Tray failure + unconditional `withdraw()` | **Fixed** |

---

## 2. Root cause A — the Tk event loop was 180 % over budget

### What was measured

`MainApp.update_ui_loop()` re-schedules itself with `self.ui.after(15, ...)`,
i.e. a **15 ms budget per tick**. Each tick performed, unconditionally:

| Stage | p50 | p95 | max |
|---|---|---|---|
| `update_dashboard()` — ~12 CTk `configure()` calls | **14.65 ms** | 16.03 ms | 21.59 ms |
| `update_frame()` — cvtColor + PIL resize + PhotoImage + label | **12.06 ms** | 13.33 ms | 18.58 ms |
| **Total per 15 ms tick** | **26.7 ms** | — | — |

`update_frame()` breakdown:

| Stage | p50 |
|---|---|
| `Image.fromarray` | 1.05 ms |
| **`PIL.Image.resize` (1280×720 -> 750×500)** | **6.24 ms** |
| `ImageTk.PhotoImage` | 1.15 ms |
| `video_label.configure(image=...)` | 3.05 ms |

**Diagnosis.** The tick needed 26.7 ms of work inside a 15 ms budget. The Tk
thread therefore never went idle, the Tcl/Tk event pump was permanently
saturated, and Windows concluded the window was hung and painted the
"Not Responding" state. The control engine was never blocked — the *view*
was consuming the thread the control engine's watchdog shared.

A second, compounding factor: a CustomTkinter `configure()` is a full Tcl
round trip costing roughly 0.5–1 ms, and the old code issued about a dozen of
them per tick **even when nothing had changed**. At 66 Hz that is ~970 ms of
pure redundant Tcl traffic per second.

### The fixes

1. **Change detection** — `SmartGestureApp._configure_if_changed()` keeps a
   per-call-site cache of the last configured values and skips the Tcl round
   trip when nothing changed. A steady gesture now costs **zero** `configure()`
   calls (locked in by `test_repeated_identical_dashboard_updates_issue_no_tcl_calls`).
2. **Cheaper frame pipeline** — one `cv2.resize(..., INTER_AREA)` *before*
   colour conversion, replacing a full-resolution `cvtColor` followed by a
   6.24 ms PIL bicubic resize. The conversion now happens on the small image.
3. **Rate limit** — `PreviewBudget` caps preview rendering at 24 FPS. 20–30
   preview FPS is indistinguishable from the camera rate to a human.
4. **Cached geometry** — `winfo_width()/winfo_height()` are queried at most
   twice a second instead of on every frame.
5. **Confidence bar** — animated from a cached value and snapped to target,
   so an idle bar performs zero `set()` calls.

### Measured result

| Metric | Before | After | Change |
|---|---|---|---|
| Tk event-loop delay p50 | 14.71 ms | **0.49 ms** | −97 % |
| Tk event-loop delay p95 | 16.13 ms | **1.08 ms** | −93 % |
| Tk event-loop delay max | 21.99 ms | 20.35 ms (one-off) | — |
| `update_dashboard` p50 | 14.65 ms | **0.40 ms** | −97 % |
| `update_frame` p50 | 12.06 ms | **0.01 ms** (throttled) | −99.9 % |



---

## 3. Root cause B — the window could vanish with no way back

`SmartGestureApp.on_closing()` called `self.withdraw()` unconditionally. If
`pystray` failed to import or the tray thread died, the user clicked X, the
window disappeared, and there was **no tray, no taskbar entry and no hotkey**
to restore it — the process kept running, still holding the camera and the
global keyboard hook. This is the "stuck, unresponsive app" experience.

Aggravating packaging fact: `pystray` was **installed in the venv but absent
from `requirements.txt` and from the PyInstaller spec**, so a frozen build
would have shipped with **no tray at all**.

### The fixes

1. **Predictable close** — `on_window_close()` honours a
   *minimize-to-tray on close* setting: X means background, or X means exit.
   The user can never hide the UI into a state they cannot escape.
2. **Restore hotkey** — `Ctrl+Alt+Shift+G` restores the dashboard.
   `Ctrl+Alt+G` remains reserved for emergency Pause/Resume and is never
   overloaded, so the emergency stop works even with no window visible.
3. **Tray rebuilt on the correct thread** — the old callbacks called
   `self.ui.after(0, ...)` *from the pystray thread*, itself a Tk
   thread-safety violation. They now post to `UiCommandQueue` and the Tk
   thread executes them.
4. **Declared and bundled** — `pystray==0.19.5` added to `requirements.txt`,
   `pystray` + `pystray._win32` added to the spec's hidden imports, and
   `_tray_icon_path()` now searches both the repo and the PyInstaller layout.
5. **Both hotkeys released on exit** — `stop_system()` unregisters
   `Ctrl+Alt+G` *and* `Ctrl+Alt+Shift+G`; a surviving hook would break every
   other application on the machine.

---

## 4. Tkinter thread-safety audit

| Thread | May touch Tk? | Mechanism |
|---|---|---|
| Camera capture | No | none needed |
| Inference / processing | No | publishes to a `Queue(maxsize=1)` |
| ActionExecutor worker | No | TTS queue only |
| `keyboard` hotkey listener | **No** | posts to `UiCommandQueue` |
| `pystray` menu thread | **No** | posts to `UiCommandQueue` |
| psutil monitoring | No | plain attribute writes |
| **Tk main thread** | **Yes — only here** | `update_ui_loop()` drains the queue |

`UiCommandQueue.post()` never blocks: a full queue drops its *oldest* entry,
because a backlog of stale show/hide intents is worse than losing one.
Locked in by `test_command_queue_from_a_worker_thread_never_touches_tk`.

---

## 5. Background Control Mode

Hiding the dashboard is a **view-only** change. The camera, MediaPipe,
classifier, pointer, event engine, ActionExecutor and both hotkeys keep
running untouched — locked in by
`test_hiding_the_dashboard_never_touches_the_control_pipeline`.

When hidden, three separate blocks of work stop:

1. `update_frame()` returns immediately — no `cvtColor`, no PIL, no PhotoImage.
2. The processing loop skips `frame.copy()`, the drawing-canvas overlay, the
   21-landmark drawing and every `cv2.putText` status overlay.
3. `PreviewBudget` reports the suppression so the saving is measurable.

### Measured result (30 s live run, real webcam)

| Metric | Dashboard VISIBLE | BACKGROUND | Change |
|---|---|---|---|
| Preview renders | 274 | **0** | −100 % |
| Previews suppressed | 0 | 439 | — |
| Tk event-loop delay p95 | 43.2 ms | **14.8 ms** | −66 % |
| Process CPU | 238 % | **185 %** | **−22 %** |
| Detector FPS | 14.5 | 14.5 | unchanged (correct) |
| Inference p50 / p95 | 57.0 / 65.9 ms | 58.0 / 71.4 ms | unchanged |
| RAM | 295 → 299 MB | 321 → 311 MB | stable, no leak |

**Background mode is strictly cheaper than the visible dashboard, and the

---

## 6. Bonus finding — the pointer filter was adding ~290 ms

The user profile at `%LOCALAPPDATA%\SmartGestureOS\profiles\default.json` has
`"smoothing": 20`. `_smoothing_cutoff()` mapped the 1–20 slider onto
2.0 Hz → 0.55 Hz, and a One Euro low pass at 0.55 Hz has a group delay of
**~1/(2π·0.55) ≈ 290 ms**. The cursor therefore trailed the hand by almost a
third of a second — which users experience as "laggy" or "frozen", and which
is indistinguishable from a UI stall.

| smoothing | cutoff (old) | delay (old) | cutoff (new) | delay (new) |
|---|---|---|---|---|
| 1 | 2.00 Hz | 56 ms | 6.00 Hz | 26 ms |
| 2 (default) | 1.92 Hz | 59 ms | 4.00 Hz | 40 ms |
| 10 | 1.31 Hz | 95 ms | 3.16 Hz | 50 ms |
| 20 (this profile) | 0.55 Hz | **260 ms** | 2.00 Hz | **80 ms** |

The slider ordering is unchanged and
`test_pointer_filter_never_adds_a_freezing_group_delay` now fails the build if
any slider position exceeds a 100 ms budget.

---

## 7. Regression tests added

`tests/test_background_mode.py` (22 tests) and four packaging tests in
`tests/test_distribution_assets.py`:

- dashboard rendering does not block control state
- latest-preview-frame semantics (mailbox, never a backlog)
- hide dashboard / show dashboard
- automation continues while the dashboard is hidden
- Pause hotkey while the dashboard is hidden
- restore hotkey is a distinct combination
- background exit cleanup (both hotkey handles released)
- Tk is never updated from a worker thread
- no old queued UI frames on restore
- no ImageTk reference accumulation
- UI startup / UI shutdown
- slow screenshot does not freeze Tk (ActionExecutor, pre-existing)
- slow app launch does not freeze the detector (ActionExecutor, pre-existing)
- pointer filter group-delay budget across all 20 slider positions
- pystray declared, bundled, and its icon locatable in both layouts

control pipeline is measurably identical in both states.**
