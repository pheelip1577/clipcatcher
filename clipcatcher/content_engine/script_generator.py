"""
script_generator.py — AI Video Script Generator using Google Gemini API.

Generates structured video scripts for World Cup YouTube Shorts using the
google-generativeai SDK.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

import google.generativeai as genai
from google.generativeai.types import RequestOptions

from content_engine.content_templates import ScriptSegment, VideoScript, ContentTemplate

logger = logging.getLogger(__name__)


class ScriptGeneratorError(RuntimeError):
    """Raised when script generation fails."""


class ScriptGenerator:
    """Uses Google Gemini API to write YouTube Shorts scripts in JSON format."""

    def __init__(self, api_key: str, model_name: str = "gemini-3.5-flash"):
        """
        Parameters
        ----------
        api_key : str
            Google Gemini API key.
        model_name : str
            Model to use (defaults to 'gemini-3.5-flash').
        """
        self.api_key = api_key
        self.model_name = model_name
        if api_key:
            genai.configure(api_key=api_key)
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
        if not self.api_key:
            logger.info("Running in Mock Mode because API key is missing.")
            return self._generate_mock(template, topic_data, topic=topic)

        # 1. Format the user prompt
        try:
            # Safe formatting that handles missing keys or extra keys gracefully
            user_prompt = self._safe_format(template.user_prompt_template, topic_data)
        except Exception as e:
            logger.error(f"Failed to format user prompt: {e}")
            raise ScriptGeneratorError(f"Prompt formatting failed: {e}") from e

        # 2. Build model and send request
        retries = 2
        last_error = None

        for attempt in range(retries + 1):
            try:
                model = genai.GenerativeModel(
                    model_name=self.model_name,
                    system_instruction=template.system_prompt
                )

                logger.info(f"Sending prompt to Gemini (Attempt {attempt+1}/{retries+1}) using {self.model_name}...")
                
                # Request JSON output
                generation_config = {
                    "response_mime_type": "application/json",
                    "temperature": 0.7,
                }

                # Set timeout/retry options
                response = model.generate_content(
                    user_prompt,
                    generation_config=generation_config,
                    request_options=RequestOptions(timeout=30)
                )

                if not response.text:
                    raise ScriptGeneratorError("Gemini returned an empty response.")

                # 3. Parse and validate
                actual_topic = topic if topic else topic_data.get("topic", "World Cup")
                script = self._parse_response(response.text, template, actual_topic)
                logger.info(f"Successfully generated script with {len(script.segments)} segments.")
                return script

            except Exception as e:
                logger.warning(f"Attempt {attempt+1} failed: {e}")
                last_error = e
                # Fallback model check on first failure
                if attempt == 0 and "gemini-3.5-flash" in self.model_name:
                    logger.info("Attempting fallback to 'gemini-2.5-flash'...")
                    self.model_name = "gemini-2.5-flash"
                elif attempt == 1 and "gemini-2.5-flash" in self.model_name:
                    logger.info("Attempting fallback to 'gemini-flash-latest'...")
                    self.model_name = "gemini-flash-latest"
                elif attempt < retries:
                    import time
                    time.sleep(2 ** attempt)

        raise ScriptGeneratorError(f"Gemini script generation failed after retries. Last error: {last_error}")

    def _safe_format(self, template_str: str, data: Dict[str, Any]) -> str:
        """Helper to format string ignoring missing keys."""
        # Use regex to find all {placeholder} elements
        placeholders = re.findall(r"\{([a-zA-Z0-9_]+)\}", template_str)
        formatted_data = {}
        for p in placeholders:
            formatted_data[p] = data.get(p, f"[{p}]")
        return template_str.format(**formatted_data)

    def _parse_response(self, response_text: str, template: ContentTemplate, topic: str) -> VideoScript:
        """Parses the JSON response from Gemini into a VideoScript object."""
        try:
            # Clean response text if it has markdown block tags
            cleaned = response_text.strip()
            if cleaned.startswith("```"):
                # strip code block formatting
                cleaned = re.sub(r"^```(?:json)?\n", "", cleaned)
                cleaned = re.sub(r"\n```$", "", cleaned)
                cleaned = cleaned.strip()

            data = json.loads(cleaned)

            # Map raw list of segments into ScriptSegment objects
            raw_segments = data.get("segments", [])
            segments = []
            
            for seg in raw_segments:
                # Calculate default duration hint based on narration word count if not present
                narration = seg.get("narration", "")
                words = len(narration.split())
                # Average speaking rate is ~130-150 words per minute (2-2.5 words per second)
                default_duration = max(3.0, round(words / 2.3, 1))
                
                segments.append(
                    ScriptSegment(
                        narration=narration,
                        visual_cue=seg.get("visual_cue", "stock footage"),
                        duration_hint=float(seg.get("duration_hint", default_duration))
                    )
                )

            # Set default title if empty
            title = data.get("title", "").strip()
            if not title:
                title = template.title_template.format(topic=topic)
            # Clip title to 100 characters (YouTube limit)
            title = title[:100]

            # Merge generated tags with template defaults
            tags = data.get("tags", [])
            if not isinstance(tags, list):
                tags = [tags] if tags else []
            all_tags = list(set(tags + template.default_tags))
            # YouTube tags limit is 500 chars total, so keep list reasonably small
            all_tags = [t.strip() for t in all_tags if t][:20]

            # Assemble description with hashtags
            desc = data.get("description", "").strip()
            if not desc:
                desc = f"World Cup 2026 update on {topic}. AI generated sports short."
            
            # Append hashtags
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
        actual_topic = topic if topic else topic_data.get("topic", "World Cup")
        logger.info(f"Generating mock script for template: {template.name}, topic: {actual_topic}")
 
        mock_segments = [
            ScriptSegment(
                narration=f"Welcome to the ultimate update on {actual_topic}! Today we are breaking down the biggest news.",
                visual_cue="cinematic soccer kick, stadium wide angle",
                duration_hint=4.5
            ),
            ScriptSegment(
                narration="Did you know that the 2026 World Cup is hosting 48 teams? That is the biggest tournament in history!",
                visual_cue="animation of world map highlighting USA, Canada and Mexico",
                duration_hint=5.0
            ),
            ScriptSegment(
                narration="Subscribe for daily World Cup updates, predictions, and insane match highlights!",
                visual_cue="channel branding watermark, smash subscribe button animation",
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
