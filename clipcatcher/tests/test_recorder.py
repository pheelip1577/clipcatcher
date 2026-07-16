import os
import time
from pathlib import Path
import pytest
from unittest.mock import MagicMock, patch
from app.recorder import StreamRecorder

def test_save_clip_excludes_open_segment(tmp_path):
    # Setup recorder
    save_dir = tmp_path / "clips"
    save_dir.mkdir()
    recorder = StreamRecorder(save_folder=str(save_dir))
    
    # Mock tmp dir for segments
    tmp_segments_dir = tmp_path / "tmp_segments"
    tmp_segments_dir.mkdir()
    recorder._tmp_dir = MagicMock()
    recorder._tmp_dir.name = str(tmp_segments_dir)
    
    # Create segment files
    seg1 = tmp_segments_dir / "seg_000000.ts"
    seg2 = tmp_segments_dir / "seg_000001.ts"
    seg3 = tmp_segments_dir / "seg_000002.ts"
    
    seg1.write_text("dummy1")
    seg2.write_text("dummy2")
    seg3.write_text("dummy3")
    
    # Set mtimes: seg1 and seg2 are old, seg3 is brand new (open segment)
    now = time.time()
    os.utime(seg1, (now - 10, now - 10))
    os.utime(seg2, (now - 5, now - 5))
    os.utime(seg3, (now, now))
    
    # Populate recorder segments
    recorder._segments = [seg1, seg2, seg3]
    recorder.ffmpeg = "ffmpeg"
    recorder.streamlink = "streamlink"
    recorder.tools_available = MagicMock(return_value=(True, "OK"))
    
    # Mock _get_segment_duration to return 10.0 seconds per segment
    recorder._get_segment_duration = MagicMock(return_value=10.0)
    
    # Mock subprocess.run to create the output file
    def mock_run(cmd, *args, **kwargs):
        out_file = Path(cmd[-1])
        out_file.write_text("fake video output")
        run_res = MagicMock()
        run_res.returncode = 0
        return run_res
    
    with patch("subprocess.run", side_effect=mock_run) as mock_subrun:
        # Save clip requesting 15s before, 5s after (total 20s)
        # Should exclude seg3 (since mtime is too new)
        # Thus should only use seg1 and seg2 (total duration = 20s)
        # start_offset should be max(0, 20 - 20) = 0
        res = recorder.save_clip(seconds_before=15, seconds_after=5, channel="test")
        
        # Verify result path
        assert res is not None
        assert res.name.startswith("test_")
        
        # Assert seg3 was excluded, and only seg1 and seg2 were written to concat file
        # Check arguments of subprocess.run
        called_args = mock_subrun.call_args[0][0]
        # Find the concat file path in the arguments
        concat_arg = None
        for i, arg in enumerate(called_args):
            if "concat" in arg and arg.endswith(".txt"):
                concat_arg = arg
                break
        
        assert concat_arg is not None
        concat_content = Path(concat_arg).read_text()
        assert f"file '{seg1.resolve()}'" in concat_content
        assert f"file '{seg2.resolve()}'" in concat_content
        assert f"file '{seg3.resolve()}'" not in concat_content
        
        # Assert start_offset (-ss) is 0.0 and duration (-t) is 20
        ss_idx = called_args.index("-ss")
        t_idx = called_args.index("-t")
        assert float(called_args[ss_idx + 1]) == 0.0
        assert int(called_args[t_idx + 1]) == 20

def test_save_clip_computes_offset_from_real_durations(tmp_path):
    save_dir = tmp_path / "clips"
    save_dir.mkdir()
    recorder = StreamRecorder(save_folder=str(save_dir))
    
    tmp_segments_dir = tmp_path / "tmp_segments"
    tmp_segments_dir.mkdir()
    recorder._tmp_dir = MagicMock()
    recorder._tmp_dir.name = str(tmp_segments_dir)
    
    seg1 = tmp_segments_dir / "seg_000000.ts"
    seg2 = tmp_segments_dir / "seg_000001.ts"
    seg1.write_text("dummy1")
    seg2.write_text("dummy2")
    
    # Make them both old so none are excluded
    now = time.time()
    os.utime(seg1, (now - 10, now - 10))
    os.utime(seg2, (now - 10, now - 10))
    
    recorder._segments = [seg1, seg2]
    recorder.ffmpeg = "ffmpeg"
    recorder.streamlink = "streamlink"
    recorder.tools_available = MagicMock(return_value=(True, "OK"))
    
    # Mock real segment durations: seg1 is 12.5s, seg2 is 9.5s (total 22s)
    durations = {seg1: 12.5, seg2: 9.5}
    recorder._get_segment_duration = lambda path: durations[path]
    
    # Mock subprocess.run to create the output file
    def mock_run(cmd, *args, **kwargs):
        out_file = Path(cmd[-1])
        out_file.write_text("fake video output")
        run_res = MagicMock()
        run_res.returncode = 0
        return run_res
    
    with patch("subprocess.run", side_effect=mock_run) as mock_subrun:
        # Request a clip of 15 seconds (total needed)
        # Cumulative duration is 22s.
        # start_offset should be cumulative_duration - total_needed = 22.0 - 15 = 7.0
        res = recorder.save_clip(seconds_before=10, seconds_after=5, channel="test")
        
        assert res is not None
        called_args = mock_subrun.call_args[0][0]
        
        ss_idx = called_args.index("-ss")
        t_idx = called_args.index("-t")
        assert float(called_args[ss_idx + 1]) == 7.0
        assert int(called_args[t_idx + 1]) == 15
