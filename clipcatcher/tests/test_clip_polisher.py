import json
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from content_engine.clip_polisher import ClipPolisher

@patch("google.genai.Client")
@patch("subprocess.run")
def test_clip_polisher_flow(mock_run, mock_client_class, tmp_path):
    # Setup temporary files
    input_clip = tmp_path / "test_clip.mp4"
    input_clip.write_text("dummy video content")
    
    output_clip = tmp_path / "polished_test_clip.mp4"
    
    # Mock settings
    mock_settings = MagicMock()
    mock_settings.get.side_effect = lambda key, default=None: {
        "ce_gemini_api_key": "fake-key",
        "ce_polish_review_folder": str(tmp_path)
    }.get(key, default)
    
    # Mock subprocess.run for ffmpeg
    def mock_run_side_effect(cmd, *args, **kwargs):
        # The last arg of cmd is the output path
        out_path = Path(cmd[-1])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("mocked output")
        return MagicMock(returncode=0)
    mock_run.side_effect = mock_run_side_effect
    
    # Mock Gemini Client and API
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    # Mock Client.files.upload
    mock_file_ref = MagicMock()
    mock_file_ref.name = "files/test-file"
    mock_file_ref.state.name = "ACTIVE"
    mock_client.files.upload.return_value = mock_file_ref
    mock_client.files.get.return_value = mock_file_ref
    
    # Mock Client.models.generate_content for transcription and metadata
    mock_transcribe_response = MagicMock()
    mock_transcribe_response.text = json.dumps({
        "words": [
            {"word": "Welcome", "start": 0.0, "end": 0.5},
            {"word": "to", "start": 0.5, "end": 0.8},
            {"word": "ClipCatcher", "start": 0.8, "end": 1.5}
        ]
    })
    
    mock_meta_response = MagicMock()
    mock_meta_response.text = json.dumps({
        "title": "Welcome to ClipCatcher! 🏆 #Shorts",
        "description": "Viral description here!",
        "tags": ["clipcatcher", "viral", "shorts"]
    })
    
    mock_client.models.generate_content.side_effect = [
        mock_transcribe_response,  # First call: transcription
        mock_meta_response         # Second call: metadata
    ]
    
    # Initialize and run polisher
    polisher = ClipPolisher(mock_settings)
    result = polisher.polish_clip(input_clip, output_clip)
    
    # Assert result structure
    assert result["video_path"] == output_clip
    assert result["title"] == "Welcome to ClipCatcher! 🏆 #Shorts"
    assert result["transcription"] == "Welcome to ClipCatcher"
    assert output_clip.exists()
    assert output_clip.with_suffix(".json").exists()
    
    # Verify metadata was saved properly in sidecar JSON
    with open(output_clip.with_suffix(".json"), "r") as f:
        saved_meta = json.load(f)
    assert saved_meta["title"] == "Welcome to ClipCatcher! 🏆 #Shorts"
    assert saved_meta["tags"] == ["clipcatcher", "viral", "shorts"]
