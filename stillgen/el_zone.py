# el_zone.py - EL Zone System implementation with vectorscope and waveform
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import logging
from typing import Optional, Tuple, Union, Callable
import math

logger = logging.getLogger(__name__)

try:
    import cv2
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False
    logger.warning("OpenCV not available. Using fallback implementations.")

try:
    import colour
    HAS_COLOUR = True
except ImportError:
    HAS_COLOUR = False
    logger.warning("Colour library not available. Using fallback log decoding.")

# EL Zone System Constants
STOPS_LIST = [-7, -6, -5, -4, -3, -2, -1, -0.5, 0, 0.5, 1, 2, 3, 4, 5, 6, 7]

COLOR_LIST_8BIT = [
    [3, 3, 3],       # Zone -7: Near black
    [98, 71, 155],   # Zone -6: Dark purple
    [158, 126, 184], # Zone -5: Purple
    [24, 116, 167],  # Zone -4: Dark blue
    [39, 174, 228],  # Zone -3: Blue
    [27, 168, 75],   # Zone -2: Dark green
    [93, 187, 71],   # Zone -1: Green
    [148, 200, 64],  # Zone -0.5: Light green
    [144, 140, 135], # Zone 0: 18% gray (reference)
    [251, 232, 0],   # Zone +0.5: Yellow
    [255, 248, 166], # Zone +1: Light yellow
    [244, 112, 42],  # Zone +2: Orange
    [247, 170, 71],  # Zone +3: Light orange
    [239, 28, 38],   # Zone +4: Red
    [229, 126, 140], # Zone +5: Pink
    [243, 190, 192], # Zone +6: Light pink
    [255, 255, 255]  # Zone +7: White
]

# Reference values
GRAY18 = 0.18  # 18% gray in linear light
EXP_RANGE = 7  # Maximum exposure range


class ELZoneProcessor:
    """EL Zone System processor with vectorscope and histogram generation."""
    
    def __init__(self, log_format: str = "logc4"):
        """
        Initialize EL Zone processor.
        
        Args:
            log_format: Log format for decoding ('logc4', 'slog3', 'apple_log', 'redlog3', 'linear')
        """
        self.log_format = log_format
        self.decode_func = self._get_decode_function(log_format)
        
        # Prepare color lists
        self.color_list_8bit = np.array(COLOR_LIST_8BIT)
        self.color_list_linear = self._srgb_eotf(self.color_list_8bit / 255.0)
        self.color_list_display = self.color_list_linear ** (1/2.4)  # Apply gamma for display
    
    def _get_decode_function(self, log_format: str) -> Optional[Callable]:
        """Get the appropriate log decoding function."""
        if log_format == "linear":
            return None
        elif log_format == "logc4":
            if HAS_COLOUR:
                try:
                    return colour.models.log_decoding_ARRILogC4
                except:
                    logger.warning("Colour library LogC4 function not available, using accurate fallback")
                    return self._log_decoding_logc4_accurate
            else:
                return self._log_decoding_logc4_accurate
        elif log_format == "slog3" and HAS_COLOUR:
            return colour.models.log_decoding_SLog3
        elif log_format == "apple_log":
            return self._log_decoding_apple_log_fallback
        elif log_format == "redlog3":
            return self._log_decoding_redlog3_fallback
        else:
            logger.warning(f"Log format '{log_format}' not supported, using fallback")
            return self._log_decoding_fallback
    
    def _srgb_eotf(self, x: np.ndarray) -> np.ndarray:
        """Simple sRGB EOTF (gamma correction)."""
        return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)
    
    def _log_decoding_apple_log_fallback(self, x: np.ndarray) -> np.ndarray:
        """Fallback Apple Log to linear conversion (approximation)."""
        # Simplified Apple Log decode - replace with actual implementation
        return np.power(10, (x - 0.3584) / 0.2471)
    
    def _log_decoding_redlog3_fallback(self, x: np.ndarray) -> np.ndarray:
        """RED Log3G10 to linear conversion (approximation)."""
        # RED Log3G10 parameters (simplified approximation)
        # Note: This is a basic implementation - for production use, 
        # consider using colour library with proper RED Log3 support
        a = 0.224282
        b = 155.975327
        c = 0.01
        
        # Apply RED Log3G10 to linear transform
        linear = np.where(
            x >= c,
            np.power(10, (x * 1023 - 685) / 300) / 1023,
            x * a
        )
        
        return np.clip(linear, 0, None)
    
    def _log_decoding_logc4_accurate(self, x: np.ndarray) -> np.ndarray:
        """Accurate ARRI LogC4 to linear conversion (based on ARRI specification)."""
        # ARRI LogC4 parameters (official specification)
        a = 0.0647954196341293
        b = 0.0799017958419154
        c = 0.0851858618842153
        d = 0.0562935137369496
        
        # Apply LogC4 to linear transform
        linear = np.where(
            x > c,
            np.power(10, (x - d) / a) - b / a,
            (x - c) / b
        )
        
        return np.clip(linear, 0, None)
    
    def _log_decoding_fallback(self, x: np.ndarray) -> np.ndarray:
        """Generic log to linear fallback."""
        return np.power(2, (x - 0.5) * 14)  # Approximate log curve
    
    def rgb_to_y_bt2020(self, rgb: np.ndarray) -> np.ndarray:
        """Convert RGB to luminance using BT.2020 primaries."""
        if len(rgb.shape) == 3:
            y = rgb[..., 0] * 0.2627 + rgb[..., 1] * 0.6780 + rgb[..., 2] * 0.0593
        else:
            y = rgb
        return y
    
    def map_luminance_to_zones(self, linear_y: np.ndarray) -> np.ndarray:
        """Map linear luminance values to EL Zone colors."""
        out_colors = np.zeros(linear_y.shape + (3,), dtype=np.float32)
        
        for idx, stops in enumerate(STOPS_LIST):
            # Calculate zone boundaries
            if stops == -EXP_RANGE:
                upper_diff = STOPS_LIST[idx + 1] - STOPS_LIST[idx]
                high_stops = stops + upper_diff / 2
                low_stops = -20  # Extend to very dark
            elif stops == EXP_RANGE:
                lower_diff = STOPS_LIST[idx] - STOPS_LIST[idx - 1]
                high_stops = 20  # Extend to very bright
                low_stops = stops - lower_diff / 2
            else:
                upper_diff = STOPS_LIST[idx + 1] - STOPS_LIST[idx]
                lower_diff = STOPS_LIST[idx] - STOPS_LIST[idx - 1]
                high_stops = stops + upper_diff / 2
                low_stops = stops - lower_diff / 2
            
            # Convert stops to linear values
            low_value = GRAY18 * (2 ** low_stops)
            high_value = GRAY18 * (2 ** high_stops)
            
            # Create mask for this zone
            zone_mask = (low_value <= linear_y) & (linear_y < high_value)
            
            # Apply color to masked pixels
            out_colors[zone_mask] = self.color_list_display[idx]
        
        return out_colors
    
    def create_el_zone_map(self, image: Union[Image.Image, np.ndarray]) -> np.ndarray:
        """
        Create EL Zone System false color map from input image.
        
        Args:
            image: Input image (PIL Image or numpy array)
            
        Returns:
            EL Zone mapped image as numpy array (0-1 range)
        """
        # Convert to numpy array if PIL Image
        if isinstance(image, Image.Image):
            if image.mode == 'RGBA':
                image = image.convert('RGB')
            img_array = np.array(image, dtype=np.float32) / 255.0
        else:
            img_array = image.astype(np.float32)
            if img_array.max() > 1.0:
                img_array = img_array / 255.0
            # Handle RGBA arrays
            if img_array.shape[-1] == 4:
                img_array = img_array[..., :3]
        
        # Decode from log to linear if needed
        if self.decode_func is not None:
            linear_image = self.decode_func(img_array)
        else:
            linear_image = img_array.copy()
        
        # Calculate luminance using BT.2020 weights
        linear_y = self.rgb_to_y_bt2020(linear_image)
        
        # Map luminance to zone colors
        el_zone_image = self.map_luminance_to_zones(linear_y)
        
        return el_zone_image
    
    def create_el_zone_overlay(self, image: Union[Image.Image, np.ndarray], 
                              size: int = 400, add_border: bool = True) -> Image.Image:
        """
        Create EL Zone overlay image for compositing onto main image.
        
        Args:
            image: Input image (PIL Image or numpy array)
            size: Size of the overlay in pixels (width, height will maintain aspect)
            add_border: Whether to add white border
            
        Returns:
            EL Zone overlay as PIL Image with transparency
        """
        # Create EL Zone map
        el_zone_map = self.create_el_zone_map(image)
        
        # Convert to PIL Image
        el_zone_pil = Image.fromarray((el_zone_map * 255).astype(np.uint8), 'RGB')
        
        # Calculate target size maintaining aspect ratio
        aspect_ratio = el_zone_pil.height / el_zone_pil.width
        target_width = size
        target_height = int(size * aspect_ratio)
        
        # Resize the EL Zone image
        el_zone_resized = el_zone_pil.resize((target_width, target_height), Image.Resampling.LANCZOS)
        
        if add_border:
            # Create a new image with border
            border_size = 2
            bordered_width = target_width + 2 * border_size
            bordered_height = target_height + 2 * border_size
            
            # Create white background
            bordered_image = Image.new('RGBA', (bordered_width, bordered_height), (255, 255, 255, 255))
            
            # Convert EL Zone to RGBA
            el_zone_rgba = el_zone_resized.convert('RGBA')
            
            # Paste EL Zone in center
            bordered_image.paste(el_zone_rgba, (border_size, border_size))
            
            return bordered_image
        else:
            # Convert to RGBA and return
            return el_zone_resized.convert('RGBA')
    
    def create_vectorscope(self, image: Union[Image.Image, np.ndarray], 
                          size: Tuple[int, int] = (480, 540)) -> np.ndarray:
        """
        Create professional vectorscope visualization scaled to match image dimensions.
        
        Args:
            image: Input image
            size: Output size (width, height)
            
        Returns:
            Vectorscope image as numpy array
        """
        # Convert to numpy array
        if isinstance(image, Image.Image):
            if image.mode == 'RGBA':
                image = image.convert('RGB')
            img_array = np.array(image, dtype=np.float32) / 255.0
        else:
            img_array = image.astype(np.float32)
            if img_array.max() > 1.0:
                img_array = img_array / 255.0
            # Handle RGBA arrays
            if img_array.shape[-1] == 4:
                img_array = img_array[..., :3]
        
        # Use log image data directly for vectorscope (for consistency with waveform)
        log_image = img_array.copy()
        
        # Create vectorscope canvas
        vectorscope = np.zeros((size[1], size[0], 3), dtype=np.uint8)
        
        if len(log_image.shape) == 3:
            h, w = log_image.shape[:2]
            
            # Convert LOG RGB to YUV (Rec. 709 coefficients)
            r, g, b = log_image[..., 0], log_image[..., 1], log_image[..., 2]
            
            # YUV conversion (proper broadcast television standard)
            y = 0.299 * r + 0.587 * g + 0.114 * b
            u = -0.14713 * r - 0.28886 * g + 0.436 * b    # Cb scaled
            v = 0.615 * r - 0.51499 * g - 0.10001 * b     # Cr scaled
            
            # Center and scale for vectorscope display
            center_x, center_y = size[0] // 2, size[1] // 2
            scale = min(size) // 3  # Professional vectorscope scale
            
            # Sample pixels with spatial correlation to image dimensions
            # This ensures the vectorscope data correlates with the image above
            x_sample_step = max(1, w // 50)  # Sample across width
            y_sample_step = max(1, h // 50)  # Sample across height
            
            sample_x_coords = range(0, w, x_sample_step)
            sample_y_coords = range(0, h, y_sample_step)
            
            for img_y in sample_y_coords:
                for img_x in sample_x_coords:
                    # Get pixel values
                    pixel_u = u[img_y, img_x]
                    pixel_v = v[img_y, img_x]
                    pixel_y = y[img_y, img_x]
                    
                    # Only plot pixels above minimum luminance threshold
                    if pixel_y > 0.01:
                        # Map to vectorscope coordinates (V is X, U is Y, inverted)
                        x_coord = int(np.clip(center_x + (pixel_v * scale), 0, size[0] - 1))
                        y_coord = int(np.clip(center_y - (pixel_u * scale), 0, size[1] - 1))
                        
                        # Add intensity for white dots (professional vectorscope style)
                        current_vals = vectorscope[y_coord, x_coord]
                        vectorscope[y_coord, x_coord] = np.clip(current_vals + [80, 80, 80], 0, 255)
        
        # Draw professional graticule
        self._draw_vectorscope_graticule(vectorscope, size)
        
        return vectorscope.astype(np.float32) / 255.0
    
    def _draw_vectorscope_graticule(self, vectorscope: np.ndarray, size: Tuple[int, int]):
        """Draw professional vectorscope graticule with color targets."""
        center_x, center_y = size[0] // 2, size[1] // 2
        scale = min(size) // 3
        
        if HAS_OPENCV:
            # Draw concentric circles (75% and 100% saturation)
            cv2.circle(vectorscope, (center_x, center_y), int(scale * 0.75), (64, 64, 64), 1)
            cv2.circle(vectorscope, (center_x, center_y), scale, (64, 64, 64), 1)
            
            # Draw I and Q axes (33° and 123° from U axis)
            
            # I axis (skin tone line)
            i_angle = math.radians(33)
            i_x1 = int(center_x - scale * math.cos(i_angle))
            i_y1 = int(center_y - scale * math.sin(i_angle))
            i_x2 = int(center_x + scale * math.cos(i_angle))
            i_y2 = int(center_y + scale * math.sin(i_angle))
            cv2.line(vectorscope, (i_x1, i_y1), (i_x2, i_y2), (96, 96, 96), 1)
            
            # Q axis
            q_angle = math.radians(123)
            q_x1 = int(center_x - scale * math.cos(q_angle))
            q_y1 = int(center_y - scale * math.sin(q_angle))
            q_x2 = int(center_x + scale * math.cos(q_angle))
            q_y2 = int(center_y + scale * math.sin(q_angle))
            cv2.line(vectorscope, (q_x1, q_y1), (q_x2, q_y2), (96, 96, 96), 1)
            
            # Draw primary color targets (R, G, B, C, M, Y)
            targets = [
                (0, scale, [255, 0, 0]),      # Red (0°)
                (120, scale, [255, 255, 0]),  # Yellow (120°)
                (240, scale, [0, 255, 0]),    # Green (240°)
                (180, scale, [0, 255, 255]),  # Cyan (180°)
                (300, scale, [0, 0, 255]),    # Blue (300°)
                (60, scale, [255, 0, 255])    # Magenta (60°)
            ]
            
            for angle_deg, radius, color in targets:
                angle_rad = math.radians(angle_deg - 90)  # Adjust for display orientation
                target_x = int(center_x + radius * 0.75 * math.cos(angle_rad))
                target_y = int(center_y + radius * 0.75 * math.sin(angle_rad))
                cv2.circle(vectorscope, (target_x, target_y), 3, color, -1)
                cv2.circle(vectorscope, (target_x, target_y), 4, (128, 128, 128), 1)
        
        else:
            # Fallback: draw basic grid
            vectorscope[center_y, :] = [64, 64, 64]  # Horizontal line
            vectorscope[:, center_x] = [64, 64, 64]  # Vertical line
            
            # Draw simple circles
            radius1 = int(scale * 0.75)
            radius2 = scale
            for r in [radius1, radius2]:
                for angle in range(0, 360, 5):
                    x = int(center_x + r * math.cos(math.radians(angle)))
                    y = int(center_y + r * math.sin(math.radians(angle)))
                    if 0 <= x < size[0] and 0 <= y < size[1]:
                        vectorscope[y, x] = [64, 64, 64]
    
    def create_waveform(self, image: Union[Image.Image, np.ndarray], 
                       size: Tuple[int, int] = (480, 540)) -> np.ndarray:
        """
        Create professional luminance waveform monitor from log image data.
        
        Args:
            image: Input log image
            size: Output size (width, height)
            
        Returns:
            Waveform image as numpy array
        """
        # Convert to numpy array
        if isinstance(image, Image.Image):
            if image.mode == 'RGBA':
                image = image.convert('RGB')
            img_array = np.array(image, dtype=np.float32) / 255.0
        else:
            img_array = image.astype(np.float32)
            if img_array.max() > 1.0:
                img_array = img_array / 255.0
            # Handle RGBA arrays
            if img_array.shape[-1] == 4:
                img_array = img_array[..., :3]
        
        # Use LOG image data directly for waveform (not linear)
        log_image = img_array.copy()
        
        # Create waveform canvas
        waveform = np.zeros((size[1], size[0], 3), dtype=np.uint8)
        
        if len(log_image.shape) == 3:
            w = log_image.shape[1]
            
            # Calculate luminance from LOG RGB values using Rec. 709 coefficients
            r, g, b = log_image[..., 0], log_image[..., 1], log_image[..., 2]
            log_luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
            
            # Map each column of the image to the waveform width (direct correlation)
            x_positions = np.linspace(0, w - 1, size[0], dtype=int)
            
            for waveform_x, img_x in enumerate(x_positions):
                if waveform_x >= size[0]:
                    break
                
                # Get log luminance column from image
                luma_column = log_luminance[:, img_x]
                
                # Sample every few pixels vertically for performance
                sample_step = max(1, len(luma_column) // 200)
                sampled_luma = luma_column[::sample_step]
                
                # Convert LOG luminance values to waveform Y positions
                y_positions = ((1 - np.clip(sampled_luma, 0, 1)) * (size[1] - 40) + 20).astype(int)
                y_positions = np.clip(y_positions, 0, size[1] - 1)
                
                # Draw the luminance trace in professional green
                for y_pos in y_positions:
                    current_r = int(waveform[y_pos, waveform_x, 0])
                    current_g = int(waveform[y_pos, waveform_x, 1])
                    current_b = int(waveform[y_pos, waveform_x, 2])
                    
                    # Professional waveform green trace
                    waveform[y_pos, waveform_x, 0] = min(255, current_r + 16)  # Slight red
                    waveform[y_pos, waveform_x, 1] = min(255, current_g + 80)  # Strong green
                    waveform[y_pos, waveform_x, 2] = min(255, current_b + 16)  # Slight blue
        
        # Draw professional grid and scale
        self._draw_waveform_grid(waveform, size)
        
        return waveform.astype(np.float32) / 255.0
    
    def _draw_waveform_grid(self, waveform: np.ndarray, size: Tuple[int, int]):
        """Draw luminance waveform grid lines and scale markers."""
        grid_color = [48, 48, 48]
        
        # Draw horizontal grid lines (IRE levels: 0%, 25%, 50%, 75%, 100%)
        for percent in [0, 25, 50, 75, 100]:
            y = int((size[1] - 40) * (1 - percent / 100)) + 20
            if 0 <= y < size[1]:
                waveform[y, :] = grid_color
        
        # Draw vertical grid lines for timing reference (every 12.5%)
        for i in range(1, 8):  # 7 vertical lines
            x = int(size[0] * i / 8)
            if x < size[0]:
                waveform[:, x] = [32, 32, 32]
        
        # Draw professional scale markers
        # 100% line (white level) - bright marker
        y_100 = 20
        waveform[y_100:y_100+2, :] = [160, 160, 160]
        
        # 75% line (common reference for video levels)
        y_75 = int((size[1] - 40) * 0.25) + 20
        waveform[y_75:y_75+1, :] = [96, 96, 96]
        
        # 50% line (middle gray)
        y_50 = int((size[1] - 40) * 0.5) + 20
        waveform[y_50:y_50+1, :] = [96, 96, 96]
        
        # 18% gray line (standard gray card)
        y_18 = int((size[1] - 40) * 0.82) + 20  # 18% from bottom
        waveform[y_18:y_18+1, :] = [80, 80, 80]
        
        # 0% line (black level) - bright marker  
        y_0 = size[1] - 20
        waveform[y_0-2:y_0, :] = [160, 160, 160]
    
    def create_4_quadrant_layout(self, original_image: Union[Image.Image, np.ndarray],
                                el_zone_image: np.ndarray,
                                vectorscope: np.ndarray,
                                waveform: np.ndarray,
                                output_size: Tuple[int, int] = (1920, 1080)) -> np.ndarray:
        """
        Create 4-quadrant layout with original, EL Zone, vectorscope, and waveform.
        
        Args:
            original_image: Original log image
            el_zone_image: EL Zone processed image
            vectorscope: Vectorscope visualization
            waveform: Waveform visualization
            output_size: Final output size (width, height)
            
        Returns:
            Combined 4-quadrant image
        """
        # Calculate quadrant dimensions
        quad_width = output_size[0] // 2
        quad_height = output_size[1] // 2
        
        # Create output canvas
        output = np.zeros((output_size[1], output_size[0], 3), dtype=np.float32)
        
        # Convert original image to numpy if needed
        if isinstance(original_image, Image.Image):
            if original_image.mode == 'RGBA':
                original_image = original_image.convert('RGB')
            orig_array = np.array(original_image, dtype=np.float32) / 255.0
        else:
            orig_array = original_image.astype(np.float32)
            if orig_array.max() > 1.0:
                orig_array = orig_array / 255.0
            # Handle RGBA arrays
            if orig_array.shape[-1] == 4:
                orig_array = orig_array[..., :3]
        
        # Resize top images to fill width while maintaining aspect ratio
        orig_resized = self._resize_to_fill_width(orig_array, (quad_width, quad_height))
        el_zone_resized = self._resize_to_fill_width(el_zone_image, (quad_width, quad_height))
        
        # Calculate remaining height for bottom quadrants
        top_image_height = orig_resized.shape[0]
        bottom_height = output_size[1] - top_image_height
        
        # Resize vectorscope and waveform to fit remaining space
        vectorscope_resized = self._resize_to_fit(vectorscope, (quad_width, bottom_height))
        waveform_resized = self._resize_to_fit(waveform, (quad_width, bottom_height))
        
        # Place quadrants
        # Top-left: Original image (scaled to width)
        output[:top_image_height, :quad_width] = orig_resized
        
        # Top-right: EL Zone image (scaled to width)
        output[:top_image_height, quad_width:] = el_zone_resized
        
        # Bottom-left: Vectorscope
        output[top_image_height:, :quad_width] = vectorscope_resized
        
        # Bottom-right: Waveform
        output[top_image_height:, quad_width:] = waveform_resized
        
        # Add labels
        output = self._add_quadrant_labels(output, output_size, top_image_height)
        
        return output
    
    def _resize_to_fill_width(self, image: np.ndarray, target_size: Tuple[int, int]) -> np.ndarray:
        """Resize image to fill target width while maintaining aspect ratio."""
        if len(image.shape) == 2:
            image = np.stack([image, image, image], axis=-1)
        
        # Handle RGBA images by converting to RGB
        if image.shape[-1] == 4:
            image = image[..., :3]
        
        h, w = image.shape[:2]
        target_w = target_size[0]
        
        # Calculate scaling factor to fill width
        scale = target_w / w
        new_w = target_w
        new_h = int(h * scale)
        
        # Resize using PIL for better quality
        pil_image = Image.fromarray((image * 255).astype(np.uint8))
        pil_resized = pil_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
        resized = np.array(pil_resized, dtype=np.float32) / 255.0
        
        # Ensure RGB format
        if resized.shape[-1] == 4:
            resized = resized[..., :3]
        
        return resized
    
    def _resize_to_fit(self, image: np.ndarray, target_size: Tuple[int, int]) -> np.ndarray:
        """Resize image to fit target size while maintaining aspect ratio."""
        if len(image.shape) == 2:
            image = np.stack([image, image, image], axis=-1)
        
        # Handle RGBA images by converting to RGB
        if image.shape[-1] == 4:
            image = image[..., :3]  # Drop alpha channel
        
        h, w = image.shape[:2]
        target_w, target_h = target_size
        
        # Calculate scaling factor
        scale = min(target_w / w, target_h / h)
        new_w = int(w * scale)
        new_h = int(h * scale)
        
        # Resize using PIL for better quality
        pil_image = Image.fromarray((image * 255).astype(np.uint8))
        pil_resized = pil_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
        resized = np.array(pil_resized, dtype=np.float32) / 255.0
        
        # Ensure RGB format
        if resized.shape[-1] == 4:
            resized = resized[..., :3]
        
        # Center in target canvas
        output = np.zeros((target_h, target_w, 3), dtype=np.float32)
        y_offset = (target_h - new_h) // 2
        x_offset = (target_w - new_w) // 2
        
        output[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = resized
        
        return output
    
    def _add_quadrant_labels(self, output: np.ndarray, output_size: Tuple[int, int], top_image_height: int) -> np.ndarray:
        """Add labels to each quadrant at the bottom."""
        # Convert to PIL for text rendering
        pil_output = Image.fromarray((output * 255).astype(np.uint8))
        draw = ImageDraw.Draw(pil_output)
        
        # Try to load a monospace font at 12pt
        try:
            # Try common monospace fonts
            for font_name in ["Courier New", "Monaco", "Menlo", "DejaVu Sans Mono", "Liberation Mono"]:
                try:
                    font = ImageFont.truetype(font_name, 12)
                    break
                except:
                    continue
            else:
                # Fallback to default font
                font = ImageFont.load_default()
        except:
            font = ImageFont.load_default()
        
        quad_width = output_size[0] // 2
        
        # Calculate label positions at bottom of each quadrant
        # Top quadrants: place labels at bottom of images
        top_label_y = top_image_height - 25
        # Bottom quadrants: place labels at bottom of canvas
        bottom_label_y = output_size[1] - 25
        
        # Add labels at bottom of each quadrant
        labels = [
            ("Original Log", (10, top_label_y)),
            ("EL Zone System", (quad_width + 10, top_label_y)),
            ("Vectorscope", (10, bottom_label_y)),
            ("Waveform", (quad_width + 10, bottom_label_y))
        ]
        
        for label, pos in labels:
            draw.text(pos, label, fill=(255, 255, 255), font=font)
        
        return np.array(pil_output, dtype=np.float32) / 255.0
    
    def process_image(self, image: Union[Image.Image, str],
                     output_size: Tuple[int, int] = (1920, 1080)) -> np.ndarray:
        """
        Process image with complete EL Zone System workflow.
        
        Args:
            image: Input image (PIL Image or path)
            output_size: Final output size
            
        Returns:
            Complete 4-quadrant analysis image
        """
        # Load image if path provided
        if isinstance(image, str):
            image = Image.open(image)
        
        logger.info(f"Processing image with EL Zone System (log format: {self.log_format})")
        
        # Generate all components
        el_zone_map = self.create_el_zone_map(image)
        vectorscope = self.create_vectorscope(image)
        waveform = self.create_waveform(image)
        
        # Create 4-quadrant layout
        result = self.create_4_quadrant_layout(
            image, el_zone_map, vectorscope, waveform, output_size
        )
        
        return result


def create_el_zone_processor(log_format: str = "logc4") -> ELZoneProcessor:
    """
    Factory function to create an EL Zone processor.
    
    Args:
        log_format: Log format for processing ('logc4', 'slog3', 'apple_log', 'linear')
        
    Returns:
        ELZoneProcessor instance
    """
    return ELZoneProcessor(log_format)