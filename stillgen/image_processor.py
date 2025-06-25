# image_processor.py - Core image processing logic
import os
import subprocess
from PIL import Image
import numpy as np
from typing import Dict, Optional
import logging

from .cdl import create_cdl_file, update_ocio_config, ColorspaceDetector, TempFileManager
from .overlay import OverlayGenerator
from .utils import extract_clip_info, generate_output_filename
from .parsers import LazyCSVLoader, parse_extraction_info, calculate_crop_from_extraction
from .el_zone import ELZoneProcessor

logger = logging.getLogger(__name__)


class StillProcessor:
    """Handles the core image processing pipeline."""
    
    def __init__(self, config, ale_data: Dict, silverstack_data: Dict, csv_loader: LazyCSVLoader):
        self.config = config
        self.ale_data = ale_data
        self.silverstack_data = silverstack_data
        self.csv_loader = csv_loader
        self.overlay_generator = OverlayGenerator(config)
        self.colorspace_detector = ColorspaceDetector()
        
        # Initialize EL Zone processor if enabled (for separate file generation)
        self.el_zone_processor = None
        if getattr(config, 'generate_el_zone', False) and not getattr(config, 'el_zone_overlay', False):
            log_format = getattr(config, 'el_zone_log_format', 'logc4')
            self.el_zone_processor = ELZoneProcessor(log_format)
        
        # Validate oiiotool is available
        self._check_oiiotool()
    
    def _check_oiiotool(self):
        """Check if oiiotool is available."""
        try:
            subprocess.run(["which", "oiiotool"], capture_output=True, check=True)
        except subprocess.CalledProcessError:
            raise RuntimeError("oiiotool not found. Please install OpenImageIO.")
    
    def process_image(self, input_path: str) -> bool:
        """Process a single image file."""
        temp_manager = TempFileManager()
        
        try:
            # Extract clip information from filename
            clip_name, tc_key = extract_clip_info(input_path)
            if not clip_name or not tc_key:
                logger.warning(f"Invalid filename format: {input_path}")
                return False
            
            # Get ALE data - try both clip name and variations
            ale_entry = self._find_ale_entry(clip_name)
            if not ale_entry:
                logger.warning(f"No ALE entry found for {clip_name}")
                return False
            
            # Get CSV data for this frame
            csv_entry = self.csv_loader.get_frame_data(clip_name, tc_key)
            
            # Get Silverstack data
            tape_name = ale_entry.get('Tape', '').strip()
            silverstack_entry = self.silverstack_data.get(tape_name) if tape_name else None
            
            # Generate output filename and path
            output_filename = generate_output_filename(ale_entry, silverstack_entry, csv_entry)
            output_path = os.path.join(self.config.output_folder, f"{output_filename}.tiff")
            
            # Generate EL Zone output path if enabled
            el_zone_output_path = None
            if self.el_zone_processor:
                el_zone_output_path = os.path.join(
                    self.config.output_folder, f"{output_filename}_exp_tool.jpg"
                )
            
            # Skip if already processed (for resume functionality)
            if self.config.resume and os.path.exists(output_path):
                # Also check EL Zone output if enabled
                if el_zone_output_path and not os.path.exists(el_zone_output_path):
                    # Generate EL Zone for existing processed image
                    self._generate_el_zone_output(input_path, el_zone_output_path, ale_entry)
                logger.debug(f"Skipping already processed: {output_path}")
                return True
            
            # Apply color transform
            processed_image_path = self._apply_color_transform(
                input_path, ale_entry, temp_manager
            )
            
            if not processed_image_path:
                return False
            
            # Load and process image
            final_image, image_bounds = self._process_image_geometry(processed_image_path, ale_entry)
            
            # Load and crop source image for EL Zone overlay if needed
            cropped_source_image = None
            el_zone_overlay_enabled = getattr(self.config, 'el_zone_overlay', False)
            logger.debug(f"process_image: el_zone_overlay config = {el_zone_overlay_enabled}")
            
            if el_zone_overlay_enabled:
                try:
                    logger.debug(f"Loading source image from: {input_path}")
                    source_image = Image.open(input_path).convert("RGBA")
                    
                    # Apply the same crop as the main image (using extraction if available)
                    width, height = source_image.size
                    crop_params = None
                    if ale_entry and 'Extraction' in ale_entry:
                        extraction_info = parse_extraction_info(ale_entry['Extraction'])
                        if extraction_info:
                            crop_params = calculate_crop_from_extraction(extraction_info)
                    
                    if crop_params:
                        left = crop_params['crop_left']
                        right = width - crop_params['crop_right']
                        top = crop_params['crop_top']
                        bottom = height - crop_params['crop_bottom']
                    else:
                        left = self.config.crop_left
                        right = width - self.config.crop_right
                        top = self.config.crop_top
                        bottom = height - self.config.crop_bottom
                    
                    cropped_source_image = source_image.crop((left, top, right, bottom))
                    
                    logger.debug(f"Source image cropped: original={source_image.size}, cropped={cropped_source_image.size}")
                except Exception as e:
                    logger.error(f"Failed to load source image for EL Zone overlay: {e}", exc_info=True)
                    cropped_source_image = None
            
            # Add overlays with image bounds info
            logger.debug(f"Calling add_overlays with source_image={cropped_source_image is not None}, bounds={image_bounds}")
            self.overlay_generator.add_overlays(
                final_image, ale_entry, silverstack_entry, csv_entry, 
                cropped_source_image, image_bounds
            )
            
            # Save final image
            self._save_image(final_image, output_path)
            
            # Generate EL Zone output if enabled
            if self.el_zone_processor and el_zone_output_path:
                self._generate_el_zone_output(input_path, el_zone_output_path, ale_entry)
            
            logger.info(f"Processed: {os.path.basename(input_path)} -> {os.path.basename(output_path)}")
            if el_zone_output_path:
                logger.info(f"EL Zone: {os.path.basename(input_path)} -> {os.path.basename(el_zone_output_path)}")
            return True
            
        except Exception as e:
            logger.error(f"Error processing {input_path}: {str(e)}")
            return False
        finally:
            temp_manager.cleanup()
    
    def _find_ale_entry(self, clip_name: str) -> Optional[Dict]:
        """Find ALE entry with fallback strategies."""
        # Direct lookup
        if clip_name in self.ale_data:
            return self.ale_data[clip_name]
        
        # Try without extensions or suffixes
        base_name = clip_name.split('.')[0].split('_')[0]
        if base_name in self.ale_data:
            return self.ale_data[base_name]
        
        # Try partial match
        for key in self.ale_data:
            if clip_name.startswith(key) or key.startswith(clip_name):
                return self.ale_data[key]
        
        return None
    
    def _apply_color_transform(self, input_path: str, ale_entry: Dict, 
                              temp_manager: TempFileManager) -> Optional[str]:
        """Apply color transformation using OCIO and CDL."""
        # Get CDL values
        asc_sop = ale_entry.get('ASC_SOP', '')
        asc_sat = ale_entry.get('ASC_SAT', '')
        
        if not asc_sop or not asc_sat:
            logger.error(f"Missing CDL values for {input_path}")
            return None
        
        # Create CDL file
        use_cache = self.config.profile.settings.get('use_cache', True)
        cdl_path = create_cdl_file(asc_sop, asc_sat, use_cache=use_cache)
        # CDL files are managed by cache or temp manager
        if not use_cache:
            temp_manager.add_file(cdl_path)
        
        # Update OCIO config
        ocio_config_path = update_ocio_config(
            self.config.config_template_path, 
            cdl_path, 
            self.config.lut_dir
        )
        temp_manager.add_file(ocio_config_path)
        
        # Set OCIO environment variable
        os.environ["OCIO"] = ocio_config_path
        
        # Detect source colorspace and check if input LUT is needed
        clip_name = os.path.basename(input_path).split('-')[0]
        source_colorspace = self.colorspace_detector.detect_colorspace(clip_name, ale_entry)
        uses_input_lut = self.colorspace_detector.uses_input_lut(clip_name)
        
        # Create temporary output path
        temp_output = os.path.join(
            os.path.dirname(input_path), 
            f"temp_{os.path.basename(input_path)}"
        )
        temp_manager.add_file(temp_output)
        
        try:
            if uses_input_lut:
                # For U and F cameras: Apply input LUT + CDL + output LUT pipeline
                # The REDLog3 colorspace already includes the input LUT transformation
                # (REDLog3G10WG_to_gm5_ARRILogC4WG4.cube) as defined in the OCIO config
                logger.debug(f"Using input LUT pipeline for camera letter: {clip_name[0]}")
                
                # Direct transform from source colorspace to final output
                # This applies: input LUT -> linear -> CDL -> output LUT
                cmd = [
                    "oiiotool",
                    input_path,
                    "--colorconvert", source_colorspace, "Output_w_Look",
                    "-o", temp_output
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    logger.error(f"Input LUT color pipeline failed: {result.stderr}")
                    return None
                    
            else:
                # Standard pipeline for other cameras: source -> linear -> CDL + output LUT
                logger.debug(f"Using standard pipeline for camera letter: {clip_name[0]}")
                
                # First convert to linear
                cmd1 = [
                    "oiiotool",
                    input_path,
                    "--colorconvert", source_colorspace, "linear",
                    "-o", temp_output
                ]
                
                result = subprocess.run(cmd1, capture_output=True, text=True)
                if result.returncode != 0:
                    logger.error(f"Color conversion to linear failed: {result.stderr}")
                    return None
                
                # Then apply CDL and LUT
                cmd2 = [
                    "oiiotool",
                    temp_output,
                    "--colorconvert", "linear", "Output_w_Look",
                    "-o", temp_output
                ]
                
                result = subprocess.run(cmd2, capture_output=True, text=True)
                if result.returncode != 0:
                    logger.error(f"CDL/LUT application failed: {result.stderr}")
                    return None
            
            return temp_output
            
        except Exception as e:
            logger.error(f"Color transform failed: {e}")
            return None
    
    def _process_image_geometry(self, image_path: str, ale_entry: Optional[Dict] = None) -> tuple[Image.Image, dict]:
        """Process image geometry (crop, resize, add black bars).
        
        Args:
            image_path: Path to the image file
            ale_entry: ALE entry containing extraction information
        
        Returns:
            tuple: (processed image, image bounds dict with x, y, width, height)
        """
        # Load image
        image = Image.open(image_path).convert("RGBA")
        width, height = image.size
        
        # Try to get crop parameters from extraction information
        crop_params = None
        if ale_entry and 'Extraction' in ale_entry:
            extraction_info = parse_extraction_info(ale_entry['Extraction'])
            if extraction_info:
                crop_params = calculate_crop_from_extraction(extraction_info)
                logger.debug(f"Using extraction-based cropping for {os.path.basename(image_path)}")
        
        # Use extraction-based crop if available, otherwise fall back to config
        if crop_params:
            left = crop_params['crop_left']
            right = width - crop_params['crop_right']
            top = crop_params['crop_top']
            bottom = height - crop_params['crop_bottom']
            logger.debug(f"Extraction crop: L{left} R{crop_params['crop_right']} T{top} B{crop_params['crop_bottom']}")
        else:
            # Fallback to config-based cropping
            left = self.config.crop_left
            right = width - self.config.crop_right
            top = self.config.crop_top
            bottom = height - self.config.crop_bottom
            logger.debug(f"Config crop: L{left} R{self.config.crop_right} T{top} B{self.config.crop_bottom}")
        
        # Crop image
        image = image.crop((left, top, right, bottom))
        
        # Calculate new dimensions maintaining aspect ratio
        new_width = self.config.output_width
        aspect_ratio = image.height / image.width
        new_height = int(new_width * aspect_ratio)
        
        # Get resize quality based on profile
        resize_quality = Image.Resampling.LANCZOS
        if self.config.profile.settings.get('resize_quality') == 'nearest':
            resize_quality = Image.Resampling.NEAREST
        
        # Resize image
        image = image.resize((new_width, new_height), resize_quality)
        
        # Create black container
        container = Image.new('RGBA', 
                            (self.config.output_width, self.config.output_height), 
                            (0, 0, 0, 255))
        
        # Calculate position to center the image vertically
        y_offset = (self.config.output_height - new_height) // 2
        container.paste(image, (0, y_offset))
        
        # Return container and image bounds
        image_bounds = {
            'x': 0,
            'y': y_offset,
            'width': new_width,
            'height': new_height
        }
        
        return container, image_bounds
    
    def _save_image(self, image: Image.Image, output_path: str):
        """Save image with appropriate quality settings."""
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Save as TIFF without quality parameter (not supported for TIFF)
        image.save(output_path, 'TIFF')
    
    def _generate_el_zone_output(self, input_path: str, output_path: str, 
                                ale_entry: Optional[Dict] = None):
        """Generate EL Zone System analysis output."""
        try:
            # Load the input image
            input_image = Image.open(input_path)
            
            # Generate complete EL Zone analysis (4-quadrant layout)
            el_zone_result = self.el_zone_processor.process_image(
                input_image, 
                output_size=(1920, 1080)
            )
            
            # Convert to PIL image and save as JPEG
            el_zone_pil = Image.fromarray((el_zone_result * 255).astype(np.uint8), 'RGB')
            el_zone_pil.save(output_path, 'JPEG', quality=95, optimize=True)
            
        except Exception as e:
            logger.error(f"Failed to generate EL Zone analysis for {input_path}: {e}")


class BatchProcessor:
    """Handle batch processing with progress tracking."""
    
    def __init__(self, config, ale_data: Dict, silverstack_data: Dict):
        self.config = config
        self.ale_data = ale_data
        self.silverstack_data = silverstack_data
        self.csv_loader = LazyCSVLoader(config.frame_csv_folder)
        self.processor = StillProcessor(config, ale_data, silverstack_data, self.csv_loader)
    
    def process_batch(self, file_paths: list) -> list:
        """Process a batch of files and return results."""
        results = []
        
        for file_path in file_paths:
            try:
                success = self.processor.process_image(file_path)
                results.append((file_path, success, None))
            except Exception as e:
                results.append((file_path, False, str(e)))
        
        return results
