import json
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from content_engine.niche_loader import NichePack, list_niches, load_niche

def test_list_niches():
    niches = list_niches()
    assert "world_cup_2026" in niches
    assert "history_facts" in niches
    assert "finance_tips" in niches

def test_load_niche():
    niche = load_niche("finance_tips")
    assert niche.display_name == "Money Minute 💸"
    assert niche.channel_name == "Money Minute"
    assert "finance_hacks" in niche.topic_pools
    assert len(niche.get_templates_data()) == 2

def test_get_topic_options():
    niche = load_niche("history_facts")
    options = niche.get_topic_options("quiz", produced=set())
    assert len(options) > 0
    topic, data = options[0]
    assert isinstance(topic, str)
    assert isinstance(data, dict)
    assert "question" in data
    assert "options" in data

def test_is_pool_low():
    niche = load_niche("finance_tips")
    niche.topic_pools = {
        "finance_hacks": [
            {"topic": "The Power of Compound Interest"},
            {"topic": "High-Yield Savings Accounts"},
            {"topic": "The 50/30/20 Budgeting Hack"}
        ]
    }
    assert niche.is_pool_low("finance_hacks", produced_set=set()) is True
    
    produced = {"wealth_hack:The Power of Compound Interest", 
                "wealth_hack:High-Yield Savings Accounts", 
                "wealth_hack:The 50/30/20 Budgeting Hack"}
    assert niche.is_pool_low("finance_hacks", produced_set=produced) is True

@patch("google.genai.Client")
def test_refill_pool(mock_client_class, tmp_path):
    # Initialize using a real niche to avoid constructor failures
    niche = load_niche("finance_tips")
    
    # Override path to temporary directory for saving
    temp_niche_path = tmp_path / "temp_niche.json"
    niche.path = temp_niche_path
    
    # Setup mock data inside the niche
    niche.topic_pools = {
        "test_pool": [
            {"topic": "Existing 1", "desc": "Desc 1"},
            {"topic": "Existing 2", "desc": "Desc 2"}
        ]
    }
    niche._data = {
        "name": "temp_niche",
        "display_name": "Temp Niche",
        "topic_pools": niche.topic_pools,
        "templates": [
            {
                "name": "temp_template",
                "topic_pool": "test_pool"
            }
        ]
    }
    
    # Save the initial mock data
    niche.save()
    
    # Mock Gemini response
    mock_response = MagicMock()
    mock_response.text = '{"new_entries": [{"topic": "New 1", "desc": "New Desc 1"}, {"topic": "New 2", "desc": "New Desc 2"}]}'
    
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response
    mock_client_class.return_value = mock_client
    
    # Call refill
    niche.refill_pool("test_pool", api_key="fake-key", count=2)
    
    # Check that topic pool now has 4 items
    pool = niche.topic_pools["test_pool"]
    assert len(pool) == 4
    assert pool[2]["topic"] == "New 1"
    assert pool[3]["topic"] == "New 2"
    
    # Verify it was saved back to file
    with open(temp_niche_path, "r") as f:
        saved_data = json.load(f)
    assert len(saved_data["topic_pools"]["test_pool"]) == 4
