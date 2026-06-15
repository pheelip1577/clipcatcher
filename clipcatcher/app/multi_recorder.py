"""
Multi-stream recorder manager.
Handles recording multiple Twitch channels in parallel and compiling them into a 2x2 layout vertical video.
"""
import subprocess
import threading
import time
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Callable
from datetime import datetime

from app.recorder import StreamRecorder, find_tool


def get_ffmpeg_font_arg() -> str:
    """Returns the font name argument for drawtext filter."""
    return "font='Arial':"


def escape_ffmpeg_text(text: str) -> str:
    """Escapes special characters in text for FFmpeg's drawtext filter."""
    t = text.replace('\\', '\\\\')
    t = t.replace(':', '\\:')
    t = t.replace("'", "")
    t = t.replace('%', '\\%')
    t = t.replace(',', '\\,')
    t = t.replace(';', '\\;')
    return t


class MultiStreamRecorder:
    """
    Manages multiple StreamRecorder instances concurrently.
    Provides utility to clip all active streams and compile them.
    """

    def __init__(self, save_folder: str):
        self.save_folder = Path(save_folder)
        self.save_folder.mkdir(parents=True, exist_ok=True)
        self._recorders: Dict[str, StreamRecorder] = {}
        self._lock = threading.Lock()
        
        self.on_error: Optional[Callable[[str], None]] = None
        self.on_status: Optional[Callable[[str], None]] = None

    def start_recording(self, channels: List[str], quality: str = "720p") -> bool:
        """Start recording a list of channels in parallel."""
        self.stop_all()
        
        with self._lock:
            for ch in channels:
                ch = ch.lower().strip()
                if not ch:
                    continue
                
                # We save channels to their own subfolders within save_folder/temp_recordings
                rec = StreamRecorder(str(self.save_folder / "temp_recordings" / ch))
                rec.on_error = lambda msg, c=ch: self._handle_recorder_error(c, msg)
                rec.on_status = lambda msg, c=ch: self._handle_recorder_status(c, msg)
                
                if rec.start(ch, quality):
                    self._recorders[ch] = rec
                else:
                    if self.on_error:
                        self.on_error(f"Failed to start recording for {ch}")
        
        return len(self._recorders) > 0

    def stop_all(self):
        """Stop all active recorders."""
        with self._lock:
            for ch, rec in self._recorders.items():
                try:
                    rec.stop()
                except Exception:
                    pass
            self._recorders.clear()

    def get_active_channels(self) -> List[str]:
        with self._lock:
            return list(self._recorders.keys())

    def _handle_recorder_error(self, channel: str, msg: str):
        if self.on_error:
            self.on_error(f"[{channel.upper()}] {msg}")

    def _handle_recorder_status(self, channel: str, msg: str):
        if self.on_status:
            self.on_status(f"[{channel.upper()}] {msg}")

    def save_grid_clip(
        self,
        channels: List[str],
        seconds_before: int = 15,
        seconds_after: int = 10,
        match_title: str = "WORLD CUP 2026",
        match_score: str = "LIVE REACTION",
    ) -> Optional[Path]:
        """
        Clips all channels and compiles them into a 2x2 grid video.
        """
        # Ensure we have ffmpeg available
        ffmpeg = find_tool("ffmpeg")
        if not ffmpeg:
            if self.on_error:
                self.on_error("ffmpeg not found. Cannot compile grid.")
            return None

        # 1. Trigger clips in parallel for all channels
        clip_paths: Dict[str, Optional[Path]] = {}
        threads = []
        
        def cut_clip(ch: str):
            rec = None
            with self._lock:
                rec = self._recorders.get(ch)
            if rec:
                try:
                    p = rec.save_clip(seconds_before, seconds_after, ch)
                    clip_paths[ch] = p
                except Exception as e:
                    clip_paths[ch] = None
                    self._handle_recorder_error(ch, f"Clip cut failed: {e}")
            else:
                clip_paths[ch] = None

        for ch in channels:
            t = threading.Thread(target=cut_clip, args=(ch,), daemon=True)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Check if we got at least one clip
        valid_clips = {ch: p for ch, p in clip_paths.items() if p and p.exists()}
        if not valid_clips:
            if self.on_error:
                self.on_error("Could not capture any clips from active streams.")
            return None

        # 2. Assemble 2x2 Grid via FFmpeg
        # Output file path
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_name = f"grid_{'_'.join(channels[:2])}_{ts}.mp4"
        out_path = self.save_folder / out_name

        total_duration = seconds_before + seconds_after

        # Call compilation helper
        success = assemble_2x2_grid(
            ffmpeg=ffmpeg,
            channels=channels,
            clip_paths=clip_paths,
            out_path=out_path,
            duration=total_duration,
            match_title=match_title,
            match_score=match_score
        )

        # 3. Clean up the individual temp clips
        for p in valid_clips.values():
            try:
                p.unlink()
            except Exception:
                pass

        if success and out_path.exists():
            return out_path
        return None


def assemble_2x2_grid(
    ffmpeg: str,
    channels: List[str],
    clip_paths: Dict[str, Optional[Path]],
    out_path: Path,
    duration: int = 25,
    match_title: str = "WORLD CUP 2026",
    match_score: str = "LIVE REACTION"
) -> bool:
    """
    FFmpeg compilation engine: stitches 4 feeds into a 1080x1920 9:16 layout.
    Features:
      - Top Banner (1080x120) with live scoreboard text
      - 2x2 Grid of 4 streamers, cropped to 540x900 each
      - Fallback to offline slate if streamer feed is missing
      - Blended audio mix of all active streams
    """
    # Pad channels to exactly 4 for the 2x2 grid layout
    channels_padded = list(channels)
    while len(channels_padded) < 4:
        channels_padded.append(f"Slot {len(channels_padded)+1}")
    channels_padded = channels_padded[:4]

    inputs = []
    filter_inputs = []
    audio_inputs = []
    
    # We will build filters for all 4 quadrants
    video_filters = []
    font_arg = get_ffmpeg_font_arg()

    input_counter = 0

    for i in range(4):
        ch = channels_padded[i]
        path = clip_paths.get(ch)
        
        # Quadrant label: uppercase streamer name (escaped)
        label = escape_ffmpeg_text(ch.upper())

        if path and Path(path).exists():
            # Valid input file
            inputs.extend(["-i", str(path)])
            
            # Crop 16:9 input dynamically to 3:5 aspect ratio, scale to 540x900, draw label
            crop_filter = (
                f"[{input_counter}:v]crop=2*trunc(in_h*3/10):in_h:(in_w-2*trunc(in_h*3/10))/2:0,"
                f"scale=540:960,"  # Scale slightly larger first to ensure drawtext bounds
                f"drawtext={font_arg}text='{label}':x=20:y=20:fontsize=28:fontcolor=white:"
                f"box=1:boxcolor=black@0.6:boxborderw=8,"
                f"scale=540:900[v{i}]"  # Scale to final 540x900 size
            )
            video_filters.append(crop_filter)
            audio_inputs.append(f"[{input_counter}:a]")
            input_counter += 1
        else:
            # Offline placeholder: solid dark color box (540x900)
            offline_color = "0x13131a"
            placeholder_filter = (
                f"color=c={offline_color}:s=540x900:d={duration}[v{i}_raw];"
                f"[v{i}_raw]drawtext={font_arg}text='{label} (OFFLINE)':x=(w-text_w)/2:y=(h-text_h)/2:"
                f"fontsize=24:fontcolor=gray:box=1:boxcolor=black@0.6:boxborderw=6[v{i}]"
            )
            video_filters.append(placeholder_filter)

    # Scoreboard top banner: 1080x120 solid color + 2 rows of text (escaped)
    esc_title = escape_ffmpeg_text(match_title.upper())
    esc_score = escape_ffmpeg_text(match_score.upper())
    scoreboard_filter = (
        f"color=c=0x0c0c10:s=1080x120:d={duration}[score_raw];"
        f"[score_raw]drawtext={font_arg}text='{esc_title}':x=(w-text_w)/2:y=20:fontsize=26:fontcolor=white,"
        f"drawtext={font_arg}text='{esc_score}':x=(w-text_w)/2:y=65:fontsize=32:fontcolor=lime[score_banner]"
    )
    video_filters.append(scoreboard_filter)

    # Grid stacking filters
    grid_assembly = (
        f"[v0][v1]hstack=inputs=2[top_row];"
        f"[v2][v3]hstack=inputs=2[bottom_row];"
        f"[score_banner][top_row][bottom_row]vstack=inputs=3[v]"
    )
    video_filters.append(grid_assembly)

    # Audio mixing filter
    if audio_inputs:
        audio_filter = f"{''.join(audio_inputs)}amix=inputs={len(audio_inputs)}:duration=first[a]"
    else:
        # Generate silence if no streams were active
        audio_filter = f"anullsrc=r=44100:cl=stereo:d={duration}[a]"
    video_filters.append(audio_filter)

    # Final combined filter complex string
    filter_complex = ";\n".join(video_filters)

    cmd = [
        ffmpeg, "-y",
    ]
    # Add input files
    cmd.extend(inputs)
    
    # Check if we need virtual audio sources
    if not audio_inputs:
        cmd.extend(["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"])
        # If we added anullsrc as an input, adjust input index in filter complex
        # But we handled silent track directly inside filter complex, so no need
        pass

    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "[a]",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-movflags", "+faststart",
        str(out_path)
    ])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=180,
        )
        if result.returncode == 0 and out_path.exists():
            return True
        else:
            err = result.stderr.decode("utf-8", errors="replace")[-600:]
            print(f"FFmpeg Grid Compilation failed:\n{err}", file=sys.stderr)
            return False
    except subprocess.TimeoutExpired:
        print("FFmpeg Grid Compilation timed out (180s limit)", file=sys.stderr)
        return False
    except Exception as e:
        print(f"FFmpeg Grid Compilation exception: {e}", file=sys.stderr)
        return False
