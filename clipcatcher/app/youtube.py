"""
YouTube API integration - handles OAuth 2.0 flow and video uploads in background.
"""
import os
import time
from pathlib import Path
from typing import Optional, Callable, Tuple
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube"
]

TOKEN_PATH = Path.home() / ".clipcatcher" / "youtube_token.json"
CLIENT_SECRETS_PATH = Path("client_secrets.json")


def get_credentials() -> Optional[Credentials]:
    """Load credentials from local token.json if it exists."""
    creds = None
    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        except Exception:
            pass
    return creds


def is_linked() -> bool:
    """Check if YouTube account is linked."""
    creds = get_credentials()
    return creds is not None and creds.valid or (creds is not None and creds.refresh_token is not None)


def get_channel_name(creds: Optional[Credentials] = None) -> Optional[str]:
    """Retrieve the linked YouTube channel name."""
    if not creds:
        creds = get_credentials()
        if not creds:
            return None
    try:
        # If credentials are expired but refreshable, refresh them
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Save the refreshed credentials
            TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(TOKEN_PATH, "w") as token_file:
                token_file.write(creds.to_json())
        
        youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
        request = youtube.channels().list(
            part="snippet",
            mine=True
        )
        response = request.execute()
        if response.get("items"):
            return response["items"][0]["snippet"]["title"]
        return "Unknown Channel"
    except Exception:
        return None


def authenticate(
    on_success: Optional[Callable[[str], None]] = None,
    on_error: Optional[Callable[[str], None]] = None
) -> Tuple[bool, str]:
    """
    Runs the OAuth 2.0 flow to link the user's YouTube account.
    Should be run in a background thread as it launches a browser and blocks.
    """
    try:
        creds = get_credentials()
        
        # If credentials are valid or refreshable, try to use/refresh them
        if creds:
            if creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
                    with open(TOKEN_PATH, "w") as token_file:
                        token_file.write(creds.to_json())
                except Exception:
                    creds = None
            elif not creds.valid:
                creds = None

        # Start interactive OAuth flow if we still don't have valid credentials
        if not creds:
            if not CLIENT_SECRETS_PATH.exists():
                raise FileNotFoundError(
                    "client_secrets.json not found in the root directory. "
                    "Please download it from Google Cloud Console."
                )
            
            # Use InstalledAppFlow to run a local redirect server
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS_PATH), SCOPES)
            # This opens a web browser for authorization
            creds = flow.run_local_server(port=0, prompt="consent")
            
            # Save credentials for next run
            TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(TOKEN_PATH, "w") as token_file:
                token_file.write(creds.to_json())
        
        channel_name = get_channel_name(creds) or "Linked Channel"
        if on_success:
            on_success(channel_name)
        return True, channel_name

    except Exception as e:
        if on_error:
            on_error(str(e))
        return False, str(e)


def unlink() -> bool:
    """Delete the saved token file to unlink the YouTube account."""
    if TOKEN_PATH.exists():
        try:
            TOKEN_PATH.unlink()
            return True
        except Exception:
            return False
    return True


def upload_video(
    filepath: str,
    title: str,
    description: str,
    tags: str,
    visibility: str,
    progress_callback: Optional[Callable[[int], None]] = None,
    success_callback: Optional[Callable[[str], None]] = None,
    error_callback: Optional[Callable[[str], None]] = None,
    publish_at: Optional[str] = None,
    category_id: str = "20"
) -> Optional[str]:
    """
    Uploads a video file to YouTube.
    Should be run in a background thread to prevent UI freezing.
    """
    try:
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Video file not found: {filepath}")

        creds = get_credentials()
        if not creds:
            raise Exception("No linked YouTube account found. Please link your account first.")
        
        # Ensure credentials are fresh
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
                with open(TOKEN_PATH, "w") as token_file:
                    token_file.write(creds.to_json())
            except Exception as e:
                err_str = str(e)
                if "invalid_scope" in err_str or "scopes" in err_str.lower():
                    raise Exception(
                        "YouTube API scopes have been updated to support custom thumbnails. "
                        "Please go to the Settings tab in ClipCatcher, click 'Unlink YouTube', "
                        "and then 'Link YouTube Channel' to re-authorize the app with new permissions."
                    )
                raise Exception(f"Failed to refresh YouTube session credentials: {e}")

        # Build YouTube service client
        youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
        
        # Split comma-separated tags
        tags_list = [t.strip() for t in tags.split(",") if t.strip()]

        body = {
            "snippet": {
                "title": title[:100],  # YouTube title limit is 100 characters
                "description": description,
                "tags": tags_list,
                "categoryId": category_id
            },
            "status": {
                "privacyStatus": visibility.lower(),  # 'private', 'unlisted', 'public'
                "selfDeclaredMadeForKids": False
            }
        }

        if publish_at:
            body["status"]["privacyStatus"] = "private"
            body["status"]["publishAt"] = publish_at

        # Create resumable upload media body
        media = MediaFileUpload(
            str(path),
            mimetype="video/mp4",
            chunksize=1024 * 1024,  # Upload in 1MB chunks
            resumable=True
        )

        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )

        # Upload the video chunk-by-chunk to report progress
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status and progress_callback:
                progress = int(status.progress() * 100)
                progress_callback(progress)

        video_id = response.get("id")
        video_url = f"https://youtu.be/{video_id}"
        if success_callback:
            success_callback(video_url)
        return video_url

    except HttpError as e:
        err_content = e.content.decode("utf-8", errors="replace")
        err_msg = f"YouTube API Error {e.resp.status}: {err_content}"
        if error_callback:
            error_callback(err_msg)
        return None
    except Exception as e:
        if error_callback:
            error_callback(str(e))
        return None


def set_thumbnail(
    video_id: str,
    thumbnail_path: str,
    error_callback: Optional[Callable[[str], None]] = None
) -> bool:
    """Upload a custom thumbnail for a YouTube video."""
    try:
        creds = get_credentials()
        if not creds:
            raise Exception("No linked YouTube account found.")
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
        media = MediaFileUpload(thumbnail_path, mimetype="image/png")
        youtube.thumbnails().set(videoId=video_id, media_body=media).execute()
        return True
    except Exception as e:
        if error_callback:
            error_callback(str(e))
        return False
