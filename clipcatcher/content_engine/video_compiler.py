"""
video_compiler.py — Video Compilation Pipeline

Assembles final 1080×1920 vertical videos (YouTube Shorts / TikTok)
from audio, visual segments, and word-level subtitles using ffmpeg.

Pipeline stages:
    1. Convert each static image to a video clip with Ken Burns zoom
    2. Concatenate all visual clips sequentially
    3. Generate an ASS subtitle file with word-by-word highlighting
    4. Merge visuals + audio + burned-in subtitles
    5. Final encode: H.264 / AAC / 30 fps / movflags +faststart

Usage:
    from content_engine.video_compiler import VideoCompiler

    compiler = VideoCompiler()
    output = compiler.compile(
        audio_path="narration.mp3",
        visual_segments=[
            {"type": "image", "path": "img1.png", "duration": 4.0},
            {"type": "video", "path": "clip.mp4", "duration": 6.0},
        ],
        subtitles=[
            {"word": "Hello", "start": 0.0, "end": 0.4},
            {"word": "world", "start": 0.45, "end": 0.9},
        ],
        output_path="final.mp4",
    )
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from app.recorder import find_tool

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────
WIDTH = 1080
HEIGHT = 1920
FPS = 30
# Scale factor for the zoompan source so the crop stays inside bounds.
_ZP_SCALE_W = 1200
_ZP_SCALE_H = 2134


class VideoCompilerError(RuntimeError):
    """Raised when any stage of the video compilation pipeline fails."""


class VideoCompiler:
    """Assembles final vertical videos (1080×1920) from audio + visuals + subtitles."""

    def __init__(self, ffmpeg_path: Optional[str] = None) -> None:
        self.ffmpeg: str = ffmpeg_path or find_tool("ffmpeg") or ""
        if not self.ffmpeg:
            raise RuntimeError(
                "ffmpeg not found. Install ffmpeg and ensure it is on PATH, "
                "or pass the path explicitly via ffmpeg_path."
            )
        logger.info("VideoCompiler initialised — ffmpeg at %s", self.ffmpeg)

    # ── Public API ───────────────────────────────────────────────────────

    def compile(
        self,
        audio_path: str | Path,
        visual_segments: Sequence[Dict[str, Any]],
        subtitles: Sequence[Dict[str, Any]],
        output_path: str | Path,
        subtitle_style: str = "word_highlight",
    ) -> Path:
        """
        Full compilation pipeline.

        Parameters
        ----------
        audio_path : path
            Path to the narration / music audio file.
        visual_segments : list of dicts
            Each dict must have:
              - ``type``:     ``"image"`` or ``"video"``
              - ``path``:     path to the source file
              - ``duration``: duration in seconds this segment should last
        subtitles : list of dicts
            Each dict must have:
              - ``word``:  the spoken word
              - ``start``: start time in seconds
              - ``end``:   end time in seconds
        output_path : path
            Destination for the final .mp4.
        subtitle_style : str
            ``"word_highlight"`` (default) — ASS word-by-word highlight.

        Returns
        -------
        Path
            The absolute path to the produced .mp4 file.

        Raises
        ------
        VideoCompilerError
            If any ffmpeg stage fails.
        FileNotFoundError
            If a source file is missing.
        """
        audio_path = Path(audio_path)
        output_path = Path(output_path)
        if not audio_path.is_file():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert subtitles to list of dicts with 'word', 'start', 'end' in seconds
        formatted_subs = []
        for w in subtitles:
            if hasattr(w, "text") and hasattr(w, "start_ms") and hasattr(w, "end_ms"):
                # SubtitleWord object
                formatted_subs.append({
                    "word": getattr(w, "text"),
                    "start": getattr(w, "start_ms") / 1000.0,
                    "end": getattr(w, "end_ms") / 1000.0
                })
            elif isinstance(w, dict):
                # Dictionary
                word_val = w.get("word", w.get("text", ""))
                start_val = w.get("start", w.get("start_ms", 0.0) / 1000.0 if "start_ms" in w else 0.0)
                end_val = w.get("end", w.get("end_ms", 0.0) / 1000.0 if "end_ms" in w else 0.0)
                formatted_subs.append({
                    "word": word_val,
                    "start": float(start_val),
                    "end": float(end_val)
                })
            else:
                formatted_subs.append(w)
        subtitles = formatted_subs

        # Create a temp working directory *inside* the output folder so that
        # intermediate files live on the same volume (avoids cross-device moves).
        work_dir = output_path.parent / f".vc_tmp_{os.getpid()}"
        work_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("Working directory: %s", work_dir)

        try:
            # ── Stage 1: Build individual video clips ────────────────────
            clip_paths: List[Path] = []
            for idx, seg in enumerate(visual_segments):
                seg_type = seg.get("type", "image")
                seg_path = Path(seg["path"])
                seg_dur = float(seg["duration"])

                if not seg_path.is_file():
                    raise FileNotFoundError(
                        f"Visual segment #{idx} not found: {seg_path}"
                    )

                clip_out = work_dir / f"clip_{idx:04d}.mp4"

                if seg_type == "image":
                    self._image_to_video(seg_path, seg_dur, clip_out)
                elif seg_type == "video":
                    self._scale_video(seg_path, seg_dur, clip_out)
                else:
                    raise VideoCompilerError(
                        f"Unknown segment type '{seg_type}' for segment #{idx}"
                    )
                clip_paths.append(clip_out)
                logger.info("Segment %d/%d ready", idx + 1, len(visual_segments))

            # ── Stage 2: Concatenate ─────────────────────────────────────
            concat_out = work_dir / "concat.mp4"
            self._concat_videos(clip_paths, concat_out)
            logger.info("Concatenation complete")

            # ── Stage 3: Generate ASS subtitles ──────────────────────────
            subs_out = work_dir / "subs.ass"
            self._generate_ass_subtitles(subtitles, subs_out)
            logger.info("Subtitles generated")

            # ── Stage 4 + 5: Merge + final encode ───────────────────────
            self._merge_audio_video_subs(concat_out, audio_path, subs_out, output_path)
            logger.info("Final video written to %s", output_path)

            return output_path.resolve()

        finally:
            # Clean up intermediate files.
            try:
                shutil.rmtree(work_dir)
                logger.debug("Cleaned up working directory")
            except Exception as exc:
                logger.warning("Could not remove temp dir %s: %s", work_dir, exc)

    # ── Private helpers ──────────────────────────────────────────────────

    def _run_ffmpeg(self, cmd: List[str], stage_name: str) -> subprocess.CompletedProcess:
        """Run an ffmpeg command and raise on failure with stderr details."""
        logger.debug("ffmpeg [%s]: %s", stage_name, " ".join(cmd))
        result = subprocess.run(
            cmd,
            capture_output=True,
            stdin=subprocess.DEVNULL,
        )
        if result.returncode != 0:
            stderr_tail = result.stderr.decode("utf-8", errors="replace")[-2000:]
            logger.error("ffmpeg [%s] failed (rc=%d):\n%s", stage_name, result.returncode, stderr_tail)
            raise VideoCompilerError(
                f"ffmpeg stage '{stage_name}' failed (returncode {result.returncode}). "
                f"Tail of stderr:\n{stderr_tail}"
            )
        return result

    def _image_to_video(
        self,
        image_path: Path,
        duration_s: float,
        output_path: Path,
    ) -> Path:
        """
        Convert a static image to a video clip with a Ken Burns (slow zoom) effect.

        The image is first up-scaled to 1200×2134, then the *zoompan* filter
        gradually zooms in (up to 1.1×) while keeping the centre in frame,
        outputting at 1080×1920 @ 30 fps.
        """
        total_frames = int(FPS * duration_s)
        if total_frames < 1:
            total_frames = 1

        # zoompan: 'z' ramps from 1.0 → 1.1 over the clip duration.
        # x/y keep the zoom centred.
        zoompan_filter = (
            f"scale={_ZP_SCALE_W}:{_ZP_SCALE_H},"
            f"zoompan="
            f"z='min(zoom+0.0005,1.1)':"
            f"x='iw/2-(iw/zoom/2)':"
            f"y='ih/2-(ih/zoom/2)':"
            f"d={total_frames}:"
            f"s={WIDTH}x{HEIGHT}:"
            f"fps={FPS}"
        )

        cmd = [
            self.ffmpeg, "-y",
            "-loop", "1",
            "-i", str(image_path),
            "-vf", zoompan_filter,
            "-t", f"{duration_s:.3f}",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            str(output_path),
        ]
        self._run_ffmpeg(cmd, "image_to_video")
        return output_path

    def _scale_video(
        self,
        video_path: Path,
        duration_s: float,
        output_path: Path,
    ) -> Path:
        """
        Scale and pad an existing video clip to exactly 1080×1920,
        trim to *duration_s*, and normalise codec/pixel-format for concat.
        """
        # scale to fit inside 1080×1920 keeping aspect, then pad to fill.
        vf = (
            f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"setsar=1"
        )
        cmd = [
            self.ffmpeg, "-y",
            "-i", str(video_path),
            "-t", f"{duration_s:.3f}",
            "-vf", vf,
            "-r", str(FPS),
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-an",  # strip audio — final audio comes from narration
            str(output_path),
        ]
        self._run_ffmpeg(cmd, "scale_video")
        return output_path

    def _concat_videos(
        self,
        video_paths: Sequence[Path],
        output_path: Path,
    ) -> Path:
        """
        Concatenate video segments using the ffmpeg concat demuxer.

        First attempts a stream-copy concat (fast).  If that fails (e.g. a
        parameter mismatch), falls back to re-encoding.
        """
        if not video_paths:
            raise VideoCompilerError("No video segments to concatenate")

        concat_list = output_path.parent / "concat_list.txt"
        with open(concat_list, "w", encoding="utf-8") as fh:
            for vp in video_paths:
                # Paths in the list must use forward slashes for ffmpeg.
                safe = str(vp.resolve()).replace("\\", "/")
                fh.write(f"file '{safe}'\n")

        # Attempt 1: stream copy (fast)
        cmd_copy = [
            self.ffmpeg, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_list),
            "-c", "copy",
            str(output_path),
        ]
        try:
            self._run_ffmpeg(cmd_copy, "concat_copy")
            return output_path
        except VideoCompilerError:
            logger.warning("Stream-copy concat failed; falling back to re-encode")

        # Attempt 2: re-encode
        cmd_reencode = [
            self.ffmpeg, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_list),
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-r", str(FPS),
            "-c:a", "aac",
            str(output_path),
        ]
        self._run_ffmpeg(cmd_reencode, "concat_reencode")
        return output_path

    def _generate_ass_subtitles(
        self,
        words: Sequence[Dict[str, Any]],
        output_path: Path,
    ) -> Path:
        """
        Generate an ASS subtitle file with word-by-word highlight animation.

        Words are grouped into phrases of up to *max_words_per_line* words.
        For each phrase a series of ``Dialogue`` events are emitted, one per
        word, where the currently spoken word is coloured yellow
        (``\\c&H00FFFF&``) and the rest are white (``\\c&HFFFFFF&``).
        """
        max_words_per_line = 7

        # ── Header ───────────────────────────────────────────────────────
        header = textwrap.dedent("""\
            [Script Info]
            Title: Auto-generated subtitles
            ScriptType: v4.00+
            WrapStyle: 0
            PlayResX: 1080
            PlayResY: 1920
            ScaledBorderAndShadow: yes

            [V4+ Styles]
            Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
            Style: Default,Arial Black,54,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,40,40,280,1

            [Events]
            Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
        """)

        lines: List[str] = [header]

        # ── Group words into phrases ─────────────────────────────────────
        phrases: List[List[Dict[str, Any]]] = []
        for i in range(0, len(words), max_words_per_line):
            phrases.append(list(words[i : i + max_words_per_line]))

        for phrase in phrases:
            phrase_start = phrase[0]["start"]
            phrase_end = phrase[-1]["end"]
            all_texts = [w["word"] for w in phrase]

            for focus_idx, focus_word in enumerate(phrase):
                w_start = focus_word["start"]
                # End time = start of next word or phrase end.
                if focus_idx + 1 < len(phrase):
                    w_end = phrase[focus_idx + 1]["start"]
                else:
                    w_end = phrase_end

                # Build the override-tagged text.
                parts: List[str] = []
                for j, txt in enumerate(all_texts):
                    if j == focus_idx:
                        parts.append(f"{{\\c&H00FFFF&}}{txt}{{\\c&HFFFFFF&}}")
                    else:
                        parts.append(txt)
                tagged_text = " ".join(parts)

                ass_start = _seconds_to_ass_ts(w_start)
                ass_end = _seconds_to_ass_ts(w_end)

                lines.append(
                    f"Dialogue: 0,{ass_start},{ass_end},Default,,0,0,0,,{tagged_text}"
                )

        output_path.write_text("\n".join(lines), encoding="utf-8")
        logger.debug("ASS subtitle file written to %s (%d phrases)", output_path, len(phrases))
        return output_path

    def _merge_audio_video_subs(
        self,
        video_path: Path,
        audio_path: Path,
        subs_path: Path,
        output_path: Path,
    ) -> Path:
        """
        Final merge: video + audio + burned-in ASS subtitles.

        Encoded as H.264 / AAC 128 kbps / 30 fps with ``movflags +faststart``
        for instant web playback.
        """
        # ASS filter path needs forward slashes and escaped colons on Windows.
        ass_filter_path = str(subs_path.resolve()).replace("\\", "/").replace(":", "\\:")

        cmd = [
            self.ffmpeg, "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-vf", f"ass='{ass_filter_path}'",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "128k",
            "-r", str(FPS),
            "-movflags", "+faststart",
            "-shortest",
            "-map", "0:v:0",
            "-map", "1:a:0",
            str(output_path),
        ]
        self._run_ffmpeg(cmd, "merge_final")
        return output_path


# ── Utility ──────────────────────────────────────────────────────────────────

def _seconds_to_ass_ts(seconds: float) -> str:
    """Convert seconds (float) to ASS timestamp ``H:MM:SS.cc``."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    # ASS uses centiseconds.
    return f"{h}:{m:02d}:{s:05.2f}"
