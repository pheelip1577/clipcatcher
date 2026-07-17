"""
Content scheduler and calendar for ContentEngine.
Manages which content to produce next, tracks production history,
respects YouTube quota limits, and handles timing.
"""
import json
import logging
import random
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

HISTORY_PATH = Path.home() / ".clipcatcher" / "ce_history.json"
IDEAS_POOL_PATH = Path.home() / ".clipcatcher" / "ce_inspiration_ideas.json"


class ContentScheduler:
    """
    Manages the content production calendar.
    - Rotates through active content templates
    - Avoids duplicate topics
    - Prioritizes timely content (match previews for upcoming matches)
    - Tracks production history
    """

    def __init__(self, settings):
        self.settings = settings
        self._history = self._load_history()

    def _load_history(self) -> list:
        """Load production history from disk."""
        try:
            if HISTORY_PATH.exists():
                with open(HISTORY_PATH) as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load history: {e}")
        return []

    def _save_history(self):
        """Save production history to disk."""
        try:
            HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(HISTORY_PATH, "w") as f:
                json.dump(self._history, f, indent=2, default=str)
        except Exception as e:
            logger.warning(f"Failed to save history: {e}")

    def load_inspiration_ideas(self) -> list:
        """Load YouTube Inspiration ideas queue from disk."""
        try:
            if IDEAS_POOL_PATH.exists():
                with open(IDEAS_POOL_PATH, encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load inspiration ideas: {e}")
        return []

    def save_inspiration_ideas(self, ideas: list):
        """Save YouTube Inspiration ideas queue to disk."""
        try:
            IDEAS_POOL_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(IDEAS_POOL_PATH, "w", encoding="utf-8") as f:
                json.dump(ideas, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Failed to save inspiration ideas: {e}")

    def get_produced_topics(self, content_type: str = None) -> set:
        """Get set of already-produced topic keys to avoid duplicates."""
        topics = set()
        for entry in self._history:
            if content_type is None or entry.get("content_type") == content_type:
                topics.add(f"{entry.get('content_type')}:{entry.get('topic', '')}")
        return topics

    def get_today_count(self) -> int:
        """Get number of videos produced today."""
        today = str(date.today())
        return sum(
            1 for e in self._history
            if e.get("produced_at", "").startswith(today)
        )

    def get_next_content(self, templates: dict, world_cup_data: dict, template_name: str = None, ignore_quota: bool = False) -> Optional[dict]:
        """
        Determine the next piece of content to produce.

        Returns dict with:
        - template_name: str
        - topic: str (specific topic for this content)
        - topic_data: dict (data to fill the template prompt)

        Returns None if quota is exhausted.
        """
        # Callers pass None since the niche refactor; pull schedule/team data
        # from the active niche pack so time-based prioritization still works
        # for niches that define those pools.
        if world_cup_data is None:
            try:
                from content_engine.niche_loader import get_active_niche_name, load_niche
                niche = load_niche(get_active_niche_name())
                world_cup_data = {
                    "schedule": niche.topic_pools.get("schedule", []),
                    "teams": niche.topic_pools.get("teams", {}),
                }
            except Exception:
                world_cup_data = {}

        max_per_day = self.settings.get("ce_max_uploads_per_day", 6)
        if not ignore_quota and self.get_today_count() >= max_per_day:
            logger.info("Daily production limit reached.")
            return None

        active_names = [template_name] if template_name else self.settings.get("ce_active_templates", [])
        produced = self.get_produced_topics()
        today = date.today()

        # Build a list of candidate (template_name, topic, topic_data) tuples
        candidates = []

        for tname in active_names:
            if tname not in templates:
                continue

            topic_options = self._get_topic_options(tname, world_cup_data, produced)
            for topic, topic_data in topic_options:
                key = f"{tname}:{topic}"
                if key not in produced:
                    candidates.append({
                        "template_name": tname,
                        "topic": topic,
                        "topic_data": topic_data,
                    })

        if not candidates:
            logger.info("No new content topics available. Consider adding more data.")
            return None

        # Build set of teams/players playing soon (next 7 days)
        playing_soon = set()
        if world_cup_data:
            for match in world_cup_data.get("schedule", []):
                m_date = match.get("date", "")
                try:
                    md = datetime.strptime(m_date, "%Y-%m-%d").date()
                    if 0 <= (md - today).days <= 7:
                        playing_soon.add(match["team_a"])
                        playing_soon.add(match["team_b"])
                        # Get players
                        t_a = world_cup_data.get("teams", {}).get(match["team_a"], {})
                        t_b = world_cup_data.get("teams", {}).get(match["team_b"], {})
                        for p in t_a.get("key_players", []) + t_b.get("key_players", []):
                            playing_soon.add(p)
                except Exception:
                    pass

        prioritized = []
        for c in candidates:
            tname = c["template_name"]
            topic = c["topic"]
            
            if tname == "youtube_inspiration":
                prioritized.append((0, c))
            elif tname == "breaking_news":
                prioritized.append((0, c))
            elif tname == "daily_recap":
                prioritized.append((0, c))
            elif tname == "match_preview":
                match_date = c["topic_data"].get("match_date", "")
                try:
                    md = datetime.strptime(match_date, "%Y-%m-%d").date()
                    days_away = (md - today).days
                    if 0 <= days_away <= 3:
                        prioritized.append((0, c))
                    elif 4 <= days_away <= 7:
                        prioritized.append((1, c))
                    else:
                        prioritized.append((2, c))
                except Exception:
                    prioritized.append((2, c))
            elif tname in ("player_profile", "squad_guide") and topic in playing_soon:
                prioritized.append((1, c))
            elif tname in ("player_profile", "squad_guide"):
                prioritized.append((2, c))
            else:
                # facts, quiz, controversy, history, top_10
                prioritized.append((3, c))

        # Sort by priority, then shuffle within same priority for variety
        prioritized.sort(key=lambda x: x[0])

        # Among same-priority items, pick randomly for variety
        top_priority = prioritized[0][0]
        same_priority = [c for p, c in prioritized if p == top_priority]
        choice = random.choice(same_priority)

        logger.info(f"Next content: [{choice['template_name']}] {choice['topic']}")
        return choice

    def _get_topic_options(self, template_name: str, data: dict, produced: set) -> list:
        """
        Generate topic options for a given template type from the active niche pack.
        """
        from content_engine.niche_loader import get_active_niche_name, load_niche
        
        niche_name = get_active_niche_name()
        niche = load_niche(niche_name)
        
        # Check topic refill if pool runs low
        t_def = None
        for t in niche.get_templates_data():
            if t["name"] == template_name:
                t_def = t
                break
                
        if t_def:
            pool_name = t_def.get("topic_pool")
            if pool_name and pool_name != "ideas":
                if niche.is_pool_low(pool_name, produced):
                    logger.info(f"Topic pool '{pool_name}' runs low. Attempting refill via Gemini...")
                    api_key = self.settings.get("ce_gemini_api_key")
                    niche.refill_pool(pool_name, api_key)
                    
        return niche.get_topic_options(template_name, produced)

    def log_production(self, content_type: str, topic: str,
                       video_path: str = "", video_url: str = "",
                       status: str = "completed"):
        """Record a completed (or failed) production."""
        entry = {
            "content_type": content_type,
            "topic": topic,
            "produced_at": datetime.now().isoformat(),
            "video_path": str(video_path),
            "video_url": video_url,
            "status": status,
        }
        self._history.append(entry)
        self._save_history()
        logger.info(f"Logged production: [{content_type}] {topic} -> {status}")

        # If successfully completed a YouTube Inspiration idea, remove it from the queue
        if content_type == "youtube_inspiration" and status == "completed":
            try:
                ideas = self.load_inspiration_ideas()
                if topic in ideas:
                    ideas.remove(topic)
                    self.save_inspiration_ideas(ideas)
                    logger.info(f"Removed '{topic}' from YouTube Inspiration ideas queue.")
            except Exception as e:
                logger.warning(f"Failed to remove completed inspiration idea from queue: {e}")

    def get_stats(self) -> dict:
        """Get production statistics."""
        today = str(date.today())
        today_entries = [e for e in self._history if e.get("produced_at", "").startswith(today)]
        return {
            "total_produced": len(self._history),
            "today_produced": len(today_entries),
            "today_successful": sum(1 for e in today_entries if e.get("status") == "completed"),
            "today_failed": sum(1 for e in today_entries if e.get("status") == "failed"),
            "remaining_today": max(0, self.settings.get("ce_max_uploads_per_day", 6) - len(today_entries)),
        }

    def clear_history(self):
        """Clear all production history."""
        self._history = []
        self._save_history()
