import json
import pytest
from unittest.mock import MagicMock, patch
from content_engine.script_generator import ScriptGenerator, ScriptGeneratorError
from content_engine.content_templates import ContentTemplate

def test_script_generator_mock_mode():
    # When api_key is empty/None, it runs in mock mode
    generator = ScriptGenerator(api_key="")
    
    template = ContentTemplate(
        name="test_temp",
        display_name="Test Template",
        duration_range=(15, 30),
        segment_count_range=(2, 4),
        system_prompt="System Prompt",
        user_prompt_template="Create script about: {topic}",
        visual_style="stock",
        default_pexels_queries=["soccer"],
        title_template="Awesome {topic} Video!",
        default_tags=["test"],
        hashtags=["#Test"]
    )
    
    script = generator.generate(template, topic_data={"topic": "Compound Interest"})
    assert script.topic == "Compound Interest"
    assert "Compound Interest" in script.title
    assert len(script.segments) == 3
    assert script.segments[0].narration.startswith("Welcome to the ultimate update on Compound Interest!")

@patch("google.genai.Client")
def test_script_generator_real_api(mock_client_class):
    # Mock response
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "title": "Compounding Wealth Secret! 🚀",
        "description": "Learn the 8th wonder of the world.",
        "tags": ["compound", "interest", "finance"],
        "segments": [
            {"narration": "This is segment 1 text", "visual_cue": "chart zoom", "duration_hint": 5.0},
            {"narration": "This is segment 2 text", "visual_cue": "piggy bank", "duration_hint": 4.5}
        ],
        "thumbnail_text": "GET RICH"
    })
    
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response
    mock_client_class.return_value = mock_client
    
    # Initialize real mode generator
    generator = ScriptGenerator(api_key="fake-key")
    
    template = ContentTemplate(
        name="wealth_hack",
        display_name="Wealth Building Hack",
        duration_range=(25, 40),
        segment_count_range=(4, 6),
        system_prompt="Create exciting hack",
        user_prompt_template="Topic: {topic}",
        visual_style="mixed",
        default_pexels_queries=["money"],
        title_template="How to Hack {topic}!",
        default_tags=["wealth", "hacks"],
        hashtags=["#WealthHacks"]
    )
    
    script = generator.generate(template, topic_data={"topic": "Compound Interest"})
    
    # Verify properties
    assert script.title == "Compounding Wealth Secret! 🚀"
    assert len(script.segments) == 2
    assert script.segments[0].narration == "This is segment 1 text"
    assert script.segments[0].duration_hint == 5.0
    assert "wealth" in script.tags
    assert "#WealthHacks" in script.description
