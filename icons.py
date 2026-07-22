"""Icon and asset generation for the PLY music player.

Generates transparent PNG icons and background images programmatically using PIL.
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from config import ASSETS_DIR, logger

def generate_default_assets() -> None:
    """Generates all default PNG assets if they do not exist."""
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Play Button
    create_icon("play", draw_play_icon)

    # 2. Pause Button
    create_icon("pause", draw_pause_icon)

    # 3. Stop Button
    create_icon("stop", draw_stop_icon)

    # 4. Next Button
    create_icon("next", draw_next_icon)

    # 5. Previous Button
    create_icon("previous", draw_previous_icon)

    # 6. Logo
    logo_path = ASSETS_DIR / "logo.png"
    if not logo_path.exists():
        create_logo(logo_path)

    # 7. Background
    bg_path = ASSETS_DIR / "background.png"
    if not bg_path.exists():
        create_background(bg_path)

    # 8. Application Music Icon
    music_path = ASSETS_DIR / "music.png"
    if not music_path.exists():
        create_music_icon(music_path)

def create_icon(name: str, draw_func) -> None:
    """Helper to create an icon PNG if it doesn't exist."""
    icon_path = ASSETS_DIR / f"{name}.png"
    if icon_path.exists():
        return

    # Create transparent image (64x64 pixels)
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Draw icon using specific drawing function
    # Use a nice purple/indigo color #6c5ce7 (RGB 108, 92, 231)
    color = (108, 92, 231, 255)
    draw_func(draw, color)
    
    try:
        img.save(icon_path, "PNG")
        logger.info("Generated asset: %s", icon_path)
    except Exception as e:
        logger.error("Failed to save icon %s: %s", name, e)

def draw_play_icon(draw: ImageDraw.Draw, color) -> None:
    # Triangle pointing right
    draw.polygon([(18, 14), (50, 32), (18, 50)], fill=color)

def draw_pause_icon(draw: ImageDraw.Draw, color) -> None:
    # Two vertical bars
    draw.rectangle([20, 14, 28, 50], fill=color)
    draw.rectangle([36, 14, 44, 50], fill=color)

def draw_stop_icon(draw: ImageDraw.Draw, color) -> None:
    # Rounded square
    draw.rounded_rectangle([16, 16, 48, 48], radius=6, fill=color)

def draw_next_icon(draw: ImageDraw.Draw, color) -> None:
    # Two triangles pointing right + bar
    draw.polygon([(16, 16), (36, 32), (16, 48)], fill=color)
    draw.polygon([(34, 16), (54, 32), (34, 48)], fill=color)
    # Stop line
    draw.rectangle([50, 16, 54, 48], fill=color)

def draw_previous_icon(draw: ImageDraw.Draw, color) -> None:
    # Two triangles pointing left + bar
    draw.polygon([(48, 16), (28, 32), (48, 48)], fill=color)
    draw.polygon([(30, 16), (10, 32), (30, 48)], fill=color)
    # Stop line
    draw.rectangle([10, 16, 14, 48], fill=color)

def create_logo(path: Path) -> None:
    """Generates a beautiful logo image."""
    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Draw a stylish glowing circle/disk
    # Outer glowing ring
    draw.ellipse([20, 20, 236, 236], outline=(108, 92, 231, 100), width=6)
    draw.ellipse([30, 30, 226, 226], outline=(108, 92, 231, 255), width=4)
    
    # Draw letter P, L, Y in the center
    # Attempt to load default font
    try:
        # Simple fallback text drawing if custom fonts are missing
        font = ImageFont.load_default()
        # Draw a custom play symbol instead of text if font is too small
        # But we can try loading a system truetype font, e.g. DejaVuSans or Arial
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", 64)
        except IOError:
            try:
                font = ImageFont.truetype("arial.ttf", 64)
            except IOError:
                font = ImageFont.load_default()
    except Exception:
        font = None

    # Draw a stylized icon in the center: a glowing play button overlapping a music note
    # Triangle play
    draw.polygon([(90, 80), (180, 128), (90, 176)], fill=(108, 92, 231, 255))
    
    # Overlay "PLY" text
    text = "PLY"
    if font:
        # Draw text at the bottom or center
        draw.text((80, 180), text, fill=(255, 255, 255, 255), font=font)
    else:
        draw.text((110, 190), text, fill=(255, 255, 255, 255))

    img.save(path, "PNG")
    logger.info("Generated logo asset: %s", path)

def create_background(path: Path) -> None:
    """Generates a dark abstract gradient background."""
    width, height = 800, 600
    img = Image.new("RGBA", (width, height), (18, 18, 20, 255)) # Dark theme color
    draw = ImageDraw.Draw(img)
    
    # Create a nice radial gradient in the corner
    for r in range(400, 0, -4):
        # Draw concentric semi-transparent circles in top-right
        alpha = int((1 - (r / 400)) * 60) # fade out
        draw.ellipse([width - r, -r, width + r, r], fill=(108, 92, 231, alpha))

    img.save(path, "PNG")
    logger.info("Generated background asset: %s", path)

def create_music_icon(path: Path) -> None:
    """Generates a beautiful application music note icon."""
    img = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = (108, 92, 231, 255) # Sleek purple accent
    
    # Draw a glowing outer rounded square/background (squircle)
    draw.rounded_rectangle([4, 4, 124, 124], radius=24, fill=(30, 30, 36, 255), outline=color, width=3)
    
    # Draw a double eighth note in the center
    # Left note head
    draw.ellipse([25, 75, 55, 105], fill=color)
    # Right note head
    draw.ellipse([70, 62, 100, 92], fill=color)
    
    # Stems
    draw.rectangle([50, 40, 55, 90], fill=color)
    draw.rectangle([95, 27, 100, 77], fill=color)
    
    # Slanted connecting beam
    draw.polygon([(50, 40), (100, 27), (100, 39), (50, 52)], fill=color)
    
    img.save(path, "PNG")
    logger.info("Generated music icon asset: %s", path)
