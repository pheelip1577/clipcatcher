"""
ContentEngine — Main pipeline orchestrator.
Coordinates the full AI content generation pipeline:
Script → Voice → Visuals → Video → Thumbnail → Upload
"""
import logging
import shutil
import sys
import time
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable

from app.settings import Settings

logger = logging.getLogger(__name__)


class ContentEngine:
    """
    Main pipeline controller for automated World Cup content generation.

    Usage:
        engine = ContentEngine(settings)
        engine.run_once()               # Generate + upload one video
        engine.run_batch(count=6)       # Generate N videos
        engine.run_scheduled()          # Start the scheduler loop
    """

    def __init__(self, settings: Settings = None):
        self.settings = settings or Settings()
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Set up logging
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [ContentEngine] %(levelname)s: %(message)s",
            datefmt="%H:%M:%S"
        )

        # Validate API keys
        self.gemini_key = self.settings.get("ce_gemini_api_key", "")
        self.pexels_key = self.settings.get("ce_pexels_api_key", "")

        if not self.gemini_key:
            logger.warning("⚠️  No Gemini API key set. Script generation will fail.")
        if not self.pexels_key:
            logger.warning("⚠️  No Pexels API key set. Stock visuals will fail.")

        # Output folder
        self.output_dir = Path(self.settings.get("ce_output_folder",
                               str(Path.home() / "Videos" / "ContentEngine")))
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Callbacks for GUI integration
        self.on_status: Optional[Callable[[str], None]] = None
        self.on_progress: Optional[Callable[[str, int], None]] = None
        self.on_video_complete: Optional[Callable[[dict], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None

    def _status(self, msg: str):
        """Log and broadcast a status update."""
        logger.info(msg)
        if self.on_status:
            try:
                self.on_status(msg)
            except Exception:
                pass

    def _progress(self, step: str, pct: int):
        """Report progress for a specific step."""
        if self.on_progress:
            try:
                self.on_progress(step, pct)
            except Exception:
                pass

    def _init_modules(self):
        """Lazy-initialize all pipeline modules."""
        from content_engine.script_generator import ScriptGenerator
        from content_engine.voice_generator import VoiceGenerator
        from content_engine.visual_assembler import VisualAssembler
        from content_engine.video_compiler import VideoCompiler
        from content_engine.thumbnail_generator import ThumbnailGenerator
        from content_engine.uploader import ContentUploader
        from content_engine.scheduler import ContentScheduler
        from content_engine.content_templates import TEMPLATES

        self.script_gen = ScriptGenerator(api_key=self.gemini_key)
        self.voice_gen = VoiceGenerator(
            voice=self.settings.get("ce_tts_voice", "en-US-GuyNeural"),
            rate=self.settings.get("ce_tts_rate", "+5%")
        )
        self.visual_asm = VisualAssembler(
            pexels_api_key=self.pexels_key,
            brand_config={
                "channel_name": self.settings.get("ce_channel_name", "World Cup Central"),
                "primary_color": (20, 20, 40),
                "secondary_color": (255, 215, 0),
                "accent_color": (0, 180, 255),
            }
        )

        compiler_type = self.settings.get("ce_compiler_type", "ffmpeg")
        if compiler_type == "hyperframes":
            from content_engine.hyperframes_compiler import HyperframesCompiler
            self.video_comp = HyperframesCompiler(
                brand_config={
                    "channel_name": self.settings.get("ce_channel_name", "World Cup Central")
                }
            )
        else:
            self.video_comp = VideoCompiler()

        self.thumb_gen = ThumbnailGenerator(
            brand_config={
                "channel_name": self.settings.get("ce_channel_name", "World Cup Central"),
                "primary_color": (20, 20, 40),
                "secondary_color": (255, 215, 0),
                "accent_color": (255, 50, 50),
            }
        )
        self.uploader = ContentUploader(self.settings)
        self.scheduler = ContentScheduler(self.settings)
        self.templates = TEMPLATES

    def run_once(self, template_name: str = None,
                 topic_override: str = None,
                 skip_upload: bool = False,
                 ignore_quota: bool = False) -> Optional[dict]:
        """
        Full pipeline for one video: generate + (optionally) upload.

        Args:
            template_name: Force a specific content type (or None for auto-pick)
            topic_override: Force a specific topic
            skip_upload: If True, generate video but don't upload
            ignore_quota: If True, bypass the daily quota limits (for manual runs)

        Returns dict with video info on success, None on failure.
        """
        self._init_modules()

        from content_engine.content_templates import TEMPLATES
        import content_engine.world_cup_data as wc_data

        # ── Step 1: Pick content ──────────────────────────────────────
        self._status("📋 Step 1/6: Selecting content...")
        self._progress("selecting", 0)

        if template_name and topic_override:
            template = TEMPLATES.get(template_name)
            if not template:
                self._status(f"❌ Unknown template: {template_name}")
                return None
            topic_data = {"topic": topic_override}
            if template_name == "youtube_inspiration":
                topic_data["idea"] = topic_override
            content = {
                "template_name": template_name,
                "topic": topic_override,
                "topic_data": topic_data,
            }
        else:
            wc_dict = {
                "teams": wc_data.TEAMS,
                "players": wc_data.PLAYERS,
                "schedule": wc_data.SCHEDULE,
            }
            content = self.scheduler.get_next_content(
                templates=TEMPLATES,
                world_cup_data=wc_dict,
                template_name=template_name,
                ignore_quota=ignore_quota
            )
            if not content:
                self._status("ℹ️  No content to produce (quota reached or no new topics).")
                return None

        tname = content["template_name"]
        topic = content["topic"]
        topic_data = content["topic_data"]
        template = TEMPLATES[tname]

        self._status(f"📝 Selected: [{template.display_name}] {topic}")
        self._progress("selecting", 100)

        # Create a working directory for this video
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_topic = "".join(c if c.isalnum() or c in " -_" else "" for c in topic)[:40].strip()
        work_dir = self.output_dir / f"{timestamp}_{tname}_{safe_topic}"
        work_dir.mkdir(parents=True, exist_ok=True)

        try:
            # ── Step 2: Generate script ───────────────────────────────
            self._status("📝 Step 2/6: Writing script with AI...")
            self._progress("script", 10)

            script = self.script_gen.generate(template, topic_data, topic=topic)
            if not script or not script.segments:
                raise RuntimeError("Script generation returned empty result")

            self._status(f"✅ Script: {len(script.segments)} segments, title: {script.title}")
            self._progress("script", 100)

            # Save script for reference
            script_path = work_dir / "script.txt"
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(f"Title: {script.title}\n")
                f.write(f"Description: {script.description}\n")
                f.write(f"Tags: {', '.join(script.tags)}\n")
                f.write(f"Thumbnail: {script.thumbnail_text}\n\n")
                for i, seg in enumerate(script.segments):
                    f.write(f"--- Segment {i+1} ---\n")
                    f.write(f"Narration: {seg.narration}\n")
                    f.write(f"Visual: {seg.visual_cue}\n")
                    f.write(f"Duration hint: {seg.duration_hint}s\n\n")

            # ── Step 3: Generate voiceover ────────────────────────────
            self._status("🎙️ Step 3/6: Generating voiceover...")
            self._progress("voice", 20)

            voice_result = self.voice_gen.generate_sync(script.segments, work_dir)
            if not voice_result or not voice_result.audio_path.exists():
                raise RuntimeError("Voice generation failed")

            duration_s = voice_result.total_duration_ms / 1000
            self._status(f"✅ Voice: {duration_s:.1f}s audio, {len(voice_result.subtitles)} words")
            self._progress("voice", 100)

            # ── Step 4: Assemble visuals ──────────────────────────────
            self._status("🖼️ Step 4/6: Creating visuals...")
            self._progress("visuals", 30)

            visual_segments = self.visual_asm.assemble_visuals(
                script, voice_result.segment_timings
            )
            if not visual_segments:
                raise RuntimeError("Visual assembly returned no segments")

            self._status(f"✅ Visuals: {len(visual_segments)} segments prepared")
            self._progress("visuals", 100)

            # ── Step 5: Compile video ─────────────────────────────────
            self._status("🎬 Step 5/6: Compiling video...")
            self._progress("compile", 40)

            output_video = work_dir / f"{safe_topic}.mp4"
            subtitle_style = self.settings.get("ce_subtitle_style", "word_highlight")

            self.video_comp.compile(
                audio_path=voice_result.audio_path,
                visual_segments=visual_segments,
                subtitles=voice_result.subtitles,
                output_path=output_video,
                subtitle_style=subtitle_style
            )

            if not output_video.exists():
                raise RuntimeError("Video compilation produced no output")

            file_size_mb = output_video.stat().st_size / (1024 * 1024)
            self._status(f"✅ Video: {output_video.name} ({file_size_mb:.1f} MB)")
            self._progress("compile", 100)

            # ── Step 5b: Generate thumbnail ───────────────────────────
            self._status("🖼️ Generating thumbnail...")
            thumbnail_path = work_dir / "thumbnail.png"
            bg_image = None
            player_image = None
            for vs in visual_segments:
                if vs.get("type") == "image":
                    bg_image = vs.get("original_bg_path")
                    player_image = vs.get("player_image_path")
                    # Fallback to visual path if no original background is found
                    if not bg_image:
                        bg_image = vs["path"]
                    break

            self.thumb_gen.generate(
                text=script.thumbnail_text,
                output_path=thumbnail_path,
                background_image=bg_image,
                player_image=player_image,
            )

            # ── Step 6: Upload to YouTube ─────────────────────────────
            video_url = None
            if not skip_upload and self.settings.get("ce_auto_upload", True):
                self._status("📤 Step 6/6: Uploading to YouTube...")
                self._progress("upload", 50)

                def upload_progress(pct):
                    self._progress("upload", pct)

                video_url = self.uploader.upload(
                    video_path=output_video,
                    title=script.title,
                    description=script.description,
                    tags=script.tags,
                    thumbnail_path=thumbnail_path if thumbnail_path.exists() else None,
                    progress_callback=upload_progress,
                )

                if video_url:
                    self._status(f"✅ Uploaded: {video_url}")
                    self._progress("upload", 100)
                else:
                    self._status("⚠️  Upload failed. Video saved locally.")
            else:
                self._status("⏭️  Upload skipped. Video saved locally.")

            # Log the production
            self.scheduler.log_production(
                content_type=tname,
                topic=topic,
                video_path=str(output_video),
                video_url=video_url or "",
                status="completed"
            )

            result = {
                "content_type": tname,
                "topic": topic,
                "title": script.title,
                "description": script.description,
                "tags": script.tags,
                "video_path": str(output_video),
                "thumbnail_path": str(thumbnail_path),
                "video_url": video_url,
                "duration_s": duration_s,
                "file_size_mb": file_size_mb,
            }

            self._status(f"🎉 Done! [{template.display_name}] {topic}")
            if self.on_video_complete:
                self.on_video_complete(result)

            return result

        except Exception as e:
            error_msg = f"❌ Pipeline failed for [{tname}] {topic}: {e}"
            self._status(error_msg)
            logger.exception(error_msg)

            self.scheduler.log_production(
                content_type=tname,
                topic=topic,
                status="failed"
            )

            if self.on_error:
                self.on_error(error_msg)

            return None

    def run_batch(self, count: int = 6, skip_upload: bool = False) -> list:
        """
        Generate multiple videos in one session.
        Stops early if quota is exhausted or no more topics.
        """
        self._status(f"🚀 Starting batch production: {count} videos...")
        results = []

        for i in range(count):
            self._status(f"\n{'='*50}")
            self._status(f"📦 Video {i+1}/{count}")
            self._status(f"{'='*50}")

            result = self.run_once(skip_upload=skip_upload)
            if result:
                results.append(result)
            else:
                self._status(f"Stopping batch at video {i+1} (no more content or quota).")
                break

            # Brief pause between videos
            if i < count - 1:
                self._status("⏳ Waiting 10 seconds before next video...")
                time.sleep(10)

        self._status(f"\n🏁 Batch complete: {len(results)}/{count} videos produced.")
        return results

    def run_scheduled(self):
        """
        Start the scheduled production loop.
        Produces videos at the configured interval until stopped.
        Runs in the current thread (blocking).
        """
        self._running = True
        interval_hours = self.settings.get("ce_schedule_interval_hours", 4)
        interval_seconds = interval_hours * 3600

        self._status(f"⏰ Scheduler started. Interval: {interval_hours}h")
        self._status("Press Ctrl+C to stop.\n")

        while self._running:
            try:
                result = self.run_once()
                if result:
                    self._status(f"✅ Produced: {result['title']}")
                else:
                    self._status("ℹ️  Nothing produced this cycle.")
            except KeyboardInterrupt:
                self._status("🛑 Scheduler stopped by user.")
                break
            except Exception as e:
                self._status(f"❌ Scheduler error: {e}")
                logger.exception("Scheduler cycle error")

            if self._running:
                next_time = datetime.now().timestamp() + interval_seconds
                next_str = datetime.fromtimestamp(next_time).strftime("%H:%M:%S")
                self._status(f"💤 Next production at {next_str} ({interval_hours}h)")

                # Sleep in small chunks so we can respond to stop()
                for _ in range(int(interval_seconds)):
                    if not self._running:
                        break
                    time.sleep(1)

        self._status("Scheduler stopped.")

    def run_scheduled_bg(self):
        """Start the scheduler in a background thread."""
        self._thread = threading.Thread(target=self.run_scheduled, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the scheduler gracefully."""
        self._running = False
        self._status("🛑 Stopping scheduler...")

    def get_stats(self) -> dict:
        """Get production statistics from the scheduler."""
        self._init_modules()
        return self.scheduler.get_stats()


def main():
    """CLI entry point for headless ContentEngine operation."""
    import argparse

    parser = argparse.ArgumentParser(description="ContentEngine — AI World Cup Content Factory")
    parser.add_argument("--batch", type=int, default=0,
                        help="Generate N videos in batch mode")
    parser.add_argument("--schedule", action="store_true",
                        help="Run in scheduled mode (continuous)")
    parser.add_argument("--test", action="store_true",
                        help="Generate one video without uploading (test mode)")
    parser.add_argument("--template", type=str, default=None,
                        help="Force a specific template (e.g., player_profile)")
    args = parser.parse_args()

    settings = Settings()
    engine = ContentEngine(settings)

    if args.test:
        print("🧪 Test mode: generating one video without upload...")
        result = engine.run_once(template_name=args.template, skip_upload=True, ignore_quota=True)
        if result:
            print(f"\n✅ Test video saved to: {result['video_path']}")
        else:
            print("\n❌ Test failed. Check logs above.")
    elif args.batch > 0:
        engine.run_batch(count=args.batch)
    elif args.schedule:
        engine.run_scheduled()
    else:
        # Default: generate one video and upload
        engine.run_once(template_name=args.template)


if __name__ == "__main__":
    main()
