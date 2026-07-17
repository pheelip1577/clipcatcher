import pytest
from unittest.mock import MagicMock, patch
from content_engine.scheduler import ContentScheduler
from content_engine.content_templates import ContentTemplate

@patch("content_engine.niche_loader.get_active_niche_name")
def test_scheduler_get_next_content_null_world_cup_data(mock_get_niche):
    mock_get_niche.return_value = "finance_tips"
    
    mock_settings = MagicMock()
    mock_settings.get.side_effect = lambda key, default=None: {
        "ce_max_uploads_per_day": 6,
        "ce_active_templates": ["wealth_hack", "saving_tip"],
        "ce_active_niche": "finance_tips"
    }.get(key, default)
    
    scheduler = ContentScheduler(mock_settings)
    scheduler._history = [] # clear history for clean test context
    
    # Mock templates dict
    templates = {
        "wealth_hack": ContentTemplate(
            name="wealth_hack",
            display_name="Wealth Hack",
            duration_range=(25, 40),
            segment_count_range=(4, 6),
            system_prompt="Create system prompt",
            user_prompt_template="Create user prompt",
            visual_style="mixed",
            default_pexels_queries=["money"],
            title_template="Title",
            default_tags=["tags"],
            hashtags=["#tags"]
        ),
        "saving_tip": ContentTemplate(
            name="saving_tip",
            display_name="Saving Tip",
            duration_range=(20, 35),
            segment_count_range=(3, 5),
            system_prompt="Create system prompt",
            user_prompt_template="Create user prompt",
            visual_style="stock",
            default_pexels_queries=["saving"],
            title_template="Title",
            default_tags=["tags"],
            hashtags=["#tags"]
        )
    }
    
    # Verify that get_next_content does not throw an error when world_cup_data is None
    next_content = scheduler.get_next_content(
        templates=templates,
        world_cup_data=None,
        template_name=None,
        ignore_quota=True
    )
    
    assert next_content is not None
    assert next_content["template_name"] in ["wealth_hack", "saving_tip"]
    assert "topic" in next_content
    assert "topic_data" in next_content
