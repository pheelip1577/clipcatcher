import subprocess
import time
import os
import shutil
from pathlib import Path

# Find tools
streamlink = shutil.which("streamlink")
ffmpeg = shutil.which("ffmpeg")

print("streamlink path:", streamlink)
print("ffmpeg path:", ffmpeg)

if not streamlink or not ffmpeg:
    print("Error: streamlink or ffmpeg not found in PATH")
    exit(1)

# Temp directory
tmp_dir = Path("test_record_tmp")
tmp_dir.mkdir(exist_ok=True)

url = "https://twitch.tv/carterefe"
quality = "best"

print("Starting streamlink process...")
streamlink_proc = subprocess.Popen(
    [streamlink, "--stdout", url, quality],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,  # Capture stderr to debug!
)

print("Starting ffmpeg process...")
seg_pattern = str(tmp_dir / "seg_%06d.ts")
ffmpeg_proc = subprocess.Popen(
    [
        ffmpeg, "-y",
        "-i", "pipe:0",
        "-c", "copy",
        "-f", "segment",
        "-segment_time", "10",
        "-segment_format", "mpegts",
        "-reset_timestamps", "1",
        seg_pattern,
    ],
    stdin=streamlink_proc.stdout,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,  # Capture stderr to debug!
)

print("Recording for 15 seconds to test...")
time.sleep(15)

print("Stopping processes...")
streamlink_proc.terminate()
ffmpeg_proc.terminate()

# Wait and read stderr
stdout_sl, stderr_sl = streamlink_proc.communicate()
stdout_ff, stderr_ff = ffmpeg_proc.communicate()

print("\n--- Streamlink Stderr ---")
print(stderr_sl.decode("utf-8", errors="replace"))

print("\n--- Ffmpeg Stderr ---")
print(stderr_ff.decode("utf-8", errors="replace"))

print("\n--- Generated Files ---")
files = list(tmp_dir.glob("*.ts"))
print(f"Found {len(files)} files:")
for f in files:
    print(f"  - {f.name} (size: {f.stat().st_size} bytes)")

# Clean up
shutil.rmtree(tmp_dir)
print("Clean up finished.")
