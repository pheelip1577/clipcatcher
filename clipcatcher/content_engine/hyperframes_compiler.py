"""
hyperframes_compiler.py — Video Compilation Pipeline using HeyGen HyperFrames

Assembles final 1080×1920 vertical videos (YouTube Shorts / TikTok)
by generating dynamic HTML pages and rendering them using the HyperFrames CLI.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from app.recorder import find_tool

logger = logging.getLogger(__name__)


class HyperframesCompilerError(RuntimeError):
    """Raised when any stage of the HyperFrames rendering pipeline fails."""


class HyperframesCompiler:
    """Renders vertical videos (1080×1920) by translating content to HTML/CSS/JS and calling HyperFrames."""

    def __init__(self, brand_config: Optional[Dict[str, Any]] = None) -> None:
        self.brand = brand_config or {}
        self.channel_name = self.brand.get("channel_name", "World Cup Central")
        
        # Locate ffmpeg/ffprobe to verify dependencies
        self.ffmpeg = find_tool("ffmpeg")
        if not self.ffmpeg:
            logger.warning("ffmpeg not found on path. HyperFrames may fail to render audio/video.")

    def compile(
        self,
        audio_path: str | Path,
        visual_segments: Sequence[Dict[str, Any]],
        subtitles: Sequence[Dict[str, Any]],
        output_path: str | Path,
        subtitle_style: str = "word_highlight",
    ) -> Path:
        """
        HyperFrames compilation pipeline.

        Parameters
        ----------
        audio_path : path
            Path to the narration audio file.
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
            Subtitle styling key (passed from ContentEngine, ignored or mapped in HTML).

        Returns
        -------
        Path
            The absolute path to the produced .mp4 file.
        """
        audio_path = Path(audio_path)
        output_path = Path(output_path)
        if not audio_path.is_file():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 1. Calculate total duration
        total_duration_s = sum(float(seg["duration"]) for seg in visual_segments)

        # 2. Format subtitles
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

        # 3. Create working directory inside the output folder (avoids cross-volume moves)
        work_dir = output_path.parent / f".hf_tmp_{os.getpid()}"
        work_dir.mkdir(parents=True, exist_ok=True)
        logger.info("HyperFrames Working Directory: %s", work_dir)

        try:
            # 4. Copy assets into the working directory with relative names
            # This bypasses browser sandbox cross-origin limitations when rendering local HTML
            rel_audio_name = "narration.mp3"
            shutil.copy2(audio_path, work_dir / rel_audio_name)

            rel_visual_segments = []
            for idx, seg in enumerate(visual_segments):
                seg_path = Path(seg["path"])
                if not seg_path.is_file():
                    raise FileNotFoundError(f"Visual segment file not found: {seg_path}")
                
                # Copy and assign relative slide path
                suffix = seg_path.suffix or ".jpg"
                rel_name = f"slide_{idx}{suffix}"
                shutil.copy2(seg_path, work_dir / rel_name)
                
                rel_visual_segments.append({
                    "type": seg.get("type", "image"),
                    "path": rel_name,
                    "duration": float(seg["duration"])
                })

            # 5. Load and populate the HTML template
            template_path = Path(__file__).parent / "templates" / "shorts_template.html"
            if not template_path.exists():
                raise FileNotFoundError(f"HyperFrames template not found: {template_path}")
            
            html_content = template_path.read_text(encoding="utf-8")

            # Construct the dynamic JS payload
            payload = {
                "channel_name": self.channel_name,
                "duration_s": total_duration_s,
                "audio_path": rel_audio_name,
                "visual_segments": rel_visual_segments,
                "subtitles": formatted_subs
            }

            # Replace the script tag content using regular expression
            payload_script = (
                f'<script id="shorts-payload">\n'
                f'    window.shortsPayload = {json.dumps(payload, indent=4)};\n'
                f'  </script>'
            )
            html_content = re.sub(
                r'<script id="shorts-payload">.*?</script>',
                lambda m: payload_script,
                html_content,
                flags=re.DOTALL
            )

            # Statically update data-duration on the stage and audio elements in the HTML content
            html_content = re.sub(
                r'data-duration="\d+(\.\d+)?"',
                f'data-duration="{total_duration_s:.3f}"',
                html_content
            )

            # Write index.html to the working directory
            index_path = work_dir / "index.html"
            index_path.write_text(html_content, encoding="utf-8")
            logger.info("Generated rendering index.html")

            # 6. Execute hyperframes render CLI via npx
            # Output goes to temporary render.mp4 in the same working directory
            temp_mp4 = work_dir / "render.mp4"
            cmd = [
                "npx", "hyperframes", "render", ".",
                "-o", "render.mp4"
            ]

            logger.info("Running hyperframes render CLI: %s", " ".join(cmd))
            
            # Run command synchronously with working directory set to work_dir
            result = subprocess.run(
                cmd,
                capture_output=True,
                cwd=str(work_dir),
                text=True,
                shell=True if os.name == "nt" else False
            )

            if result.returncode != 0:
                stderr_output = result.stderr or result.stdout
                logger.error("HyperFrames render failed (rc=%d):\n%s", result.returncode, stderr_output)
                raise HyperframesCompilerError(
                    f"npx hyperframes render failed with code {result.returncode}. Error output:\n{stderr_output}"
                )

            if not temp_mp4.exists():
                raise HyperframesCompilerError("npx hyperframes completed, but render.mp4 was not created.")

            # 7. Move compiled video to the requested output path
            shutil.move(str(temp_mp4), str(output_path))
            logger.info("Successfully compiled video using HyperFrames: %s", output_path)

            return output_path.resolve()

        finally:
            # Clean up working directory with retries (helps on Windows due to delayed file locks)
            import time
            for attempt in range(5):
                try:
                    if work_dir.exists():
                        shutil.rmtree(work_dir)
                    logger.debug("Cleaned up working directory")
                    break
                except Exception as e:
                    if attempt == 4:
                        logger.warning("Could not remove temp directory %s after 5 attempts: %s", work_dir, e)
                    else:
                        time.sleep(0.5)
