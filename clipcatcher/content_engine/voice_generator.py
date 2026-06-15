"""
voice_generator.py — Speech Synthesis Pipeline.

Converts script narration segments into high-quality speech audio files using
edge-tts, capturing word-level boundaries for animated subtitles.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import edge_tts
from app.recorder import find_tool

logger = logging.getLogger(__name__)


@dataclass
class SubtitleWord:
    """Represents a single word with precise start and end timestamps in milliseconds."""
    text: str
    start_ms: int
    end_ms: int


@dataclass
class VoiceResult:
    """Result of generating voiceovers for a script."""
    audio_path: Path                      # Path to the combined final audio file
    subtitles: List[SubtitleWord]          # List of all word timings across the video
    segment_timings: List[Tuple[int, int]] # (start_ms, end_ms) per script segment
    total_duration_ms: int                 # Total audio duration in milliseconds


class VoiceGenerator:
    """Synthesizes speech using Microsoft Edge TTS (free) with word boundary capture."""

    def __init__(self, voice: str = "en-US-GuyNeural", rate: str = "+5%"):
        """
        Parameters
        ----------
        voice : str
            Edge-TTS voice name (e.g., 'en-US-GuyNeural' or 'en-US-AriaNeural').
        rate : str
            Speed change (e.g. '+5%' or '-10%').
        """
        self.voice = voice
        self.rate = rate
        self.ffmpeg = find_tool("ffmpeg")
        self.ffprobe = find_tool("ffprobe")
        if not self.ffprobe and self.ffmpeg:
            # Try to infer ffprobe path from ffmpeg path
            ffmpeg_path = Path(self.ffmpeg)
            ffprobe_name = "ffprobe.exe" if os.name == "nt" else "ffprobe"
            inferred = ffmpeg_path.parent / ffprobe_name
            if inferred.exists():
                self.ffprobe = str(inferred)

    async def generate(self, segments: List[Any], output_dir: Path) -> VoiceResult:
        """
        Generates audio files for all segments, concatenates them, and aligns subtitles.

        Parameters
        ----------
        segments : list[ScriptSegment]
            List of segments with narration texts.
        output_dir : Path
            Folder to store intermediate and final files.

        Returns
        -------
        VoiceResult
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        temp_files: List[Path] = []
        all_words: List[SubtitleWord] = []
        segment_timings: List[Tuple[int, int]] = []
        cumulative_offset_ms = 0

        # Create a workspace folder for temp files within output_dir
        temp_workspace = Path(tempfile.mkdtemp(dir=output_dir, prefix="voice_tmp_"))

        try:
            for idx, seg in enumerate(segments):
                narration = seg.narration.strip()
                if not narration:
                    # Skip empty narration or handle as pause
                    segment_timings.append((cumulative_offset_ms, cumulative_offset_ms))
                    continue

                seg_audio_path = temp_workspace / f"seg_{idx}.mp3"
                temp_files.append(seg_audio_path)

                # Generate TTS and collect word boundaries
                logger.info(f"Synthesizing segment {idx+1}/{len(segments)}...")
                seg_words = await self._synthesize_segment(narration, seg_audio_path)

                # Determine exact audio duration of this segment
                seg_duration_ms = self._get_audio_duration_ms(seg_audio_path)
                if seg_duration_ms <= 0:
                    # Fallback to last word timing if ffprobe failed
                    if seg_words:
                        seg_duration_ms = seg_words[-1].end_ms + 100
                    else:
                        seg_duration_ms = int(seg.duration_hint * 1000)

                # Shift all word boundary timings by cumulative_offset_ms
                for w in seg_words:
                    all_words.append(
                        SubtitleWord(
                            text=w.text,
                            start_ms=w.start_ms + cumulative_offset_ms,
                            end_ms=w.end_ms + cumulative_offset_ms
                        )
                    )

                # Log segment timing range
                start_ms = cumulative_offset_ms
                end_ms = cumulative_offset_ms + seg_duration_ms
                segment_timings.append((start_ms, end_ms))

                cumulative_offset_ms += seg_duration_ms

            # Concatenate all segment audio files using ffmpeg
            final_audio_path = output_dir / "narration.mp3"
            logger.info("Concatenating audio segments...")
            self._concat_audio_files(temp_files, final_audio_path)

            return VoiceResult(
                audio_path=final_audio_path,
                subtitles=all_words,
                segment_timings=segment_timings,
                total_duration_ms=cumulative_offset_ms
            )

        finally:
            # Clean up temporary workspace directory and its contents
            try:
                shutil = __import__("shutil")
                shutil.rmtree(temp_workspace, ignore_errors=True)
            except Exception as e:
                logger.warning(f"Failed to clean up voice temp workspace: {e}")

    def generate_sync(self, segments: List[Any], output_dir: Path) -> VoiceResult:
        """Synchronous wrapper for generate."""
        return asyncio.run(self.generate(segments, output_dir))

    async def _synthesize_segment(self, text: str, output_path: Path) -> List[SubtitleWord]:
        """Synthesizes a single text string to MP3 and returns relative word boundaries."""
        words: List[SubtitleWord] = []
        # Clean emojis to prevent TTS pronouncing them (e.g. 🧠 -> "brain")
        clean_text = self._strip_emojis(text)
        communicate = edge_tts.Communicate(clean_text, self.voice, rate=self.rate, boundary="WordBoundary")

        # Open file in binary write mode
        with open(output_path, "wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                elif chunk["type"] in ("WordBoundary", "word_boundary"):
                    # Offset and duration are returned in 100-nanosecond ticks
                    offset = chunk.get("offset", 0)
                    duration = chunk.get("duration", 0)
                    word_text = chunk.get("text", "")
                    
                    start_ms = int(offset // 10000)
                    duration_ms = int(duration // 10000)
                    
                    # Clean up punctuation from word text for clean display
                    cleaned_word = word_text.strip()
                    if cleaned_word:
                        words.append(
                            SubtitleWord(
                                text=cleaned_word,
                                start_ms=start_ms,
                                end_ms=start_ms + duration_ms
                            )
                        )
        return words

    def _get_audio_duration_ms(self, path: Path) -> int:
        """Queries ffprobe to find the exact duration of an audio file in ms."""
        if not self.ffprobe:
            return 0
        try:
            cmd = [
                self.ffprobe,
                "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path)
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            duration_s = float(res.stdout.strip())
            return int(duration_s * 1000)
        except Exception as e:
            logger.warning(f"ffprobe duration check failed for {path.name}: {e}")
            return 0

    def _concat_audio_files(self, paths: List[Path], output_path: Path):
        """Uses ffmpeg concat demuxer to merge audio files together."""
        if not self.ffmpeg:
            raise RuntimeError("ffmpeg not found — cannot concatenate audio files.")

        # Create concat list file
        list_file = output_path.parent / "voice_concat.txt"
        try:
            with open(list_file, "w", encoding="utf-8") as f:
                for p in paths:
                    # Escape paths for ffmpeg concat
                    escaped_path = str(p.absolute()).replace("\\", "/")
                    f.write(f"file '{escaped_path}'\n")

            cmd = [
                self.ffmpeg,
                "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(list_file.absolute()),
                "-c", "copy",
                str(output_path.absolute())
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                logger.error(f"ffmpeg audio concat failed: {res.stderr}")
                raise RuntimeError(f"ffmpeg audio concat failed with code {res.returncode}")
        finally:
            if list_file.exists():
                try:
                    list_file.unlink()
                except Exception:
                    pass

    def _strip_emojis(self, text: str) -> str:
        """Removes emojis and special symbols from text using unicodedata category checks."""
        import unicodedata
        cleaned = []
        for char in text:
            cat = unicodedata.category(char)
            # Keep letters (L), numbers (N), punctuation (P), separators/spaces (Z)
            # Strip symbols (S) and other control characters (C)
            if cat[0] in ('L', 'N', 'P', 'Z') or char == '\n':
                cleaned.append(char)
        return "".join(cleaned)
