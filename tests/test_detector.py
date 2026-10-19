"""Unit tests for the motion-detection engine."""

import numpy as np

from detect_motion.detector import (
    VideoResult,
    _gap_frames,
    _merge_segments,
    _noise_floor,
    _temporal_filter,
)


class TestNoiseFloor:
    """Tests for _noise_floor."""

    def test_empty_scores(self):
        assert _noise_floor(np.array([]), 6.0) == 0.0

    def test_all_quiet(self):
        scores = np.zeros(100)
        assert _noise_floor(scores, 6.0) == 0.0

    def test_quiet_with_spikes(self, quiet_scores):
        floor = _noise_floor(quiet_scores, 6.0)
        # Quiet baseline should be near zero with small spikes above it.
        assert floor >= 0.0
        assert floor < 0.01

    def test_all_active(self, active_scores):
        floor = _noise_floor(active_scores, 6.0)
        # No quiet baseline exists; floor should be 0.0 (absolute fallback).
        assert floor == 0.0


class TestTemporalFilter:
    """Tests for _temporal_filter."""

    def test_no_window(self, active_scores):
        result = _temporal_filter(active_scores, 0)
        np.testing.assert_array_equal(result, active_scores)

    def test_isolated_hit_removed(self):
        # Single spike surrounded by zeros should be zeroed.
        scores = np.array([0.0, 0.0, 0.5, 0.0, 0.0])
        result = _temporal_filter(scores, window=1)
        assert result[2] == 0.0

    def test_consecutive_hits_kept(self):
        scores = np.array([0.0, 0.5, 0.6, 0.0, 0.0])
        result = _temporal_filter(scores, window=1)
        assert result[1] == 0.5
        assert result[2] == 0.6

    def test_small_array_unchanged(self):
        scores = np.array([0.1, 0.2])
        result = _temporal_filter(scores, window=2)
        np.testing.assert_array_equal(result, scores)


class TestGapFrames:
    """Tests for _gap_frames."""

    def test_normal_fps(self):
        assert _gap_frames(25.0, 1.0) == 25

    def test_zero_fps_defaults(self):
        assert _gap_frames(0.0, 1.0) == 25

    def test_custom_gap(self):
        # Python 3 uses banker's rounding: round(12.5) == 12
        assert _gap_frames(25.0, 0.5) == 12


class TestMergeSegments:
    """Tests for _merge_segments."""

    def test_empty(self):
        assert _merge_segments([], 10) == []

    def test_single_frame(self):
        assert _merge_segments([5], 10) == [[5, 5]]

    def test_consecutive_merged(self):
        assert _merge_segments([1, 2, 3, 10, 11], 2) == [[1, 3], [10, 11]]

    def test_gap_within_threshold_merged(self):
        # Gap of 2 still frames <= gap threshold of 3
        assert _merge_segments([1, 2, 5, 6], 3) == [[1, 6]]

    def test_gap_beyond_threshold_split(self):
        # Gap of 4 still frames > gap threshold of 3
        assert _merge_segments([1, 2, 7, 8], 3) == [[1, 2], [7, 8]]


class TestVideoResult:
    """Tests for the VideoResult dataclass."""

    def test_default_status_is_drop(self):
        res = VideoResult(path="/x.avi", status="drop")
        assert res.status == "drop"
        assert res.reason == ""

    def test_summary_error(self):
        res = VideoResult(path="/x.avi", status="error", reason="codec missing")
        assert res.summary() == "ERROR  codec missing"

    def test_summary_keep(self):
        res = VideoResult(
            path="/x.avi",
            status="keep",
            frames_moving=100,
            frames_sampled=1000,
            moving_fraction=0.1,
            moving_score_median=0.005,
            score_threshold=0.002,
            elapsed_s=10.5,
            sampled_fps=30.0,
        )
        s = res.summary()
        assert "KEEP" in s
        assert "100/1000" in s
        assert "10.5s" in s

    def test_moving_seconds_alias(self):
        # moving_seconds is a backwards-compatible alias, set explicitly.
        res = VideoResult(
            path="/x.avi",
            status="keep",
            moving_seconds=42.5,
            event_span_seconds=42.5,
        )
        assert res.moving_seconds == 42.5
        assert res.event_span_seconds == 42.5
