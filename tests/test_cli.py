"""Unit tests for the CLI layer."""

import os
import tempfile
from argparse import Namespace

import pytest

from detect_motion.cli import (
    apply_profile,
    build_parser,
    collect_videos,
    select_videos,
    validate_args,
)


class TestBuildParser:
    """Tests for the argument parser."""

    def test_parser_has_required_args(self):
        parser = build_parser()
        args = parser.parse_args(["--profile", "sensitive", "--workers", "4"])
        assert args.profile == "sensitive"
        assert args.workers == 4

    def test_default_profile_is_noisy(self):
        parser = build_parser()
        args = parser.parse_args([])
        assert args.profile == "noisy"

    def test_version_flag(self):
        parser = build_parser()
        args = parser.parse_args(["--version"])
        assert args.version is True


class TestValidateArgs:
    """Tests for argument validation."""

    def test_valid_args_pass(self):
        parser = build_parser()
        args = parser.parse_args(["--workers", "1", "--width", "320"])
        validate_args(parser, args)

    def test_frame_stride_must_be_positive(self):
        parser = build_parser()
        args = parser.parse_args(["--frame-stride", "0"])
        with pytest.raises(SystemExit):
            validate_args(parser, args)

    def test_width_must_be_at_least_16(self):
        parser = build_parser()
        args = parser.parse_args(["--width", "8"])
        with pytest.raises(SystemExit):
            validate_args(parser, args)


class TestApplyProfile:
    """Tests for profile application."""

    def test_profile_fills_unset_values(self):
        args = Namespace(
            width=None,
            blur=None,
            open=None,
            dilate=None,
            min_area_ratio=None,
            min_motion_ratio=None,
            mog_var_threshold=None,
            temporal=None,
            profile="balanced",
        )
        apply_profile(args)
        assert args.width == 480
        assert args.blur == 11
        assert args.open == 7
        assert args.dilate == 3
        assert args.min_area_ratio == 0.003
        assert args.min_motion_ratio == 0.0015
        assert args.mog_var_threshold == 64.0
        assert args.temporal == 1

    def test_explicit_flags_override_profile(self):
        args = Namespace(
            width=640,
            blur=None,
            open=None,
            dilate=None,
            min_area_ratio=0.01,
            min_motion_ratio=None,
            mog_var_threshold=None,
            temporal=None,
            profile="noisy",
        )
        apply_profile(args)
        # width explicitly set, should not be overridden
        assert args.width == 640
        # min_area_ratio explicitly set
        assert args.min_area_ratio == 0.01
        # unset values filled from profile
        assert args.blur == 15


class TestCollectVideos:
    """Tests for video collection."""

    def test_collects_videos_from_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            for name in ["a.avi", "b.mp4", "c.txt", "d.mkv"]:
                open(os.path.join(tmpdir, name), "w").close()
            found = collect_videos([], tmpdir, "*")
            names = sorted(os.path.basename(f) for f in found)
            assert names == ["a.avi", "b.mp4", "d.mkv"]

    def test_accepts_explicit_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            f = os.path.join(tmpdir, "test.avi")
            open(f, "w").close()
            found = collect_videos([f], tmpdir, "*")
            assert found == [f]


class TestSelectVideos:
    """Tests for video selection."""

    def test_limit_cuts_list(self):
        files = [f"/v/{i}.avi" for i in range(10)]
        result = select_videos(files, sort_key="name", limit=3)
        assert len(result) == 3

    def test_newest_first_reverses(self):
        files = [f"/v/{i}.avi" for i in range(5)]
        result = select_videos(files, sort_key="name", newest_first=True)
        assert result[0].endswith("4.avi")

    def test_no_limit_returns_all(self):
        files = [f"/v/{i}.avi" for i in range(5)]
        result = select_videos(files, sort_key="name", limit=0)
        assert len(result) == 5
