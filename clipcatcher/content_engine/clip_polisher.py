"""
clip_polisher.py — Auto-Shorts Pipeline Polisher
Converts Twitch landscape clips (16:9) into vertical Shorts (9:16)
with Gemini-based audio transcription, word-level ASS subtitles, and viral metadata generation.
"""

import os
import json
import logging
import subprocess
import shutil
import textwrap
from pathlib import Path
from typing import Optional, Dict, Any, List

from google import genai
from google.genai import types
from app.settings import Settings
from app.recorder import find_tool

logger = logging.getLogger(__name__)

FPS = 30
WIDTH = 1080
HEIGHT = 1920

def _seconds_to_ass_ts(seconds: float) -> str:
    """Convert seconds (float) to ASS timestamp H:MM:SS.cc."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"

class ClipPolisher:
    """Polishes landscape Twitch clips into viral vertical Shorts."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings()
        self.ffmpeg = find_tool("ffmpeg") or "ffmpeg"
        
    def _run_ffmpeg(self, cmd: List[str], stage_name: str):
        logger.debug(f"Running ffmpeg [{stage_name}]: {' '.join(cmd)}")
        res = subprocess.run(cmd, capture_output=True, stdin=subprocess.DEVNULL)
        if res.returncode != 0:
            err = res.stderr.decode("utf-8", errors="replace")[-2000:]
            raise RuntimeError(f"ffmpeg stage '{stage_name}' failed: {err}")
        return res

    def extract_audio(self, video_path: Path, audio_path: Path) -> Path:
        """Extracts mono 16kHz audio from video file to optimize Gemini upload."""
        cmd = [
            self.ffmpeg, "-y",
            "-i", str(video_path),
            "-vn",
            "-acodec", "libmp3lame",
            "-ar", "16000",
            "-ac", "1",
            str(audio_path)
        ]
        self._run_ffmpeg(cmd, "extract_audio")
        return audio_path

    def transcribe_audio_with_gemini(self, audio_path: Path, api_key: str) -> List[Dict[str, Any]]:
        """Uploads audio file to Gemini and requests word-level timestamps in JSON."""
        client = genai.Client(api_key=api_key)
        
        logger.info(f"Uploading audio {audio_path.name} to Gemini...")
        file_ref = client.files.upload(file=audio_path)
        
        import time
        # Wait for file processing (should be fast for short audio clips)
        for _ in range(30):
            file_ref = client.files.get(name=file_ref.name)
            if file_ref.state.name == "ACTIVE":
                break
            elif file_ref.state.name == "FAILED":
                raise RuntimeError("Gemini file processing failed")
            time.sleep(1)
            
        if file_ref.state.name != "ACTIVE":
            client.files.delete(name=file_ref.name)
            raise TimeoutError("Gemini file processing timed out")
            
        try:
            prompt = """
            Transcribe the uploaded audio with word-level timestamps.
            You MUST return a JSON object with a single key "words", which is a list of objects, each containing:
            - "word": string, the spoken word
            - "start": float, the start time in seconds
            - "end": float, the end time in seconds
            
            Format:
            {
              "words": [
                {"word": "Hello", "start": 0.12, "end": 0.45},
                ...
              ]
            }
            
            Punctuation and capitalization should be kept natural. Ensure timestamps align closely with the speech.
            """
            
            logger.info("Requesting transcription from Gemini...")
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[file_ref, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            
            res_dict = json.loads(response.text)
            return res_dict.get("words", [])
        finally:
            # Always delete the uploaded file to keep Gemini account clean
            try:
                client.files.delete(name=file_ref.name)
            except Exception as e:
                logger.warning(f"Failed to delete file {file_ref.name} from Gemini: {e}")

    def generate_viral_metadata(self, words: List[Dict[str, Any]], api_key: str) -> Dict[str, Any]:
        """Generates viral title, description, and tags based on transcription."""
        client = genai.Client(api_key=api_key)
        transcription_text = " ".join([w["word"] for w in words])
        
        # Load niche tags and hashtags for SEO relevance if active
        from content_engine.niche_loader import get_active_niche_name, load_niche
        try:
            niche = load_niche(get_active_niche_name())
            niche_context = f"Brand niche: {niche.display_name}. Channel name: {niche.channel_name}. Default hashtags: {', '.join(niche.hashtags)}"
        except Exception:
            niche_context = ""

        prompt = f"""
        Based on the following transcription of a video clip:
        "{transcription_text}"
        
        {niche_context}
        
        Generate viral metadata for YouTube Shorts/TikTok.
        Return a JSON object with:
        - "title": viral title under 100 characters (incorporate emojis/hashtags)
        - "description": engaging description containing relevant viral hashtags
        - "tags": a list of tags (strings)
        
        Format:
        {{
          "title": "Viral Title! 🚀 #Shorts",
          "description": "Engaging description...",
          "tags": ["tag1", "tag2"]
        }}
        """
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        return json.loads(response.text)

    def _generate_ass_subtitles(self, words: List[Dict[str, Any]], output_path: Path) -> Path:
        """Generates word-by-word highlighted ASS subtitles file."""
        max_words_per_line = 5
        
        header = textwrap.dedent("""\
            [Script Info]
            Title: Auto-generated subtitles
            ScriptType: v4.00+
            WrapStyle: 0
            PlayResX: 1080
            PlayResY: 1920
            ScaledBorderAndShadow: yes

            [V4+ Styles]
            Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
            Style: Default,Arial Black,60,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,40,40,960,1

            [Events]
            Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
        """)
        
        lines = [header]
        phrases = []
        for i in range(0, len(words), max_words_per_line):
            phrases.append(words[i : i + max_words_per_line])
            
        for phrase in phrases:
            phrase_start = phrase[0]["start"]
            phrase_end = phrase[-1]["end"]
            all_texts = [w["word"] for w in phrase]
            
            for focus_idx, focus_word in enumerate(phrase):
                w_start = focus_word["start"]
                if focus_idx + 1 < len(phrase):
                    w_end = phrase[focus_idx + 1]["start"]
                else:
                    w_end = phrase_end
                    
                parts = []
                for j, txt in enumerate(all_texts):
                    if j == focus_idx:
                        parts.append(f"{{\\c&H00FFFF&}}{txt}{{\\c&HFFFFFF&}}")
                    else:
                        parts.append(txt)
                tagged_text = " ".join(parts)
                
                ass_start = _seconds_to_ass_ts(w_start)
                ass_end = _seconds_to_ass_ts(w_end)
                lines.append(f"Dialogue: 0,{ass_start},{ass_end},Default,,0,0,0,,{tagged_text}")
                
        output_path.write_text("\n".join(lines), encoding="utf-8")
        return output_path

    def polish_clip(self, clip_path: Path, output_path: Path) -> Dict[str, Any]:
        """
        Executes the auto-polishing flow:
        - Extracts audio from landscape video
        - Transcribes word-level timestamps using Gemini
        - Crops landscape (16:9) video to centered vertical (9:16)
        - Overlays word-highlight ASS subtitles on the vertical video
        - Generates viral titles, descriptions, and tags
        - Returns a dict containing local paths and metadata
        """
        api_key = self.settings.get("ce_gemini_api_key")
        if not api_key:
            raise ValueError("ce_gemini_api_key settings variable is not configured")
            
        tmp_dir = clip_path.parent / f".polish_tmp_{os.getpid()}"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        
        temp_audio = tmp_dir / "temp_audio.mp3"
        temp_ass = tmp_dir / "temp_subs.ass"
        
        try:
            # 1. Extract audio
            logger.info("Polishing: Extracting audio from clip...")
            self.extract_audio(clip_path, temp_audio)
            
            # 2. Gemini transcription
            logger.info("Polishing: Sending audio to Gemini for transcription...")
            words = self.transcribe_audio_with_gemini(temp_audio, api_key)
            
            # 3. ASS subtitles generation
            logger.info("Polishing: Generating ASS subtitles...")
            self._generate_ass_subtitles(words, temp_ass)
            
            # 4. Burn subtitles + crop to 9:16 vertical
            logger.info("Polishing: Running ffmpeg vertical crop and burn-in...")
            ass_filter_path = str(temp_ass.resolve()).replace("\\", "/").replace(":", "\\:")
            
            vf_filter = f"crop=ih*9/16:ih,scale=1080:1920,ass='{ass_filter_path}'"
            
            output_path.parent.mkdir(parents=True, exist_ok=True)
            cmd = [
                self.ffmpeg, "-y",
                "-i", str(clip_path),
                "-vf", vf_filter,
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "23",
                "-c:a", "aac",
                "-b:a", "128k",
                "-r", "30",
                "-movflags", "+faststart",
                str(output_path)
            ]
            self._run_ffmpeg(cmd, "crop_and_burn_subs")
            
            # 5. Gemini Metadata
            logger.info("Polishing: Generating viral metadata using Gemini...")
            meta = self.generate_viral_metadata(words, api_key)
            
            # Write metadata sidecar file next to the video
            meta_path = output_path.with_suffix(".json")
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)
                
            return {
                "video_path": output_path,
                "metadata_path": meta_path,
                "title": meta.get("title", "Polished Clip"),
                "description": meta.get("description", ""),
                "tags": meta.get("tags", []),
                "transcription": " ".join([w["word"] for w in words])
            }
        finally:
            # Cleanup temp folder
            try:
                shutil.rmtree(tmp_dir)
            except Exception as e:
                logger.warning(f"Failed to cleanup temp directory {tmp_dir}: {e}")
