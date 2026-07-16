import json
import os
import random
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from app.settings import Settings

class NichePack:
    def __init__(self, name: str):
        self.name = name
        self.niches_dir = Path(__file__).resolve().parent / "niches"
        self.path = self.niches_dir / f"{name}.json"
        
        # If it doesn't exist, try the home settings folder as well
        if not self.path.exists():
            self.path = Path.home() / ".clipcatcher" / "niches" / f"{name}.json"
            
        if not self.path.exists():
            raise FileNotFoundError(f"Niche pack '{name}' not found at {self.path}")
            
        with open(self.path, "r", encoding="utf-8") as f:
            self._data = json.load(f)
            
        self.display_name = self._data.get("display_name", name)
        self.channel_name = self._data.get("channel_name", "Content Channel")
        self.hashtags = self._data.get("hashtags", [])
        self.default_tags = self._data.get("default_tags", [])
        self.brand_colors = self._data.get("brand_colors", {
            "primary": [20, 20, 40],
            "secondary": [255, 215, 0],
            "accent": [0, 180, 255],
            "thumbnail_accent": [255, 50, 50]
        })
        self.rss_search_query = self._data.get("rss_search_query", "")
        self.visual_sources = self._data.get("visual_sources", {
            "sportsdb_enabled": False,
            "pexels_default_terms": ["video", "clip"],
            "pexels_sport_term": "soccer"
        })
        self.tone_preamble = self._data.get("tone_preamble", "")
        self.subscribe_cta = self._data.get("subscribe_cta", "Subscribe for more!")
        self.topic_pools = self._data.get("topic_pools", {})

    def get_templates_data(self) -> list:
        return self._data.get("templates", [])

    def get_topic_options(self, template_name: str, produced: set) -> list:
        """
        Generate topic options for a template from this niche's topic pool.
        Matches the expected output: list of (topic_str, topic_data_dict).
        """
        if template_name == "breaking_news":
            return self._fetch_trending_news(produced)
        elif template_name == "youtube_inspiration":
            return self._load_inspiration_ideas()

        # Find template pool
        topic_pool = None
        for t in self.get_templates_data():
            if t["name"] == template_name:
                topic_pool = t.get("topic_pool")
                break
        
        if not topic_pool:
            return []

        pool = self.topic_pools.get(topic_pool)
        if not pool:
            return []

        options = []

        # ── World Cup 2026 Special Legacy Formatting ──────────────────────────
        if self.name == "world_cup_2026":
            if template_name == "match_preview":
                for match in pool:
                    topic = f"{match['team_a']} vs {match['team_b']}"
                    t_a_data = self.topic_pools["teams"].get(match["team_a"], {})
                    t_b_data = self.topic_pools["teams"].get(match["team_b"], {})
                    
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
                for name, pdata in pool.items():
                    topic = name
                    stats_str = f"Age: {pdata.get('age', '')}, International Goals: {pdata.get('goals_international', '')}"
                    options.append((topic, {
                        "player_name": name,
                        "nationality": pdata.get("country", ""),
                        "country": pdata.get("country", ""),
                        "position": pdata.get("position", ""),
                        "club": pdata.get("club", ""),
                        "age": pdata.get("age", ""),
                        "goals_international": pdata.get("goals_international", ""),
                        "stats": stats_str,
                        "fun_facts": pdata.get("fun_facts", []),
                        "tournament_role": f"Talisman and key {pdata.get('position', 'player')} for {pdata.get('country', '')} at World Cup 2026",
                    }))
            elif template_name == "top_10":
                for item in pool:
                    topic = item.get("title", "")
                    options.append((topic, {
                        "topic": topic,
                        "list_title": topic,
                        "context": f"A viral countdown of the most iconic moments: {topic}",
                        "suggested_entries": "; ".join(item.get("items", [])),
                        "items": item.get("items", []),
                    }))
            elif template_name == "daily_recap":
                from datetime import date, timedelta
                today = date.today()
                yesterday = today - timedelta(days=1)
                recap_matches = [
                    m for m in pool 
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
                for i, q in enumerate(pool):
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
            elif template_name == "transfer_quiz":
                for i, q in enumerate(pool):
                    topic = f"Transfer Quiz #{i+1}: {q['player_name']}"
                    transfers_summary = " -> ".join([f"{t['club']} ({t['years']})" for t in q["transfers"]])
                    options_list = ", ".join(q["options"])
                    options.append((topic, {
                        "topic": f"Transfer History: {q['player_name']}",
                        "player_name": q["player_name"],
                        "transfers_summary": transfers_summary,
                        "options_list": options_list,
                        "options": q["options"],
                        "hint": q["hint"],
                        "difficulty": q.get("difficulty", "medium"),
                        "answer": q["player_name"],
                        "transfers": q["transfers"],
                    }))
            elif template_name == "national_team_quiz":
                for i, q in enumerate(pool):
                    topic = f"National Lineup Quiz #{i+1}: {q['national_team']}"
                    clubs_list = ", ".join(q["clubs"])
                    options_list = ", ".join(q["options"])
                    options.append((topic, {
                        "topic": f"Squad Lineup: {q['national_team']}",
                        "national_team": q["national_team"],
                        "clubs_list": clubs_list,
                        "clubs": q["clubs"],
                        "options_list": options_list,
                        "options": q["options"],
                        "hint": q["hint"],
                        "difficulty": q.get("difficulty", "medium"),
                        "answer": q["national_team"],
                    }))
            elif template_name == "history":
                for fact in pool:
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
                for team_name, tdata in pool.items():
                    topic = f"{team_name} Squad Guide"
                    star = tdata.get("key_players", ["TBD"])[0]
                    options.append((topic, {
                        "country": team_name,
                        "team_name": team_name,
                        "manager": tdata.get("coach", "TBD"),
                        "coach": tdata.get("coach", "TBD"),
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
                for item in pool:
                    topic = item.get("title", "")
                    options.append((topic, {
                        "event": item.get("title", ""),
                        "title": topic,
                        "match": item.get("title", ""),
                        "tournament": f"World Cup {item.get('year', '')}",
                        "key_figures": "Players and referees involved in the incident",
                        "what_happened": item.get("description", ""),
                        "description": item.get("description", ""),
                        "controversy_reason": "Decisive decision sparking global debate",
                        "aftermath": "Legendary tournament fallout and fan debate",
                        "year": item.get("year", ""),
                    }))
            elif template_name == "facts":
                for item in pool:
                    topic = item.get("title", "")
                    options.append((topic, {
                        "topic": item.get("title", ""),
                        "title": topic,
                        "category": "Rules and Knowledge",
                        "details": item.get("explanation", ""),
                        "explanation": item.get("explanation", ""),
                        "wc_connection": "Applies directly to World Cup 2026 regulations",
                    }))

        # ── Generic Niche Formatting ──────────────────────────────────────────
        else:
            if isinstance(pool, dict):
                for key, val in pool.items():
                    topic = key
                    topic_data = val if isinstance(val, dict) else {"value": val}
                    if "topic" not in topic_data:
                        topic_data["topic"] = topic
                    options.append((topic, topic_data))
            elif isinstance(pool, list):
                for item in pool:
                    if isinstance(item, dict):
                        topic = item.get("topic") or item.get("title") or item.get("name") or item.get("player_name") or item.get("national_team") or str(item)
                        # Make sure topic is in topic_data
                        topic_data = dict(item)
                        topic_data["topic"] = topic
                        options.append((topic, topic_data))
                    else:
                        options.append((str(item), {"topic": str(item)}))
                        
        return options

    def _fetch_trending_news(self, produced: set) -> list:
        """Generic trending news RSS fetcher using rss_search_query."""
        if not self.rss_search_query:
            return []
        import urllib.request
        import xml.etree.ElementTree as ET
        url = f"https://news.google.com/rss/search?q={self.rss_search_query}&hl=en-US&gl=US&ceid=US:en"
        options = []
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=8) as response:
                xml_data = response.read()
            root = ET.fromstring(xml_data)
            for item in root.findall(".//item")[:15]:
                raw_title = item.find("title").text or ""
                cleaned_title = raw_title.rsplit(" - ", 1)[0].strip()
                if not cleaned_title:
                    continue
                
                raw_desc = item.find("description").text or ""
                cleaned_desc = re.sub(r'<[^>]*>', '', raw_desc).strip()
                cleaned_desc = cleaned_desc[:250]
                
                topic = f"News: {cleaned_title}"
                if topic in produced:
                    continue
                
                # Special entity matching for World Cup
                entities_str = f"{self.display_name} trending updates"
                if self.name == "world_cup_2026":
                    mentioned = []
                    title_lower = cleaned_title.lower()
                    for team_name in self.topic_pools.get("teams", {}):
                        if team_name.lower() in title_lower:
                            mentioned.append(team_name)
                    for player_name in self.topic_pools.get("players", {}):
                        if player_name.lower() in title_lower:
                            mentioned.append(player_name)
                    if mentioned:
                        entities_str = ", ".join(mentioned)
                
                options.append((topic, {
                    "headline": cleaned_title,
                    "summary": cleaned_desc or cleaned_title,
                    "entities": entities_str,
                    "topic": topic
                }))
        except Exception:
            pass
        return options

    def _load_inspiration_ideas(self) -> list:
        """Loads inspiration ideas from the local inspiration JSON."""
        ideas_path = Path.home() / ".clipcatcher" / "ce_inspiration_ideas.json"
        if not ideas_path.exists():
            return []
        try:
            with open(ideas_path, "r", encoding="utf-8") as f:
                ideas = json.load(f)
            return [(idea, {"idea": idea, "topic": idea}) for idea in ideas]
        except Exception:
            return []

    def is_pool_low(self, pool_name: str, produced_set: set) -> bool:
        """Checks if the number of unused topics in this pool is low (< 5)."""
        pool = self.topic_pools.get(pool_name, [])
        if not pool:
            return False
            
        # Get list of all produced topics
        produced_topics = {k.split(":", 1)[1] for k in produced_set if ":" in k}
        
        unused_count = 0
        if isinstance(pool, dict):
            for topic in pool.keys():
                if topic not in produced_topics:
                    unused_count += 1
        elif isinstance(pool, list):
            for item in pool:
                topic = ""
                if isinstance(item, dict):
                    topic = item.get("topic") or item.get("title") or item.get("name") or item.get("player_name") or item.get("national_team") or ""
                else:
                    topic = str(item)
                if topic and topic not in produced_topics:
                    unused_count += 1
                    
        return unused_count < 5

    def refill_pool(self, pool_name: str, api_key: str, count: int = 15):
        """Call Gemini to generate new topics and append them to the pool JSON file."""
        if not api_key:
            return
            
        pool = self.topic_pools.get(pool_name)
        if not pool:
            return
            
        # Get one example entry
        example_entry = None
        if isinstance(pool, dict):
            example_entry = next(iter(pool.values()))
        elif isinstance(pool, list) and len(pool) > 0:
            example_entry = pool[0]
            
        if not example_entry:
            return
            
        # Gather existing topic strings for deduping
        existing_topics = []
        if isinstance(pool, dict):
            existing_topics = list(pool.keys())
        elif isinstance(pool, list):
            for item in pool:
                if isinstance(item, dict):
                    t = item.get("topic") or item.get("title") or item.get("name") or item.get("player_name") or item.get("national_team") or ""
                    if t: existing_topics.append(t)
                else:
                    existing_topics.append(str(item))
                    
        # Call Gemini using google-genai
        try:
            from google import genai
            from google.genai import types
            
            client = genai.Client(api_key=api_key)
            prompt = f"""
            You are a creative content strategist. We need to generate new topics for our content generation pool "{pool_name}" for the niche "{self.display_name}".
            
            Format of each entry in the pool must match this exact JSON schema:
            {json.dumps(example_entry, indent=2)}
            
            Please generate {count} new, unique, and highly engaging topic entries matching this exact structure.
            Do NOT repeat or generate any of these already existing topics:
            {", ".join(existing_topics[:50])}
            
            Return ONLY a valid JSON object containing a key "new_entries" which is a list of the generated entries.
            No markdown formatting, no code block backticks, no explanatory text.
            """
            
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            
            # Clean response text from backticks if present
            resp_text = response.text.strip()
            if resp_text.startswith("```"):
                resp_text = re.sub(r"^```(?:json)?\n", "", resp_text)
                resp_text = re.sub(r"\n```$", "", resp_text).strip()
                
            data = json.loads(resp_text)
            new_entries = data.get("new_entries", [])
            
            if not new_entries:
                return
                
            # Append new entries to pool
            if isinstance(pool, dict):
                for entry in new_entries:
                    key = entry.get("topic") or entry.get("title") or entry.get("name") or entry.get("player_name") or entry.get("national_team") or str(entry)
                    pool[key] = entry
            elif isinstance(pool, list):
                for entry in new_entries:
                    pool.append(entry)
                    
            # Save back to file
            self.save()
            print(f"Successfully refilled pool '{pool_name}' with {len(new_entries)} new entries.")
        except Exception as e:
            print(f"Failed to refill pool via Gemini: {e}")

    def save(self):
        """Save this niche pack data back to the JSON file."""
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)


def get_active_niche_name() -> str:
    s = Settings()
    return s.get("ce_active_niche", "world_cup_2026")


def load_niche(name: str) -> NichePack:
    return NichePack(name)


def list_niches() -> list[str]:
    """List all available niche pack names in the niches folders."""
    niches_dir = Path(__file__).resolve().parent / "niches"
    local_dir = Path.home() / ".clipcatcher" / "niches"
    
    niche_files = []
    for d in (niches_dir, local_dir):
        if d.exists():
            niche_files.extend(list(d.glob("*.json")))
            
    # Return unique base names without .json
    names = sorted(list({f.stem for f in niche_files}))
    # Ensure world_cup_2026 is always available
    if not names:
        names = ["world_cup_2026"]
    return names
