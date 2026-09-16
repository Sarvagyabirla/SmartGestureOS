# Production Architecture Audit

## 1. main.py
**SEVERITY**: HIGH
**ROOT CAUSE**: Memory bounds on `pending_frames` are weakly enforced. Inference backlog is not dropped if ML queue stalls. FPS telemetry is combined instead of separate (Capture/Inference/UI). Timers use `time.time()` instead of `time.perf_counter()`.
**USER IMPACT**: Stale frames cause perceived latency. Memory leak if ML stalls. Misleading FPS metrics.
**FIX**: Enforce max 3 pending frames. Drop stale ML results. Implement monotonic clocks. Measure 5 different FPS metrics and latency percentiles.
**TEST REQUIRED**: Queue/backpressure tests, memory leak tests.

## 2. src/models.py
**SEVERITY**: HIGH
**ROOT CAUSE**: Missing unified canonical landmark dataclass separating normalized vs pixel space. Missing `GestureResult` dataclass with separation of tracking vs shape confidence.
**USER IMPACT**: Gesture logic mixes pixel and normalized coordinates. Confidence is inaccurate (hand score mixed with gesture shape).
**FIX**: Implement strict `Landmark`, `GestureResult`, and `ActionResult` dataclasses.
**TEST REQUIRED**: Unit tests for models.

## 3. src/gesture_classifier.py
**SEVERITY**: CRITICAL
**ROOT CAUSE**: Classifier uses strict finger logic without enough noise margin. Cross fingers, Call Me, Rock On are poorly discriminated. Handedness score incorrectly modifies gesture confidence.
**USER IMPACT**: Hard to trigger specific gestures. High false positive rate for Pointing vs Pinch.
**FIX**: Make classifier rotation-tolerant using geometric relationships. Implement robust Call Me, Rock On, Crossed Fingers logic. Disentangle shape confidence from handedness.
**TEST REQUIRED**: Extensive unit tests for all discrete and continuous poses under rotation and scale.

## 4. src/event_engine.py
**SEVERITY**: CRITICAL
**ROOT CAUSE**: Pinch logic immediately triggers drag. Double click window is fragile. No true failsafe for hand lost.
**USER IMPACT**: Unintentional dragging when trying to click. Stuck mouse buttons if hand is lost while dragging.
**FIX**: Implement robust temporal state machine (IDLE, HOVER, PINCH_DOWN, PINCH_RELEASE_WAIT, DRAGGING, SCROLLING). Add `on_hand_lost()` that releases mouse buttons.
**TEST REQUIRED**: Event Engine state transition tests (single pinch, double pinch, drag hold, drop).

## 5. src/gesture_mapper.py
**SEVERITY**: MEDIUM
**ROOT CAUSE**: `GestureHoldTimer` is used globally introducing lag. Discrete vs Continuous gestures are not separated. Mode isolation is weak (e.g. Pinch clears canvas in DRAW).
**USER IMPACT**: Gestures feel sluggish. Unintentional triggers across modes.
**FIX**: Remove hold delay for Pointing, Dragging, Scrolling, Drawing. Add explicit mode cooldown on transition. Fix strict mappings per mode (e.g., DRAW clear = Closed Fist).
**TEST REQUIRED**: Mode isolation tests.

## 6. src/mouse_controller.py & src/virtual_mouse.py
**SEVERITY**: HIGH
**ROOT CAUSE**: Missing `release_all` failsafe. Scrolling compares raw distances without accumulation. Deadzone logic can cause stickiness.
**USER IMPACT**: Stuck mouse clicks. Jumpy scrolling. Difficult precision movement.
**FIX**: Implement `release_all()`. Use normalized Y movement with accumulation/rate-limiting for scrolling. Tune OneEuroFilter params.
**TEST REQUIRED**: Scroll normalization tests, virtual mouse interaction tests.

## 7. src/drawing.py & src/desktop_controller.py
**SEVERITY**: MEDIUM
**ROOT CAUSE**: Screenshot and drawing save do not verify file existence or use a proper writable user-data directory. Action results are unverified.
**USER IMPACT**: Files might fail to save without user knowing.
**FIX**: Implement `ActionResult`. Use `%LOCALAPPDATA%` for user files. Verify saves.
**TEST REQUIRED**: Action controller tests.

## 8. src/camera.py
**SEVERITY**: MEDIUM
**ROOT CAUSE**: Camera reconnect logic does not reset gesture state.
**USER IMPACT**: Stuck state upon camera disconnect.
**FIX**: Hook camera disconnect to `event_engine.on_hand_lost()`.
**TEST REQUIRED**: Camera disconnect simulation.
