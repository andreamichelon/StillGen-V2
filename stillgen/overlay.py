# overlay.py - Text and logo overlay generation
import os
from PIL import Image, ImageDraw, ImageFont
from typing import Dict, Optional, Tuple, List
import logging
from functools import lru_cache
from pathlib import Path

from .parsers import get_value_fuzzy

logger = logging.getLogger(__name__)


class FontCache:
    """Cache for loaded fonts."""
    
    def __init__(self):
        self._cache = {}
        self._default_font_paths = [
            "/System/Library/Fonts/Helvetica.ttc",  # macOS
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",  # Linux
            "C:\\Windows\\Fonts\\arial.ttf"  # Windows
        ]
    
    @lru_cache(maxsize=8)
    def get_font(self, font_path: str, size: int) -> ImageFont.FreeTypeFont:
        """Get a font with caching."""
        cache_key = f"{font_path}:{size}"
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        try:
            font = ImageFont.truetype(font_path, size)
            self._cache[cache_key] = font
            return font
        except OSError:
            logger.warning(f"Failed to load font from {font_path}, trying fallbacks")
            
            # Try default system fonts
            for default_path in self._default_font_paths:
                if os.path.exists(default_path):
                    try:
                        font = ImageFont.truetype(default_path, size)
                        self._cache[cache_key] = font
                        logger.info(f"Using fallback font: {default_path}")
                        return font
                    except OSError:
                        continue
            
            # Final fallback to default font
            font = ImageFont.load_default()
            self._cache[cache_key] = font
            return font


class ImageCache:
    """Cache for loaded images (logos)."""
    
    def __init__(self):
        self._cache = {}
    
    @lru_cache(maxsize=4)
    def load_image(self, path: str) -> Optional[Image.Image]:
        """Load an image with caching."""
        if path in self._cache:
            return self._cache[path]
        
        try:
            image = Image.open(path).convert("RGBA")
            self._cache[path] = image
            return image
        except Exception as e:
            logger.error(f"Failed to load image {path}: {e}")
            return None


class OverlayGenerator:
    """Generate text and logo overlays for images."""
    
    def __init__(self, config):
        self.config = config
        self.font_cache = FontCache()
        self.image_cache = ImageCache()
    
    def add_overlays(self, image: Image.Image, ale_entry: Dict, 
                    silverstack_entry: Optional[Dict], csv_entry: Optional[Dict]):
        """Add all overlays to the image."""
        # Add logos
        if not self.config.profile.settings.get('skip_overlays', False):
            self._add_logos(image)
        
        # Add text overlays
        self._add_text_overlays(image, ale_entry, silverstack_entry, csv_entry)
    
    def _add_logos(self, image: Image.Image):
        """Add logo images to the container."""
        logo = self.image_cache.load_image(self.config.logo_image)
        tool = self.image_cache.load_image(self.config.tool_image)
        
        if not logo or not tool:
            logger.warning("Logo images not found, skipping logo overlay")
            return
        
        # Calculate scaling to fit within max height
        max_height = self.config.logo_max_height
        spacing = self.config.logo_spacing
        available_height = max_height - spacing
        
        # Calculate scaling factors
        logo_scale = min(1.0, available_height / (logo.height + tool.height))
        tool_scale = logo_scale
        
        # Calculate new dimensions
        new_logo_size = (int(logo.width * logo_scale), int(logo.height * logo_scale))
        new_tool_size = (int(tool.width * tool_scale), int(tool.height * tool_scale))
        
        # Resize images
        logo = logo.resize(new_logo_size, Image.Resampling.LANCZOS)
        tool = tool.resize(new_tool_size, Image.Resampling.LANCZOS)
        
        # Calculate positions (bottom left)
        padding = self.config.logo_padding
        tool_y = image.height - tool.height - padding
        logo_y = tool_y - logo.height - spacing
        
        # Paste logos
        image.paste(logo, (padding, logo_y), logo)
        image.paste(tool, (padding, tool_y), tool)
    
    def _add_text_overlays(self, image: Image.Image, ale_entry: Dict,
                          silverstack_entry: Optional[Dict], csv_entry: Optional[Dict]):
        """Add text overlays to the image."""
        draw = ImageDraw.Draw(image)
        
        # Add top text columns
        self._add_top_text(draw, ale_entry, silverstack_entry, csv_entry)
        
        # Add bottom center text (clip name)
        self._add_bottom_center_text(draw, ale_entry)
        
        # Add bottom right text
        self._add_bottom_right_text(draw, ale_entry, silverstack_entry, csv_entry)
        
        # Add bottom left text (director/cinematographer)
        self._add_bottom_left_text(draw, silverstack_entry)
    
    def _add_top_text(self, draw: ImageDraw.Draw, ale_entry: Dict,
                     silverstack_entry: Optional[Dict], csv_entry: Optional[Dict]):
        """Add top text columns."""
        font = self.font_cache.get_font(self.config.font_path, self.config.font_size_medium)
        
        # Prepare column texts
        column_texts = self._prepare_column_texts(ale_entry, silverstack_entry, csv_entry)
        
        # Calculate layout
        margin = self.config.text_margin
        usable_width = self.config.output_width - 2 * margin
        num_columns = len(column_texts)
        
        if num_columns == 0:
            return
        
        segment_width = usable_width / num_columns
        
        # Draw each column
        for i, text in enumerate(column_texts):
            # Calculate text dimensions
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            
            # Calculate position
            column_start_x = margin + i * segment_width
            centering_offset = (segment_width - text_width) // 2
            draw_x = column_start_x + centering_offset
            
            # Draw text
            draw.multiline_text((int(draw_x), self.config.text_y_top), text, 
                               font=font, fill="white")
    
    def _prepare_column_texts(self, ale_entry: Dict, silverstack_entry: Optional[Dict], 
                            csv_entry: Optional[Dict]) -> List[str]:
        """Prepare text content for top columns."""
        # Column 1: Look Name and ISO
        look_name = get_value_fuzzy(silverstack_entry, 'Look Name') if silverstack_entry else 'N/A'
        iso_value = get_value_fuzzy(ale_entry, 'Iso', 'ISO')
        col1_text = f"Look Name: {look_name}\nISO: {iso_value}"
        
        # Column 2: White Balance
        wb = get_value_fuzzy(ale_entry, 'White balance', 'White Balance')
        wb_tint = get_value_fuzzy(ale_entry, 'White balance tint', 'White Balance Tint')
        col2_text = f"WB: {wb}\nTint: {wb_tint}"
        
        # Column 3: Shutter and FPS
        shutter_angle = get_value_fuzzy(silverstack_entry, 'Shutter Angle') if silverstack_entry else None
        if not shutter_angle or shutter_angle == 'N/A':
            shutter_angle = get_value_fuzzy(ale_entry, 'Shutter', 'Shutter Angle')
        sensor_fps = get_value_fuzzy(ale_entry, 'Sensor fps', 'Sensor FPS')
        col3_text = f"Shutter Angle: {shutter_angle}\nSensor FPS: {sensor_fps}"
        
        # Column 4: Focus and Aperture
        focus_distance = get_value_fuzzy(csv_entry, 'Focus Distance', 'Focus Distance (ft)') if csv_entry else 'N/A'
        aperture = get_value_fuzzy(csv_entry, 'Aperture', 'F-Stop') if csv_entry else 'N/A'
        col4_text = f"Focus Distance: {focus_distance}\nAperture: {aperture}"
        
        # Column 5: Lens
        lens_model = get_value_fuzzy(csv_entry, 'Lens Model', 'Lens') if csv_entry else 'N/A'
        focal_length = get_value_fuzzy(csv_entry, 'Focal Length', 'Focal Length (mm)') if csv_entry else 'N/A'
        col5_text = f"Lens: {lens_model}\nFocal Length: {focal_length}"

        # Column 6: Filters
        nd_filter = get_value_fuzzy(silverstack_entry, 'ND Filter', default='- -') if silverstack_entry else '- -'
        lens_filter = get_value_fuzzy(silverstack_entry, 'Lens Filter', default='N/F') if silverstack_entry else 'N/F'
        col6_text = f"ND Filter: {nd_filter}\nLens Filter: {lens_filter}"
        
        # Column 7: Camera Orientation
        camera_tilt = get_value_fuzzy(csv_entry, 'Camera tilt', 'Camera Tilt', 'Tilt') if csv_entry else 'N/A'
        camera_roll = get_value_fuzzy(csv_entry, 'Camera roll', 'Camera Roll', 'Roll') if csv_entry else 'N/A'
        col7_text = f"Camera Tilt: {camera_tilt}\nCamera Roll: {camera_roll}"
        
        return [col1_text, col2_text, col3_text, col4_text, col5_text, col6_text, col7_text]
    
    def _add_bottom_center_text(self, draw: ImageDraw.Draw, ale_entry: Dict):
        """Add bottom center text (clip name)."""
        font = self.font_cache.get_font(self.config.font_path, self.config.font_size_large)
        
        text = get_value_fuzzy(ale_entry, 'Name', 'Clip Name')
        
        # Calculate position
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        x = (self.config.output_width - text_width) // 2
        y = self.config.output_height - self.config.text_y_bottom
        
        draw.text((x, y), text, font=font, fill="white")
    
    def _add_bottom_right_text(self, draw: ImageDraw.Draw, ale_entry: Dict,
                               silverstack_entry: Optional[Dict], csv_entry: Optional[Dict]):
        """Add bottom right text columns."""
        font = self.font_cache.get_font(self.config.font_path, self.config.font_size_small)
        
        # Column 1: Tape and Timecode
        tape = get_value_fuzzy(ale_entry, 'Tape', 'Reel')
        timecode = get_value_fuzzy(csv_entry, 'Timecode', 'TC') if csv_entry else 'N/A'
        col1_text = f"Tape: {tape}\n\nTimecode: {timecode}"
        
        # Column 2: Shoot Date, Day, and Unit
        shoot_date = get_value_fuzzy(ale_entry, 'Shoot Date', 'Shoot date')
        shoot_day = get_value_fuzzy(ale_entry, 'Shoot day', 'Shoot Day', 'Shooting Day')
        crew_unit = get_value_fuzzy(silverstack_entry, 'Crew Unit', 'Unit') if silverstack_entry else ''
        
        col2_text = f"Shoot Date: {shoot_date}\n\nShoot Day: {shoot_day}"
        if crew_unit and crew_unit != 'N/A':
            col2_text += f"_{crew_unit}"
        
        # Calculate positions
        margin = self.config.logo_padding
        spacing = 100  # Space between columns
        
        # Get text dimensions
        bbox1 = draw.textbbox((0, 0), col1_text, font=font)
        bbox2 = draw.textbbox((0, 0), col2_text, font=font)
        col1_width = bbox1[2] - bbox1[0]
        col2_width = bbox2[2] - bbox2[0]
        
        # Position columns (right-aligned)
        col2_x = self.config.output_width - col2_width - margin
        col1_x = col2_x - col1_width - spacing
        y = self.config.output_height - self.config.text_y_bottom
        
        # Draw text
        draw.multiline_text((col1_x, y), col1_text, font=font, fill="white")
        draw.multiline_text((col2_x, y), col2_text, font=font, fill="white")
    
    def _add_bottom_left_text(self, draw: ImageDraw.Draw, silverstack_entry: Optional[Dict]):
        """Add bottom left text (director and cinematographer)."""
        if not silverstack_entry:
            return
        
        font = self.font_cache.get_font(self.config.font_path, self.config.font_size_medium)
        
        director = get_value_fuzzy(silverstack_entry, 'Director')
        cinematographer = get_value_fuzzy(silverstack_entry, 'Cinematographer', 'DP', 'DOP')
        
        if director == 'N/A' and cinematographer == 'N/A':
            return
        
        text = f"Director: {director}\n \nCinematographer: {cinematographer}"
        
        # Position next to logos
        # Get logo dimensions to position text appropriately
        logo = self.image_cache.load_image(self.config.logo_image)
        if logo:
            # Calculate scaling (same as in _add_logos)
            max_height = self.config.logo_max_height
            spacing = self.config.logo_spacing
            available_height = max_height - spacing
            
            tool = self.image_cache.load_image(self.config.tool_image)
            if tool:
                logo_scale = min(1.0, available_height / (logo.height + tool.height))
                scaled_logo_width = int(logo.width * logo_scale)
                scaled_tool_height = int(tool.height * logo_scale)
                
                # Position text to the right of logos
                x = self.config.logo_padding + scaled_logo_width + 20
                
                # Position above the tool image
                padding = self.config.logo_padding
                tool_y = self.config.output_height - scaled_tool_height - padding
                y = tool_y - 160
                
                draw.multiline_text((x, y), text, font=font, fill="white")


class TextLayoutCalculator:
    """Calculate optimal text layout for overlays."""
    
    @staticmethod
    def calculate_column_layout(texts: List[str], font: ImageFont.FreeTypeFont, 
                               container_width: int, margin: int) -> List[Tuple[int, int]]:
        """Calculate x positions for evenly spaced text columns."""
        num_columns = len(texts)
        if num_columns == 0:
            return []
        
        usable_width = container_width - 2 * margin
        segment_width = usable_width / num_columns
        
        positions = []
        draw = ImageDraw.Draw(Image.new('RGB', (1, 1)))  # Dummy draw for text measurement
        
        for i, text in enumerate(texts):
            # Get text width
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            
            # Calculate centered position within segment
            segment_start = margin + i * segment_width
            centering_offset = (segment_width - text_width) // 2
            x = segment_start + centering_offset
            
            positions.append((int(x), text_width))
        
        return positions
    
    @staticmethod
    def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
        """Wrap text to fit within maximum width."""
        words = text.split()
        lines = []
        current_line = []
        
        draw = ImageDraw.Draw(Image.new('RGB', (1, 1)))  # Dummy draw for text measurement
        
        for word in words:
            test_line = ' '.join(current_line + [word])
            bbox = draw.textbbox((0, 0), test_line, font=font)
            line_width = bbox[2] - bbox[0]
            
            if line_width <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                    current_line = [word]
                else:
                    # Word is too long, add it anyway
                    lines.append(word)
        
        if current_line:
            lines.append(' '.join(current_line))
        
        return lines


def create_test_overlay(config, output_path: str = "test_overlay.png"):
    """Create a test image with overlays for validation."""
    # Create test data
    test_ale = {
        'Name': 'A001_C002_0123AB',
        'Tape': 'A001',
        'ISO': '800',
        'White balance': '5600K',
        'White balance tint': '0',
        'Sensor fps': '23.976',
        'Shutter': '180°',
        'ASC_SOP': '(1.0 1.0 1.0)(0.0 0.0 0.0)(1.0 1.0 1.0)',
        'ASC_SAT': '1.0',
        'Shoot Date': '2024-01-15',
        'Shoot day': 'Day 1'
    }
    
    test_silverstack = {
        'Look Name': 'Day_Exterior',
        'Director': 'John Doe',
        'Cinematographer': 'Jane Smith',
        'Crew Unit': 'Main',
        'Shutter Angle': '180°'
    }
    
    test_csv = {
        'Timecode': '01:23:45:12',
        'Lens Model': 'Zeiss Master Prime',
        'Focal Length': '35mm',
        'Focus Distance': '6.5ft',
        'Aperture': 'T2.8',
        'Camera tilt': '+5.2°',
        'Camera roll': '-0.3°'
    }
    
    # Create test image
    test_image = Image.new('RGBA', (config.output_width, config.output_height), (50, 50, 50, 255))
    
    # Add overlays
    generator = OverlayGenerator(config)
    generator.add_overlays(test_image, test_ale, test_silverstack, test_csv)
    
    # Save test image
    test_image.save(output_path)
    logger.info(f"Test overlay image saved to {output_path}")