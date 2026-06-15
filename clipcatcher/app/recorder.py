"""
Stream recorder.
Uses streamlink to get the stream URL and ffmpeg to record a rolling buffer,
then cuts clips from that buffer when triggered.
"""
import subprocess
import threading
import time
import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional, Callable
from datetime import datetime


def find_tool(name: str) -> Optional[str]:
    """Find a binary in PATH or common install locations."""
    path = shutil.which(name)
    if path:
        return path
    # Windows extras
    extras = []
    if os.name == "nt":
        extras = [
            rf"C:\Program Files\ffmpeg\bin\{name}.exe",
            rf"C:\ffmpeg\bin\{name}.exe",
            os.path.join(os.path.expanduser("~"), "ffmpeg", "bin", f"{name}.exe"),
        ]
    for e in extras:
        if os.path.isfile(e):
            return e
    return None


class StreamRecorder:
    """
    Records a Twitch stream to a rolling temp file using streamlink + ffmpeg.
    When triggered, cuts the last N seconds as a clip.

    Architecture:
      streamlink stdout → ffmpeg stdin → rolling segment files on disk
      On trigger: ffmpeg concat + trim the relevant segments → output clip
    """

    SEGMENT_DURATION = 10   # seconds per segment file
    MAX_SEGMENTS = 30       # keep 30 × 10s = 5 min of rolling buffer

    def __init__(self, save_folder: str):
        self.save_folder = Path(save_folder)
        self.save_folder.mkdir(parents=True, exist_ok=True)

        self._tmp_dir: Optional[tempfile.TemporaryDirectory] = None
        self._streamlink_proc: Optional[subprocess.Popen] = None
        self._ffmpeg_proc: Optional[subprocess.Popen] = None
        self._record_thread: Optional[threading.Thread] = None
        self._running = False
        self._segments: list[Path] = []
        self._segments_lock = threading.Lock()

        self.on_error: Optional[Callable[[str], None]] = None
        self.on_status: Optional[Callable[[str], None]] = None

        # Tool paths
        self.streamlink = find_tool("streamlink")
        self.ffmpeg = find_tool("ffmpeg")

    def tools_available(self) -> tuple[bool, str]:
        """Check if required tools are installed. Returns (ok, message)."""
        missing = []
        if not self.streamlink:
            missing.append("streamlink")
        if not self.ffmpeg:
            missing.append("ffmpeg")
        if missing:
            return False, f"Missing tools: {', '.join(missing)}. See README for install instructions."
        return True, "OK"

    def start(self, channel: str, quality: str = "best") -> bool:
        """Start recording. Returns True if started successfully."""
        ok, msg = self.tools_available()
        if not ok:
            if self.on_error:
                self.on_error(msg)
            return False

        self._tmp_dir = tempfile.TemporaryDirectory(prefix="clipcatcher_")
        self._running = True
        self._segments = []

        self._record_thread = threading.Thread(
            target=self._record_loop,
            args=(channel, quality),
            daemon=True,
        )
        self._record_thread.start()
        return True

    def stop(self):
        """Stop recording and clean up."""
        self._running = False
        for proc in (self._streamlink_proc, self._ffmpeg_proc):
            if proc:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
        if self._tmp_dir:
            try:
                self._tmp_dir.cleanup()
            except Exception:
                pass

    def save_clip(
        self,
        seconds_before: int = 15,
        seconds_after: int = 10,
        channel: str = "clip",
    ) -> Optional[Path]:
        """
        Cut a clip from the rolling buffer.
        Returns the path to the saved .mp4, or None on failure.
        """
        ok, msg = self.tools_available()
        if not ok:
            if self.on_error:
                self.on_error(msg)
            return None

        with self._segments_lock:
            segs = list(self._segments)

        if not segs:
            if self.on_error:
                self.on_error("No recorded data yet - wait a few seconds after connecting")
            return None

        # Figure out which segments we need
        total_needed = seconds_before + seconds_after
        segs_needed = max(1, (total_needed // self.SEGMENT_DURATION) + 2)
        relevant = segs[-segs_needed:]

        # Write concat list
        concat_file = Path(self._tmp_dir.name) / f"concat_{int(time.time())}.txt"
        with open(concat_file, "w") as f:
            for s in relevant:
                f.write(f"file '{s}'\n")

        # Output path
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = self.save_folder / f"{channel}_{ts}.mp4"

        # Use ffmpeg to concat and trim to the desired duration
        # We take from (total_concat_duration - seconds_before - seconds_after) to end
        concat_duration = len(relevant) * self.SEGMENT_DURATION
        start_offset = max(0, concat_duration - seconds_before - seconds_after)

        cmd = [
            self.ffmpeg, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-ss", str(start_offset),
            "-t", str(total_needed),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-movflags", "+faststart",
            str(out_path),
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                stdin=subprocess.DEVNULL,
                timeout=60,
            )
            if result.returncode == 0 and out_path.exists():
                return out_path
            else:
                err = result.stderr.decode("utf-8", errors="replace")[-500:]
                if self.on_error:
                    self.on_error(f"ffmpeg clip error: {err}")
                return None
        except subprocess.TimeoutExpired:
            if self.on_error:
                self.on_error("ffmpeg timed out cutting clip")
            return None
        except Exception as e:
            if self.on_error:
                self.on_error(f"Clip save failed: {e}")
            return None

    # ── Internal ──────────────────────────────────────────────────────────

    def _record_loop(self, channel: str, quality: str):
        """Main recording loop: streamlink → ffmpeg segment files."""
        url = f"https://twitch.tv/{channel}"
        seg_num = [0]

        def next_seg_path() -> Path:
            p = Path(self._tmp_dir.name) / f"seg_{seg_num[0]:06d}.ts"
            seg_num[0] += 1
            return p

        # Start streamlink to get raw stream
        try:
            self._streamlink_proc = subprocess.Popen(
                [
                    self.streamlink,
                    "--stdout",
                    url,
                    quality,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            if self.on_error:
                self.on_error(f"streamlink failed to start: {e}")
            return

        if self.on_status:
            self.on_status("Buffering stream...")

        # Pipe streamlink into ffmpeg which writes SEGMENT_DURATION-second segments
        seg_pattern = str(Path(self._tmp_dir.name) / "seg_%06d.ts")
        try:
            self._ffmpeg_proc = subprocess.Popen(
                [
                    self.ffmpeg, "-y",
                    "-i", "pipe:0",
                    "-c", "copy",
                    "-f", "segment",
                    "-segment_time", str(self.SEGMENT_DURATION),
                    "-segment_format", "mpegts",
                    "-reset_timestamps", "1",
                    seg_pattern,
                ],
                stdin=self._streamlink_proc.stdout,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            if self.on_error:
                self.on_error(f"ffmpeg failed to start: {e}")
            return

        # Watch the tmp dir for new segment files and track them
        tmp = Path(self._tmp_dir.name)
        seen: set = set()

        while self._running:
            time.sleep(1)
            current = sorted(tmp.glob("seg_*.ts"))
            for seg in current:
                if seg not in seen:
                    seen.add(seg)
                    with self._segments_lock:
                        self._segments.append(seg)
                        # Trim old segments
                        while len(self._segments) > self.MAX_SEGMENTS:
                            old = self._segments.pop(0)
                            try:
                                old.unlink()
                            except Exception:
                                pass

            if self._ffmpeg_proc.poll() is not None:
                if self._running and self.on_error:
                    self.on_error("Recording stopped unexpectedly — is the channel live?")
                break
