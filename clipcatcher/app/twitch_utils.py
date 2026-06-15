"""
Twitch helpers - no API key needed for basic stream validation.
We use the public Twitch page to check if a channel is live.
"""
import re
import urllib.request
import urllib.error
from typing import Optional


def parse_channel(raw: str) -> Optional[str]:
    """Extract channel name from URL or raw string."""
    raw = raw.strip().rstrip("/")
    # URL forms
    m = re.search(r"twitch\.tv/([a-zA-Z0-9_]+)", raw, re.IGNORECASE)
    if m:
        return m.group(1).lower()
    # Bare name
    if re.match(r"^[a-zA-Z0-9_]{3,25}$", raw):
        return raw.lower()
    return None


def check_channel_live(channel: str) -> tuple[bool, str]:
    """
    Check if a Twitch channel exists and is currently live.
    Returns (is_live, status_message).
    Does a lightweight HTTP check - no API key required.
    """
    url = f"https://www.twitch.tv/{channel}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            html = resp.read(32768).decode("utf-8", errors="replace")
            # Twitch embeds isLiveBroadcast in page JSON-LD when live
            if '"isLiveBroadcast":true' in html or "isLiveBroadcast" in html:
                return True, "Live"
            # Channel exists but may not be live - still allow connection
            # (streamlink will error if truly offline)
            return False, "Channel found but may not be live"
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False, f"Channel '{channel}' not found on Twitch"
        return False, f"HTTP {e.code} checking channel"
    except urllib.error.URLError:
        # Network error - don't block the user, let streamlink handle it
        return False, "Could not verify (network error) — trying anyway"
    except Exception as e:
        return False, f"Could not verify: {e}"
