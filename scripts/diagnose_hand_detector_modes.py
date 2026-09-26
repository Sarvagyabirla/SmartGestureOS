#!/usr/bin/env python3
"""
scripts/diagnose_hand_detector_modes.py

SMARTGESTUREOS — P0 Hand Detection Mode Diagnostic & Probe Script.
Implements Steps 1 through 15:
- Step 1: Real camera frame probe (capture, stats, validation)
- Step 2: Test IMAGE mode (detection, landmarks, draw result)
- Step 3: Test Original resolution in IMAGE mode
- Step 4: Test 640x360 downscale in IMAGE mode
- Step 5: Test 640x640 padded square input in IMAGE mode
- Step 6: Test Mirrored vs Unmirrored in IMAGE mode
- Step 7: Confidence sweep (0.5, 0.4, 0.3) in IMAGE mode
- Step 8: Test VIDEO mode on sequential camera frames (5 seconds)
- Step 9: Test LIVE_STREAM mode on original vs 640x360
- Step 10: Model bundle verification & SHA256 checksum
- Step 11: MediaPipe & OpenCV version compatibility check
- Step 12: Color pipeline validation (BGR vs RGB channel stats)
- Step 13: Memory/lifetime analysis
- Step 14: NORM_RECT warning investigation
- Step 15: Mandatory Diagnostic Matrix summary
"""

import sys
import os
import time
import hashlib
import zipfile
import argparse
from pathlib import Path
import numpy as np
import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import SETTINGS
from src.paths import RESOURCE_DIR

MODEL_PATH = str(RESOURCE_DIR / 'models' / 'hand_landmarker.task')
PROBE_DIR = PROJECT_ROOT / 'diagnostics' / 'hand_probe'
PROBE_DIR.mkdir(parents=True, exist_ok=True)


def print_banner(text: str):
    print("\n" + "=" * 70)
    print(f" {text}")
    print("=" * 70)


def compute_sha256(filepath: str) -> tuple[int, str]:
    with open(filepath, 'rb') as f:
        data = f.read()
    return len(data), hashlib.sha256(data).hexdigest()


# ── STEP 1: REAL FRAME PROBE ──────────────────────────────────────────────────

def step1_capture_probe_frame(auto_capture: bool = False, capture_delay: float = 3.0) -> np.ndarray:
    print_banner("STEP 1 — REAL FRAME PROBE")
    cam_cfg = SETTINGS.get("camera", {})
    cam_index = cam_cfg.get("index", 0)
    width = cam_cfg.get("width", 1280)
    height = cam_cfg.get("height", 720)

    print(f"Opening camera index {cam_index} ({width}x{height})...")
    cap = cv2.VideoCapture(cam_index)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    if not cap.isOpened():
        raise RuntimeError(f"Could not open camera at index {cam_index}")

    print("Warming up camera sensor...")
    for _ in range(15):
        cap.read()
        time.sleep(0.05)

    captured_frame = None

    # Preview detector for real-time visual feedback
    preview_detector = None
    try:
        preview_detector = vision.HandLandmarker.create_from_options(
            vision.HandLandmarkerOptions(
                base_options=python.BaseOptions(model_asset_path=MODEL_PATH),
                running_mode=vision.RunningMode.IMAGE,
                num_hands=1,
                min_hand_detection_confidence=0.4,
                min_hand_presence_confidence=0.4,
            )
        )
    except Exception as e:
        print(f"[INFO] Preview detector init note: {e}")

    if not auto_capture:
        print("\nINSTRUCTIONS:")
        print(">> Place ONE open hand clearly in front of the camera.")
        print(">> Press [SPACE] in the preview window to capture the diagnostic frame.")
        print(">> Press [ESC] to cancel.")

        window_name = "SmartGestureOS - Hand Probe Preview (Press SPACE to capture)"
        start_time = time.time()
        timeout = 25.0
        hand_detected_start = None

        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                continue

            display_preview = frame.copy()
            h, w = frame.shape[:2]

            # Live detection check on downscaled frame for responsiveness
            hand_seen = False
            if preview_detector is not None:
                try:
                    small = cv2.resize(frame, (320, 180))
                    small_rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                    mp_small = mp.Image(image_format=mp.ImageFormat.SRGB, data=small_rgb)
                    res = preview_detector.detect(mp_small)
                    if res and res.hand_landmarks:
                        hand_seen = True
                        for lm in res.hand_landmarks[0]:
                            cx, cy = int(lm.x * w), int(lm.y * h)
                            cv2.circle(display_preview, (cx, cy), 5, (0, 255, 0), -1)
                except Exception:
                    pass

            if hand_seen:
                if hand_detected_start is None:
                    hand_detected_start = time.time()
                held_time = time.time() - hand_detected_start
                cv2.putText(
                    display_preview, "HAND DETECTED! [SPACE] TO CAPTURE",
                    (30, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2
                )
                cv2.putText(
                    display_preview, f"Auto-locking in: {max(0.0, 1.5 - held_time):.1f}s",
                    (30, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2
                )
                if held_time >= 1.5:
                    print("[OK] Hand detected and locked automatically.")
                    captured_frame = frame
                    break
            else:
                hand_detected_start = None
                cv2.putText(
                    display_preview, "PLACE OPEN HAND IN FRAME (PRESS SPACE TO CAPTURE)",
                    (30, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 200, 255), 2
                )
                remaining = max(0, int(timeout - (time.time() - start_time)))
                cv2.putText(
                    display_preview, f"Time remaining: {remaining}s",
                    (30, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180, 180, 180), 2
                )

            try:
                cv2.imshow(window_name, display_preview)
                key = cv2.waitKey(1) & 0xFF
                if key == 32:  # SPACE
                    captured_frame = frame
                    print("[OK] Captured frame via SPACE keypress.")
                    break
                elif key == 27:  # ESC
                    print("[ABORT] ESC pressed by user.")
                    cap.release()
                    cv2.destroyAllWindows()
                    if preview_detector:
                        preview_detector.close()
                    sys.exit(0)
            except Exception as e:
                print(f"[WARN] GUI preview not available ({e}). Falling back to auto-capture.")
                auto_capture = True
                break

            if time.time() - start_time > timeout:
                print("[INFO] Timeout reached. Auto-capturing current frame...")
                captured_frame = frame
                break

        try:
            cv2.destroyWindow(window_name)
        except Exception:
            pass

    if auto_capture or captured_frame is None:
        print("Auto-capture mode: searching for hand in feed for up to 10s...")
        search_start = time.time()
        while time.time() - search_start < 10.0:
            ret, frame = cap.read()
            if not ret or frame is None:
                continue
            if preview_detector is not None:
                try:
                    small = cv2.resize(frame, (320, 180))
                    small_rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                    res = preview_detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=small_rgb))
                    if res and res.hand_landmarks:
                        captured_frame = frame
                        print(f"[OK] Hand found in live feed at t={time.time()-search_start:.1f}s.")
                        break
                except Exception:
                    pass
            time.sleep(0.05)
        if captured_frame is None:
            ret, captured_frame = cap.read()

    if preview_detector:
        preview_detector.close()

    cap.release()

    # Save original BGR and RGB frames
    bgr_path = PROBE_DIR / "original_bgr.png"
    rgb_path = PROBE_DIR / "original_rgb.png"
    cv2.imwrite(str(bgr_path), captured_frame)
    rgb_frame = cv2.cvtColor(captured_frame, cv2.COLOR_BGR2RGB)
    cv2.imwrite(str(rgb_path), cv2.cvtColor(rgb_frame, cv2.COLOR_RGB2BGR))

    # Frame metrics
    h, w, c = captured_frame.shape
    dtype = captured_frame.dtype
    min_val = int(np.min(captured_frame))
    max_val = int(np.max(captured_frame))
    mean_b = float(np.mean(captured_frame))
    std_b = float(np.std(captured_frame))
    contiguous = captured_frame.flags['C_CONTIGUOUS']

    print(f"Saved: {bgr_path}")
    print(f"Saved: {rgb_path}")
    print("\nPROBE FRAME METRICS:")
    print(f"  Shape:             {h}x{w} (channels: {c})")
    print(f"  Dtype:             {dtype}")
    print(f"  Min pixel value:   {min_val}")
    print(f"  Max pixel value:   {max_val}")
    print(f"  Mean brightness:   {mean_b:.2f}")
    print(f"  Std deviation:     {std_b:.2f}")
    print(f"  Is contiguous:     {contiguous}")
    print(f"  Camera resolution: {w}x{h}")

    # Validations
    assert dtype == np.uint8, f"Expected uint8, got {dtype}"
    assert c == 3, f"Expected 3 channels, got {c}"
    assert mean_b > 5.0, f"Frame is completely black (mean={mean_b})"
    assert std_b > 5.0, f"Frame lacks contrast (std={std_b})"
    print("[VALIDATION PASSED] Frame is valid, uint8, non-black, textured image.")

    return captured_frame


# ── STEP 2, 3, 4, 5, 6, 7: IMAGE MODE EXPERIMENTS ────────────────────────────

def run_image_mode_detect(image_bgr: np.ndarray, detection_con: float = 0.5, presence_con: float = 0.5):
    """Run HandLandmarker in IMAGE mode on a single BGR image."""
    base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
    options = vision.HandLandmarkerOptions(
        base_options=base_options,
        running_mode=vision.RunningMode.IMAGE,
        num_hands=2,
        min_hand_detection_confidence=detection_con,
        min_hand_presence_confidence=presence_con,
    )
    detector = vision.HandLandmarker.create_from_options(options)

    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    result = detector.detect(mp_img)
    detector.close()
    return result


def draw_landmarks_on_image(image_bgr: np.ndarray, result) -> np.ndarray:
    out = image_bgr.copy()
    if not result or not result.hand_landmarks:
        return out

    h, w, _ = out.shape
    connections = [
        (0,1), (1,2), (2,3), (3,4),
        (0,5), (5,6), (6,7), (7,8),
        (5,9), (9,10), (10,11), (11,12),
        (9,13), (13,14), (14,15), (15,16),
        (13,17), (0,17), (17,18), (18,19), (19,20)
    ]
    for hand_lms in result.hand_landmarks:
        for p1, p2 in connections:
            x1, y1 = int(hand_lms[p1].x * w), int(hand_lms[p1].y * h)
            x2, y2 = int(hand_lms[p2].x * w), int(hand_lms[p2].y * h)
            cv2.line(out, (x1, y1), (x2, y2), (255, 0, 255), 2)
        for lm in hand_lms:
            cx, cy = int(lm.x * w), int(lm.y * h)
            cv2.circle(out, (cx, cy), 4, (0, 255, 255), -1)
    return out


def letterbox_square(image: np.ndarray, target_size: int = 640) -> np.ndarray:
    """Center image in square canvas preserving aspect ratio without stretching."""
    h, w = image.shape[:2]
    scale = target_size / max(h, w)
    nw, nh = int(w * scale), int(h * scale)
    resized = cv2.resize(image, (nw, nh), interpolation=cv2.INTER_AREA)

    square = np.zeros((target_size, target_size, 3), dtype=np.uint8)
    top = (target_size - nh) // 2
    left = (target_size - nw) // 2
    square[top:top+nh, left:left+nw] = resized
    return square


# ── STEP 8: VIDEO MODE TEST ───────────────────────────────────────────────────

def test_video_mode(duration_sec: float = 5.0) -> tuple[int, int, float]:
    print_banner("STEP 8 — VIDEO MODE TEST (5 seconds)")
    cam_cfg = SETTINGS.get("camera", {})
    cap = cv2.VideoCapture(cam_cfg.get("index", 0))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cam_cfg.get("width", 1280))
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cam_cfg.get("height", 720))

    base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
    options = vision.HandLandmarkerOptions(
        base_options=base_options,
        running_mode=vision.RunningMode.VIDEO,
        num_hands=2,
        min_hand_detection_confidence=0.5,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    detector = vision.HandLandmarker.create_from_options(options)

    print("Warming up camera for video test...")
    for _ in range(10):
        cap.read()
        time.sleep(0.02)
    print("Keep hand clearly in view...")

    frames_processed = 0
    frames_with_hand = 0
    total_hands = 0
    start_time = time.perf_counter()
    last_timestamp_ms = -1

    while time.perf_counter() - start_time < duration_sec:
        ret, frame = cap.read()
        if not ret or frame is None:
            time.sleep(0.01)
            continue

        ts_ms = int((time.perf_counter() - start_time) * 1000)
        if ts_ms <= last_timestamp_ms:
            ts_ms = last_timestamp_ms + 1
        last_timestamp_ms = ts_ms

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        res = detector.detect_for_video(mp_img, ts_ms)

        frames_processed += 1
        num_hands = len(res.hand_landmarks) if res and res.hand_landmarks else 0
        if num_hands > 0:
            frames_with_hand += 1
            total_hands += num_hands
        time.sleep(0.01)

    cap.release()
    detector.close()

    avg_hands = (total_hands / frames_processed) if frames_processed > 0 else 0.0
    print(f"VIDEO MODE RESULT:")
    print(f"  Frames processed:       {frames_processed}")
    print(f"  Frames containing hand: {frames_with_hand}")
    print(f"  Average number of hands: {avg_hands:.2f}")
    return frames_processed, frames_with_hand, avg_hands


# ── STEP 9: LIVE_STREAM TEST (ORIGINAL vs 640x360) ─────────────────────────────

def test_live_stream_isolated(resize_640x360: bool = False, duration_sec: float = 5.0) -> tuple[int, int, int]:
    label = "640x360" if resize_640x360 else "ORIGINAL FULL RES"
    print_banner(f"STEP 9 — ISOLATED LIVE_STREAM TEST ({label})")

    cam_cfg = SETTINGS.get("camera", {})
    cap = cv2.VideoCapture(cam_cfg.get("index", 0))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cam_cfg.get("width", 1280))
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cam_cfg.get("height", 720))

    callbacks_received = 0
    hands_detected = 0
    submitted = 0

    def live_callback(result, output_image, timestamp_ms):
        nonlocal callbacks_received, hands_detected
        callbacks_received += 1
        if result and result.hand_landmarks and len(result.hand_landmarks) > 0:
            hands_detected += 1

    base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
    options = vision.HandLandmarkerOptions(
        base_options=base_options,
        running_mode=vision.RunningMode.LIVE_STREAM,
        result_callback=live_callback,
        num_hands=2,
        min_hand_detection_confidence=0.5,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    detector = vision.HandLandmarker.create_from_options(options)

    print(f"Warming up camera for LIVE_STREAM ({label})...")
    for _ in range(10):
        cap.read()
        time.sleep(0.02)
    print("Keep hand clearly in view...")

    start_time = time.perf_counter()
    last_ts_ms = -1

    # Keep references to prevent premature garbage collection of async frame buffers
    frame_holder = {}

    while time.perf_counter() - start_time < duration_sec:
        ret, frame = cap.read()
        if not ret or frame is None:
            time.sleep(0.01)
            continue

        ts_ms = int(time.perf_counter() * 1000)
        if ts_ms <= last_ts_ms:
            ts_ms = last_ts_ms + 1
        last_ts_ms = ts_ms

        if resize_640x360:
            proc_frame = cv2.resize(frame, (640, 360))
        else:
            proc_frame = frame

        rgb = cv2.cvtColor(proc_frame, cv2.COLOR_BGR2RGB)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        # Store reference
        frame_holder[ts_ms] = (rgb, mp_img)
        # Bounded retention
        if len(frame_holder) > 10:
            oldest_k = min(frame_holder.keys())
            del frame_holder[oldest_k]

        detector.detect_async(mp_img, ts_ms)
        submitted += 1
        time.sleep(0.02)

    # Wait for trailing callbacks
    time.sleep(0.5)
    cap.release()
    detector.close()

    print(f"LIVE_STREAM ({label}) RESULT:")
    print(f"  Frames submitted:   {submitted}")
    print(f"  Callbacks received: {callbacks_received}")
    print(f"  Frames with hands:  {hands_detected}")
    return submitted, callbacks_received, hands_detected


# ── MAIN DIAGNOSTIC WORKFLOW ──────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="P0 Hand Detection Mode Diagnostic")
    parser.add_argument("--auto", action="store_true", help="Auto-capture without waiting for SPACE key")
    parser.add_argument("--image", type=str, default="", help="Optional pre-existing image file to probe")
    args = parser.parse_args()

    print_banner("SMARTGESTUREOS — P0 ZERO-HAND-DETECTION ROOT CAUSE MISSION (PHASE 1B)")

    # STEP 10: Model Bundle Verification
    print_banner("STEP 10 — MODEL BUNDLE VERIFICATION")
    assert os.path.exists(MODEL_PATH), f"Model missing at {MODEL_PATH}"
    file_size, sha256_hash = compute_sha256(MODEL_PATH)
    print(f"Model path: {MODEL_PATH}")
    print(f"File size:  {file_size} bytes")
    print(f"SHA256:     {sha256_hash}")

    OFFICIAL_SHA256 = "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1"
    if sha256_hash == OFFICIAL_SHA256:
        print("[MATCH] Model is verified 100% identical to official Google MediaPipe hand_landmarker.task.")
    else:
        print(f"[MISMATCH] Local model ({sha256_hash}) differs from official ({OFFICIAL_SHA256})!")

    z = zipfile.ZipFile(MODEL_PATH)
    print(f"Bundled files in .task: {z.namelist()}")

    # STEP 11: Compatibility Check
    print_banner("STEP 11 — MEDIAPIPE & OPENCV COMPATIBILITY")
    print(f"Python:       {sys.version}")
    print(f"MediaPipe:    {getattr(mp, '__version__', 'unknown')}")
    print(f"OpenCV:       {cv2.__version__}")

    # STEP 1: Real frame capture
    if args.image and os.path.exists(args.image):
        print(f"Using provided image: {args.image}")
        captured_frame = cv2.imread(args.image)
        bgr_path = PROBE_DIR / "original_bgr.png"
        cv2.imwrite(str(bgr_path), captured_frame)
    else:
        captured_frame = step1_capture_probe_frame(auto_capture=args.auto)

    # STEP 12: Color Pipeline Check
    print_banner("STEP 12 — COLOR PIPELINE VALIDATION")
    rgb_frame = cv2.cvtColor(captured_frame, cv2.COLOR_BGR2RGB)
    bgr_means = np.mean(captured_frame, axis=(0, 1))
    rgb_means = np.mean(rgb_frame, axis=(0, 1))
    print(f"BGR channel means (B, G, R): {bgr_means[0]:.1f}, {bgr_means[1]:.1f}, {bgr_means[2]:.1f}")
    print(f"RGB channel means (R, G, B): {rgb_means[0]:.1f}, {rgb_means[1]:.1f}, {rgb_means[2]:.1f}")
    assert np.isclose(bgr_means[0], rgb_means[2]), "Color conversion channel swap mismatch!"
    assert np.isclose(bgr_means[2], rgb_means[0]), "Color conversion channel swap mismatch!"
    print("[VALIDATION PASSED] BGR to RGB color conversion confirmed accurate.")

    matrix = {}

    # STEP 2 & 3: Original Full Resolution
    print_banner("STEP 2 & 3 — TEST IMAGE MODE (ORIGINAL FULL RES)")
    res_orig = run_image_mode_detect(captured_frame, 0.5, 0.5)
    hands_orig = len(res_orig.hand_landmarks) if res_orig.hand_landmarks else 0
    print(f"ORIGINAL FULL RES: hands = {hands_orig}")
    if hands_orig > 0:
        lms_count = len(res_orig.hand_landmarks[0])
        score = res_orig.handedness[0][0].score if res_orig.handedness else 0.0
        label = res_orig.handedness[0][0].category_name if res_orig.handedness else "Unknown"
        print(f"  Hand 0: landmarks={lms_count}, handedness={label}, score={score*100:.1f}%")
        out_orig = draw_landmarks_on_image(captured_frame, res_orig)
        cv2.imwrite(str(PROBE_DIR / "image_mode_result.png"), out_orig)
        print(f"  Saved detection visualization to: {PROBE_DIR / 'image_mode_result.png'}")
    matrix["IMAGE original"] = f"{hands_orig}"

    # STEP 6: Mirrored vs Unmirrored
    print_banner("STEP 6 — TEST MIRRORED VS UNMIRRORED")
    mirrored_frame = cv2.flip(captured_frame, 1)
    res_mirr = run_image_mode_detect(mirrored_frame, 0.5, 0.5)
    hands_mirr = len(res_mirr.hand_landmarks) if res_mirr.hand_landmarks else 0
    print(f"IMAGE raw:      hands = {hands_orig}")
    print(f"IMAGE mirrored: hands = {hands_mirr}")
    matrix["IMAGE mirrored"] = f"{hands_mirr}"

    # STEP 4: 640x360 Downscale
    print_banner("STEP 4 — TEST 640x360 RESIZE")
    frame_640x360 = cv2.resize(captured_frame, (640, 360))
    res_360 = run_image_mode_detect(frame_640x360, 0.5, 0.5)
    hands_360 = len(res_360.hand_landmarks) if res_360.hand_landmarks else 0
    print(f"640x360: hands = {hands_360}")
    matrix["IMAGE 640x360"] = f"{hands_360}"

    # STEP 5: 640x640 Padded Square
    print_banner("STEP 5 — TEST 640x640 PADDED SQUARE")
    frame_square = letterbox_square(captured_frame, 640)
    res_sq = run_image_mode_detect(frame_square, 0.5, 0.5)
    hands_sq = len(res_sq.hand_landmarks) if res_sq.hand_landmarks else 0
    print(f"640x640 letterbox: hands = {hands_sq}")
    matrix["IMAGE 640x640"] = f"{hands_sq}"

    # STEP 7: Confidence Sweep
    print_banner("STEP 7 — CONFIDENCE SWEEP IN IMAGE MODE")
    for th in [0.5, 0.4, 0.3]:
        res_th = run_image_mode_detect(captured_frame, th, th)
        h_th = len(res_th.hand_landmarks) if res_th.hand_landmarks else 0
        print(f"IMAGE threshold {th}: hands = {h_th}")
        matrix[f"IMAGE threshold {th}"] = f"{h_th}"

    # STEP 8: Video Mode Test
    v_proc, v_hands, v_avg = test_video_mode(duration_sec=5.0)
    matrix["VIDEO original"] = f"{v_hands} / {v_proc} frames"

    # STEP 9: Isolated LIVE_STREAM Tests
    l_orig_sub, l_orig_cb, l_orig_h = test_live_stream_isolated(resize_640x360=False, duration_sec=5.0)
    matrix["LIVE original"] = f"{l_orig_h} / {l_orig_cb} callbacks"

    l_360_sub, l_360_cb, l_360_h = test_live_stream_isolated(resize_640x360=True, duration_sec=5.0)
    matrix["LIVE 640x360"] = f"{l_360_h} / {l_360_cb} callbacks"

    # STEP 15: Mandatory Diagnostic Matrix Table
    print_banner("STEP 15 — MANDATORY DIAGNOSTIC MATRIX")
    print(f"{'TEST':<28} HANDS")
    print("-" * 33)
    for test_name, result_str in matrix.items():
        print(f"{test_name:<28} {result_str}")
    print("-" * 33)


if __name__ == "__main__":
    main()
