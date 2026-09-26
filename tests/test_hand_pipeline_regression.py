"""
Regression tests for Hand Landmark Pipeline (§Phase I):
- detector available and telemetry
- strictly increasing timestamps
- stale reset does not reject future results
- callback queue consumption
- hand result survives pipeline
"""

import time
import queue
import numpy as np
import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

from src.gesture_detector import GestureDetector
from src.models import Landmark


@dataclass
class MockNormalizedLandmark:
    x: float
    y: float
    z: float


@dataclass
class MockHandLandmarkerResult:
    hand_landmarks: list
    handedness: list
    hand_world_landmarks: list = None


class TestHandPipelineRegression:
    def test_detector_available_and_telemetry(self):
        """Phase I: Verify detector initialization attributes and telemetry counters."""
        with patch("src.gesture_detector.vision.HandLandmarker.create_from_options") as mock_create:
            mock_create.return_value = MagicMock()
            det = GestureDetector()

        assert det.available is True
        assert det.error is None
        assert det.frames_submitted == 0
        assert det.callbacks_received == 0
        assert det.hands_detected_count == 0
        assert det.last_submitted_timestamp_ms == -1

    def test_detector_increasing_timestamps(self):
        """Phase I: Verify detect_async enforces strictly increasing timestamps."""
        with patch("src.gesture_detector.vision.HandLandmarker.create_from_options") as mock_create:
            mock_inst = MagicMock()
            mock_create.return_value = mock_inst
            det = GestureDetector()

        dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)

        # Call with identical or non-increasing timestamps
        det.detect_async(dummy_img, 1000)
        det.detect_async(dummy_img, 1000)
        det.detect_async(dummy_img, 999)

        # The internal timestamps must be strictly increasing
        calls = mock_inst.detect_for_video.call_args_list
        assert len(calls) == 3
        ts0 = calls[0][0][1]
        ts1 = calls[1][0][1]
        ts2 = calls[2][0][1]

        assert ts0 == 1000
        assert ts1 == 1001
        assert ts2 == 1002
        assert det.frames_submitted == 3

    def test_process_frame_rejects_invalid_image_without_raising(self):
        with patch("src.gesture_detector.vision.HandLandmarker.create_from_options") as mock_create:
            mock_create.return_value = MagicMock()
            det = GestureDetector()

        assert det.process_frame(None, 1000) is None
        assert det.frames_processed == 0

    def test_stale_reset_does_not_reject_future_results(self):
        """Phase I: Verify stale reset does not reject future valid callbacks."""
        with patch("src.gesture_detector.vision.HandLandmarker.create_from_options") as mock_create:
            mock_create.return_value = MagicMock()
            det = GestureDetector()

        # Simulate prior submitted frame at ts=5000
        det.last_submitted_timestamp_ms = 5000

        # Disconnect / reset happens: min_accepted_timestamp_ms is set
        min_accepted = det.last_submitted_timestamp_ms + 1
        det.clear_results()

        # An old in-flight callback arrives from ts=4900
        old_res = MockHandLandmarkerResult(hand_landmarks=[], handedness=[])
        det._result_callback(old_res, None, 4900)

        # Future callback arrives from ts=5001
        future_res = MockHandLandmarkerResult(hand_landmarks=[[MockNormalizedLandmark(0.5, 0.5, 0.0)] * 21], handedness=[])
        det._result_callback(future_res, None, 5001)

        # Main loop draining simulation
        accepted_results = []
        while not det.results_queue.empty():
            ts, res = det.results_queue.get_nowait()
            if ts >= min_accepted:
                accepted_results.append((ts, res))

        # Old result rejected, future result accepted
        assert len(accepted_results) == 1
        assert accepted_results[0][0] == 5001

    def test_callback_queue_consumption(self):
        """Phase I: Verify results_queue safely handles put/get without deadlock."""
        with patch("src.gesture_detector.vision.HandLandmarker.create_from_options") as mock_create:
            mock_create.return_value = MagicMock()
            det = GestureDetector()

        # Queue maxsize is 2. Push 3 items — oldest should be dropped without exception
        res1 = MockHandLandmarkerResult(hand_landmarks=[], handedness=[])
        res2 = MockHandLandmarkerResult(hand_landmarks=[], handedness=[])
        res3 = MockHandLandmarkerResult(hand_landmarks=[], handedness=[])

        det._result_callback(res1, None, 100)
        det._result_callback(res2, None, 200)
        det._result_callback(res3, None, 300)

        assert det.callbacks_received == 3
        # Should contain newest two: 200 and 300
        items = []
        while not det.results_queue.empty():
            items.append(det.results_queue.get_nowait())

        assert len(items) == 2
        assert items[0][0] == 200
        assert items[1][0] == 300

    def test_hand_result_survives_pipeline(self):
        """Phase I: Verify hand result is converted to 21 landmarks and drawn on display_frame."""
        with patch("src.gesture_detector.vision.HandLandmarker.create_from_options") as mock_create:
            mock_create.return_value = MagicMock()
            det = GestureDetector()

        # 21 mock landmarks
        raw_lms = [MockNormalizedLandmark(x=i * 0.04, y=i * 0.04, z=0.0) for i in range(21)]
        res = MockHandLandmarkerResult(
            hand_landmarks=[raw_lms],
            handedness=[[MagicMock(score=0.95)]],
        )

        hands_data = det.get_all_hands_data(res, (720, 1280, 3))
        assert len(hands_data) == 1
        assert len(hands_data[0]["landmarks"]) == 21
        assert hands_data[0]["score"] == 95

        # Test landmark drawing onto frame
        test_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        det.draw_landmarks(test_frame, hands_data[0]["landmarks"])

        # Pixels must be modified (colored lines and circles drawn)
        assert test_frame.sum() > 0

    def test_detected_hand_landmarks_cycle_through_rgb_colors(self):
        with patch("src.gesture_detector.vision.HandLandmarker.create_from_options") as mock_create:
            mock_create.return_value = MagicMock()
            det = GestureDetector()

        landmarks = [Landmark(id=i, pixel_x=32, pixel_y=32, x=0.5, y=0.5, z=0.0) for i in range(21)]
        red_frame = np.zeros((64, 64, 3), dtype=np.uint8)
        green_frame = np.zeros_like(red_frame)

        det.draw_landmarks(red_frame, landmarks, color_phase=0.0)
        det.draw_landmarks(green_frame, landmarks, color_phase=1.0 / 3.0)

        red_ring = red_frame[32, 36]
        green_ring = green_frame[32, 36]
        assert tuple(red_ring) == (0, 0, 255)
        assert tuple(green_ring) == (0, 255, 0)
