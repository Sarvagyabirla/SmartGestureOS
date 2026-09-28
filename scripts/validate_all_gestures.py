"""Comprehensive live physical gesture validation suite.

Runs the real production pipeline (Camera -> GestureDetector -> GestureClassifier)
with all OS action execution strictly suppressed.

Auto-grades each gesture based on sustained recognition (350-500ms continuous hold),
tracking confusions, latency (median & p95), and confidence without requiring
manual PASS/FAIL clicks.
"""

import argparse
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sys
import time
from typing import Dict, List, Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from config import SETTINGS
from src.camera import Camera
from src.gesture_detector import GestureDetector
from src.gesture_classifier import GestureClassifier
from src.models import GestureResult, Landmark

logger = logging.getLogger("GestureValidator")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

ALL_GESTURES = (
    ("Pointing", "Extend index finger straight; fold middle, ring, pinky."),
    ("Pinch", "Touch tips of thumb and index finger together."),
    ("Two Fingers", "Extend index and middle fingers straight up, close together."),
    ("Three Fingers", "Extend index, middle, and ring fingers together; pinky folded."),
    ("Four Fingers", "Extend index, middle, ring, and pinky fingers; thumb folded."),
    ("Open Palm", "Open entire hand flat with all five fingers spread."),
    ("Closed Fist", "Curl all four fingers into a tight fist."),
    ("Thumb Up", "Fold four fingers into a fist; point thumb distinctly upward."),
    ("Thumb Down", "Fold four fingers into a fist; point thumb distinctly downward."),
    ("Victory", "Extend index and middle fingers in a clear 'V' shape (spread apart)."),
    ("Rock On", "Extend thumb, index, and pinky; fold middle and ring fingers."),
    ("Call Me", "Extend thumb and pinky outwards; fold index, middle, ring fingers."),
    ("Middle Finger", "Extend only the middle finger; fold index, ring, pinky fingers."),
    ("Crossed Fingers", "Extend index and middle fingers and cross index over middle."),
)


class GestureValidatorApp:
    """Validator adapter for backward compatibility and manual report recording."""
    def __init__(self, output_path=None, headless=True, camera_index=None):
        self.output_path = output_path
        self.headless = headless
        self.attempts = {name: [] for name, _ in ALL_GESTURES}
        self.live_validator = LiveGestureValidator(
            camera_index=camera_index,
            output_path=output_path,
            use_mock=headless,
        )

    def record_attempt(self, gesture_name, passed, detected_as=None, confidence=0.0, latency_ms=0.0):
        if gesture_name not in self.attempts:
            self.attempts[gesture_name] = []
        self.attempts[gesture_name].append({
            "passed": bool(passed),
            "detected_as": detected_as or "Unknown",
            "confidence": float(confidence),
            "latency_ms": float(latency_ms),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def save_report(self):
        summary = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "gestures": {}
        }
        total_attempts = 0
        total_passes = 0
        for name, records in self.attempts.items():
            passes = sum(1 for r in records if r["passed"])
            total = len(records)
            rate = (passes / total * 100.0) if total > 0 else 0.0
            total_attempts += total
            total_passes += passes
            summary["gestures"][name] = {
                "attempts": total,
                "passes": passes,
                "accuracy_percent": round(rate, 1),
                "history": records
            }
        summary["total_attempts"] = total_attempts
        summary["total_passes"] = total_passes
        summary["overall_accuracy_percent"] = round((total_passes / total_attempts * 100.0) if total_attempts > 0 else 0.0, 1)

        if self.output_path:
            with open(self.output_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2)
        return summary


class LiveGestureValidator:
    def __init__(self, camera_index=None, attempts_per_gesture=5, hold_required_ms=350,
                 attempt_timeout_s=4.0, output_path=None, use_mock=False):
        self.camera_index = camera_index if camera_index is not None else SETTINGS["camera"]["index"]
        self.attempts_per_gesture = attempts_per_gesture
        self.hold_required_ms = hold_required_ms
        self.attempt_timeout_s = attempt_timeout_s
        self.use_mock = use_mock

        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        logs_dir = REPO_ROOT / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        self.output_path = output_path or (logs_dir / f"gesture-validation-{timestamp_str}.json")

        self.classifier = GestureClassifier()
        self.detector = None
        self.camera = None

    def initialize_hardware(self):
        if self.use_mock:
            logger.info("Running in mock mode — skipping physical webcam and detector.")
            return True

        logger.info(f"Initializing camera on index {self.camera_index}...")
        self.camera = Camera(
            index=self.camera_index,
            width=SETTINGS["camera"]["width"],
            height=SETTINGS["camera"]["height"],
            fps=SETTINGS["camera"]["fps"],
        )
        self.camera.start()

        # Wait briefly for camera to connect
        t0 = time.time()
        while time.time() - t0 < 3.0:
            if self.camera.is_connected:
                break
            time.sleep(0.1)

        if not self.camera.is_connected:
            logger.warning("Camera did not connect within timeout.")

        logger.info("Initializing MediaPipe GestureDetector...")
        self.detector = GestureDetector()
        if not self.detector.detector_available:
            logger.error(f"Detector failed to initialize: {self.detector.detector_error}")
            return False

        logger.info("Hardware pipeline successfully initialized.")
        return True

    def close(self):
        if self.camera is not None:
            self.camera.stop()
            self.camera = None
        if self.detector is not None:
            self.detector.close()
            self.detector = None

    def run_validation(self, on_attempt_start=None, on_frame_update=None) -> Dict[str, Any]:
        """Runs auto-graded validation across all gestures."""
        results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "attempts_per_gesture": self.attempts_per_gesture,
            "hold_required_ms": self.hold_required_ms,
            "gestures": {},
            "total_attempts": 0,
            "total_successful": 0,
            "overall_recognition_rate": 0.0,
        }

        for gesture_name, description in ALL_GESTURES:
            logger.info(f"\n==========================================")
            logger.info(f"TARGET: {gesture_name}")
            logger.info(f"Instructions: {description}")
            logger.info(f"==========================================")

            gesture_attempts = []
            raw_confusions = {}
            stable_confusions = {}
            latencies_ms = []
            confidences = []

            for attempt_idx in range(1, self.attempts_per_gesture + 1):
                if on_attempt_start:
                    on_attempt_start(gesture_name, attempt_idx, self.attempts_per_gesture, description)

                logger.info(f"--- Attempt {attempt_idx}/{self.attempts_per_gesture} for {gesture_name} ---")
                attempt_res = self._run_single_attempt(
                    target_gesture=gesture_name,
                    on_frame_update=on_frame_update,
                )

                gesture_attempts.append(attempt_res)
                if attempt_res["passed"]:
                    latencies_ms.append(attempt_res["recognition_ms"])
                    confidences.append(attempt_res["final_confidence"])

                for conf, count in attempt_res["raw_confusions"].items():
                    raw_confusions[conf] = raw_confusions.get(conf, 0) + count
                for conf, count in attempt_res["stable_confusions"].items():
                    stable_confusions[conf] = stable_confusions.get(conf, 0) + count

                # Small settle pause between attempts
                time.sleep(0.4)

            successful = sum(1 for a in gesture_attempts if a["passed"])
            rec_rate = (successful / len(gesture_attempts) * 100.0) if gesture_attempts else 0.0

            sorted_latencies = sorted(latencies_ms)
            median_ms = sorted_latencies[len(sorted_latencies) // 2] if sorted_latencies else 0.0
            p95_idx = int(len(sorted_latencies) * 0.95)
            p95_ms = sorted_latencies[p95_idx] if sorted_latencies else 0.0
            avg_conf = (sum(confidences) / len(confidences)) if confidences else 0.0

            results["gestures"][gesture_name] = {
                "attempts": len(gesture_attempts),
                "successful_attempts": successful,
                "recognition_rate": round(rec_rate, 1),
                "median_recognition_ms": round(median_ms, 1),
                "p95_recognition_ms": round(p95_ms, 1),
                "average_confidence": round(avg_conf, 1),
                "raw_confusion_counts": raw_confusions,
                "stable_confusion_counts": stable_confusions,
                "attempt_details": gesture_attempts,
            }

            results["total_attempts"] += len(gesture_attempts)
            results["total_successful"] += successful

        total = results["total_attempts"]
        success = results["total_successful"]
        results["overall_recognition_rate"] = round((success / total * 100.0) if total > 0 else 0.0, 1)

        # Write to JSON
        with open(self.output_path, "w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=2)

        logger.info(f"\n[DONE] Validation finished. Overall Recognition Rate: {results['overall_recognition_rate']}%")
        logger.info(f"Report saved to: {self.output_path}")
        return results

    def _run_single_attempt(self, target_gesture: str, on_frame_update=None) -> Dict[str, Any]:
        """Auto-grades one gesture attempt without manual intervention."""
        self.classifier.reset()
        attempt_start = time.perf_counter()
        target_hold_start = None
        passed = False
        recognition_ms = 0.0
        final_confidence = 0.0
        raw_confusions = {}
        stable_confusions = {}

        if self.use_mock:
            # Mock mode for testing validator logic
            time.sleep(0.1)
            return {
                "passed": True,
                "recognition_ms": 120.0,
                "final_confidence": 92.0,
                "raw_confusions": {},
                "stable_confusions": {},
            }

        last_frame_id = -1
        while (time.perf_counter() - attempt_start) < self.attempt_timeout_s:
            now = time.perf_counter()
            frame, frame_id, captured_at = self.camera.read_with_timestamp()
            if frame is None or frame_id == last_frame_id:
                time.sleep(0.01)
                continue
            last_frame_id = frame_id

            # Process frame through MediaPipe
            results = self.detector.process_frame(frame, int(now * 1000))
            hands = self.detector.get_all_hands_data(results, frame.shape) if results else []

            raw_gesture = "None"
            stable_gesture = "None"
            confidence = 0.0

            if hands:
                res = self.classifier.classify(hands)
                raw_gesture = res.raw_gesture
                stable_gesture = res.gesture
                confidence = float(res.confidence)

            # Record confusions
            if raw_gesture != target_gesture and raw_gesture not in ("None", "Unknown"):
                raw_confusions[raw_gesture] = raw_confusions.get(raw_gesture, 0) + 1
            if stable_gesture != target_gesture and stable_gesture not in ("None", "Unknown"):
                stable_confusions[stable_gesture] = stable_confusions.get(stable_gesture, 0) + 1

            # Check for sustained target gesture
            is_target = (stable_gesture == target_gesture) or (raw_gesture == target_gesture and confidence >= 60)
            if is_target:
                if target_hold_start is None:
                    target_hold_start = now
                held_ms = (now - target_hold_start) * 1000.0
                if held_ms >= self.hold_required_ms:
                    passed = True
                    recognition_ms = (target_hold_start - attempt_start) * 1000.0
                    final_confidence = confidence
                    break
            else:
                target_hold_start = None

            if on_frame_update:
                on_frame_update({
                    "target": target_gesture,
                    "hands_detected": len(hands) > 0,
                    "raw_gesture": raw_gesture,
                    "stable_gesture": stable_gesture,
                    "confidence": confidence,
                    "held_ms": (now - target_hold_start) * 1000.0 if target_hold_start else 0.0,
                    "required_ms": self.hold_required_ms,
                    "elapsed_s": now - attempt_start,
                })

            time.sleep(0.01)

        return {
            "passed": passed,
            "recognition_ms": round(recognition_ms, 1),
            "final_confidence": round(final_confidence, 1),
            "raw_confusions": raw_confusions,
            "stable_confusions": stable_confusions,
        }


def run_cli_validation(attempts=5, output=None, mock=False):
    validator = LiveGestureValidator(
        attempts_per_gesture=attempts,
        output_path=output,
        use_mock=mock
    )
    if not validator.initialize_hardware():
        logger.error("Failed to initialize hardware pipeline.")
        sys.exit(1)

    try:
        results = validator.run_validation()
        print("\n" + "=" * 50)
        print(f"VALIDATION SUMMARY ({results['total_successful']}/{results['total_attempts']} passed - {results['overall_recognition_rate']}%)")
        print("=" * 50)
        for g_name, g_data in results["gestures"].items():
            print(f"  {g_name:16}: {g_data['successful_attempts']}/{g_data['attempts']} ({g_data['recognition_rate']}%) | Median: {g_data['median_recognition_ms']} ms | Conf: {g_data['average_confidence']}%")
        print("=" * 50)
        return results
    finally:
        validator.close()


def main():
    parser = argparse.ArgumentParser(description="Live Physical Gesture Validation Suite for SmartGestureOS")
    parser.add_argument("--attempts", "-a", type=int, default=5, help="Number of attempts per gesture (default 5)")
    parser.add_argument("--output", "-o", type=Path, default=None, help="Custom output JSON path")
    parser.add_argument("--mock", action="store_true", help="Run with mock frames for automated pipeline testing")
    args = parser.parse_args()

    run_cli_validation(attempts=args.attempts, output=args.output, mock=args.mock)


if __name__ == "__main__":
    main()
