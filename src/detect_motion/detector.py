"""Core motion-detection engine.

Per video, frames are decoded, downscaled to a small working resolution,
converted to grayscale, blurred, and compared against a background model
(MOG2) or a reference frame (diff). Morphological opening removes speckle,
dilation re-joins moving objects, and connected-component analysis measures
the area of surviving motion blobs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import cv2
import numpy as np


@dataclass
class VideoResult:
    """Analysis result for a single video."""

    path: str
    status: str  # keep | drop | error
    reason: str = ""
    method: str = "diff"
    fps: float = 0.0
    frames_total: int = 0
    frames_sampled: int = 0
    frames_moving: int = 0
    frames_scored: int = 0
    scene_cuts: int = 0
    brightness_median: float = 0.0
    light_change_ratio: float = 0.0
    moving_fraction: float = 0.0
    largest_blob_median: float = 0.0
    blob_count_median: float = 0.0
    moving_score_median: float = 0.0
    moving_score_p95: float = 0.0
    noise_floor: float = 0.0
    area_threshold: float = 0.0
    score_threshold: float = 0.0
    threshold_basis: str = "absolute"
    threshold_margin: float = 0.0
    first_moving_frame: int | None = None
    last_moving_frame: int | None = None
    moving_segments: list[list[int]] = field(default_factory=list)
    # Backwards-compatible alias for event_span_seconds.
    moving_seconds: float = 0.0
    active_motion_seconds: float = 0.0
    event_span_seconds: float = 0.0
    elapsed_s: float = 0.0
    sampled_fps: float = 0.0
    preview: str | None = None
    moved_to: str | None = None
    deleted: bool = False

    def summary(self) -> str:
        """Return a one-line human-readable summary."""
        if self.status == "error":
            return f"ERROR  {self.reason}"
        return (
            f"{self.status.upper():5s} "
            f"moving={self.frames_moving}/{self.frames_sampled} "
            f"({self.moving_fraction * 100:.2f}%) "
            f"score_med={self.moving_score_median:.5f} "
            f"thr={self.score_threshold:.5f} "
            f"{self.elapsed_s:.1f}s {self.sampled_fps:.0f}fps"
        )


def _noise_floor(scores: np.ndarray, k: float) -> float:
    """Estimate the robust noise level of per-frame motion scores.

    The lowest 20 % of scores are used as the "no movement" reference, not
    all frames: if movement occupies most of the clip, the overall median IS
    the motion level and thresholding on it would cancel the signal out.

    Returns median + k * 1.4826 * MAD, where MAD is scaled to estimate
    standard deviation.
    """
    if scores.size == 0:
        return 0.0
    _ = float(np.median(scores))  # overall median (unused, kept for clarity)
    cutoff = float(np.percentile(scores, 20))
    quiet = scores[scores <= cutoff]
    if quiet.size < 3:  # movement in nearly every frame: use absolute floor
        return 0.0
    med = float(np.median(quiet))
    mad = float(np.median(np.abs(quiet - med)))
    return med + k * 1.4826 * mad


class _ExposureNormaliser:
    """Track a slowly-updated reference brightness and align each frame to it.

    Without this, a background model trained before a lighting change goes
    stale: every frame afterwards mismatches it and the whole clip reads as
    movement even though nothing moved. Rescaling by a single global
    gain/offset cancels the exposure change while leaving objects alone,
    because they differ from the background locally, not in overall brightness.
    """

    def __init__(self, rate: float) -> None:
        self.rate = rate
        self.mean: float | None = None
        self.std = 1.0

    def __call__(self, gray: np.ndarray) -> np.ndarray:
        img = gray.astype(np.float32)
        m, s = cv2.meanStdDev(img)
        m = float(m[0][0])
        s = float(s[0][0])
        if self.mean is None:
            self.mean, self.std = m, s or 1.0
            return gray
        corrected = (img - m) * (self.std / max(s, 1e-3)) + self.mean
        self.mean += (m - self.mean) * self.rate
        self.std += (s - self.std) * self.rate
        return np.clip(corrected, 0, 255).astype(np.uint8)


def _temporal_filter(scores: np.ndarray, window: int) -> np.ndarray:
    """Zero frames whose motion is not confirmed by a neighbour.

    Sensor grain and codec noise produce isolated single-frame hits that
    vanish on the next frame, while a real object keeps lighting up its
    pixels over consecutive frames. Requiring corroboration removes that
    noise without raising the threshold so far that dim movement is lost.
    """
    if window <= 0 or scores.size < 3:
        return scores
    out = scores.copy()
    hits = scores > 0
    for i in np.flatnonzero(hits):
        lo, hi = max(0, i - window), min(scores.size, i + window + 1)
        if int(hits[lo:hi].sum()) < 2:
            out[i] = 0.0
    return out


def _gap_frames(fps: float, gap_seconds: float = 1.0) -> int:
    """Return how many still frames may separate two moving frames before a gap."""
    if fps <= 0:
        fps = 25.0
    return max(1, int(round(fps * gap_seconds)))


def _merge_segments(frames: list[int], gap: int) -> list[list[int]]:
    """Merge moving frame numbers into [start, end] frame ranges.

    Consecutive moving frames join, as do runs separated by fewer than
    ``gap`` still frames, so one event that blinks reads as a single
    segment instead of scattered single-frame hits.
    """
    if not frames:
        return []
    ordered = sorted(set(frames))
    segments: list[list[int]] = [[ordered[0], ordered[0]]]
    for f in ordered[1:]:
        if f - segments[-1][1] <= gap:
            segments[-1][1] = f
        else:
            segments.append([f, f])
    return segments


def analyse_video(path: str, args) -> VideoResult:
    """Analyse a single video for motion.

    Parameters
    ----------
    path:
        Video file to analyse.
    args:
        Namespace-like object with detection settings (profile, width,
        frame_stride, blur, open, dilate, min_area_ratio, exclude,
        adaptive, mog_var_threshold, temporal, min_motion_ratio,
        min_motion_frames, min_motion_fraction, max_motion_fraction).

    Returns
    -------
    VideoResult
        Per-video analysis result.
    """
    import time

    started = time.time()
    # One OpenCV thread per worker process; per-process speed is unchanged
    # but this prevents CPU oversubscription when several workers run.
    cv2.setNumThreads(1)
    result = VideoResult(path=path, status="drop", method=args.method)

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        result.status = "error"
        result.reason = "cannot open (missing, truncated or unsupported codec)"
        result.elapsed_s = time.time() - started
        return result

    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    meta_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if src_w <= 0 or src_h <= 0:
        cap.release()
        result.status = "error"
        result.reason = "no video stream / zero-sized frames"
        result.elapsed_s = time.time() - started
        return result

    # Working resolution requested by the user / profile.
    work_w = min(args.width, src_w)
    work_w -= work_w % 2
    work_h = max(2, int(round(src_h * work_w / src_w)))
    work_h -= work_h % 2

    # Ask the decoder to downscale directly; re-fetch what it agreed to.
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, work_w)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, work_h)
    work_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or work_w)
    work_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or work_h)
    work_w -= work_w % 2
    work_h -= work_h % 2

    frame_area = float(work_w * work_h)
    min_blob_area = max(1, int(args.min_area_ratio * frame_area))

    blur_k = args.blur if args.blur % 2 == 1 else args.blur + 1
    # A wide opening kills grain: 3x3 lets speckle through and surviving
    # specks add up to "motion".
    open_k = np.ones((max(1, args.open), max(1, args.open)), np.uint8)
    dil_k = np.ones((args.dilate, args.dilate), np.uint8) if args.dilate > 1 else None

    # Exclusion zones, converted once from fractions to working pixels.
    excluded: list[tuple[int, int, int, int]] = []
    for spec in args.exclude:
        try:
            fx, fy, fw, fh = (float(v) for v in spec.split(","))
        except ValueError:
            # SystemExit raised here intentionally; no exception chaining needed.
            raise SystemExit(  # noqa: B904
                f"--exclude expects X,Y,W,H as fractions, got {spec!r}"
            )
        x0, y0 = int(fx * work_w), int(fy * work_h)
        x1, y1 = (
            min(work_w, int((fx + fw) * work_w)),
            min(work_h, int((fy + fh) * work_h)),
        )
        if x1 > x0 and y1 > y0:
            excluded.append((x0, y0, x1, y1))

    # Pre-compute a single exclusion mask; apply with bitwise_and per frame.
    exclusion_mask = np.ones((work_h, work_w), dtype=np.uint8) * 255
    for x0, y0, x1, y1 in excluded:
        exclusion_mask[y0:y1, x0:x1] = 0
    has_exclusions = len(excluded) > 0

    scores: list[float] = []
    score_frames: list[int] = []  # true frame index for each score
    largest_blobs: list[float] = []
    blob_counts: list[int] = []
    bg = None  # MOG2 background-subtractor state
    prev_gray = None  # previous frame, for scene-cut detection
    prev_brightness: float | None = None
    brightness_deltas: list[float] = []
    scene_cuts = 0
    scene_cut_level = max(25, args.mog_var_threshold // 2)
    gray_lag: list[np.ndarray] = []  # ring buffer of recent frames (method=diff)
    # Exposure normalisation was removed from the CLI; keep the class for the
    # single-pass meanStdDev call path if re-enabled later.
    _ = _ExposureNormaliser(0.0)
    idx = -1
    sampled = 0

    try:
        while True:
            if args.frame_stride > 1:
                # grab() decodes but skips BGR conversion/copy for skipped frames.
                # Seeking avoids JPEG decode but is ~3x slower on MJPG AVI because
                # OpenCV still decodes forward internally.
                if not cap.grab():
                    break
                idx += 1
                if idx % args.frame_stride:
                    continue
                ok, frame = cap.retrieve()
                if not ok:
                    break
            else:
                ok, frame = cap.read()
                if not ok:
                    break
                idx += 1
            sampled += 1

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            # Box blur instead of Gaussian: faster, nearly identical noise reduction.
            gray = cv2.blur(gray, (blur_k, blur_k))

            # Brightness tracked separately from local motion: a global brightness
            # step is not something moving in the scene.
            brightness = float(gray.mean())
            if prev_brightness is not None:
                brightness_deltas.append(abs(brightness - prev_brightness))
            prev_brightness = brightness

            # A scene cut invalidates the background model; restart it rather
            # than reporting the cut itself as movement.
            if prev_gray is not None:
                step = cv2.absdiff(gray, prev_gray)
                if float(np.count_nonzero(step > scene_cut_level)) / frame_area > 0.40:
                    scene_cuts += 1
                    bg = None
                    prev_gray = gray
                    continue

            prev_gray = gray

            if args.method == "mog2":
                if bg is None:
                    bg = cv2.createBackgroundSubtractorMOG2(
                        history=300,
                        varThreshold=args.mog_var_threshold,
                        detectShadows=True,
                    )
                mask = bg.apply(gray, learningRate=-1.0)
                # MOG2 encodes shadows as 127 and foreground as 255; keep 255 only.
                mask = cv2.compare(mask, 255, cv2.CMP_EQ)
                mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, open_k)
                if dil_k is not None:
                    mask = cv2.dilate(mask, dil_k)
            else:
                if len(gray_lag) < 2:
                    gray_lag.append(gray)
                    continue
                ref = gray_lag.pop(0)
                gray_lag.append(gray)
                diff = cv2.absdiff(gray, ref)
                _, mask = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
                mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, open_k)
                if dil_k is not None:
                    mask = cv2.dilate(mask, dil_k)

            if has_exclusions:
                mask = cv2.bitwise_and(mask, exclusion_mask)

            # connectedComponentsWithStats instead of findContours: faster area-only
            # blob measurement; stats is Nx5 [x, y, width, height, area], label 0 is bg.
            num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
            areas = stats[1:, cv2.CC_STAT_AREA]  # skip background label 0
            kept = areas[areas >= min_blob_area]
            area = int(kept.sum())
            scores.append(area / frame_area)
            # Remember the true frame index; it cannot be reconstructed from the
            # position in `scores` because warm-up frames produce no score.
            score_frames.append(idx)
            largest_blobs.append(float(kept.max()) if kept.size else 0.0)
            blob_counts.append(int(kept.size))

    except Exception as exc:  # corrupt frame mid-stream
        cap.release()
        result.status = "error"
        result.reason = f"decode failure at frame {idx}: {exc}"
        result.elapsed_s = time.time() - started
        return result

    cap.release()

    score_arr = np.asarray(scores, dtype=np.float64)
    score_arr = _temporal_filter(score_arr, args.temporal)
    scored = int(score_arr.size)
    result.frames_total = idx + 1 if meta_frames <= 0 else meta_frames
    result.frames_sampled = sampled
    result.frames_scored = scored
    result.scene_cuts = scene_cuts
    if brightness_deltas:
        arr = np.asarray(brightness_deltas)
        result.brightness_median = round(float(np.median(arr)), 3)
        # Share of frames where the whole image steps in brightness: lighting change,
        # not object motion.
        result.light_change_ratio = round(float(np.count_nonzero(arr > 2.0)) / arr.size, 4)
    median_score = float(np.median(score_arr)) if score_arr.size else 0.0
    # A quiet baseline exists only if most frames sit near the absolute minimum.
    # When they do not (day/light transitions, movement throughout), the noise
    # floor IS the signal; trusting it would discard the movement.
    quiet_baseline = median_score < 5.0 * args.min_motion_ratio
    if args.adaptive and quiet_baseline:
        result.noise_floor = _noise_floor(score_arr, 6.0)
        result.score_threshold = max(args.min_motion_ratio, result.noise_floor)
        result.threshold_basis = (
            "adaptive" if result.noise_floor > args.min_motion_ratio else "absolute"
        )
    else:
        result.noise_floor = 0.0
        result.score_threshold = args.min_motion_ratio
        result.threshold_basis = "absolute"
    result.area_threshold = min_blob_area / frame_area

    if score_arr.size:
        result.moving_score_median = float(np.median(score_arr))
        result.moving_score_p95 = float(np.percentile(score_arr, 95))
        # Frames where nearly the whole image moves are exposure/lighting flicker:
        # a scene-level change, not object motion, so drop them.
        ok_mask = (score_arr >= result.score_threshold) & (score_arr <= args.max_motion_fraction)
        moving_indices = [score_frames[p] for p in np.flatnonzero(ok_mask)]
        result.frames_moving = len(moving_indices)
        result.moving_fraction = result.frames_moving / scored
        # Headroom the decision had: positive means the median frame sits below the
        # threshold, i.e. the clip is genuinely quiet.
        result.threshold_margin = round(result.score_threshold - median_score, 6)
        moving_blobs = np.asarray(largest_blobs)[ok_mask] if largest_blobs else np.array([])
        moving_counts = np.asarray(blob_counts)[ok_mask] if blob_counts else np.array([])
        result.largest_blob_median = (
            float(np.median(moving_blobs)) / frame_area if moving_blobs.size else 0.0
        )
        result.blob_count_median = float(np.median(moving_counts)) if moving_counts.size else 0.0
        result.moving_segments = _merge_segments(moving_indices, _gap_frames(fps))
        if fps > 0:
            # Event span includes still gaps inside merged events...
            result.event_span_seconds = round(
                sum(b - a + 1 for a, b in result.moving_segments) / fps, 2
            )
            # ...versus frames actually flagged as moving.
            result.active_motion_seconds = round(result.frames_moving / fps, 2)
        # Backwards-compatible alias for event_span_seconds.
        result.moving_seconds = result.event_span_seconds
        if moving_indices:
            result.first_moving_frame = int(moving_indices[0])
            result.last_moving_frame = int(moving_indices[-1])

    # Base the minimum on frames that actually produced a score; never demand
    # more moving frames than the clip can provide.
    need_frames = max(
        args.min_motion_frames,
        int(math.ceil(args.min_motion_fraction * scored)),
    )
    if scored > 0:
        need_frames = min(need_frames, scored)
    if scored == 0 or result.frames_moving < need_frames:
        result.status = "drop"
        result.reason = (
            f"only {result.frames_moving} moving frames, need {need_frames} "
            f"(threshold {result.score_threshold:.5f})"
        )
    else:
        result.status = "keep"

    result.elapsed_s = time.time() - started
    result.fps = fps
    if result.elapsed_s > 0:
        result.sampled_fps = round(result.frames_total / result.elapsed_s, 1)
    return result
