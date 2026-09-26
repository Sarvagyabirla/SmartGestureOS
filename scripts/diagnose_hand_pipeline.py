"""
SmartGestureOS - Real Hardware Hand Pipeline Diagnostic Script
Validates the active production path:
Camera -> frame acquisition -> frame resize -> GestureDetector.process_frame()
-> MediaPipe VIDEO inference -> get_all_hands_data() -> landmark drawing

Outputs:
Camera frames:
Detector available:
Detector error:
Frames submitted:
Inference results returned:
Frames with hand:
Average camera-to-landmark latency:
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


def run_diagnostics(
    duration_sec: float = 10.0,
    inference_width: int = 640,
    inference_height: int = 360,
):
    if duration_sec <= 0 or inference_width <= 0 or inference_height <= 0:
        raise ValueError("Duration and inference dimensions must be positive")

    print("=" * 60)
    print("SMARTGESTUREOS - REAL PIPELINE DIAGNOSTIC")
    print(f"Running for {duration_sec} seconds... Hold hand up to webcam.")
    print(f"Inference frame: {inference_width}x{inference_height}")
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

    print("\nGET READY: Hold your open hand up in front of the webcam...")
    for c in range(3, 0, -1):
        print(f"  Starting in {c}...")
        time.sleep(1.0)
    print("  RECORDING NOW!\n")

    camera_frames_count = 0
    frames_submitted = 0
    results_received = 0
    frames_with_hand = 0
    inference_latencies = []
    camera_to_landmark_latencies = []

    last_frame_id = -1
    last_inference_time = 0.0
    last_timestamp_ms = -1
    inference_interval = 1.0 / 30.0

    start_time = time.perf_counter()
    last_heartbeat = start_time

    while time.perf_counter() - start_time < duration_sec:
        loop_time = time.perf_counter()
        frame, frame_id, captured_at = camera.read_with_timestamp()

        if frame is not None and frame_id != last_frame_id:
            last_frame_id = frame_id
            camera_frames_count += 1

            if loop_time - last_inference_time >= inference_interval:
                timestamp_ms = int(loop_time * 1000)
                if timestamp_ms <= last_timestamp_ms:
                    timestamp_ms = last_timestamp_ms + 1
                last_timestamp_ms = timestamp_ms

                small_frame = cv2.resize(frame, (inference_width, inference_height))

                start_inf = time.perf_counter()
                res = detector.process_frame(small_frame, timestamp_ms)
                inf_latency = (time.perf_counter() - start_inf) * 1000
                inference_latencies.append(inf_latency)

                frames_submitted += 1
                last_inference_time = loop_time

                hands_data = []
                if res is not None:
                    results_received += 1
                    hands_data = detector.get_all_hands_data(
                        res, (inference_height, inference_width, 3)
                    )
                    if captured_at is not None:
                        camera_to_landmark_latencies.append(
                            (time.perf_counter() - captured_at) * 1000
                        )

                if hands_data:
                    frames_with_hand += 1

        if loop_time - last_heartbeat >= 2.0:
            elapsed = int(loop_time - start_time)
            print(f"[{elapsed}s] Camera frames: {camera_frames_count}, Inference frames: {frames_submitted}, Results: {results_received}, Hands: {frames_with_hand}")
            last_heartbeat = loop_time

        time.sleep(0.01)

    elapsed_sec = max(time.perf_counter() - start_time, 1e-6)
    camera.stop()
    detector.close()

    avg_inference_latency = (
        sum(inference_latencies) / len(inference_latencies)
        if inference_latencies else 0.0
    )
    avg_pipeline_latency = (
        sum(camera_to_landmark_latencies) / len(camera_to_landmark_latencies)
        if camera_to_landmark_latencies else 0.0
    )

    print("\n" + "=" * 60)
    print("FINAL DIAGNOSTIC REPORT:")
    print(f"Camera frames: {camera_frames_count}")
    print(f"Detector available: {detector.available}")
    print(f"Detector error: {detector.error}")
    print(f"Frames submitted: {frames_submitted}")
    print(f"Inference results returned: {results_received}")
    print(f"Camera FPS: {camera_frames_count / elapsed_sec:.2f}")
    print(f"Inference FPS: {frames_submitted / elapsed_sec:.2f}")
    print(f"Frames with hand: {frames_with_hand}")
    print(f"Average detector latency: {avg_inference_latency:.2f} ms")
    print(f"Average camera-to-landmark latency: {avg_pipeline_latency:.2f} ms")
    print("=" * 60)


if __name__ == "__main__":
    dur = 10.0
    width, height = 640, 360
    if len(sys.argv) > 1:
        try:
            dur = float(sys.argv[1])
        except ValueError:
            pass
    if len(sys.argv) > 3:
        try:
            width, height = int(sys.argv[2]), int(sys.argv[3])
        except ValueError:
            pass
    run_diagnostics(dur, width, height)
