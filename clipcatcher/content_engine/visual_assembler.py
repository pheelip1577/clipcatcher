"""
visual_assembler.py — Visual Asset Generation Pipeline.

Fetches real player/team images from TheSportsDB and stock images from the
Pexels API.  Generates branded vertical graphics (text cards, player stat
cards, quiz cards) using Pillow.
"""

from __future__ import annotations

import logging
import random
import re
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter

logger = logging.getLogger(__name__)

# TheSportsDB free-tier API base URL (key "3" is a free dev key)
TSDB_BASE = "https://www.thesportsdb.com/api/v1/json/3"


class VisualAssembler:
    """Fetches real player/team images (TheSportsDB) and stock images (Pexels),
    and generates branded cards for YouTube Shorts."""

    def __init__(self, pexels_api_key: str, brand_config: Dict[str, Any]):
        """
        Parameters
        ----------
        pexels_api_key : str
            Authorization key for Pexels API.
        brand_config : dict
            Visual identity settings:
            - channel_name: str
            - primary_color: tuple (R, G, B)
            - secondary_color: tuple (R, G, B)
            - accent_color: tuple (R, G, B)
        """
        self.pexels_key = pexels_api_key
        self.brand = brand_config
        self.channel_name = brand_config.get("channel_name", "World Cup Central")
        self.c_primary = brand_config.get("primary_color", (10, 10, 25))
        self.c_secondary = brand_config.get("secondary_color", (255, 215, 0))  # Gold
        self.c_accent = brand_config.get("accent_color", (0, 180, 255))      # Neon Cyan

        # Cache for TheSportsDB lookups to avoid repeat API calls
        self._tsdb_player_cache: Dict[str, Optional[dict]] = {}
        self._tsdb_team_cache: Dict[str, Optional[dict]] = {}

        # Common Windows fonts to try loading
        self.font_paths = [
            "C:\\Windows\\Fonts\\segoeuib.ttf",  # Segoe UI Bold
            "C:\\Windows\\Fonts\\arialbd.ttf",   # Arial Bold
            "C:\\Windows\\Fonts\\impact.ttf",    # Impact
            "C:\\Windows\\Fonts\\trebucbd.ttf",  # Trebuchet MS Bold
        ]

    def _get_font(self, size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
        """Attempts to load a bold custom font, falling back to default."""
        for path in self.font_paths:
            try:
                if Path(path).exists():
                    return ImageFont.truetype(path, size)
            except Exception:
                pass
        return ImageFont.load_default()

    # ── TheSportsDB helpers ──────────────────────────────────────────────

    def _tsdb_search_player(self, player_name: str) -> Optional[dict]:
        """Search TheSportsDB for a player by name. Returns the first match dict or None."""
        if player_name in self._tsdb_player_cache:
            return self._tsdb_player_cache[player_name]

        try:
            url = f"{TSDB_BASE}/searchplayers.php"
            params = {"p": player_name}
            res = requests.get(url, params=params, timeout=10)
            res.raise_for_status()
            data = res.json()
            players = data.get("player")
            if players:
                # Prefer soccer/football players
                for p in players:
                    sport = (p.get("strSport") or "").lower()
                    if sport in ("soccer", "football"):
                        self._tsdb_player_cache[player_name] = p
                        return p
                # If no soccer player found, return the first result anyway
                self._tsdb_player_cache[player_name] = players[0]
                return players[0]
        except Exception as e:
            logger.warning(f"TheSportsDB player search failed for '{player_name}': {e}")

        self._tsdb_player_cache[player_name] = None
        return None

    def _tsdb_search_team(self, team_name: str) -> Optional[dict]:
        """Search TheSportsDB for a team by name. Returns the first match dict or None."""
        if team_name in self._tsdb_team_cache:
            return self._tsdb_team_cache[team_name]

        try:
            url = f"{TSDB_BASE}/searchteams.php"
            params = {"t": team_name}
            res = requests.get(url, params=params, timeout=10)
            res.raise_for_status()
            data = res.json()
            teams = data.get("teams")
            if teams:
                # Prefer soccer/football teams
                for t in teams:
                    sport = (t.get("strSport") or "").lower()
                    if sport in ("soccer", "football"):
                        self._tsdb_team_cache[team_name] = t
                        return t
                self._tsdb_team_cache[team_name] = teams[0]
                return teams[0]
        except Exception as e:
            logger.warning(f"TheSportsDB team search failed for '{team_name}': {e}")

        self._tsdb_team_cache[team_name] = None
        return None

    def _tsdb_get_player_image(self, player_name: str, output_dir: Path) -> Optional[Path]:
        """
        Fetch a real photo of *player_name* from TheSportsDB.
        Tries cutout → thumb → fanart in that preference order.
        Returns the local file path or None.
        """
        player = self._tsdb_search_player(player_name)
        if not player:
            return None

        # Ordered preference: cutout (transparent), thumb (portrait), fanart
        image_fields = [
            "strCutout",
            "strThumb",
            "strRender",
            "strFanart1",
            "strFanart2",
            "strFanart3",
            "strFanart4",
        ]

        for field in image_fields:
            img_url = player.get(field)
            if img_url and img_url.strip():
                try:
                    safe_name = re.sub(r'[^a-zA-Z0-9]', '_', player_name.lower())[:30]
                    ext = "png" if "cutout" in field.lower() or "render" in field.lower() else "jpg"
                    img_path = output_dir / f"tsdb_player_{safe_name}_{random.randint(1000,9999)}.{ext}"

                    logger.info(f"Downloading TheSportsDB {field} for '{player_name}'...")
                    img_res = requests.get(img_url.strip(), timeout=15)
                    img_res.raise_for_status()

                    with open(img_path, "wb") as f:
                        f.write(img_res.content)

                    # Verify it's a valid image
                    with Image.open(img_path) as test_img:
                        test_img.verify()

                    logger.info(f"✅ Got real player image for '{player_name}' ({field}): {img_path.name}")
                    return img_path
                except Exception as e:
                    logger.warning(f"Failed to download {field} for '{player_name}': {e}")
                    continue

        logger.info(f"No usable image found on TheSportsDB for player '{player_name}'.")
        return None

    def _tsdb_get_team_image(self, team_name: str, output_dir: Path) -> Optional[Path]:
        """
        Fetch a team image from TheSportsDB.
        For national teams (which rarely have fanart), falls back to
        fetching a key player's image from that country.
        Returns the local file path or None.
        """
        team = self._tsdb_search_team(team_name)

        if team:
            # Ordered preference: fanart → banner → badge → stadium
            image_fields = [
                "strTeamFanart1",
                "strTeamFanart2",
                "strTeamFanart3",
                "strTeamFanart4",
                "strTeamBanner1",
                "strTeamBanner2",
                "strBadge",
                "strStadiumThumb",
            ]

            for field in image_fields:
                img_url = team.get(field)
                if img_url and img_url.strip():
                    try:
                        safe_name = re.sub(r'[^a-zA-Z0-9]', '_', team_name.lower())[:30]
                        img_path = output_dir / f"tsdb_team_{safe_name}_{random.randint(1000,9999)}.jpg"

                        logger.info(f"Downloading TheSportsDB {field} for '{team_name}'...")
                        img_res = requests.get(img_url.strip(), timeout=15)
                        img_res.raise_for_status()

                        with open(img_path, "wb") as f:
                            f.write(img_res.content)

                        # Verify it's a valid image
                        with Image.open(img_path) as test_img:
                            test_img.verify()

                        logger.info(f"✅ Got real team image for '{team_name}' ({field}): {img_path.name}")
                        return img_path
                    except Exception as e:
                        logger.warning(f"Failed to download {field} for '{team_name}': {e}")
                        continue

        # Fallback for national teams: fetch a star player's image instead
        # (e.g. for "Argentina" → get a photo of Messi or Álvarez)
        try:
            from content_engine.world_cup_data import TEAMS
            team_data = TEAMS.get(team_name, {})
            key_players = team_data.get("key_players", [])
            if key_players:
                logger.info(f"No team imagery for '{team_name}', trying key player: {key_players[0]}")
                player_img = self._tsdb_get_player_image(key_players[0], output_dir)
                if player_img and player_img.exists():
                    return player_img
                # Try second player if first fails
                if len(key_players) > 1:
                    player_img = self._tsdb_get_player_image(key_players[1], output_dir)
                    if player_img and player_img.exists():
                        return player_img
        except ImportError:
            pass

        logger.info(f"No usable image found on TheSportsDB for team '{team_name}'.")
        return None

    def _extract_entities_from_topic(self, script: Any) -> Tuple[List[str], List[str]]:
        """
        Extract player names and team/country names from the script topic,
        visual cues, and the world_cup_data module.

        Returns
        -------
        (player_names, team_names)
        """
        player_names: List[str] = []
        team_names: List[str] = []

        topic = getattr(script, "topic", "") or ""
        content_type = getattr(script, "content_type", "") or ""

        # Try to match against known players/teams from world_cup_data
        try:
            from content_engine.world_cup_data import PLAYERS, TEAMS

            # Check if topic matches a known player
            for pname in PLAYERS:
                if pname.lower() in topic.lower():
                    player_names.append(pname)

            # Check if topic matches a known team/country
            for tname in TEAMS:
                if tname.lower() in topic.lower():
                    team_names.append(tname)
                    # Also add the national team name variant for TheSportsDB
                    # e.g. "Brazil" -> also try "Brazil" as a team search
        except ImportError:
            pass

        # For player_profile content, the topic IS the player name
        if content_type == "player_profile" and not player_names:
            player_names.append(topic.strip())

        # For squad_guide, the topic is the country
        if content_type == "squad_guide" and not team_names:
            team_names.append(topic.strip())

        # For match_preview, try to extract both team names ("Team A vs Team B")
        if content_type == "match_preview":
            vs_match = re.search(r'(.+?)\s+(?:vs?\.?|versus)\s+(.+)', topic, re.IGNORECASE)
            if vs_match:
                for team in [vs_match.group(1).strip(), vs_match.group(2).strip()]:
                    if team and team not in team_names:
                        team_names.append(team)

        return player_names, team_names

    def _extract_players_from_visual_cue(self, visual_cue: str) -> List[str]:
        """
        Try to extract player names from a visual cue by matching against
        the known player database.
        """
        found = []
        try:
            from content_engine.world_cup_data import PLAYERS
            cue_lower = visual_cue.lower()
            for pname in PLAYERS:
                if pname.lower() in cue_lower:
                    found.append(pname)
        except ImportError:
            pass
        return found

    def _extract_teams_from_visual_cue(self, visual_cue: str) -> List[str]:
        """
        Try to extract team/country names from a visual cue by matching against
        the known team database.
        """
        found = []
        try:
            from content_engine.world_cup_data import TEAMS
            cue_lower = visual_cue.lower()
            for tname in TEAMS:
                if tname.lower() in cue_lower:
                    found.append(tname)
        except ImportError:
            pass
        return found

    def fetch_stock_image(self, query: str, output_dir: Path) -> Optional[Path]:
        """
        Searches Pexels for a portrait photo and downloads it.
        Returns the local path or None on failure.
        """
        if not self.pexels_key:
            logger.warning("No Pexels API key provided. Skipping fetch.")
            return None

        headers = {"Authorization": self.pexels_key}
        url = "https://api.pexels.com/v1/search"
        params = {
            "query": query,
            "orientation": "portrait",
            "per_page": 5
        }

        try:
            logger.info(f"Searching Pexels for: '{query}'...")
            res = requests.get(url, headers=headers, params=params, timeout=10)
            res.raise_for_status()
            data = res.json()

            photos = data.get("photos", [])
            if not photos:
                logger.warning(f"No stock images found on Pexels for: '{query}'")
                return None

            # Pick a random photo from the top 5 to avoid repetition
            photo = random.choice(photos)
            src_url = photo.get("src", {}).get("large2x", photo.get("src", {}).get("original", ""))
            if not src_url:
                return None

            img_path = output_dir / f"pexels_{photo['id']}.jpg"
            logger.info(f"Downloading stock photo {photo['id']}...")
            img_res = requests.get(src_url, timeout=15)
            img_res.raise_for_status()

            with open(img_path, "wb") as f:
                f.write(img_res.content)

            return img_path

        except Exception as e:
            logger.warning(f"Failed to fetch stock image for '{query}': {e}")
            return None

    def create_text_card(
        self,
        text: str,
        subtitle: str = "",
        style: str = "intro",
        size: Tuple[int, int] = (1080, 1920),
        output_path: Optional[Path] = None
    ) -> Path:
        """
        Generates a premium vertical graphic text card using Pillow.
        Uses a beautiful vertical gradient, centered bold text, and a decorative border.
        """
        width, height = size
        img = Image.new("RGB", size, self.c_primary)
        draw = ImageDraw.Draw(img)

        # 1. Draw smooth vertical gradient background
        # Interpolate between deep primary color (bottom) and a darker tone (top)
        color_start = self.c_primary
        color_end = (0, 0, 5)  # Near black
        for y in range(height):
            ratio = y / height
            r = int(color_start[0] * ratio + color_end[0] * (1 - ratio))
            g = int(color_start[1] * ratio + color_end[1] * (1 - ratio))
            b = int(color_start[2] * ratio + color_end[2] * (1 - ratio))
            draw.line([(0, y), (width, y)], fill=(r, g, b))

        # 2. Draw a subtle glowing decorative border
        border_inset = 40
        draw.rectangle(
            [border_inset, border_inset, width - border_inset, height - border_inset],
            outline=self.c_accent,
            width=6
        )
        draw.rectangle(
            [border_inset + 10, border_inset + 10, width - border_inset - 10, height - border_inset - 10],
            outline=self.c_secondary,
            width=2
        )

        # 3. Add Watermark / Channel branding at the bottom
        wm_font = self._get_font(28)
        draw.text(
            (width / 2, height - 120),
            self.channel_name.upper(),
            font=wm_font,
            fill=self.c_secondary,
            anchor="mm"
        )

        # 4. Text wrap and render centered text
        text_font = self._get_font(72)
        lines = textwrap.wrap(text, width=18)
        
        # Calculate vertical positioning
        line_height = 90
        total_text_height = len(lines) * line_height
        start_y = height / 2 - total_text_height / 2

        if subtitle:
            start_y -= 60  # Shift up slightly to fit subtitle

        # Render main text lines
        for i, line in enumerate(lines):
            draw.text(
                (width / 2, start_y + (i * line_height)),
                line,
                font=text_font,
                fill=(255, 255, 255),
                anchor="mm"
            )

        # 5. Render Subtitle below the main text
        if subtitle:
            sub_font = self._get_font(42)
            sub_y = start_y + total_text_height + 40
            sub_lines = textwrap.wrap(subtitle, width=28)
            for i, line in enumerate(sub_lines):
                draw.text(
                    (width / 2, sub_y + (i * 50)),
                    line,
                    font=sub_font,
                    fill=self.c_accent,
                    anchor="mm"
                )

        # 6. Save or return image path
        if not output_path:
            raise ValueError("Output path must be specified.")
        img.save(output_path, "JPEG", quality=95)
        return output_path

    def create_player_card(
        self,
        player_name: str,
        country: str,
        position: str,
        stats: Dict[str, Any],
        output_path: Path
    ) -> Path:
        """Creates a highly premium statistics/profile card for a player."""
        width, height = 1080, 1920
        img = Image.new("RGB", (width, height), self.c_primary)
        draw = ImageDraw.Draw(img)

        # 1. Gradient Background
        for y in range(height):
            ratio = y / height
            r = int(self.c_primary[0] * ratio + 10 * (1 - ratio))
            g = int(self.c_primary[1] * ratio + 10 * (1 - ratio))
            b = int(self.c_primary[2] * ratio + 10 * (1 - ratio))
            draw.line([(0, y), (width, y)], fill=(r, g, b))

        # Inset glowing borders
        draw.rectangle([40, 40, width - 40, height - 40], outline=self.c_accent, width=8)

        # 2. Player Name Heading
        title_font = self._get_font(76)
        draw.text((width / 2, 220), player_name.upper(), font=title_font, fill=self.c_secondary, anchor="mm")

        # Sub-heading (Country & Position)
        sub_font = self._get_font(40)
        draw.text((width / 2, 300), f"{country} | {position}", font=sub_font, fill=(255, 255, 255), anchor="mm")

        # Draw a separator line
        draw.line([(200, 360), (880, 360)], fill=self.c_accent, width=4)

        # 3. Render stats container card
        card_box = [150, 420, 930, 1600]
        draw.rectangle(card_box, fill=(15, 15, 35), outline=self.c_secondary, width=4)

        # Fill in statistics inside the container
        stat_font_lbl = self._get_font(42)
        stat_font_val = self._get_font(46)
        
        y_pos = 500
        for label, val in stats.items():
            # Left aligned label
            draw.text((220, y_pos), str(label).upper(), font=stat_font_lbl, fill=(180, 180, 200), anchor="lm")
            # Right aligned value
            draw.text((860, y_pos), str(val), font=stat_font_val, fill=(255, 255, 255), anchor="rm")
            
            # Subtle divider
            draw.line([(200, y_pos + 60), (880, y_pos + 60)], fill=(40, 40, 70), width=2)
            y_pos += 130

        # Watermark
        wm_font = self._get_font(28)
        draw.text((width / 2, height - 120), self.channel_name.upper(), font=wm_font, fill=self.c_secondary, anchor="mm")

        img.save(output_path, "JPEG", quality=95)
        return output_path

    def assemble_visuals(self, script: Any, segment_timings: List[Tuple[int, int]]) -> List[Dict[str, Any]]:
        """
        Coordinates generating/downloading visuals matching each script segment.

        Image source priority:
        1. TheSportsDB — for real player photos and team imagery
        2. Pexels — for generic backgrounds/atmosphere (stadiums, crowds)
        3. Pillow-generated branded cards — fallback when APIs fail

        Parameters
        ----------
        script : VideoScript
            The video script structure.
        segment_timings : list of tuples
            The (start_ms, end_ms) timestamps per segment.

        Returns
        -------
        list of dicts
            [{'type': 'image', 'path': str, 'duration': float}]
        """
        visuals_dir = Path("content_engine_workspace")
        visuals_dir.mkdir(exist_ok=True)

        visual_segments = []

        # Pre-extract all player and team names referenced in this script
        topic_players, topic_teams = self._extract_entities_from_topic(script)
        logger.info(f"Entities from topic — players: {topic_players}, teams: {topic_teams}")

        # Find matching quiz question in database if it is a quiz
        quiz_data = None
        quiz_bg_path = None
        if script.content_type == "quiz":
            try:
                from content_engine.world_cup_data import QUIZ_QUESTIONS
                target_start = script.topic.split(": ", 1)[-1][:40].lower()
                for q in QUIZ_QUESTIONS:
                    if q["question"].lower().startswith(target_start) or target_start in q["question"].lower():
                        quiz_data = q
                        break
            except Exception as e:
                logger.warning(f"Failed to match quiz question in database: {e}")
            
            if not quiz_data:
                quiz_data = {
                    "question": "Which country has played the most World Cup matches without winning?",
                    "options": ["Mexico", "Switzerland", "Sweden", "South Korea"],
                    "answer": "Mexico",
                    "answer_detail": "Mexico has played 60 World Cup matches without lifting the trophy."
                }

            # Download a nice quiz background image — try TheSportsDB team image first
            try:
                # Extract any team names from the quiz question for a relevant bg
                quiz_teams = self._extract_teams_from_visual_cue(quiz_data["question"])
                if quiz_teams:
                    quiz_bg_path = self._tsdb_get_team_image(quiz_teams[0], visuals_dir)
                if not quiz_bg_path or not quiz_bg_path.exists():
                    bg_query = self._extract_pexels_query(quiz_data["question"])
                    quiz_bg_path = self.fetch_stock_image(bg_query, visuals_dir)
                if not quiz_bg_path or not quiz_bg_path.exists():
                    quiz_bg_path = self.fetch_stock_image("soccer stadium", visuals_dir)
            except Exception as e:
                logger.warning(f"Failed to download background image for quiz: {e}")

        for idx, seg in enumerate(script.segments):
            timing = segment_timings[idx]
            duration_s = (timing[1] - timing[0]) / 1000.0

            visual_cue = seg.visual_cue
            seg_path = visuals_dir / f"visual_{idx}_{random.randint(1000, 9999)}.jpg"

            # 0. Custom high-impact first frame hook generation (Thumbnail equivalent)
            if idx == 0 and hasattr(script, "thumbnail_text") and script.thumbnail_text:
                hook_text = script.thumbnail_text
                if script.content_type == "quiz" and quiz_data:
                    ans_word = quiz_data["answer"].lower()
                    if ans_word in hook_text.lower():
                        hook_text = "IMPOSSIBLE QUIZ!"
                
                # Fetch player / team cutout
                player_image_path = None
                cue_players = self._extract_players_from_visual_cue(visual_cue)
                all_players = list(dict.fromkeys(cue_players + topic_players))
                for pname in all_players:
                    path = self._tsdb_get_player_image(pname, visuals_dir)
                    if path and path.exists():
                        player_image_path = path
                        break
                
                if not player_image_path:
                    cue_teams = self._extract_teams_from_visual_cue(visual_cue)
                    all_teams = list(dict.fromkeys(cue_teams + topic_teams))
                    for tname in all_teams:
                        path = self._tsdb_get_team_image(tname, visuals_dir)
                        if path and path.exists():
                            player_image_path = path
                            break
                            
                # Fetch Pexels background
                query = self._extract_pexels_query(visual_cue)
                original_bg_path = self.fetch_stock_image(query, visuals_dir)
                if not original_bg_path or not original_bg_path.exists():
                    original_bg_path = self.fetch_stock_image("soccer stadium", visuals_dir)
                    
                self._create_high_impact_visual_frame(
                    player_img_path=player_image_path,
                    bg_img_path=original_bg_path,
                    text=hook_text,
                    output_path=seg_path,
                    content_type=script.content_type,
                    quiz_data=quiz_data
                )
                
                visual_segments.append({
                    "type": "image",
                    "path": str(seg_path.absolute()),
                    "duration": duration_s,
                    "original_bg_path": str(original_bg_path.absolute()) if original_bg_path else None,
                    "player_image_path": str(player_image_path.absolute()) if player_image_path else None,
                })
                continue

            # 1. Special Quiz Visual Card Generation
            if script.content_type == "quiz" and quiz_data and idx in (1, 2, 3):
                frame_type = idx  # 1: question, 2: countdown, 3: answer
                self.create_quiz_graphic(
                    quiz_data["question"],
                    quiz_data["options"],
                    quiz_data["answer"],
                    quiz_data["answer_detail"],
                    frame_type,
                    seg_path,
                    bg_image_path=quiz_bg_path
                )
                visual_segments.append({
                    "type": "image",
                    "path": str(seg_path.absolute()),
                    "duration": duration_s
                })
                continue

            # 2. Player Profile Template & Stat card decision
            if script.content_type == "player_profile" and idx == 1:
                # Generate a player stat card for the second segment
                stats = {
                    "Club": topic_data_fallback(script, "club", "Top European Club"),
                    "Age": topic_data_fallback(script, "age", "25"),
                    "Int. Goals": topic_data_fallback(script, "goals_international", "15"),
                    "Role": topic_data_fallback(script, "position", "Forward"),
                    "Nation": topic_data_fallback(script, "country", "World Cup Star"),
                }
                self.create_player_card(script.topic, script.topic, stats["Role"], stats, seg_path)
                visual_segments.append({
                    "type": "image",
                    "path": str(seg_path.absolute()),
                    "duration": duration_s
                })
                continue

            # 3. Text style cards or fallback
            if "quiz_question" in visual_cue or "text_card" in visual_cue:
                subtitle = "Make your guess!" if "question" in visual_cue else ""
                self.create_text_card(seg.narration[:60] + "...", subtitle, style="intro", output_path=seg_path)
                visual_segments.append({
                    "type": "image",
                    "path": str(seg_path.absolute()),
                    "duration": duration_s
                })
                continue

            # ── 4. SMART IMAGE SOURCING (TheSportsDB → Pexels → fallback) ──
            image_path = None

            # 4a. Try to find player images from TheSportsDB
            #     Check visual cue AND topic-level players
            cue_players = self._extract_players_from_visual_cue(visual_cue)
            all_players = list(dict.fromkeys(cue_players + topic_players))  # deduplicate, preserve order

            for pname in all_players:
                image_path = self._tsdb_get_player_image(pname, visuals_dir)
                if image_path and image_path.exists():
                    logger.info(f"🎯 Using TheSportsDB player image for '{pname}' (segment {idx})")
                    break

            # 4b. If no player image, try team images from TheSportsDB
            if not image_path or not image_path.exists():
                cue_teams = self._extract_teams_from_visual_cue(visual_cue)
                all_teams = list(dict.fromkeys(cue_teams + topic_teams))

                for tname in all_teams:
                    image_path = self._tsdb_get_team_image(tname, visuals_dir)
                    if image_path and image_path.exists():
                        logger.info(f"🎯 Using TheSportsDB team image for '{tname}' (segment {idx})")
                        break

            # 4c. Fall back to Pexels for generic/atmospheric shots
            if not image_path or not image_path.exists():
                query = self._extract_pexels_query(visual_cue)
                image_path = self.fetch_stock_image(query, visuals_dir)
                if image_path and image_path.exists():
                    logger.info(f"📷 Using Pexels stock image for segment {idx} (query: '{query}')")

            # 4d. Use the image or create a branded text card as final fallback
            if image_path and image_path.exists():
                # If first frame, apply a high-impact hook overlay (with spoiler safety)
                if idx == 0 and hasattr(script, "thumbnail_text") and script.thumbnail_text:
                    hook_text = script.thumbnail_text
                    if script.content_type == "quiz" and quiz_data:
                        ans_word = quiz_data["answer"].lower()
                        if ans_word in hook_text.lower():
                            hook_text = "IMPOSSIBLE QUIZ!"
                    self._apply_visual_hook_overlay(image_path, hook_text)
                visual_segments.append({
                    "type": "image",
                    "path": str(image_path.absolute()),
                    "duration": duration_s
                })
            else:
                # Fallback: create a beautiful branded card using narration
                logger.info(f"All image sources failed for segment {idx}. Creating fallback text card...")
                self.create_text_card(
                    text=seg.narration[:80] + "...",
                    subtitle="World Cup 2026",
                    style="stat",
                    output_path=seg_path
                )
                visual_segments.append({
                    "type": "image",
                    "path": str(seg_path.absolute()),
                    "duration": duration_s
                })

        # Add 1.5 seconds of padding to the final segment to prevent audio cutting short
        if visual_segments:
            visual_segments[-1]["duration"] += 1.5
            logger.info("Extended final visual segment duration by 1.5s to prevent audio cut-off.")

        return visual_segments

    def _apply_visual_hook_overlay(self, image_path: Path, hook_text: str):
        """Applies a giant, high-impact text hook overlay on top of the first segment image."""
        try:
            with Image.open(image_path) as img:
                if img.mode != "RGB":
                    img = img.convert("RGB")
                
                draw = ImageDraw.Draw(img)
                width, height = img.size
                
                # Scaled to image width (around 7.5% of width)
                font_size = int(width * 0.075)
                if font_size < 24:
                    font_size = 24
                font = self._get_font(font_size)
                
                # Wrap the hook text
                lines = textwrap.wrap(hook_text.upper(), width=14)
                
                line_height = int(font_size * 1.3)
                text_height = len(lines) * line_height
                
                # Position in the upper-middle of the screen (around 35% from the top)
                center_y = int(height * 0.35)
                start_y = center_y - (text_height // 2)
                
                for i, line in enumerate(lines):
                    try:
                        bbox = draw.textbbox((0, 0), line, font=font)
                        tw = bbox[2] - bbox[0]
                        th = bbox[3] - bbox[1]
                    except AttributeError:
                        tw, th = draw.textsize(line, font=font)
                    
                    tx = (width - tw) // 2
                    ty = start_y + (i * line_height)
                    
                    padding_x = 24
                    padding_y = 12
                    box_coords = [tx - padding_x, ty - padding_y, tx + tw + padding_x, ty + th + padding_y]
                    
                    # Shadow offset
                    draw.rectangle([c + 6 for c in box_coords], fill=(0, 0, 0))
                    # Vibrant backing box (yellow/gold secondary color)
                    draw.rectangle(box_coords, fill=self.c_secondary)
                    # Thin black border
                    draw.rectangle(box_coords, outline=(0, 0, 0), width=3)
                    
                    # Draw text
                    draw.text((tx, ty - 2), line, font=font, fill=(0, 0, 0))
                
                img.save(image_path, "JPEG", quality=95)
                logger.info(f"Applied visual hook overlay to {image_path.name}: '{hook_text}'")
        except Exception as e:
            logger.warning(f"Failed to apply visual hook overlay: {e}")

    def _extract_pexels_query(self, visual_cue: str) -> str:
        """Converts detailed visual cues into short, searchable Pexels queries."""
        # Lowercase and clean
        q = visual_cue.lower().strip()
        
        # Remove unwanted sports terminology to prevent mismatch (e.g. baseball)
        unwanted_sports = ["baseball", "basketball", "tennis", "golf", "cricket", "rugby", "hockey", "american football"]
        for sport in unwanted_sports:
            q = q.replace(sport, "soccer")
            
        # Remove common filler/UI words
        filler_words = r"\b(showing|illustration of|image of|photo of|clip of|background of|a|an|the|on-screen|onscreen|text|graphic|with|options|appearing|choice|multiple|show|screen|display|overlay|card|diagram|animation|concept|suggested|entries|various|highlighting|pointing|thinking|person|closeup|wide|angle|aerial|panoramic|spinning|rotating|glowing|shimmering|pulsing|faded|darkened|blurred)\b"
        q = re.sub(filler_words, "", q)
        
        # Keep only letters, spaces
        q = re.sub(r"[^a-z\s]", "", q)
        
        # Split and filter stop words
        stop_words = {"and", "or", "to", "in", "at", "on", "with", "from", "by", "for", "about", "that", "this", "these", "those", "be", "is", "are", "was", "were", "been", "have", "has", "had", "do", "does", "did", "can", "could", "would", "should", "will", "shall", "may", "might", "must", "of", "no", "yes", "not", "but"}
        words = [w for w in q.split() if w not in stop_words and len(w) > 2]
        
        # Select the most representative keywords
        if not words:
            return "soccer"
            
        # Check if we have football specific keywords, prioritize them
        football_terms = {"soccer", "football", "match", "player", "stadium", "pitch", "goal", "referee", "world", "cup", "kick", "penalty", "jersey", "crest", "trophy"}
        
        priority_words = []
        other_words = []
        for w in words:
            if w in football_terms or w in ["mexico", "brazil", "argentina", "germany", "france", "england", "spain", "portugal", "italy", "netherlands", "croatia", "morocco", "uruguay", "usa", "canada"]:
                priority_words.append(w)
            else:
                other_words.append(w)
                
        selected_words = (priority_words + other_words)[:3]
        query = " ".join(selected_words)
        
        # Ensure the query is context-locked to football/soccer
        has_football_term = any(term in query for term in football_terms)
        if not has_football_term:
            query = f"{query} soccer"
            
        return query

    def _crop_to_portrait(self, img: Image.Image, target_width: int, target_height: int) -> Image.Image:
        """Resizes and crops a PIL Image to fill target_width x target_height in portrait mode."""
        img_w, img_h = img.size
        target_ratio = target_width / target_height
        img_ratio = img_w / img_h
        
        if img_ratio > target_ratio:
            # Image is too wide: scale based on height
            new_h = target_height
            new_w = int(img_w * (target_height / img_h))
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.ANTIALIAS)
            # Crop center width
            left = (new_w - target_width) // 2
            img = img.crop((left, 0, left + target_width, target_height))
        else:
            # Image is too tall: scale based on width
            new_w = target_width
            new_h = int(img_h * (target_width / img_w))
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.ANTIALIAS)
            # Crop center height
            top = (new_h - target_height) // 2
            img = img.crop((0, top, target_width, top + target_height))
        return img

    def create_quiz_graphic(
        self,
        question: str,
        options: List[str],
        answer: str,
        answer_detail: str,
        frame_type: int,  # 1: question, 2: countdown, 3: answer
        output_path: Path,
        bg_image_path: Optional[Path] = None
    ) -> Path:
        """Generates a premium visual card for Interactive Quiz segments matching user styling."""
        width, height = 1080, 1920
        
        # 1. Background Setup (Stock image with dark overlay or deep gradient fallback)
        if bg_image_path and Path(bg_image_path).is_file():
            try:
                with Image.open(bg_image_path) as bg_img:
                    img = bg_img.convert("RGBA")
                    img = self._crop_to_portrait(img, width, height)
                
                # Apply a semi-transparent dark overlay (navy/dark gray) for readability
                overlay = Image.new("RGBA", (width, height), (10, 10, 20, 175))
                img = Image.alpha_composite(img, overlay)
            except Exception as e:
                logger.warning(f"Failed to load background image {bg_image_path}: {e}")
                img = Image.new("RGBA", (width, height), (10, 10, 20, 255))
        else:
            # Fallback to beautiful vertical gradient background
            img = Image.new("RGBA", (width, height), (10, 10, 20, 255))
            draw = ImageDraw.Draw(img)
            color_start = self.c_primary
            color_end = (5, 5, 12, 255)
            for y in range(height):
                ratio = y / height
                r = int(color_start[0] * ratio + color_end[0] * (1 - ratio))
                g = int(color_start[1] * ratio + color_end[1] * (1 - ratio))
                b = int(color_start[2] * ratio + color_end[2] * (1 - ratio))
                draw.line([(0, y), (width, y)], fill=(r, g, b, 255))

        draw = ImageDraw.Draw(img)

        # Theme colors
        c_orange = (235, 130, 0, 255)     # Amber/orange border and active elements
        c_green = (50, 220, 50, 255)       # Neon green for correct answers
        c_gray = (100, 100, 110, 255)      # Medium gray for inactive/wrong answers
        c_dark_gray = (50, 50, 60, 255)    # Dark gray for inactive borders
        c_box_bg = (12, 12, 18, 210)       # Semi-transparent dark background for cards
        c_box_bg_incorrect = (8, 8, 12, 230) # Darker, more opaque background for incorrect options
        c_box_bg_correct = (12, 45, 12, 220) # Semi-transparent green background for correct option

        # 2. Draw Question Box
        q_box = [100, 260, 980, 560]
        # Rounded rectangle for the question box
        draw.rounded_rectangle(q_box, radius=24, fill=c_box_bg, outline=c_orange, width=4)

        # Question text (wrapped)
        q_font = self._get_font(48)
        q_lines = textwrap.wrap(question, width=28)
        
        # Center the text inside the question box vertically
        line_height = 65
        total_text_height = len(q_lines) * line_height
        start_y = q_box[1] + (300 - total_text_height) // 2
        
        for idx, line in enumerate(q_lines):
            draw.text(
                (width / 2, start_y + (idx * line_height)),
                line,
                font=q_font,
                fill=(255, 255, 255, 255),
                anchor="mm"
            )

        # 3. Draw Options
        opt_font = self._get_font(42)
        opt_y = 630
        letter_mapping = ["A", "B", "C", "D"]
        
        for o_idx, opt in enumerate(options):
            # Clean option text
            opt_text = opt
            if len(opt_text) >= 2 and opt_text[1] == ')':
                letter = opt_text[0]
                val_text = opt_text[2:].strip()
            else:
                letter = letter_mapping[o_idx]
                val_text = opt.strip()

            # Determine styling based on frame_type (1: Question, 2: Countdown, 3: Answer Reveal)
            is_correct = (
                val_text.lower() == answer.lower() or 
                opt_text.lower() == answer.lower() or 
                letter.lower() == answer[0].lower() or 
                answer.lower().startswith(val_text.lower())
            )
            
            box_fill = c_box_bg
            box_outline = c_orange
            letter_fill = c_orange
            text_color = (255, 255, 255, 255)
            letter_text_color = (0, 0, 0, 255)
            border_width = 3

            if frame_type == 3:
                # Answer Reveal coloring
                if is_correct:
                    box_fill = c_box_bg_correct
                    box_outline = c_green
                    letter_fill = c_green
                    text_color = (255, 255, 255, 255)
                    border_width = 5
                else:
                    box_fill = c_box_bg_incorrect
                    box_outline = c_dark_gray
                    letter_fill = c_gray
                    text_color = (130, 130, 140, 255)
                    letter_text_color = (30, 30, 30, 255)

            # Option Container Box
            box_coords = [150, opt_y, 930, opt_y + 130]
            draw.rounded_rectangle(box_coords, radius=18, fill=box_fill)

            # Option Letter Tab (rounded left side, flat right side)
            letter_box = [150, opt_y, 250, opt_y + 130]
            draw.rounded_rectangle(letter_box, radius=18, fill=letter_fill)
            # Flatten the right side of the letter tab by drawing a flat rectangle over it
            draw.rectangle([200, opt_y, 250, opt_y + 130], fill=letter_fill)

            # Draw the outer container outline
            draw.rounded_rectangle(box_coords, radius=18, outline=box_outline, width=border_width)

            # Draw vertical line separating the letter box from the option text
            draw.line([(250, opt_y), (250, opt_y + 130)], fill=box_outline, width=border_width)

            # Letter Text
            draw.text(
                (200, opt_y + 65),
                letter,
                font=self._get_font(48),
                fill=letter_text_color,
                anchor="mm"
            )

            # Option Text
            draw.text(
                (285, opt_y + 65),
                val_text,
                font=opt_font,
                fill=text_color,
                anchor="lm"
            )

            # If Answer Reveal state and this is correct, draw checkmark
            if frame_type == 3 and is_correct:
                # Draw a neat vector checkmark: two connected lines
                cx, cy = 880, opt_y + 65
                draw.line([(cx - 16, cy + 2), (cx - 6, cy + 12)], fill=c_green, width=6)
                draw.line([(cx - 6, cy + 12), (cx + 16, cy - 12)], fill=c_green, width=6)

            opt_y += 165

        # 4. Timer Bar or Answer Explanation
        if frame_type == 2:
            # THINKING... header and custom progress bar
            draw.text(
                (width / 2, opt_y + 35),
                "THINKING...",
                font=self._get_font(34),
                fill=c_orange,
                anchor="mm"
            )
            # Outer bar (track)
            bar_coords = [250, opt_y + 70, 830, opt_y + 105]
            draw.rounded_rectangle(bar_coords, radius=18, fill=(150, 150, 160, 80), outline=(200, 200, 210, 100), width=2)
            
            # Progress fill (fixed at 45% for visual indicator during thinking segment)
            fill_width = int((830 - 250) * 0.45)
            if fill_width > 36:
                draw.rounded_rectangle(
                    [250, opt_y + 70, 250 + fill_width, opt_y + 105],
                    radius=18,
                    fill=c_orange
                )
                
        elif frame_type == 3:
            # Explanation Box
            exp_box = [150, opt_y + 10, 930, opt_y + 190]
            draw.rounded_rectangle(exp_box, radius=18, fill=c_box_bg, outline=c_green, width=3)
            
            draw.text(
                (width / 2, opt_y + 40),
                "EXPLANATION",
                font=self._get_font(32),
                fill=c_green,
                anchor="mm"
            )
            
            detail_font = self._get_font(30)
            detail_lines = textwrap.wrap(answer_detail, width=42)
            det_y = opt_y + 85
            for line in detail_lines[:2]:
                draw.text(
                    (width / 2, det_y),
                    line,
                    font=detail_font,
                    fill=(220, 220, 235, 255),
                    anchor="mm"
                )
                det_y += 40

        # 5. Channel Watermark / Branding at the bottom
        wm_font = self._get_font(28)
        draw.text(
            (width / 2, height - 120),
            self.channel_name.upper(),
            font=wm_font,
            fill=c_orange,
            anchor="mm"
        )

        # Save as RGB JPEG
        final_img = img.convert("RGB")
        final_img.save(output_path, "JPEG", quality=95)
        logger.info(f"Saved custom quiz graphic frame: {output_path.name}")
        return output_path

    def _create_high_impact_visual_frame(
        self,
        player_img_path: Optional[Path],
        bg_img_path: Optional[Path],
        text: str,
        output_path: Path,
        content_type: str = "",
        quiz_data: Optional[dict] = None
    ) -> Path:
        """Composites a premium vertical visual cover for the first frame hook."""
        width, height = 1080, 1920
        
        # 1. Prepare Background
        img = None
        if bg_img_path and bg_img_path.is_file():
            try:
                img = Image.open(bg_img_path).convert("RGBA")
                img = self._crop_to_portrait(img, width, height)
                # Blur background for depth of field and readability
                img = img.filter(ImageFilter.GaussianBlur(radius=15))
                # Add dark navy tint overlay
                overlay = Image.new("RGBA", (width, height), (10, 10, 25, 140))
                img = Image.alpha_composite(img, overlay)
            except Exception as e:
                logger.warning(f"Failed to process background {bg_img_path}: {e}")
                
        if img is None:
            # Deep premium gradient fallback
            img = Image.new("RGBA", (width, height), (10, 10, 20, 255))
            draw = ImageDraw.Draw(img)
            for y in range(height):
                ratio = y / height
                r = int(self.c_primary[0] * ratio + 5 * (1 - ratio))
                g = int(self.c_primary[1] * ratio + 5 * (1 - ratio))
                b = int(self.c_primary[2] * ratio + 10 * (1 - ratio))
                draw.line([(0, y), (width, y)], fill=(r, g, b, 255))
                
        draw = ImageDraw.Draw(img)
        
        # 2. Draw Accent Glow behind player/text (bottom-right center)
        glow_color = self.c_accent
        glow_size = 900
        try:
            glow = Image.new("RGBA", (glow_size, glow_size), (0, 0, 0, 0))
            glow_draw = ImageDraw.Draw(glow)
            glow_draw.ellipse([0, 0, glow_size, glow_size], fill=(*glow_color, 80))
            glow = glow.filter(ImageFilter.GaussianBlur(radius=150))
            img.paste(glow, (width // 2 - 100, height // 2 - 100), mask=glow)
        except Exception as e:
            logger.warning(f"Failed to draw visual glow: {e}")
            
        # 3. Composite Player/Team Image
        has_player = False
        if player_img_path and player_img_path.is_file():
            try:
                p_img = Image.open(player_img_path).convert("RGBA")
                is_png = player_img_path.suffix.lower() == ".png"
                
                # Check if it has transparency (is cutout)
                has_alpha = False
                if is_png and "alpha" in p_img.getbands():
                    extrema = p_img.getextrema()
                    if len(extrema) >= 4 and extrema[3][0] < 255:
                        has_alpha = True
                
                if has_alpha:
                    # Scale player cutout to fit bottom right (approx 55% of height)
                    p_w, p_h = p_img.size
                    target_h = int(height * 0.55)
                    target_w = int(p_w * (target_h / p_h))
                    p_img = p_img.resize((target_w, target_h), Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.ANTIALIAS)
                    
                    # Generate neon outline glow
                    p_alpha = p_img.split()[3]
                    outline_mask = p_alpha.filter(ImageFilter.MaxFilter(15)) # dilate
                    outline_mask = outline_mask.filter(ImageFilter.GaussianBlur(radius=10))
                    
                    outline_glow = Image.new("RGBA", p_img.size, (*self.c_secondary, 255))
                    glow_back = Image.new("RGBA", (width, height), (0, 0, 0, 0))
                    
                    px = width - target_w + 50
                    py = height - target_h + 50
                    
                    glow_back.paste(outline_glow, (px, py), mask=outline_mask)
                    glow_back = glow_back.filter(ImageFilter.GaussianBlur(radius=8))
                    
                    img = Image.alpha_composite(img, glow_back)
                    img.paste(p_img, (px, py), mask=p_img)
                    has_player = True
                else:
                    # Non-transparent player image (JPEG). Crop into a circle badge
                    badge_size = 500
                    mask = Image.new("L", (badge_size, badge_size), 0)
                    mask_draw = ImageDraw.Draw(mask)
                    mask_draw.ellipse([10, 10, badge_size - 10, badge_size - 10], fill=255)
                    mask = mask.filter(ImageFilter.GaussianBlur(radius=2))
                    
                    p_cropped = self._crop_to_portrait(p_img, badge_size, badge_size)
                    
                    badge = Image.new("RGBA", (badge_size, badge_size), (0, 0, 0, 0))
                    badge.paste(p_cropped, (0, 0), mask=mask)
                    
                    # Draw gold border on a layer behind the badge
                    border_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
                    border_draw = ImageDraw.Draw(border_layer)
                    bx = width - badge_size - 80
                    by = height - badge_size - 180
                    border_draw.ellipse([bx - 6, by - 6, bx + badge_size + 6, by + badge_size + 6], outline=self.c_secondary, width=8)
                    
                    img = Image.alpha_composite(img, border_layer)
                    img.paste(badge, (bx, by), mask=mask)
                    has_player = True
            except Exception as e:
                logger.warning(f"Failed to composite player image: {e}")
                
        draw = ImageDraw.Draw(img)
        
        # 4. Draw Slanted Text Banners (Multi-line)
        hook_text = text.upper()
        lines = textwrap.wrap(hook_text, width=14)
        
        font_size = int(width * 0.08)  # ~86px
        font = self._get_font(font_size)
        
        line_height = int(font_size * 1.3)
        total_text_height = len(lines) * line_height
        
        # If we have a player on the right, position text on the left, otherwise center it
        start_x = 80 if has_player else (width - int(width * 0.7)) // 2
        start_y = int(height * 0.32) - (total_text_height // 2)
        
        for i, line in enumerate(lines[:3]): # Max 3 lines
            bbox = draw.textbbox((0, 0), line, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            
            padding_x = 35
            padding_y = 15
            
            lx = start_x
            ly = start_y + (i * line_height)
            
            t_color = (255, 255, 255, 255)
            b_outline = self.c_accent
            if i == len(lines) - 1 or i == 1:
                t_color = self.c_secondary
                b_outline = (255, 50, 50, 255)
                
            pts = [
                (lx - padding_x, ly - padding_y),
                (lx + tw + padding_x, ly - padding_y),
                (lx + tw + padding_x - 15, ly + th + padding_y),
                (lx - padding_x - 15, ly + th + padding_y)
            ]
            
            shadow_pts = [(pt[0] + 6, pt[1] + 6) for pt in pts]
            draw.polygon(shadow_pts, fill=(0, 0, 0, 160))
            
            draw.polygon(pts, fill=(12, 12, 18, 230))
            draw.polygon(pts, outline=b_outline, width=4)
            
            cx = lx + tw // 2 - 8
            cy = ly + th // 2
            draw.text((cx + 3, cy + 3), line, font=font, fill=(0, 0, 0, 255), anchor="mm")
            draw.text((cx, cy), line, font=font, fill=t_color, anchor="mm")
            
        # 5. Draw Badges
        badge_text = "TRENDING"
        if content_type == "breaking_news":
            badge_text = "BREAKING"
        elif content_type == "match_preview":
            badge_text = "LIVE REACTION" if "live" in text.lower() else "PREVIEW"
        elif content_type == "quiz":
            badge_text = "IMPOSSIBLE"
            
        badge_font = self._get_font(28)
        bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
        bw = bbox[2] - bbox[0]
        bh = bbox[3] - bbox[1]
        
        badge_coords = [60, 80, 60 + bw + 40, 80 + bh + 30]
        draw.rounded_rectangle(badge_coords, radius=10, fill=(255, 30, 30, 255))
        tx = (badge_coords[0] + badge_coords[2]) // 2
        ty = (badge_coords[1] + badge_coords[3]) // 2
        draw.text((tx, ty - 2), badge_text, font=badge_font, fill=(255, 255, 255, 255), anchor="mm")
        
        # 6. Channel Watermark
        wm_font = self._get_font(28)
        draw.text(
            (width / 2, height - 120),
            self.channel_name.upper(),
            font=wm_font,
            fill=self.c_secondary,
            anchor="mm"
        )
        
        final_img = img.convert("RGB")
        final_img.save(output_path, "JPEG", quality=95)
        logger.info(f"Saved custom high-impact visual frame: {output_path.name}")
        return output_path


def topic_data_fallback(script: Any, key: str, default: str) -> str:
    """Helper to extract topic data safely from script metadata."""
    try:
        # Check if topic_data or attributes exist on the script
        return getattr(script, key, default)
    except Exception:
        return default
