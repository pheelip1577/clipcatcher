"""
script_generator.py — AI Video Script Generator using Google Gemini API.

Generates structured video scripts for YouTube Shorts using the new google-genai SDK.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

from google import genai
from google.genai import types

from content_engine.content_templates import ScriptSegment, VideoScript, ContentTemplate

logger = logging.getLogger(__name__)


JSON_FORMAT_INSTRUCTIONS = """
You MUST return ONLY valid JSON (no markdown fences, no commentary outside the JSON).
The JSON must conform EXACTLY to this schema:
{
  "segments": [
    {
      "narration": "<string — what the TTS voice says>",
      "visual_cue": "<string — description of the image, clip, or graphic to show>",
      "duration_hint": <float — seconds this segment should last>
    }
  ],
  "title": "<string — video title, max 100 chars, with emoji>",
  "description": "<string — video description, 2-4 sentences + hashtags>",
  "tags": ["<string>", "..."],
  "thumbnail_text": "<string — 2-5 bold words for the thumbnail overlay>",
  "content_type": "<string — the template name>",
  "topic": "<string — the specific topic of this video>"
}
"""


class ScriptGeneratorError(RuntimeError):
    """Raised when script generation fails."""


class ScriptGenerator:
    """Uses Google Gemini API to write YouTube Shorts scripts in JSON format."""

    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash"):
        """
        Parameters
        ----------
        api_key : str
            Google Gemini API key.
        model_name : str
            Model to use (defaults to 'gemini-2.5-flash').
        """
        self.api_key = api_key
        self.model_name = model_name
        self.client = None
        if api_key:
            self.client = genai.Client(api_key=api_key)
        else:
            logger.warning("No Gemini API key provided. Generator will run in mock mode.")

    def generate(self, template: ContentTemplate, topic_data: Dict[str, Any], topic: Optional[str] = None) -> VideoScript:
        """
        Generates a VideoScript for the given template and topic.

        Parameters
        ----------
        template : ContentTemplate
            The template definition with prompts.
        topic_data : dict
            Context data for formatting the user prompt.
        topic : str, optional
            The actual unique topic string.

        Returns
        -------
        VideoScript
        """
        if not self.api_key or not self.client:
            logger.info("Running in Mock Mode because API key is missing.")
            return self._generate_mock(template, topic_data, topic=topic)

        # 1. Format the user prompt
        try:
            user_prompt = self._safe_format(template.user_prompt_template, topic_data)
        except Exception as e:
            logger.error(f"Failed to format user prompt: {e}")
            raise ScriptGeneratorError(f"Prompt formatting failed: {e}") from e

        # 2. Build model and send request (non-mutating fallback model name)
        retries = 2
        last_error = None
        current_model = self.model_name

        # Prepare system instruction
        system_instruction = template.system_prompt
        if "schema" not in system_instruction.lower():
            system_instruction = f"{system_instruction}\n\n{JSON_FORMAT_INSTRUCTIONS}"

        for attempt in range(retries + 1):
            try:
                logger.info(f"Sending prompt to Gemini (Attempt {attempt+1}/{retries+1}) using {current_model}...")
                
                config = types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    temperature=0.7,
                )
                
                response = self.client.models.generate_content(
                    model=current_model,
                    contents=user_prompt,
                    config=config
                )

                if not response.text:
                    raise ScriptGeneratorError("Gemini returned an empty response.")

                # 3. Parse and validate
                actual_topic = topic if topic else topic_data.get("topic", "Topic")
                script = self._parse_response(response.text, template, actual_topic)
                logger.info(f"Successfully generated script with {len(script.segments)} segments.")
                return script

            except Exception as e:
                logger.warning(f"Attempt {attempt+1} failed: {e}")
                last_error = e
                # Fallback model check on first failure
                if attempt == 0 and "gemini-3.5-flash" in current_model:
                    logger.info("Attempting fallback to 'gemini-2.5-flash'...")
                    current_model = "gemini-2.5-flash"
                elif attempt == 0 and "gemini-2.5-flash" in current_model:
                    logger.info("Attempting fallback to 'gemini-2.5-flash'...") # stay or change
                elif attempt == 1:
                    logger.info("Attempting fallback to 'gemini-2.5-flash'...")
                    current_model = "gemini-2.5-flash"
                
                if attempt < retries:
                    import time
                    time.sleep(2 ** attempt)

        raise ScriptGeneratorError(f"Gemini script generation failed after retries. Last error: {last_error}")

    def _safe_format(self, template_str: str, data: Dict[str, Any]) -> str:
        """Helper to format string ignoring missing keys."""
        placeholders = re.findall(r"\{([a-zA-Z0-9_]+)\}", template_str)
        formatted_data = {}
        for p in placeholders:
            formatted_data[p] = data.get(p, f"[{p}]")
        return template_str.format(**formatted_data)

    def _parse_response(self, response_text: str, template: ContentTemplate, topic: str) -> VideoScript:
        """Parses the JSON response from Gemini into a VideoScript object."""
        try:
            cleaned = response_text.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\n", "", cleaned)
                cleaned = re.sub(r"\n```$", "", cleaned)
                cleaned = cleaned.strip()

            data = json.loads(cleaned)

            raw_segments = data.get("segments", [])
            segments = []
            
            for seg in raw_segments:
                narration = seg.get("narration", "")
                words = len(narration.split())
                default_duration = max(3.0, round(words / 2.3, 1))
                
                segments.append(
                    ScriptSegment(
                        narration=narration,
                        visual_cue=seg.get("visual_cue", "stock footage"),
                        duration_hint=float(seg.get("duration_hint", default_duration))
                    )
                )

            title = data.get("title", "").strip()
            if not title:
                title = template.title_template.replace("{topic}", topic)
            title = title[:100]

            tags = data.get("tags", [])
            if not isinstance(tags, list):
                tags = [tags] if tags else []
            all_tags = list(set(tags + template.default_tags))
            all_tags = [t.strip() for t in all_tags if t][:20]

            desc = data.get("description", "").strip()
            if not desc:
                desc = f"Special update on {topic}. AI generated short."
            
            hashtags_str = " ".join(template.hashtags)
            if hashtags_str and hashtags_str not in desc:
                desc = f"{desc}\n\n{hashtags_str}"

            return VideoScript(
                segments=segments,
                title=title,
                description=desc,
                tags=all_tags,
                thumbnail_text=data.get("thumbnail_text", topic[:15].upper()),
                content_type=template.name,
                topic=topic
            )

        except Exception as e:
            logger.error(f"Failed to parse Gemini JSON output: {e}\nRaw output was:\n{response_text}")
            raise ScriptGeneratorError(f"Failed to parse JSON response: {e}") from e

    def _generate_mock(self, template: ContentTemplate, topic_data: Dict[str, Any], topic: Optional[str] = None) -> VideoScript:
        """Returns a high-quality mock script when API key is missing."""
        actual_topic = topic if topic else topic_data.get("topic", "Topic")
        
        from content_engine.niche_loader import get_active_niche_name, load_niche
        try:
            niche = load_niche(get_active_niche_name())
            display_name = niche.display_name
            cta = niche.subscribe_cta
        except Exception:
            display_name = "niche"
            cta = "Subscribe for daily updates!"
            
        logger.info(f"Generating mock script for template: {template.name}, topic: {actual_topic} in niche: {display_name}")
 
        mock_segments = [
            ScriptSegment(
                narration=f"Welcome to the ultimate update on {actual_topic}! Today we are breaking down the biggest secrets.",
                visual_cue="cinematic opening shot, high dynamic range",
                duration_hint=4.5
            ),
            ScriptSegment(
                narration=f"This is a game changer for our {display_name} community. Make sure to pay close attention to this tip.",
                visual_cue="infographic showing statistics and charts",
                duration_hint=5.0
            ),
            ScriptSegment(
                narration=f"{cta}",
                visual_cue="watermark logo, hit subscribe animation",
                duration_hint=4.0
            )
        ]
 
        title = template.title_template.replace("{topic}", actual_topic)[:100]
        desc = f"Auto-generated {template.display_name} about {actual_topic}.\n\n" + " ".join(template.hashtags)
 
        return VideoScript(
            segments=mock_segments,
            title=title,
            description=desc,
            tags=template.default_tags,
            thumbnail_text=actual_topic[:12].upper(),
            content_type=template.name,
            topic=actual_topic
        )
