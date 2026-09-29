"""
Focused tests for the FAST POINTER PATH primitives in src/pointer_path.py.

Every clock is injected. Nothing here sleeps or reads wall-clock time, so
these tests are deterministic and cannot flake under CI load.

Coverage contract for this module (PointerIntent / RateMeter / LatencyMeter
/ PointerMetrics) plus a structural guard so the class-ownership regression
that shipped in the last commit cannot silently return.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import pointer_path
from src.pointer_path import (
    CONFLICTING_RAW,
    GRACE_MS_MAX,
    GRACE_MS_MIN,
    LatencyMeter,
    POINTING,
    PointerIntent,
    PointerMetrics,
    RateMeter,
)

UNKNOWN = "Unknown"


class FakeClock:
    """Deterministic monotonic clock."""

    def __init__(self, start=0.0):
        self.now = float(start)

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += float(seconds)
        return self.now


@pytest.fixture
def clock():
    return FakeClock()


def enter_pointing(intent, clock, samples=3, stable="None"):
    """Drive the intent to the active state and return the last sample time."""
    for _ in range(samples):
        clock.advance(0.033)
        intent.update(POINTING, stable, now=clock.now)
    return clock.now


# ── PointerIntent: entry ────────────────────────────────────────────────────

def test_entry_requires_configured_number_of_samples(clock):
    intent = PointerIntent(enter_samples=3, grace_ms=100, clock=clock)

    for expected_samples in (1, 2):
        clock.advance(0.033)
        assert intent.update(POINTING, "None", now=clock.now) is False
        assert intent.state == "entering"
        assert intent.active is False

    clock.advance(0.033)
    assert intent.update(POINTING, "None", now=clock.now) is True
    assert intent.state == "active"


def test_stable_pointing_accelerates_entry_beyond_sample_count(clock):
    intent = PointerIntent(enter_samples=5, grace_ms=100, clock=clock)

    clock.advance(0.033)
    assert intent.update(POINTING, POINTING, now=clock.now) is True
    assert intent.state == "active"


def test_fresh_pointing_keeps_pointer_active(clock):
    intent = PointerIntent(enter_samples=1, grace_ms=100, clock=clock)
    enter_pointing(intent, clock, samples=1)

    for _ in range(30):
        clock.advance(0.033)
        assert intent.update(POINTING, POINTING, now=clock.now) is True
        assert intent.state == "active"
    assert intent.active is True


# ── PointerIntent: bounded grace ────────────────────────────────────────────

def test_single_unknown_keeps_pointer_alive_in_grace(clock):
    intent = PointerIntent(enter_samples=1, grace_ms=100, clock=clock)
    enter_pointing(intent, clock, samples=1)

    clock.advance(0.02)  # one dropped inference, well inside the window
    assert intent.update(UNKNOWN, POINTING, now=clock.now) is True
    assert intent.state == "grace"
    assert intent.active is True


def test_grace_expires_after_bounded_timeout(clock):
    intent = PointerIntent(enter_samples=1, grace_ms=100, clock=clock)
    enter_pointing(intent, clock, samples=1)

    clock.advance((GRACE_MS_MAX / 1000.0) + 0.01)
    assert intent.update(UNKNOWN, POINTING, now=clock.now) is False
    assert intent.state == "inactive"
    assert intent.active is False


def test_grace_does_not_extend_itself_while_unknowing(clock):
    """An unknown must not keep refreshing the grace deadline forever."""
    intent = PointerIntent(enter_samples=1, grace_ms=100, clock=clock)
    enter_pointing(intent, clock, samples=1)

    clock.advance(0.06)
    assert intent.update(UNKNOWN, POINTING, now=clock.now) is True
    clock.advance(0.06)  # 120 ms total since the last real Pointing
    assert intent.update(UNKNOWN, POINTING, now=clock.now) is False


def test_conflicting_stable_pose_ends_grace_early(clock):
    intent = PointerIntent(enter_samples=1, grace_ms=100, clock=clock)
    enter_pointing(intent, clock, samples=1)

    clock.advance(0.02)
    assert intent.update(UNKNOWN, "Pinch", now=clock.now) is False
    assert intent.active is False


def test_grace_window_is_clamped_to_bounded_range():
    assert GRACE_MS_MIN <= 100.0 <= GRACE_MS_MAX
    assert PointerIntent(grace_ms=0).grace_ms == GRACE_MS_MIN
    assert PointerIntent(grace_ms=99_000).grace_ms == GRACE_MS_MAX


# ── PointerIntent: immediate exits ──────────────────────────────────────────

@pytest.mark.parametrize("conflict", sorted(CONFLICTING_RAW))
def test_conflicting_gesture_exits_pointer_immediately(conflict, clock):
    intent = PointerIntent(enter_samples=1, grace_ms=100, clock=clock)
    enter_pointing(intent, clock, samples=1)
    assert intent.active is True

    clock.advance(0.033)
    assert intent.update(conflict, conflict, now=clock.now) is False
    assert intent.state == "inactive"
    assert intent.active is False


@pytest.mark.parametrize(
    "conflict",
    ["Pinch", "Two Fingers", "Three Fingers", "Four Fingers", "Call Me"],
)
def test_named_conflicts_exit_pointer_immediately(conflict, clock):
    """Spelled out separately: these are the presentation-critical gestures."""
    intent = PointerIntent(enter_samples=1, grace_ms=100, clock=clock)
    enter_pointing(intent, clock, samples=1)

    clock.advance(0.033)
    assert intent.update(conflict, conflict, now=clock.now) is False
    assert intent.active is False


def test_custom_trained_gesture_also_exits_pointer(clock):
    """Any unrecognised label is treated as conflicting by default."""
    intent = PointerIntent(enter_samples=1, grace_ms=100, clock=clock)
    enter_pointing(intent, clock, samples=1)

    clock.advance(0.033)
    assert intent.update("My Custom Gesture", "My Custom Gesture", now=clock.now) is False
    assert intent.active is False


# ── PointerIntent: reset ────────────────────────────────────────────────────

def test_reset_clears_all_intent_state(clock):
    intent = PointerIntent(enter_samples=1, grace_ms=100, clock=clock)
    enter_pointing(intent, clock, samples=4)
    assert intent.active is True

    intent.reset()

    assert intent.active is False
    assert intent.state == "inactive"
    assert intent._pointing_samples == 0
    assert intent._last_pointing_at == 0.0


def test_no_stale_state_survives_reset(clock):
    """After reset, a neutral sample must not resurrect the pointer."""
    intent = PointerIntent(enter_samples=1, grace_ms=100, clock=clock)
    enter_pointing(intent, clock, samples=4)
    intent.reset()

    clock.advance(0.01)
    assert intent.update(UNKNOWN, POINTING, now=clock.now) is False
    assert intent.active is False

    # Entry hysteresis restarts from scratch, not from the pre-reset count.
    clock.advance(0.033)
    assert intent.update(POINTING, "None", now=clock.now) is True  # enter_samples=1


def test_apply_settings_retunes_live_intent(clock):
    intent = PointerIntent(enter_samples=4, grace_ms=100, clock=clock)
    intent.apply_settings(enter_samples=1, grace_ms=90)
    assert intent.enter_samples == 1
    assert intent.grace_ms == 90.0

    clock.advance(0.033)
    assert intent.update(POINTING, "None", now=clock.now) is True


# ── RateMeter ───────────────────────────────────────────────────────────────

def test_rate_meter_reports_measured_cadence(clock):
    meter = RateMeter(window=10, clock=clock)
    for _ in range(6):
        meter.add(clock.advance(0.05))
    # 6 samples spanning 0.25 s -> 5 intervals
    assert meter.fps == pytest.approx(5 / 0.25)
    assert meter.total == 6


def test_rate_meter_is_zero_without_enough_samples(clock):
    meter = RateMeter(window=10, clock=clock)
    assert meter.fps == 0.0
    meter.add(clock.advance(0.1))
    assert meter.fps == 0.0  # a single sample has no interval
    assert meter.age == 0.0


def test_rate_meter_ignores_non_monotonic_samples(clock):
    meter = RateMeter(window=10, clock=clock)
    meter.add(5.0)
    meter.add(5.0)
    assert meter.fps == 0.0


def test_rate_meter_reset_clears_samples(clock):
    meter = RateMeter(window=10, clock=clock)
    for _ in range(4):
        meter.add(clock.advance(0.1))
    assert meter.total == 4

    meter.reset()
    assert meter.total == 0
    assert meter.fps == 0.0


# ── LatencyMeter ────────────────────────────────────────────────────────────

def test_latency_meter_mean():
    meter = LatencyMeter(window=10)
    for value in (10.0, 20.0, 30.0):
        meter.add_ms(value)
    assert meter.mean_ms == pytest.approx(20.0)
    assert meter.count == 3


def test_latency_meter_median_odd_sample_count():
    meter = LatencyMeter(window=10)
    for value in (30.0, 10.0, 20.0):
        meter.add_ms(value)
    assert meter.median_ms == pytest.approx(20.0)


def test_latency_meter_median_even_sample_count():
    meter = LatencyMeter(window=10)
    for value in (10.0, 20.0, 30.0, 40.0):
        meter.add_ms(value)
    assert meter.median_ms == pytest.approx(25.0)


def test_latency_meter_add_seconds_converts_to_ms():
    meter = LatencyMeter(window=10)
    meter.add_seconds(0.016)
    meter.add_seconds(0.034)
    assert meter.median_ms == pytest.approx(25.0)


def test_latency_meter_reset():
    meter = LatencyMeter(window=10)
    for value in (10.0, 20.0, 30.0):
        meter.add_ms(value)

    meter.reset()
    assert meter.count == 0
    assert meter.mean_ms == 0.0
    assert meter.median_ms == 0.0


# ── PointerMetrics ──────────────────────────────────────────────────────────

def test_pointer_metrics_counts_actual_cursor_updates(clock):
    metrics = PointerMetrics(window=30, clock=clock)
    for _ in range(4):
        clock.advance(0.033)
        metrics.record_update()

    # 4 samples spanning 3 x 33 ms -> 3 intervals at 30.3 Hz
    assert metrics.samples == 4
    assert metrics.pointer_fps == pytest.approx(3 / (3 * 0.033), rel=1e-6)
    assert metrics.updates.total == 4


def test_pointer_metrics_reports_zero_rate_for_a_stalled_clock(clock):
    """Samples sharing one timestamp have no interval and must not divide by 0."""
    metrics = PointerMetrics(window=30, clock=clock)
    for _ in range(4):
        metrics.record_update()
    assert metrics.samples == 4
    assert metrics.pointer_fps == 0.0


def test_pointer_metrics_records_suppression_separately(clock):
    metrics = PointerMetrics(window=30, clock=clock)
    metrics.record_update()
    metrics.record_update()
    metrics.record_suppressed()
    metrics.record_suppressed()
    metrics.record_suppressed()

    assert metrics.samples == 2, "suppressed samples must not count as updates"
    assert metrics.suppressed == 3
    assert metrics.as_dict()["pointer_suppressed"] == 3


def test_pointer_metrics_records_capture_to_pointer_latency(clock):
    metrics = PointerMetrics(window=30, clock=clock)
    for _ in range(3):
        capture_at = clock.now
        clock.advance(0.040)
        metrics.record_update(capture_at=capture_at)

    # Capture timestamp -> cursor update is 40 ms for every sample.
    assert metrics.capture_to_pointer.median_ms == pytest.approx(40.0)
    assert metrics.as_dict()["capture_to_pointer_ms"] == pytest.approx(40.0)


def test_pointer_metrics_ignores_negative_capture_latency(clock):
    """A clock skew must never produce a negative user-visible latency."""
    metrics = PointerMetrics(window=30, clock=clock)
    clock.advance(1.0)
    metrics.record_update(capture_at=clock.now + 5.0)
    assert metrics.capture_to_pointer.median_ms == 0.0


def test_pointer_metrics_records_inference_latency(clock):
    metrics = PointerMetrics(window=30, clock=clock)
    for value in (18.0, 20.0, 22.0):
        metrics.inference.add_ms(value)
    report = metrics.as_dict()
    assert report["inference_median_ms"] == pytest.approx(20.0)
    assert report["inference_mean_ms"] == pytest.approx(20.0)


def test_pointer_metrics_resets_safely(clock):
    metrics = PointerMetrics(window=30, clock=clock)
    for _ in range(3):
        metrics.record_update(capture_at=clock.now)
        clock.advance(0.033)
    metrics.record_suppressed()

    metrics.reset()

    assert metrics.samples == 0
    assert metrics.suppressed == 0
    assert metrics.updates.total == 0
    assert metrics.pointer_fps == 0.0
    assert metrics.capture_to_pointer.count == 0


def test_pointer_metrics_as_dict_exposes_every_reported_field(clock):
    report = PointerMetrics(window=10, clock=clock).as_dict()
    assert set(report) == {
        "pointer_fps",
        "pointer_samples",
        "pointer_suppressed",
        "capture_to_pointer_ms",
        "capture_to_pointer_p95_ms",
        "inference_median_ms",
        "inference_mean_ms",
    }


# ── structural guard ────────────────────────────────────────────────────────
# The previous commit shipped this module with methods displaced into the
# wrong class. These assertions make that class of regression fail loudly
# instead of becoming unreachable dead code.

def test_latency_statistics_belong_to_latency_meter():
    assert isinstance(LatencyMeter.__dict__["mean_ms"], property)
    assert isinstance(LatencyMeter.__dict__["median_ms"], property)
    # They must read LatencyMeter's own buffer, not a neighbour's.
    assert "_samples" in LatencyMeter.__dict__["mean_ms"].fget.__code__.co_names
    assert "_samples" in LatencyMeter.__dict__["median_ms"].fget.__code__.co_names


def test_latency_statistics_are_not_leaked_into_pointer_metrics():
    assert "mean_ms" not in PointerMetrics.__dict__
    assert "median_ms" not in PointerMetrics.__dict__


def test_pointer_intent_exposes_state_and_reset():
    assert isinstance(PointerIntent.__dict__["state"], property)
    assert "_state" in PointerIntent.__dict__["state"].fget.__code__.co_names
    assert callable(PointerIntent.__dict__["reset"])


def test_module_constants_are_defined():
    assert POINTING == "Pointing"
    assert UNKNOWN in pointer_path.NEUTRAL_RAW
    assert "None" in pointer_path.NEUTRAL_RAW
    assert POINTING not in CONFLICTING_RAW
    assert UNKNOWN not in CONFLICTING_RAW
    assert len(CONFLICTING_RAW) >= 13

    meter = LatencyMeter(window=10)
    for value in (10.0, 20.0, 30.0):
        meter.add_ms(value)

    meter.reset()
    assert meter.count == 0
    assert meter.mean_ms == 0.0
    assert meter.median_ms == 0.0

    assert GRACE_MS_MIN <= 100.0 <= GRACE_MS_MAX
    assert PointerIntent(grace_ms=0).grace_ms == GRACE_MS_MIN
    assert PointerIntent(grace_ms=99_000).grace_ms == GRACE_MS_MAX
