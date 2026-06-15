"""
thumbnail_generator.py — YouTube Thumbnail Generator

Generates eye-catching 1280×720 thumbnails for YouTube Shorts / videos
using Pillow.  Designed for the AI World Cup content pipeline.

Features:
    • Gradient or image backgrounds with dark overlay
    • Large bold text with thick black stroke for legibility
    • Accent colour bar / glow
    • Channel-name watermark in the corner

Usage:
    from content_engine.thumbnail_generator import ThumbnailGenerator

    gen = ThumbnailGenerator(brand_config={
        "channel_name": "AI World Cup",
        "font_path": None,       # uses default if None
        "watermark_size": 24,
    })
    gen.generate(
        text="GOAL OF THE CENTURY",
        output_path=Path("thumb.png"),
        accent_color=(255, 50, 50),
    )
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError as exc:
    raise ImportError(
        "Pillow is required for thumbnail generation. "
        "Install it with:  pip install Pillow"
    ) from exc

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────
THUMB_WIDTH = 1280
THUMB_HEIGHT = 720


class ThumbnailGenerator:
    """Generates branded YouTube thumbnails (1280×720)."""

    # Default gradient colours (dark blue → deep purple)
    _DEFAULT_GRADIENT_START = (15, 12, 41)
    _DEFAULT_GRADIENT_END = (48, 16, 78)

    def __init__(self, brand_config: Dict) -> None:
        """
        Parameters
        ----------
        brand_config : dict
            Configuration dictionary.  Recognised keys:

            - ``channel_name`` (str): Name shown as watermark.  *Required.*
            - ``font_path`` (str | None): Path to a .ttf / .otf font for
              the main title text.  Falls back to the Pillow default font.
            - ``watermark_size`` (int): Font size for the watermark (default 24).
            - ``gradient_start`` (tuple[int,int,int]): RGB start colour.
            - ``gradient_end`` (tuple[int,int,int]): RGB end colour.
        """
        self.brand = brand_config
        self._channel_name: str = brand_config.get("channel_name", "")
        self._font_path: Optional[str] = brand_config.get("font_path")
        self._watermark_size: int = int(brand_config.get("watermark_size", 24))
        self._gradient_start: Tuple[int, int, int] = tuple(
            brand_config.get("gradient_start", self._DEFAULT_GRADIENT_START)
        )
        self._gradient_end: Tuple[int, int, int] = tuple(
            brand_config.get("gradient_end", self._DEFAULT_GRADIENT_END)
        )

    # ── Public API ───────────────────────────────────────────────────────

    def generate(
        self,
        text: str,
        output_path: Path | str,
        background_image: Optional[Path | str] = None,
        accent_color: Tuple[int, int, int] = (255, 50, 50),
        player_image: Optional[Path | str] = None,
    ) -> Path:
        """
        Create a 1280×720 thumbnail and save it.

        Parameters
        ----------
        text : str
            Short, punchy title (2–4 words ideal).
        output_path : path
            Destination file (PNG or JPEG).
        background_image : path, optional
            An image to use as the background.
        accent_color : tuple
            RGB tuple used for decorative elements (colour bar, glow).
        player_image : path, optional
            Path to player cutout/portrait image to paste on the right side.

        Returns
        -------
        Path
            Absolute path to the saved thumbnail.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        canvas = Image.new("RGB", (THUMB_WIDTH, THUMB_HEIGHT))
        draw = ImageDraw.Draw(canvas)

        # ── 1. Background ────────────────────────────────────────────────
        if background_image is not None:
            bg_path = Path(background_image)
            if bg_path.is_file():
                canvas = self._apply_image_background(canvas, bg_path)
                draw = ImageDraw.Draw(canvas)
            else:
                logger.warning("Background image not found (%s); using gradient", bg_path)
                self._draw_gradient(draw)
        else:
            self._draw_gradient(draw)

        # ── 2. Accent colour bar (bottom strip) ─────────────────────────
        bar_height = 8
        draw.rectangle(
            [0, THUMB_HEIGHT - bar_height, THUMB_WIDTH, THUMB_HEIGHT],
            fill=accent_color,
        )

        # ── 3. Accent radial glow behind player area (right side) ─────────
        glow_color = accent_color
        glow_size = 600
        try:
            glow = self._create_glow(glow_color, radius=300, intensity=100)
            glow_x = THUMB_WIDTH - 450 - glow.width // 2
            glow_y = THUMB_HEIGHT // 2 - glow.height // 2
            canvas.paste(
                Image.alpha_composite(canvas.convert("RGBA"), self._position_glow(glow, glow_x, glow_y)).convert("RGB")
            )
            draw = ImageDraw.Draw(canvas)
        except Exception as e:
            logger.warning(f"Failed to draw glow in thumbnail: {e}")

        # ── 4. Player Cutout / Portrait composite ───────────────────────
        has_player = False
        if player_image is not None:
            player_path = Path(player_image)
            if player_path.is_file():
                try:
                    p_img = Image.open(player_path).convert("RGBA")
                    is_png = player_path.suffix.lower() == ".png"
                    
                    # Transparency check
                    has_alpha = False
                    if is_png and "alpha" in p_img.getbands():
                        extrema = p_img.getextrema()
                        if len(extrema) >= 4 and extrema[3][0] < 255:
                            has_alpha = True
                    
                    if has_alpha:
                        # Scale to fit right side (approx 95% of height)
                        target_p_h = int(THUMB_HEIGHT * 0.95)
                        target_p_w = int(p_img.width * (target_p_h / p_img.height))
                        p_img = p_img.resize((target_p_w, target_p_h), Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.ANTIALIAS)
                        
                        # Glowing outline mask
                        p_alpha = p_img.split()[3]
                        glow_mask = p_alpha.filter(ImageFilter.MaxFilter(15)) # dilate
                        glow_mask = glow_mask.filter(ImageFilter.GaussianBlur(radius=10))
                        
                        glow_layer = Image.new("RGBA", p_img.size, (*self.brand.get("secondary_color", (255, 215, 0)), 255))
                        glow_back = Image.new("RGBA", (THUMB_WIDTH, THUMB_HEIGHT), (0, 0, 0, 0))
                        
                        px = THUMB_WIDTH - target_p_w + 30
                        py = THUMB_HEIGHT - target_p_h
                        
                        glow_back.paste(glow_layer, (px, py), mask=glow_mask)
                        glow_back = glow_back.filter(ImageFilter.GaussianBlur(radius=6))
                        
                        # Composite
                        canvas_rgba = canvas.convert("RGBA")
                        canvas_rgba = Image.alpha_composite(canvas_rgba, glow_back)
                        canvas_rgba.paste(p_img, (px, py), mask=p_img)
                        canvas = canvas_rgba.convert("RGB")
                        draw = ImageDraw.Draw(canvas)
                        has_player = True
                    else:
                        # JPEG non-transparent image: crop to oval badge
                        badge_size = 350
                        mask = Image.new("L", (badge_size, badge_size), 0)
                        mask_draw = ImageDraw.Draw(mask)
                        mask_draw.ellipse([10, 10, badge_size - 10, badge_size - 10], fill=255)
                        mask = mask.filter(ImageFilter.GaussianBlur(radius=2))
                        
                        p_cropped = self._crop_to_portrait(p_img, badge_size, badge_size)
                        
                        badge = Image.new("RGBA", (badge_size, badge_size), (0, 0, 0, 0))
                        badge.paste(p_cropped, (0, 0), mask=mask)
                        
                        # Gold border
                        bx = THUMB_WIDTH - badge_size - 60
                        by = (THUMB_HEIGHT - badge_size) // 2
                        
                        border_layer = Image.new("RGBA", (THUMB_WIDTH, THUMB_HEIGHT), (0, 0, 0, 0))
                        border_draw = ImageDraw.Draw(border_layer)
                        border_draw.ellipse([bx - 4, by - 4, bx + badge_size + 4, by + badge_size + 4], outline=self.brand.get("secondary_color", (255, 215, 0)), width=6)
                        
                        canvas_rgba = canvas.convert("RGBA")
                        canvas_rgba = Image.alpha_composite(canvas_rgba, border_layer)
                        canvas_rgba.paste(badge, (bx, by), mask=mask)
                        canvas = canvas_rgba.convert("RGB")
                        draw = ImageDraw.Draw(canvas)
                        has_player = True
                except Exception as e:
                    logger.warning(f"Failed to draw player image in thumbnail: {e}")

        # ── 5. Slanted Title text with outline ───────────────────────────
        title_font = self._load_font(size=72)
        wrapped = self._word_wrap(text.upper(), max_chars=16)
        
        line_spacing = 15
        line_height = 80
        total_height = len(wrapped) * line_height + line_spacing * (len(wrapped) - 1)
        
        # Position on the left side
        start_x = 80
        start_y = (THUMB_HEIGHT - total_height) // 2
        
        for idx, line in enumerate(wrapped[:3]): # Limit to 3 lines
            bbox = draw.textbbox((0, 0), line, font=title_font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            
            padding_x = 30
            padding_y = 15
            
            lx = start_x
            ly = start_y + idx * (line_height + line_spacing)
            
            t_color = (255, 255, 255)
            b_outline = self.brand.get("accent_color", (255, 50, 50))
            if idx == len(wrapped) - 1 or idx == 1:
                t_color = self.brand.get("secondary_color", (255, 215, 0))
                b_outline = (0, 180, 255) # Cyan highlight border
                
            pts = [
                (lx - padding_x, ly - padding_y),
                (lx + tw + padding_x, ly - padding_y),
                (lx + tw + padding_x - 12, ly + th + padding_y),
                (lx - padding_x - 12, ly + th + padding_y)
            ]
            
            # Shadow
            shadow_pts = [(pt[0] + 5, pt[1] + 5) for pt in pts]
            draw.polygon(shadow_pts, fill=(0, 0, 0))
            
            # Backdrop box
            draw.polygon(pts, fill=(10, 10, 15))
            draw.polygon(pts, outline=b_outline, width=3)
            
            # Text outline and fill
            cx = lx + tw // 2 - 6
            cy = ly + th // 2
            draw.text((cx + 2, cy + 2), line, font=title_font, fill=(0, 0, 0), anchor="mm")
            draw.text((cx, cy), line, font=title_font, fill=t_color, anchor="mm")

        # ── 6. Channel watermark ─────────────────────────────────────────
        if self._channel_name:
            wm_font = self._load_font(size=self._watermark_size)
            self._draw_watermark(draw, wm_font)

        # ── Save ─────────────────────────────────────────────────────────
        fmt = "JPEG" if output_path.suffix.lower() in (".jpg", ".jpeg") else "PNG"
        canvas.save(str(output_path), format=fmt, quality=95)
        logger.info("Thumbnail saved to %s (%s)", output_path, fmt)
        return output_path.resolve()

    # ── Private helpers ──────────────────────────────────────────────────

    def _load_font(self, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        """Load a TrueType font or fall back to the Pillow default."""
        if self._font_path:
            try:
                return ImageFont.truetype(self._font_path, size)
            except (OSError, IOError):
                logger.warning("Could not load font %s; using default", self._font_path)
        # Try a common system font before falling back to default
        for fallback in ("arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf", "Impact.ttf"):
            try:
                return ImageFont.truetype(fallback, size)
            except (OSError, IOError):
                continue
        return ImageFont.load_default()

    def _draw_gradient(self, draw: ImageDraw.Draw) -> None:
        """Fill the canvas with a vertical linear gradient."""
        r1, g1, b1 = self._gradient_start
        r2, g2, b2 = self._gradient_end

        for y in range(THUMB_HEIGHT):
            ratio = y / THUMB_HEIGHT
            r = int(r1 + (r2 - r1) * ratio)
            g = int(g1 + (g2 - g1) * ratio)
            b = int(b1 + (b2 - b1) * ratio)
            draw.line([(0, y), (THUMB_WIDTH, y)], fill=(r, g, b))

    def _apply_image_background(self, canvas: Image.Image, bg_path: Path) -> Image.Image:
        """Resize image to fill canvas, then apply a dark overlay for readability."""
        bg = Image.open(bg_path).convert("RGB")

        # Resize to cover the entire canvas (crop excess)
        bg_ratio = max(THUMB_WIDTH / bg.width, THUMB_HEIGHT / bg.height)
        new_w = int(bg.width * bg_ratio)
        new_h = int(bg.height * bg_ratio)
        bg = bg.resize((new_w, new_h), Image.LANCZOS)

        # Centre-crop to exact dimensions
        left = (new_w - THUMB_WIDTH) // 2
        top = (new_h - THUMB_HEIGHT) // 2
        bg = bg.crop((left, top, left + THUMB_WIDTH, top + THUMB_HEIGHT))

        # Dark overlay (semi-transparent black)
        overlay = Image.new("RGBA", (THUMB_WIDTH, THUMB_HEIGHT), (0, 0, 0, 140))
        bg = bg.convert("RGBA")
        bg = Image.alpha_composite(bg, overlay)
        return bg.convert("RGB")

    @staticmethod
    def _create_glow(
        color: Tuple[int, int, int],
        radius: int = 250,
        intensity: int = 120,
    ) -> Image.Image:
        """Create a soft radial glow image (RGBA)."""
        size = radius * 2
        glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(glow)
        draw.ellipse([0, 0, size, size], fill=(*color, intensity))
        glow = glow.filter(ImageFilter.GaussianBlur(radius=radius // 2))
        return glow

    @staticmethod
    def _position_glow(glow: Image.Image, x: int, y: int) -> Image.Image:
        """Place the glow image on a full-canvas RGBA layer."""
        layer = Image.new("RGBA", (THUMB_WIDTH, THUMB_HEIGHT), (0, 0, 0, 0))
        layer.paste(glow, (x, y), mask=glow)
        return layer

    def _draw_title(
        self,
        draw: ImageDraw.Draw,
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    ) -> None:
        """Draw centred, outlined title text on the canvas."""
        # Word-wrap if necessary (aim for ≤20 chars per line)
        wrapped = self._word_wrap(text, max_chars=20)

        # Calculate total text block height
        line_spacing = 12
        line_bboxes = [draw.textbbox((0, 0), line, font=font) for line in wrapped]
        line_heights = [bb[3] - bb[1] for bb in line_bboxes]
        total_height = sum(line_heights) + line_spacing * (len(wrapped) - 1)

        y_cursor = (THUMB_HEIGHT - total_height) // 2

        for line, bbox in zip(wrapped, line_bboxes):
            line_w = bbox[2] - bbox[0]
            x = (THUMB_WIDTH - line_w) // 2
            # Draw stroke (outline) then fill
            draw.text(
                (x, y_cursor),
                line,
                font=font,
                fill=(255, 255, 255),
                stroke_width=5,
                stroke_fill=(0, 0, 0),
            )
            y_cursor += (bbox[3] - bbox[1]) + line_spacing

    def _draw_watermark(self, draw: ImageDraw.Draw, font: ImageFont.FreeTypeFont | ImageFont.ImageFont) -> None:
        """Draw a small channel-name watermark in the bottom-right corner."""
        text = self._channel_name
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        x = THUMB_WIDTH - text_w - 24
        y = THUMB_HEIGHT - (bbox[3] - bbox[1]) - 24
        draw.text(
            (x, y),
            text,
            font=font,
            fill=(255, 255, 255, 200),
            stroke_width=2,
            stroke_fill=(0, 0, 0),
        )

    @staticmethod
    def _word_wrap(text: str, max_chars: int = 20) -> list[str]:
        """
        Simple word-wrap: split text into lines no longer than *max_chars*.
        Each word is kept whole.
        """
        words = text.split()
        lines: list[str] = []
        current: list[str] = []
        length = 0

        for word in words:
            if current and length + len(word) + 1 > max_chars:
                lines.append(" ".join(current))
                current = [word]
                length = len(word)
            else:
                current.append(word)
                length += len(word) + (1 if len(current) > 1 else 0)

        if current:
            lines.append(" ".join(current))
        return lines or [""]

    def _crop_to_portrait(self, img: Image.Image, target_width: int, target_height: int) -> Image.Image:
        """Resizes and crops a PIL Image to fill target_width x target_height in portrait mode."""
        img_w, img_h = img.size
        target_ratio = target_width / target_height
        img_ratio = img_w / img_h
        
        if img_ratio > target_ratio:
            new_h = target_height
            new_w = int(img_w * (target_height / img_h))
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.ANTIALIAS)
            left = (new_w - target_width) // 2
            img = img.crop((left, 0, left + target_width, target_height))
        else:
            new_w = target_width
            new_h = int(img_h * (target_width / img_w))
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.ANTIALIAS)
            top = (new_h - target_height) // 2
            img = img.crop((0, top, target_width, top + target_height))
        return img
