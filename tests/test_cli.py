"""Unit tests for the CLI layer."""

import os
import tempfile
from argparse import Namespace

import pytest

from detect_motion.cli import (
    apply_defaults,
    apply_profile,
    apply_result,
    build_parser,
    collect_videos,
    select_videos,
    validate_args,
)
from detect_motion.detector import VideoResult


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


class TestApplyDefaults:
    """Tests for the tier-2 defaults applied before the profile."""

    def test_profile_motion_ratio_is_not_masked(self):
        parser = build_parser()
        expected = {"noisy": 0.002, "balanced": 0.0015, "sensitive": 0.001}
        for profile, ratio in expected.items():
            args = parser.parse_args(["--profile", profile])
            apply_defaults(args)
            # The flag is gone from the parser; only the profile may set it.
            assert getattr(args, "min_motion_ratio", None) is None
            apply_profile(args)
            assert args.min_motion_ratio == ratio
            assert args.min_area_ratio is not None


class TestApplyResult:
    """Tests for acting on a clip the moment its analysis finishes."""

    @staticmethod
    def _args(tmp_path, **overrides):
        args = Namespace(
            output_dir=str(tmp_path / "keep"),
            drop_dir=str(tmp_path / "drop"),
            move=True,
            delete=False,
            dry_run=False,
        )
        for key, value in overrides.items():
            setattr(args, key, value)
        return args

    def test_keep_is_moved_immediately(self, tmp_path):
        src = tmp_path / "a.avi"
        src.write_bytes(b"payload")
        res = VideoResult(path=str(src), status="keep")
        tag, freed = apply_result(res, self._args(tmp_path))
        assert tag == "moved to keep"
        assert freed == 0
        assert not src.exists()
        assert (tmp_path / "keep" / "a.avi").read_bytes() == b"payload"
        assert res.moved_to.endswith("a.avi")

    def test_copy_keeps_the_original(self, tmp_path):
        src = tmp_path / "a.avi"
        src.write_bytes(b"payload")
        res = VideoResult(path=str(src), status="keep")
        tag, _ = apply_result(res, self._args(tmp_path, move=False))
        assert tag == "copied to keep"
        assert src.exists()
        assert (tmp_path / "keep" / "a.avi").exists()

    def test_drop_is_moved_immediately(self, tmp_path):
        src = tmp_path / "b.avi"
        src.write_bytes(b"payload")
        res = VideoResult(path=str(src), status="drop")
        tag, _ = apply_result(res, self._args(tmp_path))
        assert tag == "moved to drop"
        assert not src.exists()
        assert (tmp_path / "drop" / "b.avi").exists()

    def test_delete_reports_freed_bytes(self, tmp_path):
        src = tmp_path / "c.avi"
        src.write_bytes(b"12345")
        res = VideoResult(path=str(src), status="drop")
        tag, freed = apply_result(res, self._args(tmp_path, drop_dir=None, delete=True))
        assert tag == "deleted"
        assert freed == 5
        assert res.deleted is True
        assert not src.exists()

    def test_dry_run_touches_nothing(self, tmp_path):
        src = tmp_path / "d.avi"
        src.write_bytes(b"payload")
        args = self._args(tmp_path, dry_run=True, output_dir=None, drop_dir=None)
        for status in ("keep", "drop"):
            tag, freed = apply_result(VideoResult(path=str(src), status=status), args)
            assert (tag, freed) == ("", 0)
        assert src.exists()

    def test_error_result_is_left_alone(self, tmp_path):
        src = tmp_path / "e.avi"
        src.write_bytes(b"payload")
        res = VideoResult(path=str(src), status="error", reason="bad codec")
        assert apply_result(res, self._args(tmp_path)) == ("", 0)
        assert src.exists()


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

    def test_sorts_by_mtime_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            older = os.path.join(tmpdir, "older.avi")
            newer = os.path.join(tmpdir, "newer.avi")
            open(older, "w").close()
            open(newer, "w").close()
            os.utime(older, (1_000_000, 1_000_000))
            os.utime(newer, (2_000_000, 2_000_000))

            result = select_videos([newer, older])

            assert [os.path.basename(p) for p in result] == ["older.avi", "newer.avi"]
