"""
measure_pointer_pipeline.py — measure the pointer path; never tune blind.

This drives the REAL GestureDetector, GestureClassifier and MouseController
over a REAL hand photograph, with a stubbed Win32 layer so the operator's real
cursor is never moved. It exists because "the cursor feels laggy" has many
possible layers, and the correct fix differs for each:

  A. detector cadence  -> measured here
  B. classifier gating -> measured here (how often raw != Pointing)
  C. filter + deadzone -> measured here (commanded vs achieved lag)

Nothing here is extrapolated to 60 FPS. Every number is a real observation.
"""
import argparse
import math
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import cv2  # noqa: E402
import numpy as np  # noqa: E402


def _stub_win32():
    """Neutralise the real desktop: measure, never move the operator's cursor."""
    import ctypes
    import screeninfo
    from types import SimpleNamespace

    fake = MagicMock()
    fake.SetCursorPos = MagicMock(return_value=1)
    fake.mouse_event = MagicMock()
    ctypes.windll = SimpleNamespace(user32=fake, dxva2=MagicMock())
    monitor = MagicMock(x=0, y=0, width=1920, height=1080, is_primary=True)
    screeninfo.get_monitors = lambda: [monitor]



def measure_detector_and_classifier(image, frames, jitter_px):
    """Real detector + real classifier over a held hand with synthetic jitter."""
    from src.gesture_detector import GestureDetector
    from src.gesture_classifier import GestureClassifier

    detector = GestureDetector()
    if not detector.detector_available:
        raise SystemExit(f"Detector unavailable: {detector.detector_error}")
    classifier = GestureClassifier()
    classifier.reset()

    rng = np.random.default_rng(1234)
    raw_labels, stable_labels, times = Counter(), Counter(), []

    for index in range(frames):
        frame = image
        if jitter_px:
            noise = rng.integers(-jitter_px, jitter_px + 1, size=image.shape, dtype=np.int16)
            frame = np.clip(image.astype(np.int16) + noise, 0, 255).astype(np.uint8)

        start = time.perf_counter()
        results = detector.process_frame(frame, int(start * 1000) + index)
        times.append(time.perf_counter() - start)

        hands = detector.get_all_hands_data(results, frame.shape)
        result = classifier.classify(hands)
        raw_labels[result.raw_gesture] += 1
        stable_labels[result.gesture] += 1

    hands_seen = detector.frames_with_hands
    detector.close()

    span = sum(times)
    return {
        "detector_fps": (len(times) - 1) / span if span > 0 else 0.0,
        "inference_mean_ms": statistics.fmean(times) * 1000.0,
        "inference_median_ms": statistics.median(times) * 1000.0,
        "raw_labels": dict(raw_labels),
        "stable_labels": dict(stable_labels),
        "frames_with_hand": hands_seen,
    }



def measure_pointer_filter(cadence_hz, sweep_seconds, amplitude_px):
    """Isolate filter/deadzone latency: command a known sweep, measure lag.

    The classifier is bypassed on purpose so this measures ONLY the pointer
    path (One Euro + deadzone + SetCursorPos). A lagging result here is a
    filtering problem; a clean result here means any felt lag originates
    upstream in detector cadence or classifier gating.
    """
    from src.mouse_controller import MouseController
    from src.models import Landmark

    controller = MouseController()
    dt = 1.0 / cadence_hz
    steps = max(2, int(cadence_hz * sweep_seconds))
    errors, issued = [], 0

    for step in range(steps):
        target_x = int(640 + amplitude_px * (2.0 * step / (steps - 1) - 1.0))
        target_y = 360
        landmarks = [
            Landmark(id=i, pixel_x=target_x, pixel_y=target_y,
                     x=target_x / 1280.0, y=target_y / 720.0, z=0.0)
            for i in range(21)
        ]
        landmarks[9] = Landmark(
            id=9, pixel_x=target_x, pixel_y=target_y - 180,
            x=target_x / 1280.0, y=(target_y - 180) / 720.0, z=0.0,
        )
        moved = controller.process_pointer(
            landmarks, "Pointing", "Pointing", 1280, 720, now=step * dt
        )
        if moved:
            issued += 1
            actual = controller.mouse.user32.SetCursorPos.call_args.args
            commanded = controller.mouse.map_coordinates(target_x, target_y, 1280, 720)
            errors.append(math.hypot(actual[0] - commanded[0], actual[1] - commanded[1]))
        time.sleep(dt)

    return controller, {
        "commanded_cadence_hz": cadence_hz,
        "pointer_samples": steps,
        "pointer_updates_issued": issued,
        "achieved_pointer_fps": issued / sweep_seconds if sweep_seconds else 0.0,
        "lag_median_px": round(statistics.median(errors), 2) if errors else 0.0,
        "lag_max_px": round(max(errors), 2) if errors else 0.0,
        "engine_state": str(controller.engine.state),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=REPO_ROOT / "tests" / "test_hand.jpg")
    parser.add_argument("--frames", type=int, default=60)
    parser.add_argument("--jitter", type=int, default=2)
    parser.add_argument("--cadence", type=float, default=30.0)
    parser.add_argument("--sweep-seconds", type=float, default=3.0)
    parser.add_argument("--amplitude", type=int, default=500)
    args = parser.parse_args()

    _stub_win32()
    image = cv2.imread(str(args.image))
    if image is None:
        raise SystemExit(f"Could not read {args.image}")

    print("=" * 70)
    print("A. DETECTOR + CLASSIFIER  (real model, real hand image)")
    print("=" * 70)
    for key, value in measure_detector_and_classifier(image, args.frames, args.jitter).items():
        print(f"  {key:28s} {value}")

    print()
    print("=" * 70)
    print("B. POINTER FILTER + DEADZONE  (classifier bypassed on purpose)")
    print("=" * 70)
    controller, stats = measure_pointer_filter(
        args.cadence, args.sweep_seconds, args.amplitude
    )
    for key, value in stats.items():
        print(f"  {key:28s} {value}")

    cutoff = controller.mouse.smoother.min_cutoff
    print()
    print("  effective pointer settings actually driving the filter:")
    for key, value in getattr(controller, "effective_pointer_settings", {}).items():
        print(f"    {key:26s} {value}")
    print(f"    {'beta':26s} {controller.mouse.smoother.beta:.4f}")
    print(f"    {'rest time constant':26s} {1000.0 / (2.0 * math.pi * cutoff):.1f} ms")



def synthesise_pointing(base_landmarks, curl=0.15, thumb_curl=0.80):
    """Build a realistic Pointing pose from REAL detected hand geometry.

    Uses the real wrist/MCP positions so proportions and scale are genuine.
    Index stays extended; middle, ring and pinky curl toward the palm; the
    thumb curls, because a raised thumb would classify as Thumb Up rather
    than Pointing.

    ``curl`` is the fraction of the extended distance that is RETAINED
    between each finger's MCP and its PIP/DIP/TIP. It was originally 0.62,
    which left the middle/ring/pinky fingers still substantially extended and
    so produced a genuine "Four Fingers"/"Open Palm" pose rather than a
    Pointing one. The fixture was invalid: it was measuring the classifier's
    correct behaviour, not pointer performance. 0.15 reproduces a clearly
    curled hand, which is what a real pointing pose looks like.
    """
    import copy

    lms = [copy.deepcopy(lm) for lm in base_landmarks]
    chains = ((9, 10, 11, 12), (13, 14, 15, 16), (17, 18, 19, 20))
    for mcp, pip, dip, tip in chains:
        source = lms[mcp]
        for joint in (pip, dip, tip):
            origin = lms[joint]
            lms[joint] = type(origin)(
                id=origin.id,
                x=source.x + (origin.x - source.x) * curl,
                y=source.y + (origin.y - source.y) * curl,
                z=source.z + (origin.z - source.z) * curl,
                pixel_x=source.pixel_x,
                pixel_y=source.pixel_y,
            )
    thumb_mcp = lms[2]
    for joint in (3, 4):
        origin = lms[joint]
        lms[joint] = type(origin)(
            id=origin.id,
            x=thumb_mcp.x + (origin.x - thumb_mcp.x) * thumb_curl,
            y=thumb_mcp.y + (origin.y - thumb_mcp.y) * thumb_curl,
            z=thumb_mcp.z + (origin.z - thumb_mcp.z) * thumb_curl,
            pixel_x=thumb_mcp.pixel_x,
            pixel_y=thumb_mcp.pixel_y,
        )
    return lms


def measure_full_path_pointer(base_landmarks, samples, cadence_hz, sweep_px):
    """THE decisive measurement: pointer rate through the REAL classifier.

    Section B bypasses the classifier and only proves the filter is fast.
    This section does not: it feeds a realistic Pointing pose through
    GestureClassifier and MouseController.process_landmarks exactly as
    production does, and counts how many samples actually move the cursor.
    A low achieved rate here is classifier gating, not filter latency.
    """
    from src.gesture_classifier import GestureClassifier
    from src.mouse_controller import MouseController

    classifier = GestureClassifier()
    classifier.reset()
    controller = MouseController()
    dt = 1.0 / cadence_hz
    raw_labels, stable_labels = Counter(), Counter()
    moved, prev_tip = 0, None

    for step in range(samples):
        offset = sweep_px * (2.0 * step / max(1, samples - 1) - 1.0)
        lms = synthesise_pointing(base_landmarks)
        for landmark in lms:
            # Shift x by the SAME delta as pixel_x. Recomputing x from
            # pixel_x would destroy the curl interpolation applied above,
            # because synthesise_pointing gives curled joints their MCP's
            # pixel_x while keeping an interpolated normalised x.
            landmark.pixel_x = int(landmark.pixel_x + offset)
            landmark.x += offset / 1280.0
        result = classifier.classify([{"landmarks": lms, "score": 95}])
        raw_labels[result.raw_gesture] += 1
        stable_labels[result.gesture] += 1

        if controller.process_landmarks(
            lms, result.gesture, result.raw_gesture, 1280, 720, now=step * dt
        ) is None:
            pass
        tip = (lms[8].pixel_x, lms[8].pixel_y)
        if prev_tip is not None and tip != prev_tip:
            moved += 1
        prev_tip = tip
        time.sleep(dt)

    return controller, {
        "samples": samples,
        "raw_labels": dict(raw_labels),
        "stable_labels": dict(stable_labels),
        "frames_where_raw_is_Pointing":
            f"{raw_labels['Pointing']}/{samples} "
            f"({100.0 * raw_labels['Pointing'] / samples:.0f}%)",
        "moves_issued": moved,
        "pointer_intent_state": controller.pointer_intent.state,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=REPO_ROOT / "tests" / "test_hand.jpg")
    parser.add_argument("--frames", type=int, default=60)
    parser.add_argument("--jitter", type=int, default=2)
    parser.add_argument("--cadence", type=float, default=30.0)
    parser.add_argument("--sweep-seconds", type=float, default=3.0)
    parser.add_argument("--amplitude", type=int, default=500)
    args = parser.parse_args()

    _stub_win32()
    image = cv2.imread(str(args.image))
    if image is None:
        raise SystemExit(f"Could not read {args.image}")

    print("=" * 70)
    print("A. DETECTOR + CLASSIFIER  (real model, real hand image)")
    print("=" * 70)
    for key, value in measure_detector_and_classifier(image, args.frames, args.jitter).items():
        print(f"  {key:28s} {value}")

    print()
    print("=" * 70)
    print("B. POINTER FILTER + DEADZONE  (classifier bypassed on purpose)")
    print("=" * 70)
    controller, stats = measure_pointer_filter(
        args.cadence, args.sweep_seconds, args.amplitude
    )
    for key, value in stats.items():
        print(f"  {key:28s} {value}")
    cutoff = controller.mouse.smoother.min_cutoff
    print()
    print("  effective pointer settings actually driving the filter:")
    for key, value in getattr(controller, "effective_pointer_settings", {}).items():
        print(f"    {key:26s} {value}")
    print(f"    {'beta':26s} {controller.mouse.smoother.beta:.4f}")
    print(f"    {'rest time constant':26s} {1000.0 / (2.0 * math.pi * cutoff):.1f} ms")

    print()
    print("=" * 70)
    print("C. FULL PATH  (real classifier -> real pointer path, pointing pose)")
    print("=" * 70)
    from src.gesture_detector import GestureDetector

    probe = GestureDetector()
    results = probe.process_frame(image, 1)
    hands = probe.get_all_hands_data(results, image.shape)
    probe.close()
    if not hands:
        raise SystemExit("No hand detected in the reference image")
    controller2, full = measure_full_path_pointer(
        hands[0]["landmarks"], args.frames, args.cadence, args.amplitude
    )
    for key, value in full.items():
        print(f"  {key:28s} {value}")
    print(f"  {'SetCursorPos calls':28s} {controller2.mouse.updates}")
    print(f"  {'samples swallowed':28s} {controller2.pointer_metrics.suppressed}")

    # ── Fixture sanity gate ───────────────────────────────────────────────
    # A synthetic fixture that does not actually produce the gesture it
    # claims is invalid, and every number derived from it is meaningless.
    # Refuse to report a performance figure rather than print a
    # self-contradictory one.
    print()
    problems = []
    if full["raw_labels"].get("Pointing", 0) == 0:
        problems.append("raw label never reported Pointing")
    if full["stable_labels"].get("Pointing", 0) == 0:
        problems.append("stable label never reported Pointing")
    if controller2.pointer_intent.state != "active":
        problems.append(f"pointer intent ended in {controller2.pointer_intent.state!r}")
    if controller2.mouse.updates == 0:
        problems.append("no SetCursorPos calls were issued")
    if problems:
        print("FIXTURE INVALID - performance numbers above are NOT trustworthy:")
        for problem in problems:
            print(f"  - {problem}")
        print("  The synthetic Pointing pose does not match classifier geometry.")
        raise SystemExit(2)
    print("FIXTURE VALID: Pointing -> stable Pointing -> pointer active -> SetCursorPos")


if __name__ == "__main__":
    main()

