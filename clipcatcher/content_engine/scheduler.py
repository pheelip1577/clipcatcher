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
        Generate topic options for a given template type from world cup data.

        Returns list of (topic_str, topic_data_dict) tuples.
        """
        from content_engine.world_cup_data import (
            TEAMS, PLAYERS, SCHEDULE, HISTORICAL_FACTS,
            QUIZ_QUESTIONS, CONTROVERSIES, TOP_10_TOPICS, FACTS_AND_RULES
        )

        options = []

        if template_name == "breaking_news":
            options = self._fetch_trending_news(data, produced)

        elif template_name == "match_preview":
            for match in SCHEDULE:
                topic = f"{match['team_a']} vs {match['team_b']}"
                t_a_data = TEAMS.get(match["team_a"], {})
                t_b_data = TEAMS.get(match["team_b"], {})
                
                match_details = f"Stage: {match.get('stage', 'Group Stage')}, Venue: {match.get('venue', '')}, Date: {match.get('date', '')}"
                key_players = f"{match['team_a']}: {', '.join(t_a_data.get('key_players', []))} | {match['team_b']}: {', '.join(t_b_data.get('key_players', []))}"
                recent_form = f"{match['team_a']}: Strong competitor, Coach: {t_a_data.get('coach', 'TBD')} | {match['team_b']}: Coach: {t_b_data.get('coach', 'TBD')}"
                h2h = f"Both teams eager for victory. Best Finish - {match['team_a']}: {t_a_data.get('best_finish', 'TBD')} | {match['team_b']}: {t_b_data.get('best_finish', 'TBD')}"
                stakes = f"Group stage battle. Fun Fact - {match['team_a']}: {t_a_data.get('fun_fact', '')}"

                options.append((topic, {
                    "team_a": match["team_a"],
                    "team_b": match["team_b"],
                    "match_details": match_details,
                    "key_players": key_players,
                    "recent_form": recent_form,
                    "h2h": h2h,
                    "stakes": stakes,
                    "stage": match.get("stage", "Group Stage"),
                    "venue": match.get("venue", ""),
                    "match_date": match.get("date", ""),
                    "team_a_data": t_a_data,
                    "team_b_data": t_b_data,
                }))

        elif template_name == "player_profile":
            for name, pdata in PLAYERS.items():
                topic = name
                stats_str = f"Age: {pdata.get('age', '')}, International Goals: {pdata.get('goals_international', '')}"
                options.append((topic, {
                    "player_name": name,
                    "nationality": pdata.get("country", ""),
                    "country": pdata.get("country", ""),  # Keep for backward compatibility
                    "position": pdata.get("position", ""),
                    "club": pdata.get("club", ""),
                    "age": pdata.get("age", ""),
                    "goals_international": pdata.get("goals_international", ""),
                    "stats": stats_str,
                    "fun_facts": pdata.get("fun_facts", []),
                    "tournament_role": f"Talisman and key {pdata.get('position', 'player')} for {pdata.get('country', '')} at World Cup 2026",
                }))

        elif template_name == "top_10":
            for item in TOP_10_TOPICS:
                topic = item.get("title", "")
                options.append((topic, {
                    "topic": topic,
                    "list_title": topic, # Keep for backward compatibility
                    "context": f"A viral countdown of the most iconic moments: {topic}",
                    "suggested_entries": "; ".join(item.get("items", [])),
                    "items": item.get("items", []), # Keep for backward compatibility
                }))

        elif template_name == "daily_recap":
            today = date.today()
            yesterday = today - timedelta(days=1)
            recap_matches = [
                m for m in SCHEDULE 
                if m.get("date") == str(today) or m.get("date") == str(yesterday)
            ]
            if recap_matches:
                topic = f"Recap {today.isoformat()}"
                results_list = []
                for m in recap_matches:
                    results_list.append(f"{m['team_a']} vs {m['team_b']} ({m.get('date', '')})")
                results_str = "; ".join(results_list)
                
                options.append((topic, {
                    "matchday": today.strftime("%B %d, %Y"),
                    "results": results_str,
                    "key_moments": "Standout tactical play, intense pressure, and game-changing goals.",
                    "standout_performers": "Key squad leaders and standout performers.",
                    "standings_impact": "Crucial impact on group stage standings and tournament progression.",
                    "tomorrow_matches": "Upcoming matches scheduled to continue the tournament action.",
                    "date": str(today),
                    "matches": recap_matches,
                    "results_summary": "Daily match summaries",
                }))

        elif template_name == "quiz":
            for i, q in enumerate(QUIZ_QUESTIONS):
                topic = f"Quiz #{i+1}: {q['question'][:50]}"
                options.append((topic, {
                    "topic": "World Cup Trivia",
                    "difficulty": q.get("difficulty", "medium"),
                    "specific_question": q["question"],
                    "related_facts": f"Options: {', '.join(q['options'])}\nAnswer: {q['answer']}\nDetail: {q.get('answer_detail', '')}",
                    "question": q["question"],
                    "options": q["options"],
                    "answer": q["answer"],
                    "answer_detail": q.get("answer_detail", ""),
                }))

        elif template_name == "history":
            today_mmdd = datetime.now().strftime("%m-%d")
            for fact in HISTORICAL_FACTS:
                topic = f"{fact.get('year', '')} - {fact.get('event', '')[:50]}"
                options.append((topic, {
                    "date": f"{fact.get('date', '')}, {fact.get('year', '')}",
                    "event": fact.get("event", ""),
                    "key_figures": "Legendary players, managers, and referees",
                    "tournament_context": f"World Cup held in {fact.get('year', '')}",
                    "legacy": "Iconic sports heritage and folklore",
                    "year": fact.get("year", ""),
                }))

        elif template_name == "squad_guide":
            for team_name, tdata in TEAMS.items():
                topic = f"{team_name} Squad Guide"
                star = tdata.get("key_players", ["TBD"])[0]
                options.append((topic, {
                    "country": team_name,
                    "team_name": team_name, # Keep for backward compatibility
                    "manager": tdata.get("coach", "TBD"),
                    "coach": tdata.get("coach", "TBD"), # Keep for backward compatibility
                    "playing_style": "High-intensity technical display",
                    "star_player": star,
                    "key_players": ", ".join(tdata.get("key_players", [])),
                    "group": tdata.get("group", ""),
                    "group_opponents": f"Teams in Group {tdata.get('group', '')}",
                    "fifa_ranking": "Top global tier",
                    "qualification_record": "Qualified successfully",
                    "strengths": tdata.get("fun_fact", "Strong team spirit"),
                    "weaknesses": "Tournament pressure",
                    "flag": tdata.get("flag", ""),
                    "titles": tdata.get("titles", 0),
                    "best_finish": tdata.get("best_finish", ""),
                    "fun_fact": tdata.get("fun_fact", ""),
                }))

        elif template_name == "controversy":
            for item in CONTROVERSIES:
                topic = item.get("title", "")
                options.append((topic, {
                    "event": item.get("title", ""),
                    "title": topic, # Keep for backward compatibility
                    "match": item.get("title", ""),
                    "tournament": f"World Cup {item.get('year', '')}",
                    "key_figures": "Players and referees involved in the incident",
                    "what_happened": item.get("description", ""),
                    "description": item.get("description", ""), # Keep for backward compatibility
                    "controversy_reason": "Decisive decision sparking global debate",
                    "aftermath": "Legendary tournament fallout and fan debate",
                    "year": item.get("year", ""),
                }))

        elif template_name == "facts":
            for item in FACTS_AND_RULES:
                topic = item.get("title", "")
                options.append((topic, {
                    "topic": item.get("title", ""),
                    "title": topic, # Keep for backward compatibility
                    "category": "Rules and Knowledge",
                    "details": item.get("explanation", ""),
                    "explanation": item.get("explanation", ""), # Keep for backward compatibility
                    "wc_connection": "Applies directly to World Cup 2026 regulations",
                }))

        elif template_name == "youtube_inspiration":
            ideas = self.load_inspiration_ideas()
            for idea in ideas:
                topic = idea
                options.append((topic, {
                    "idea": idea,
                    "topic": topic
                }))

        return options

    def _fetch_trending_news(self, data: dict, produced: set) -> list:
        """Fetch trending news from Google News RSS feed."""
        import urllib.request
        import xml.etree.ElementTree as ET
        import re

        options = []
        url = "https://news.google.com/rss/search?q=world+cup+2026+soccer+OR+fifa+world+cup+2026&hl=en-US&gl=US&ceid=US:en"
        try:
            logger.info("Fetching trending World Cup 2026 news from Google News RSS...")
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=8) as response:
                xml_data = response.read()
            root = ET.fromstring(xml_data)
            items = root.findall('.//item')
            
            for item in items[:15]:  # Process top 15 news items
                raw_title = item.find('title').text or ""
                # Clean source suffix (e.g. "Title - The Athletic" -> "Title")
                cleaned_title = raw_title.rsplit(" - ", 1)[0].strip()
                if not cleaned_title:
                    continue
                
                # Clean HTML from description if any
                raw_desc = item.find('description').text or ""
                cleaned_desc = re.sub(r'<[^>]*>', '', raw_desc).strip()
                cleaned_desc = cleaned_desc[:250]  # limit length
                
                topic = f"News: {cleaned_title}"
                
                # Match entities
                mentioned = []
                title_lower = cleaned_title.lower()
                for team_name in data.get("teams", {}):
                    if team_name.lower() in title_lower:
                        mentioned.append(team_name)
                for player_name in data.get("players", {}):
                    if player_name.lower() in title_lower:
                        mentioned.append(player_name)
                entities_str = ", ".join(mentioned) if mentioned else "World Cup 2026 players and squads"
                
                options.append((topic, {
                    "headline": cleaned_title,
                    "summary": cleaned_desc or cleaned_title,
                    "entities": entities_str,
                    "topic": topic
                }))
            logger.info(f"Successfully loaded {len(options)} news options from RSS.")
        except Exception as e:
            logger.warning(f"Failed to fetch trending news RSS: {e}")
        return options

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
