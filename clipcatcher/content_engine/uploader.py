"""
YouTube upload wrapper for ContentEngine.
Wraps app/youtube.py with ContentEngine-specific logic:
- SEO-optimized metadata
- Automatic #Shorts tagging
- Thumbnail upload
- Quota tracking
- Retry logic
"""
import logging
import time
import json
import threading
from pathlib import Path
from datetime import datetime, date
from typing import Optional, Callable

from app import youtube

logger = logging.getLogger(__name__)

QUOTA_PATH = Path.home() / ".clipcatcher" / "ce_quota.json"


class ContentUploader:
    """Handles YouTube uploads for ContentEngine videos."""

    def __init__(self, settings):
        self.settings = settings
        self._lock = threading.Lock()

    def _load_quota(self) -> dict:
        """Load today's quota usage."""
        try:
            if QUOTA_PATH.exists():
                with open(QUOTA_PATH) as f:
                    data = json.load(f)
                if data.get("date") == str(date.today()):
                    return data
        except Exception:
            pass
        return {"date": str(date.today()), "uploads": 0}

    def _save_quota(self, data: dict):
        """Save quota usage."""
        try:
            QUOTA_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(QUOTA_PATH, "w") as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning(f"Failed to save quota data: {e}")

    def get_uploads_today(self) -> int:
        """Get number of uploads completed today."""
        return self._load_quota().get("uploads", 0)

    def get_uploads_remaining(self) -> int:
        """Get remaining upload slots for today."""
        max_uploads = self.settings.get("ce_max_uploads_per_day", 6)
        return max(0, max_uploads - self.get_uploads_today())

    def can_upload(self) -> bool:
        """Check if we can upload (quota not exceeded)."""
        return self.get_uploads_remaining() > 0

    def upload(
        self,
        video_path: Path,
        title: str,
        description: str,
        tags: list,
        thumbnail_path: Path = None,
        visibility: str = None,
        category_id: str = None,
        progress_callback: Optional[Callable[[int], None]] = None,
        max_retries: int = 2
    ) -> Optional[str]:
        """
        Upload a video to YouTube with ContentEngine metadata.

        Returns the video URL on success, None on failure.
        """
        with self._lock:
            if not self.can_upload():
                logger.warning("Daily upload quota exceeded. Skipping upload.")
                return None

        if visibility is None:
            visibility = self.settings.get("ce_upload_visibility", "public")
        if category_id is None:
            category_id = self.settings.get("ce_youtube_category", "17")

        # Ensure #Shorts is in title
        if "#Shorts" not in title and "#shorts" not in title:
            short_tag = " #Shorts"
            if len(title) + len(short_tag) <= 100:
                title += short_tag

        # Ensure title fits YouTube's 100-char limit
        title = title[:100]

        # Add standard hashtags to description
        channel_name = self.settings.get("ce_channel_name", "World Cup Central")
        description += f"\n\n🔔 Follow @{channel_name} for daily World Cup content!"
        description += "\n\n#WorldCup #WorldCup2026 #Football #Soccer #Shorts"

        # Convert tags list to comma-separated string (youtube.py expects string)
        tags_str = ",".join(tags) if isinstance(tags, list) else tags

        # Check YouTube is linked
        if not youtube.is_linked():
            logger.error("YouTube account not linked. Please authenticate first.")
            return None

        # Upload with retries
        video_url = None
        last_error = None

        for attempt in range(max_retries + 1):
            if attempt > 0:
                wait_time = 5 * attempt
                logger.info(f"Retry {attempt}/{max_retries} in {wait_time}s...")
                time.sleep(wait_time)

            result = {"url": None, "error": None}

            def on_success(url):
                result["url"] = url

            def on_error(err):
                result["error"] = err

            youtube.upload_video(
                filepath=str(video_path),
                title=title,
                description=description,
                tags=tags_str,
                visibility=visibility,
                progress_callback=progress_callback,
                success_callback=on_success,
                error_callback=on_error,
                category_id=category_id
            )

            if result["url"]:
                video_url = result["url"]
                logger.info(f"✅ Upload successful: {video_url}")
                break
            else:
                last_error = result["error"]
                logger.warning(f"Upload attempt {attempt + 1} failed: {last_error}")

        if not video_url:
            logger.error(f"All upload attempts failed. Last error: {last_error}")
            return None

        # Update quota
        with self._lock:
            quota = self._load_quota()
            quota["uploads"] = quota.get("uploads", 0) + 1
            self._save_quota(quota)

        # Upload thumbnail if provided
        if thumbnail_path and thumbnail_path.exists():
            video_id = video_url.split("/")[-1]
            try:
                youtube.set_thumbnail(
                    video_id=video_id,
                    thumbnail_path=str(thumbnail_path)
                )
                logger.info(f"✅ Thumbnail uploaded for {video_id}")
            except Exception as e:
                logger.warning(f"Thumbnail upload failed (non-critical): {e}")

        return video_url
