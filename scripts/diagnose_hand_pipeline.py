"""
SmartGestureOS - Real Hardware Hand Pipeline Diagnostic Script
Validates:
Camera -> frame acquisition -> frame resize -> GestureDetector.detect_async()
-> MediaPipe LIVE_STREAM callback -> results_queue -> get_all_hands_data()

Outputs:
Camera frames:
Detector available:
Detector error:
Frames submitted:
Callbacks received:
Frames with hand:
Average callback latency:
"""

import sys
import os
import time
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import cv2
from src.camera import Camera
from src.gesture_detector import GestureDetector
from config import SETTINGS


def run_diagnostics(duration_sec: float = 10.0):
    print("=" * 60)
    print("SMARTGESTUREOS - REAL PIPELINE DIAGNOSTIC")
    print(f"Running for {duration_sec} seconds... Hold hand up to webcam.")
    print("=" * 60)

    cam_cfg = SETTINGS.get("camera", {})
    camera = Camera(
        index=cam_cfg.get("index", 0),
        width=cam_cfg.get("width", 1280),
        height=cam_cfg.get("height", 720),
        fps=cam_cfg.get("fps", 30),
    )

    detector = GestureDetector()
    print(f"Detector available: {detector.available}")
    print(f"Detector error: {detector.error}")

    if not detector.available:
        print("HAND TRACKING UNAVAILABLE:", detector.error)
        return

    cam_started = camera.start()
    print(f"Camera start returned: {cam_started}, is_connected: {camera.is_connected}")

    # Give camera capture thread a moment to connect and grab first frame
    time.sleep(1.0)

    camera_frames_count = 0
    frames_submitted = 0
    callbacks_received = 0
    frames_with_hand = 0
    latencies = []

    last_frame_id = -1
    last_inference_time = 0.0
    last_timestamp_ms = -1
    inference_interval = 1.0 / 30.0

    start_time = time.perf_counter()
    last_heartbeat = start_time

    while time.perf_counter() - start_time < duration_sec:
        loop_time = time.perf_counter()
        frame, frame_id = camera.read()

        if frame is not None and frame_id != last_frame_id:
            last_frame_id = frame_id
            camera_frames_count += 1

            if loop_time - last_inference_time >= inference_interval:
                timestamp_ms = int(loop_time * 1000)
                if timestamp_ms <= last_timestamp_ms:
                    timestamp_ms = last_timestamp_ms + 1
                last_timestamp_ms = timestamp_ms

                small_frame = cv2.resize(frame, (640, 360))
                detector.detect_async(small_frame, timestamp_ms)
                frames_submitted += 1
                last_inference_time = loop_time

        # Drain callbacks from detector.results_queue
        while not detector.results_queue.empty():
            res_ts, res = detector.results_queue.get_nowait()
            callbacks_received += 1
            if res_ts is not None:
                lat = (time.perf_counter() * 1000) - res_ts
                latencies.append(lat)

            if res and res.hand_landmarks:
                hands_data = detector.get_all_hands_data(res, (360, 640, 3))
                if hands_data and len(hands_data) > 0:
                    frames_with_hand += 1

        if loop_time - last_heartbeat >= 2.0:
            elapsed = int(loop_time - start_time)
            print(f"[{elapsed}s] Cam frames: {camera_frames_count}, Submitted: {frames_submitted}, Callbacks: {callbacks_received}, Hands: {frames_with_hand}")
            last_heartbeat = loop_time

        time.sleep(0.01)

    # Allow trailing callbacks to arrive
    time.sleep(0.5)
    while not detector.results_queue.empty():
        res_ts, res = detector.results_queue.get_nowait()
        callbacks_received += 1
        if res_ts is not None:
            lat = (time.perf_counter() * 1000) - res_ts
            latencies.append(lat)
        if res and res.hand_landmarks:
            hands_data = detector.get_all_hands_data(res, (360, 640, 3))
            if hands_data and len(hands_data) > 0:
                frames_with_hand += 1

    camera.stop()
    detector.close()

    avg_latency = (sum(latencies) / len(latencies)) if latencies else 0.0

    print("\n" + "=" * 60)
    print("FINAL DIAGNOSTIC REPORT:")
    print(f"Camera frames: {camera_frames_count}")
    print(f"Detector available: {detector.available}")
    print(f"Detector error: {detector.error}")
    print(f"Frames submitted: {frames_submitted}")
    print(f"Callbacks received: {callbacks_received}")
    print(f"Frames with hand: {frames_with_hand}")
    print(f"Average callback latency: {avg_latency:.2f} ms")
    print("=" * 60)


if __name__ == "__main__":
    dur = 10.0
    if len(sys.argv) > 1:
        try:
            dur = float(sys.argv[1])
        except ValueError:
            pass
    run_diagnostics(dur)
