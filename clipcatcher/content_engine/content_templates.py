"""
Content Templates for AI YouTube Shorts Engine.
Defines template classes and helper functions, loaded dynamically from the active niche pack.
"""

from dataclasses import dataclass, field
from typing import Optional
from app.settings import Settings
from content_engine.niche_loader import load_niche

@dataclass
class ScriptSegment:
    """A single segment of a video script."""
    narration: str          # What the TTS voice will say
    visual_cue: str         # What image/graphic to show
    duration_hint: float    # Suggested duration in seconds


@dataclass
class VideoScript:
    """Complete output produced by an LLM from a content template."""
    segments: list          # list of ScriptSegment dicts
    title: str              # YouTube title
    description: str        # YouTube description
    tags: list              # YouTube tags
    thumbnail_text: str     # Bold text for thumbnail
    content_type: str       # Template name
    topic: str              # Specific topic


@dataclass
class ContentTemplate:
    """Blueprint for one category of YouTube Shorts content."""
    name: str                    # 'match_preview', 'player_profile', etc.
    display_name: str            # 'Match Preview'
    duration_range: tuple        # (min_seconds, max_seconds)
    segment_count_range: tuple   # (min_segments, max_segments)
    system_prompt: str           # Full LLM system prompt
    user_prompt_template: str    # LLM user prompt with {placeholders}
    visual_style: str            # 'stock_footage', 'text_cards', 'mixed'
    default_pexels_queries: list # Default search terms
    title_template: str          # YouTube title format
    default_tags: list           # Default tags
    hashtags: list               # Description hashtags


TEMPLATES: dict[str, ContentTemplate] = {}
_loaded_niche_name = None

def _check_and_load_niche_templates():
    global _loaded_niche_name
    s = Settings()
    active_name = s.get("ce_active_niche", "world_cup_2026")
    if active_name != _loaded_niche_name:
        try:
            niche = load_niche(active_name)
            TEMPLATES.clear()
            for t_data in niche.get_templates_data():
                TEMPLATES[t_data["name"]] = ContentTemplate(
                    name=t_data["name"],
                    display_name=t_data["display_name"],
                    duration_range=tuple(t_data["duration_range"]),
                    segment_count_range=tuple(t_data["segment_count_range"]),
                    system_prompt=t_data["system_prompt"],
                    user_prompt_template=t_data["user_prompt_template"],
                    visual_style=t_data["visual_style"],
                    default_pexels_queries=t_data.get("default_pexels_queries") or t_data.get("pexels_queries") or [],
                    title_template=t_data["title_template"],
                    default_tags=t_data["default_tags"],
                    hashtags=t_data["hashtags"]
                )
            _loaded_niche_name = active_name
        except Exception as e:
            print(f"Error loading niche templates: {e}")


def get_template(name: str) -> ContentTemplate:
    """Look up a ContentTemplate by name."""
    _check_and_load_niche_templates()
    if name not in TEMPLATES:
        available = list(TEMPLATES.keys())
        raise KeyError(
            f"Unknown template '{name}'. Available templates: {available}"
        )
    return TEMPLATES[name]


def get_all_templates() -> list[ContentTemplate]:
    """Return a list of every registered ContentTemplate."""
    _check_and_load_niche_templates()
    return list(TEMPLATES.values())


def get_active_templates(active_names: list[str]) -> list[ContentTemplate]:
    """Return only the templates whose names appear in *active_names*."""
    _check_and_load_niche_templates()
    templates = []
    for name in active_names:
        if name in TEMPLATES:
            templates.append(get_template(name))
    return templates
