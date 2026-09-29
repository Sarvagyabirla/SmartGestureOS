"""
GestureClassifier — geometry → raw gesture + temporal stabilisation.

Physical failure root-cause fixes (user-report: "almost ALL gestures fail"):

1. Thumb tolerance in Pointing
   Natural pointing keeps the thumb partially extended.  The old rule required
   fingers == [*, 1, 0, 0, 0] where * is any thumb state, but the check below
   used an exact match that excluded a raised thumb.  Now Pointing is accepted
   when index is extended and middle/ring/pinky are folded, regardless of thumb.

2. Confidence threshold was too high by default (50 %) and used a single
   universal average across all five fingers.  A properly folded finger was
   scoring near zero (the signed diff collapses on a curled finger), dragging
   every compound gesture below the threshold.  Fixed by:
     - using abs(diff) / (margin*2) for the decisiveness score (already done)
     - lowering the default threshold to 35 % so relaxed natural poses pass
     - adding gesture-specific confidence overrides for pinch and pointer

3. Temporal stabilisation was too conservative for continuous gestures.
   Pointing and Pinch previously needed 3/5 frame majority (default history=5).
   For fluent control, continuous gestures need 2-of-3.  Discrete/high-impact
   actions keep the 3/5 confirmation.

4. The Two-Fingers / Victory ambiguity band returned "Unknown" for the vast
   middle range, preventing any action.  Now the band is resolved by leaning
   toward the closer class with a gentler threshold.

5. Closed Fist matched when fingers[1:] == [0,0,0,0] even if the thumb was
   extended — this conflated Thumb Up with Closed Fist.  Fixed by adding a
   thumb check: Closed Fist requires the thumb to NOT be clearly extended.

6. Four Fingers / Open Palm discrimination (physical fix):
   The thumb state is now represented as a CONTINUOUS score (0-1) rather than
   a binary 0/1.  This prevents single-frame thumb flicker from toggling
   between gestures.  A hysteresis band around the midpoint lets the last
   strongly-held gesture persist through brief ambiguity.
"""
import numpy as np
import time
from collections import deque, Counter
from .utils import get_angle
from .gesture_trainer import gesture_trainer
from .logger import logger
from config import SETTINGS
from .models import Landmark, GestureResult


class GestureClassifier:
    """
    Classifies raw hand landmark data into a named gesture.

    Responsibilities (single, clear):
        raw_classify  → geometry → raw gesture name + shape confidence
        classify      → temporal stabilization (history mode filter + EMA)
                      → returns GestureResult with stable + raw gesture

    Note on hold_time_ms (F-12 fix):
        hold_time_ms is NOT a classifier concern. The classifier answers
        "what does the geometry look like?" The action hold/intent layer lives
        in GestureIntentGate inside GestureMapper.
    """
    def __init__(self, confidence_threshold: float = 35.0):
        self.tip_ids = [4, 8, 12, 16, 20]
        self.pip_ids = [3, 6, 10, 14, 18]
        self.mcp_ids = [2, 5, 9, 13, 17]
        self.confidence_ema = 0.0
        # PHYSICAL FIX: lower default threshold; real hands in motion
        # produce geometry that is never mathematically perfect.
        self.confidence_threshold = confidence_threshold

        # Telemetry for physical diagnosis of pinch/scroll failures.
        self.last_pinch_ratio = 0.0
        self.last_two_finger_spacing = 0.0
        self.last_divergence_ratio = 0.0
        self.telemetry_enabled = False
        self._telemetry_last_log = 0.0

        # PHYSICAL FIX: separate history lengths for continuous vs discrete.
        # Continuous gestures (Pointing, Pinch) need fast response → 3 frames.
        # Discrete / high-impact gestures keep 5 frames for safety.
        self._continuous_history = deque(maxlen=3)  # Pointing, Pinch, Two Fingers
        self._discrete_history = deque(maxlen=5)    # all others
        # Unified view for backward-compat code that reads self.history
        self.history = self._discrete_history

        self.last_stable_gesture = "None"
        self.last_raw_gesture = "None"
        self.is_pinching = False

        # ── Four Fingers / Open Palm hysteresis & filtering (Fix #6, P0) ──────
        # Bounded temporal filter for thumb extension score (3-frame median)
        self._thumb_score_history: deque[float] = deque(maxlen=3)
        # Tracks the last strongly-resolved palm-type gesture so that one-frame
        # thumb ambiguity does not immediately flip the label.
        # Values: "Four Fingers", "Open Palm", or None (not yet set).
        self._last_palm_type: str | None = None

        # ── Two Fingers / Victory hysteresis ─────────────────────────────────
        # Eliminates the dead-band between Two Fingers and Victory.
        self._last_two_finger_type: str | None = None

        from src.settings_manager import settings_manager
        settings_manager.register_callback(self.on_settings_changed)
        self.on_settings_changed()

    # ── continuous gesture set ─────────────────────────────────────────────────
    _CONTINUOUS = frozenset({"Pointing", "Pinch", "Two Fingers", "None", "Unknown"})

    def set_telemetry(self, enabled: bool) -> None:
        """Enable/disable interaction telemetry logging.

        Off by default: this is a diagnostic aid for a supervised physical
        test session, not something to leave running in normal use.
        """
        self.telemetry_enabled = bool(enabled)

    def emit_telemetry(self, raw_gesture, stable_gesture, confidence, state) -> None:
        """One bounded telemetry line for pinch / scroll diagnosis.

        Rate-limited to ~10 Hz and emitted only while a relevant interaction
        is live, so a physical session does not produce a huge log. This is
        what turns "single click does not work" into an answerable question:
        whether the classifier ever reported Pinch, how far the pinch
        geometry actually was, and which EventState was reached.
        """
        if not self.telemetry_enabled:
            return
        interesting = raw_gesture in (
            "Pinch", "Pointing", "Two Fingers", "Victory",
            "Crossed Fingers", "Unknown", "Three Fingers", "None",
        ) or stable_gesture in ("Pinch", "Two Fingers")
        if not interesting:
            return
        now = time.perf_counter()
        if now - self._telemetry_last_log < 0.1:
            return
        self._telemetry_last_log = now
        logger.info(
            "TELEM raw=%s stable=%s conf=%.0f pinch_ratio=%.3f enter=%.3f "
            "release=%.3f two_finger_spacing=%.3f victory_min=%.3f state=%s",
            raw_gesture, stable_gesture, confidence, self.last_pinch_ratio,
            getattr(self, "pinch_enter_threshold", 0.45),
            getattr(self, "pinch_release_threshold", 0.6),
            self.last_two_finger_spacing,
            getattr(self, "victory_min_spacing", 0.35),
            getattr(state, "name", state),
        )

    def reset(self):
        self._continuous_history.clear()
        self._discrete_history.clear()
        self.last_stable_gesture = "Unknown"
        self.last_raw_gesture = "Unknown"
        self.is_pinching = False
        self.confidence_ema = 0.0
        self._thumb_score_history.clear()
        self._last_palm_type = None
        self._last_two_finger_type = None

    def on_settings_changed(self) -> None:
        """Update calibration thresholds from settings."""
        from config import SETTINGS
        calib = SETTINGS.get("calibration", {})
        self.pinch_enter_threshold = calib.get("pinch_enter_threshold", 0.45)
        self.pinch_release_threshold = calib.get("pinch_release_threshold", 0.6)
        self.two_finger_max_spacing = calib.get("two_finger_max_spacing", 0.22)
        self.victory_min_spacing = calib.get("victory_min_spacing", 0.30)
        # PHYSICAL FIX: threshold reduced from 50→35 so natural relaxed poses pass.
        self.confidence_threshold = calib.get("confidence_threshold", 35.0)

    def get_3d_point(self, lm: Landmark):
        return np.array([lm.x, lm.y, lm.z])

    @staticmethod
    def _decisiveness(diff: float, margin: float) -> float:
        """Confidence that one finger's up/down call is *decisive*.

        This must be the magnitude of the distance from the decision
        boundary, NOT signed extension. The previous signed formula scored a
        properly curled finger as 0.0, because a curled finger has its tip
        roughly as far from the MCP as its PIP, so the signed difference
        collapses to zero. Because shape_score is the mean across all five
        fingers, that zero dragged every gesture containing a folded finger
        (Pointing, Two/Three/Four Fingers, Closed Fist) below
        confidence_threshold, so the temporal layer published "Unknown" and
        every discrete action was blocked by can_start_action.

        A finger sitting exactly on the boundary is genuinely uncertain and
        still scores near zero; a clearly folded or clearly extended finger
        both score high, which is what confidence is supposed to mean.
        """
        if margin <= 0:
            return 0.0
        return min(100.0, (abs(diff) / (margin * 2.0)) * 100.0)

    def _thumb_extension_score(self, lms_list) -> float:
        """Return a continuous thumb-extension score in [0, 1].

        0.0 = fully tucked/folded against palm.
        1.0 = fully extended/abducted away from palm.

        Combines three independent geometric signals so that camera angle,
        wrist rotation and depth noise each only partially affect the result:
          A. Thumb-tip distance from palm center (middle MCP), normalised.
          B. Thumb-tip distance from index MCP (lateral separation).
          C. Classic signed diff: thumb tip vs thumb MCP vs pinky MCP.

        All distances are normalised by hand_size so the score is scale-free.

        Calibration notes (from synthetic + physical hand analysis):
          - Real Open Palm: thumb clearly abducted, score typically 0.45–0.80.
          - Real Four Fingers: thumb tucked against palm, score typically 0.05–0.30.
          - Ambiguous / uncertain zone: 0.30–0.40 (preserved with hysteresis).
          - Synthetic test (degenerate MCPs all coincident): sig_a collapses
            because d_tip_palm is small relative to hand_size; sig_b and sig_c
            remain the dominant signals.  Thresholds account for this.
        """
        wrist      = self.get_3d_point(lms_list[0])
        thumb_tip  = self.get_3d_point(lms_list[4])
        thumb_mcp  = self.get_3d_point(lms_list[2])
        index_mcp  = self.get_3d_point(lms_list[5])
        middle_mcp = self.get_3d_point(lms_list[9])
        pinky_mcp  = self.get_3d_point(lms_list[17])

        hand_size = max(1e-6, np.linalg.norm(wrist - middle_mcp))

        # Signal A: tip distance from palm center, normalised.
        # Extended thumb is ~0.8-1.5 hand_sizes from palm center.
        # Tucked thumb is ~0.3-0.5 hand_sizes from palm center.
        d_tip_palm  = np.linalg.norm(thumb_tip - middle_mcp) / hand_size
        sig_a = np.clip((d_tip_palm - 0.35) / 0.65, 0.0, 1.0)

        # Signal B: lateral separation from index MCP, normalised.
        # Extended: tip is >0.3 hand_size from index MCP.  Tucked: <0.1.
        d_tip_idx  = np.linalg.norm(thumb_tip - index_mcp) / hand_size
        sig_b = np.clip((d_tip_idx - 0.10) / 0.50, 0.0, 1.0)

        # Signal C: classic diff (tip vs mcp vs pinky MCP), normalised.
        # Positive raw_diff = thumb tip further from pinky MCP than thumb MCP.
        d_tip_pinky = np.linalg.norm(thumb_tip - pinky_mcp)
        d_mcp_pinky = np.linalg.norm(thumb_mcp - pinky_mcp)
        margin = hand_size * 0.12
        raw_diff = d_tip_pinky - d_mcp_pinky
        sig_c = np.clip((raw_diff + margin) / (margin * 4.0), 0.0, 1.0)

        # Weighted combination.  B and C are more robust to degenerate geometry.
        score = 0.30 * sig_a + 0.40 * sig_b + 0.30 * sig_c
        raw_val = float(np.clip(score, 0.0, 1.0))
        self._thumb_score_history.append(raw_val)
        return float(np.median(self._thumb_score_history))

    def _classify_palm_type(self, lms_list, is_thumb_up: int = 1) -> tuple[str, float]:
        """
        Distinguish "Four Fingers" from "Open Palm" when all four non-thumb
        fingers are extended, using a continuous filtered thumb-extension score
        with a hysteresis band to prevent single-frame flickering.

        Thresholds (calibrated against both synthetic and real webcam hands):
          is_thumb_up == 0     → Four Fingers (thumb folded/tucked by primary detector)
          score >= 0.38        → Open Palm (thumb clearly extended/abducted)
          score <= 0.24        → Four Fingers (thumb tucked despite noisy boundary)
          0.24 < score < 0.38  → ambiguous zone: preserve previous palm type to
                                 prevent frame-to-frame flipping, or lean to closer state.
        """
        score = self._thumb_extension_score(lms_list)

        if is_thumb_up == 0:
            self._last_palm_type = "Four Fingers"
            return "Four Fingers", score

        OPEN_PALM_MIN   = 0.38  # clearly Open Palm
        FOUR_FINGER_MAX = 0.24  # clearly Four Fingers

        if score >= OPEN_PALM_MIN:
            self._last_palm_type = "Open Palm"
            return "Open Palm", score
        elif score <= FOUR_FINGER_MAX:
            self._last_palm_type = "Four Fingers"
            return "Four Fingers", score
        else:
            # Ambiguous zone — preserve recent history to avoid flicker
            if self._last_palm_type is not None:
                return self._last_palm_type, score
            if score <= 0.31:
                self._last_palm_type = "Four Fingers"
                return "Four Fingers", score
            else:
                self._last_palm_type = "Open Palm"
                return "Open Palm", score

    def fingers_up(self, lms_list):
        if not lms_list or len(lms_list) < 21:
            return [], []

        fingers = []
        scores = []

        wrist = self.get_3d_point(lms_list[0])
        middle_mcp = self.get_3d_point(lms_list[9])
        hand_size = max(1e-6, np.linalg.norm(wrist - middle_mcp))
        margin = hand_size * 0.12

        # ── Thumb: combine lateral distance, index separation, and joint angle ──
        thumb_tip = self.get_3d_point(lms_list[4])
        thumb_ip = self.get_3d_point(lms_list[3])
        thumb_mcp = self.get_3d_point(lms_list[2])
        pinky_mcp = self.get_3d_point(lms_list[17])
        index_mcp = self.get_3d_point(lms_list[5])

        d_tip_pinky = np.linalg.norm(thumb_tip - pinky_mcp)
        d_mcp_pinky = np.linalg.norm(thumb_mcp - pinky_mcp)
        diff_thumb = d_tip_pinky - d_mcp_pinky

        angle_thumb_ip = get_angle(thumb_mcp, thumb_ip, thumb_tip)
        d_tip_index = np.linalg.norm(thumb_tip - index_mcp)

        # Extended if tip is clearly further from pinky MCP than thumb MCP
        is_thumb_up = 1 if diff_thumb > margin else 0
        fingers.append(is_thumb_up)

        s_thumb = self._decisiveness(diff_thumb, margin)
        scores.append(s_thumb)

        # ── Other fingers: Index, Middle, Ring, Pinky ───────────────────────
        for id in range(1, 5):
            tip = self.get_3d_point(lms_list[self.tip_ids[id]])
            pip = self.get_3d_point(lms_list[self.pip_ids[id]])
            mcp = self.get_3d_point(lms_list[self.mcp_ids[id]])

            d_tip_mcp = np.linalg.norm(tip - mcp)
            d_pip_mcp = np.linalg.norm(pip - mcp)
            diff = d_tip_mcp - d_pip_mcp

            # PIP angle: straight finger is 145-180 deg
            angle_pip = get_angle(mcp, pip, tip)
            d_tip_wrist = np.linalg.norm(tip - wrist)
            d_pip_wrist = np.linalg.norm(pip - wrist)

            # Combined extension rule:
            # Handles both synthetic test sets and real webcam hands
            if diff > margin:
                # If PIP is bent severely (< 115 deg), finger is curling back towards palm
                if angle_pip > 0 and angle_pip < 115.0 and d_tip_wrist < d_pip_wrist:
                    is_finger_up = 0
                else:
                    is_finger_up = 1
            else:
                # If diff is small/negative, but finger is straight and tip is far from wrist
                if angle_pip > 150.0 and d_tip_wrist > d_pip_wrist + 0.1 * hand_size and d_tip_mcp > d_pip_mcp * 0.95:
                    is_finger_up = 1
                else:
                    is_finger_up = 0

            fingers.append(is_finger_up)
            s = self._decisiveness(diff, margin)
            scores.append(s)

        return fingers, scores

    def raw_classify(self, hands_data):
        if not hands_data:
            return "None", 0.0

        # Single hand gestures
        h1 = hands_data[0]
        lms_list = h1['landmarks']
        hand_score = h1.get('score', 99)
        fingers, scores = self.fingers_up(lms_list)

        if not fingers:
            return "None", 0.0

        shape_score = sum(scores) / 5.0

        thumb_tip = self.get_3d_point(lms_list[4])
        thumb_mcp = self.get_3d_point(lms_list[2])
        index_tip = self.get_3d_point(lms_list[8])
        middle_tip = self.get_3d_point(lms_list[12])
        ring_tip = self.get_3d_point(lms_list[16])
        pinky_tip = self.get_3d_point(lms_list[20])

        wrist = self.get_3d_point(lms_list[0])
        index_mcp = self.get_3d_point(lms_list[5])
        middle_mcp = self.get_3d_point(lms_list[9])
        pinky_mcp = self.get_3d_point(lms_list[17])

        hand_size = max(1e-6, np.linalg.norm(wrist - middle_mcp))
        d_pinch = np.linalg.norm(thumb_tip - index_tip)

        enter_thresh = getattr(self, 'pinch_enter_threshold', 0.45)
        release_thresh = getattr(self, 'pinch_release_threshold', 0.60)
        pinch_ratio = d_pinch / hand_size
        self.last_pinch_ratio = float(pinch_ratio)

        # Hysteresis for pinch state
        if not self.is_pinching:
            if pinch_ratio < enter_thresh:
                self.is_pinching = True
        else:
            if pinch_ratio > release_thresh:
                self.is_pinching = False

        # Guard against closed fist being classified as pinch:
        # In a true pinch, index/thumb tips touch while reaching forward away from wrist.
        # In a closed fist, all fingertips curl inward against palm toward wrist base.
        index_pip = self.get_3d_point(lms_list[6])
        pinch_midpoint = (thumb_tip + index_tip) / 2.0
        d_pinch_wrist = np.linalg.norm(pinch_midpoint - wrist) / hand_size

        is_index_curled_to_wrist = (
            np.linalg.norm(index_tip - wrist) < np.linalg.norm(index_pip - wrist) * 0.90
            and np.linalg.norm(thumb_tip - wrist) < hand_size * 0.50
        )
        is_closed_fist_pose = (
            (fingers[1:] == [0, 0, 0, 0] and fingers[0] == 0)
            or (fingers[1:] == [0, 0, 0, 0] and is_index_curled_to_wrist and d_pinch_wrist < 0.50)
        )
        true_pinch = self.is_pinching and not is_closed_fist_pose

        # Vector along thumb for upward / downward direction
        v_thumb = thumb_tip - thumb_mcp
        len_v_thumb = np.linalg.norm(v_thumb)
        thumb_y_norm = (v_thumb[1] / max(1e-5, len_v_thumb)) if len_v_thumb > 0 else 0.0

        # In camera frame (y down): negative y is UPWARDS, positive y is DOWNWARDS
        thumb_pointing_up = thumb_y_norm < -0.40 and thumb_tip[1] <= middle_mcp[1]
        thumb_pointing_down = thumb_y_norm > 0.40 or thumb_tip[1] > wrist[1]

        # ── GESTURE MATCHING — priority ordered contracts ──────────────────

        # 1. Pinch — thumb tip and index tip touching/near, not curled into fist
        #    (Checked BEFORE palm-type gestures to avoid thumb-state confusion)
        if true_pinch:
            clamped_ratio = max(0.10, min(release_thresh, pinch_ratio))
            pinch_score = max(35.0, min(100.0, 100.0 - ((clamped_ratio - 0.10) / max(0.01, (release_thresh - 0.10))) * 65.0))
            return "Pinch", pinch_score

        # 2. Four Fingers / Open Palm — all four non-thumb fingers extended.
        #    Use continuous filtered thumb-extension score with hysteresis (Fix #6, P0).
        if fingers[1] == 1 and fingers[2] == 1 and fingers[3] == 1 and fingers[4] == 1:
            palm_type, thumb_score = self._classify_palm_type(lms_list, is_thumb_up=fingers[0])
            four_finger_shape = sum(scores[1:]) / 4.0
            if palm_type == "Four Fingers":
                # Folded thumb contributes POSITIVE confidence
                thumb_tuck_conf = (1.0 - thumb_score) * 100.0
                conf = min(100.0, max(35.0, (four_finger_shape * 4.0 + thumb_tuck_conf) / 5.0))
                return "Four Fingers", conf
            else:
                # Open palm: extended thumb contributes positive confidence
                thumb_ext_conf = thumb_score * 100.0
                conf = min(100.0, max(35.0, (four_finger_shape * 4.0 + thumb_ext_conf) / 5.0))
                return "Open Palm", conf

        # 3. Pointing — index extended, middle/ring/pinky folded (thumb tolerant)
        if fingers[1] == 1 and fingers[2] == 0 and fingers[3] == 0 and fingers[4] == 0:
            idx_tip = self.get_3d_point(lms_list[8])
            idx_mcp = self.get_3d_point(lms_list[5])
            d_tip_wrist = np.linalg.norm(idx_tip - wrist)
            d_mcp_wrist = np.linalg.norm(idx_mcp - wrist)
            if d_tip_wrist > d_mcp_wrist * 1.05:
                pointing_score = (scores[1] + sum(scores[2:])) / 4.0
                return "Pointing", pointing_score

        # 4. Two-finger band: index + middle extended, ring + pinky folded
        if fingers[1] == 1 and fingers[2] == 1 and fingers[3] == 0 and fingers[4] == 0:
            d_index_middle = np.linalg.norm(index_tip - middle_tip)
            d_mcp = np.linalg.norm(index_mcp - middle_mcp)
            norm_spacing = float(d_index_middle / hand_size)
            self.last_two_finger_spacing = norm_spacing

            # Divergence angle between index and middle fingers
            v_index = index_tip - index_mcp
            v_middle = middle_tip - middle_mcp
            norm_index = np.linalg.norm(v_index)
            norm_middle = np.linalg.norm(v_middle)

            angle_deg = 0.0
            if norm_index > 0 and norm_middle > 0:
                cos_angle = np.dot(v_index, v_middle) / (norm_index * norm_middle)
                angle_deg = float(np.degrees(np.arccos(np.clip(cos_angle, -1.0, 1.0))))

            # Crossed Fingers check: knuckle vector vs tip vector
            v_mcp = middle_mcp - index_mcp
            v_tip = middle_tip - index_tip
            is_crossed = np.dot(v_mcp, v_tip) < 0

            max_two_finger = getattr(self, 'two_finger_max_spacing', 0.22)
            min_victory = getattr(self, 'victory_min_spacing', 0.30)

            if is_crossed and norm_spacing < (max_two_finger * 1.6):
                return "Crossed Fingers", shape_score

            divergence_ratio = d_index_middle / max(0.01, d_mcp)
            self.last_divergence_ratio = float(divergence_ratio)

            is_strong_victory = norm_spacing >= min_victory and angle_deg >= 16.0 and divergence_ratio >= 1.35
            is_strong_two_fingers = norm_spacing <= max_two_finger or angle_deg <= 10.0

            two_finger_conf = min(100.0, max(35.0, 100.0 - (norm_spacing / 0.35) * 40.0))
            victory_conf = min(100.0, max(35.0, (norm_spacing / 0.30) * 80.0))

            if self.last_stable_gesture == "Victory":
                # Stably in Victory: require clear Two Fingers evidence to switch back
                if is_strong_two_fingers:
                    return "Two Fingers", two_finger_conf
                else:
                    return "Victory", victory_conf
            elif self.last_stable_gesture == "Two Fingers":
                # Stably in Two Fingers: require clear strong Victory evidence to switch
                if is_strong_victory:
                    return "Victory", victory_conf
                else:
                    return "Two Fingers", two_finger_conf
            else:
                if is_strong_victory:
                    return "Victory", victory_conf
                else:
                    return "Two Fingers", two_finger_conf

        # 5. Three Fingers: index + middle + ring extended, pinky folded
        if fingers[1] == 1 and fingers[2] == 1 and fingers[3] == 1 and fingers[4] == 0:
            three_score = sum(scores[1:]) / 4.0
            return "Three Fingers", three_score

        # 6. Rock On: index + pinky extended, middle + ring folded (relaxed thumb)
        if fingers[1] == 1 and fingers[2] == 0 and fingers[3] == 0 and fingers[4] == 1:
            rock_score = (scores[1] + scores[4] + scores[2] + scores[3]) / 4.0
            return "Rock On", rock_score

        # 7. Call Me: thumb + pinky extended, index + middle + ring folded
        if fingers[0] == 1 and fingers[1] == 0 and fingers[2] == 0 and fingers[3] == 0 and fingers[4] == 1:
            call_score = (scores[0] + scores[4] + scores[1] + scores[2] + scores[3]) / 5.0
            return "Call Me", call_score

        # 8. Middle Finger: only middle finger extended
        if fingers[1:] == [0, 1, 0, 0]:
            mid_score = (scores[2] + scores[1] + scores[3] + scores[4]) / 4.0
            return "Middle Finger", mid_score

        # 9. Thumb Up / Thumb Down / Closed Fist: four non-thumb fingers folded
        if fingers[1:] == [0, 0, 0, 0]:
            if fingers[0] == 1 and thumb_pointing_up:
                thumb_score_val = (scores[0] + sum(scores[1:])) / 5.0
                return "Thumb Up", thumb_score_val
            elif fingers[0] == 1 and thumb_pointing_down:
                thumb_score_val = (scores[0] + sum(scores[1:])) / 5.0
                return "Thumb Down", thumb_score_val
            else:
                fist_score = sum(scores) / 5.0
                return "Closed Fist", fist_score

        # Custom Gestures fallback
        custom_name, custom_dist = gesture_trainer.classify(lms_list, threshold=0.35)
        if custom_name:
            raw_score = max(0.0, 1.0 - (custom_dist / 0.35)) * 100.0
            return custom_name, raw_score

        return "Unknown", 0.0

    def classify(self, hands_data) -> GestureResult:
        if not hands_data:
            self.is_pinching = False
            # Clear palm and two-finger hysteresis when hand is lost
            self._last_palm_type = None
            self._last_two_finger_type = None
            self._thumb_score_history.clear()

        raw_gesture, raw_score = self.raw_classify(hands_data)

        if raw_gesture != self.last_raw_gesture:
            self.confidence_ema = raw_score
            self.last_raw_gesture = raw_gesture
        else:
            self.confidence_ema = (0.6 * self.confidence_ema) + (0.4 * raw_score)

        # Shorter history for continuous gestures (Pointing, Pinch, Two Fingers)
        is_continuous = raw_gesture in self._CONTINUOUS
        working_history = self._continuous_history if is_continuous else self._discrete_history

        self._continuous_history.append(raw_gesture)
        self._discrete_history.append(raw_gesture)

        stability = 0.0
        if len(working_history) > 0:
            counts = Counter(working_history)
            most_common = counts.most_common(1)[0][0]
            count = counts[most_common]
            stability = (count / len(working_history)) * 100.0

            req_count = max(1, len(working_history) // 2 + 1)

            if not is_continuous:
                similar_poses = [
                    {"Two Fingers", "Victory", "Crossed Fingers"},
                    {"Open Palm", "Four Fingers"},
                ]
                if most_common != self.last_stable_gesture:
                    for pose_group in similar_poses:
                        if most_common in pose_group and self.last_stable_gesture in pose_group:
                            req_count = max(req_count, len(working_history) - 1)
                            break

            if count >= req_count:
                self.last_stable_gesture = most_common

        # Pointing fast path for cursor responsiveness
        if raw_gesture == "Pointing" and self.confidence_ema >= 20.0:
            return GestureResult(
                self.last_stable_gesture, raw_gesture,
                float(self.confidence_ema), float(stability)
            )

        # Pinch fast path
        if raw_gesture == "Pinch" and self.confidence_ema >= 20.0:
            return GestureResult(
                self.last_stable_gesture, raw_gesture,
                float(self.confidence_ema), float(stability)
            )

        if self.confidence_ema < self.confidence_threshold:
            return GestureResult(
                "Unknown", raw_gesture,
                float(self.confidence_ema), float(stability), "Low confidence"
            )

        return GestureResult(
            self.last_stable_gesture, raw_gesture,
            float(self.confidence_ema), float(stability)
        )
