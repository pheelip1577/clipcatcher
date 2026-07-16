"""
Settings manager - saves and loads user config to/from JSON.
"""
import json
import os
from pathlib import Path
from typing import Any


DEFAULT_SETTINGS = {
    "threshold": 8.0,
    "detection_mode": "relative",
    "hype_multiplier": 3.0,
    "hype_min_floor": 2.0,
    "hype_warmup": 60,
    "buf_before": 15,
    "buf_after": 10,
    "cooldown": 30,
    "quality": "best",
    "save_folder": str(Path.home() / "Videos" / "ClipCatcher"),
    "notify_on_clip": True,
    "sound_on_spike": False,
    "tiktok_crop": True,
    "tiktok_watermark": True,
    "youtube_auto_upload": False,
    "youtube_upload_shorts": True,
    "youtube_visibility": "private",
    "youtube_title_template": "{channel} - {hype}% Hype Moment! #shorts",
    "youtube_description": "Auto-clipped by ClipCatcher\nChannel: twitch.tv/{channel}\nCaptured: {datetime}\nHype: {hype}%\nDuration: {duration}s",
    "youtube_tags": "twitch,clip,shorts",
    "youtube_schedule_uploads": False,
    "youtube_schedule_interval": 12.0,
    "youtube_last_scheduled_time": "",
    "wc_streamers": ["ishowspeed", "castro1021", "ibai", "davooeneize"],
    "match_title": "WORLD CUP 2026",
    "match_score": "LIVE REACTION",
    "youtube_wc_grid_template": "{streamer1} vs {streamer2} vs {streamer3} vs {streamer4} INSANE REACTION! #shorts #worldcup",
    # ─── ContentEngine settings ─────────────────────────────────────────
    "ce_active_niche": "world_cup_2026",
    "ce_enabled": False,
    "ce_gemini_api_key": "",
    "ce_pexels_api_key": "",
    "ce_tts_voice": "en-US-GuyNeural",
    "ce_tts_rate": "+18%",
    "ce_output_folder": str(Path.home() / "Videos" / "ContentEngine"),
    "ce_max_uploads_per_day": 6,
    "ce_upload_visibility": "public",
    "ce_youtube_category": "17",
    "ce_channel_name": "World Cup Central",
    "ce_schedule_interval_hours": 4,
    "ce_active_templates": [
        "youtube_inspiration", "breaking_news", "match_preview", "player_profile",
        "top_10", "daily_recap", "quiz", "history",
        "squad_guide", "controversy", "facts"
    ],
    "ce_background_music": False,
    "ce_subtitle_style": "word_highlight",
    "ce_auto_upload": True,
    "ce_compiler_type": "ffmpeg",
}

CONFIG_PATH = Path.home() / ".clipcatcher" / "settings.json"


class Settings:
    def __init__(self):
        self._data: dict[str, Any] = dict(DEFAULT_SETTINGS)
        self.load()

    def load(self):
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH) as f:
                    saved = json.load(f)
                self._data.update(saved)
            except Exception:
                pass

    def save(self):
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump(self._data, f, indent=2)

    def get(self, key: str, default=None):
        return self._data.get(key, DEFAULT_SETTINGS.get(key, default))

    def set(self, key: str, value: Any):
        self._data[key] = value
        self.save()

    def __getitem__(self, key):
        return self.get(key)

    def __setitem__(self, key, value):
        self.set(key, value)
