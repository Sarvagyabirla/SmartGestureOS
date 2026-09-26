"""Regression checks for the production synchronous VIDEO hand pipeline."""

from dataclasses import dataclass
from threading import Event, Thread
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.gesture_detector import GestureDetector, vision
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
    hand_world_landmarks: list | None = None


@pytest.fixture
def detector_and_backend():
    backend = MagicMock()
    backend.detect_for_video.return_value = MockHandLandmarkerResult([], [])
    with patch(
        "src.gesture_detector.vision.HandLandmarker.create_from_options",
        return_value=backend,
    ) as create:
        detector = GestureDetector()
    yield detector, backend, create
    detector.close()


class TestHandPipelineRegression:
    def test_detector_initializes_video_without_callback(self, detector_and_backend):
        detector, _, create = detector_and_backend
        options = create.call_args.args[0]

        assert options.running_mode == vision.RunningMode.VIDEO
        assert options.result_callback is None
        assert detector.available is True
        assert detector.error is None
        assert detector.frames_processed == 0
        assert detector.frames_with_hands == 0
        assert detector.last_submitted_timestamp_ms == -1

    def test_initialization_failure_is_reported_without_crashing(self):
        with patch(
            "src.gesture_detector.vision.HandLandmarker.create_from_options",
            side_effect=RuntimeError("model initialization failed"),
        ):
            detector = GestureDetector()

        assert detector.available is False
        assert "model initialization failed" in detector.error
        assert detector.process_frame(np.zeros((2, 2, 3), dtype=np.uint8), 1000) is None
        detector.close()

    def test_results_are_returned_directly_and_hand_loss_is_fresh(self, detector_and_backend):
        detector, backend, _ = detector_and_backend
        hand = [MockNormalizedLandmark(0.5, 0.5, 0.0) for _ in range(21)]
        with_hand = MockHandLandmarkerResult([hand], [])
        no_hand = MockHandLandmarkerResult([], [])
        backend.detect_for_video.side_effect = [with_hand, no_hand]
        frame = np.zeros((2, 2, 3), dtype=np.uint8)

        assert detector.process_frame(frame, 1000) is with_hand
        assert detector.process_frame(frame, 1001) is no_hand
        assert detector.get_all_hands_data(no_hand, frame.shape) == []
        assert detector.frames_processed == 2
        assert detector.frames_with_hands == 1
        assert detector.last_detection_timestamp == 1001

    def test_timestamps_increase_after_duplicates_reversal_and_rejected_input(
        self, detector_and_backend
    ):
        detector, backend, _ = detector_and_backend
        frame = np.zeros((2, 2, 3), dtype=np.uint8)

        detector.process_frame(frame, 1000)
        detector.process_frame(frame, 1000)
        detector.process_frame(frame, 999)
        assert detector.process_frame(None, 1005) is None
        detector.process_frame(frame, 1000)

        assert [call.args[1] for call in backend.detect_for_video.call_args_list] == [
            1000, 1001, 1002, 1006
        ]
        assert detector.frames_processed == 4

    def test_bgr_frame_is_converted_to_rgb_without_changing_input(self, detector_and_backend):
        detector, backend, _ = detector_and_backend
        bgr = np.array([[[10, 20, 30], [40, 50, 60]]], dtype=np.uint8)
        original = bgr.copy()

        detector.process_frame(bgr, 1000)

        image = backend.detect_for_video.call_args.args[0]
        np.testing.assert_array_equal(
            image.numpy_view(), np.array([[[30, 20, 10], [60, 50, 40]]], dtype=np.uint8)
        )
        np.testing.assert_array_equal(bgr, original)

    @pytest.mark.parametrize(
        "frame",
        [None, np.zeros((2, 2), dtype=np.uint8), np.zeros((2, 2, 4), dtype=np.uint8)],
        ids=["missing", "grayscale", "four_channels"],
    )
    def test_invalid_input_is_rejected_before_inference(self, detector_and_backend, frame):
        detector, backend, _ = detector_and_backend

        assert detector.process_frame(frame, 1000) is None
        backend.detect_for_video.assert_not_called()
        assert detector.frames_processed == 0

    def test_inference_failure_returns_none_then_next_frame_recovers(self, detector_and_backend):
        detector, backend, _ = detector_and_backend
        recovered_result = MockHandLandmarkerResult([], [])
        backend.detect_for_video.side_effect = [RuntimeError("transient failure"), recovered_result]
        frame = np.zeros((2, 2, 3), dtype=np.uint8)

        assert detector.process_frame(frame, 1000) is None
        assert detector.frames_processed == 0
        assert detector.process_frame(frame, 1000) is recovered_result
        assert detector.frames_processed == 1
        assert backend.detect_for_video.call_args.args[1] == 1001

    def test_close_is_idempotent_and_prevents_later_inference(self, detector_and_backend):
        detector, backend, _ = detector_and_backend

        detector.close()
        detector.close()

        assert detector.available is False
        backend.close.assert_called_once_with()
        assert detector.process_frame(np.zeros((2, 2, 3), dtype=np.uint8), 1000) is None
        backend.detect_for_video.assert_not_called()

    def test_close_waits_for_inflight_frame_before_releasing_backend(self, detector_and_backend):
        detector, backend, _ = detector_and_backend
        inference_started = Event()
        finish_inference = Event()
        close_requested = Event()
        backend_closed = Event()
        result = MockHandLandmarkerResult([], [])
        returned_results = []

        def infer(image, timestamp):
            inference_started.set()
            if not finish_inference.wait(timeout=2.0):
                raise TimeoutError("test did not release inference")
            return result

        def close():
            close_requested.set()
            detector.close()

        backend.detect_for_video.side_effect = infer
        backend.close.side_effect = backend_closed.set
        frame = np.zeros((2, 2, 3), dtype=np.uint8)
        worker = Thread(target=lambda: returned_results.append(detector.process_frame(frame, 1000)))
        closer = Thread(target=close)
        worker.start()
        try:
            assert inference_started.wait(timeout=1.0)
            closer.start()
            assert close_requested.wait(timeout=1.0)
            assert not backend_closed.wait(timeout=0.05)
        finally:
            finish_inference.set()
            worker.join(timeout=2.0)
            if closer.ident is not None:
                closer.join(timeout=2.0)

        assert not worker.is_alive()
        assert not closer.is_alive()
        assert returned_results == [result]
        assert backend_closed.is_set()
        assert detector.available is False

    def test_hand_result_survives_inference_conversion_and_drawing(self, detector_and_backend):
        detector, backend, _ = detector_and_backend
        raw = [MockNormalizedLandmark(i * 0.04, i * 0.04, -0.01) for i in range(21)]
        world = [MockNormalizedLandmark(i * 0.01, i * 0.02, -0.03) for i in range(21)]
        backend.detect_for_video.return_value = MockHandLandmarkerResult(
            hand_landmarks=[raw],
            handedness=[[MagicMock(score=0.95)]],
            hand_world_landmarks=[world],
        )
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)

        result = detector.process_frame(frame, 1000)
        hands = detector.get_all_hands_data(result, frame.shape)

        assert len(hands) == 1
        assert len(hands[0]["landmarks"]) == 21
        assert hands[0]["score"] == 95
        fingertip = hands[0]["landmarks"][20]
        assert fingertip.id == 20
        assert (fingertip.pixel_x, fingertip.pixel_y) == (1024, 576)
        assert (fingertip.world_x, fingertip.world_y, fingertip.world_z) == (0.2, 0.4, -0.03)

        detector.draw_landmarks(frame, hands[0]["landmarks"], color_phase=0.0)
        assert frame.sum() > 0

    @pytest.mark.parametrize(
        ("phase", "bgr"),
        [(0.0, (0, 0, 255)), (1.0 / 3.0, (0, 255, 0)), (2.0 / 3.0, (255, 0, 0))],
        ids=["red", "green", "blue"],
    )
    def test_detected_hand_landmarks_cycle_through_rgb_colors(
        self, detector_and_backend, phase, bgr
    ):
        detector, _, _ = detector_and_backend
        landmarks = [
            Landmark(id=i, pixel_x=32, pixel_y=32, x=0.5, y=0.5, z=0.0)
            for i in range(21)
        ]
        frame = np.zeros((64, 64, 3), dtype=np.uint8)

        detector.draw_landmarks(frame, landmarks, color_phase=phase)

        assert tuple(frame[32, 36]) == bgr
        assert tuple(frame[32, 32]) == (255, 255, 255)
