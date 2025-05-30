# config.py - Configuration management
import os
import json
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple, Optional, Dict
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class ProcessingProfile:
    """Processing profile with quality settings."""
    PREVIEW = "preview"
    FINAL = "final"
    
    def __init__(self, profile_name: str = "final"):
        self.name = profile_name
        self.settings = self._get_settings(profile_name)
    
    def _get_settings(self, profile_name: str) -> dict:
        profiles = {
            "preview": {
                "resize_quality": "nearest",
                "skip_overlays": False,
                "output_quality": 85,
                "max_dimension": 1920,
                "use_cache": True
            },
            "final": {
                "resize_quality": "lanczos",
                "skip_overlays": False,
                "output_quality": 95,
                "max_dimension": 3840,
                "use_cache": True
            }
        }
        return profiles.get(profile_name, profiles["final"])


@dataclass
class Config:
    """Configuration for StillGen processing."""
    # Required paths
    input_folder: str
    output_folder: str
    lut_dir: str
    frame_csv_folder: str
    lab_ale_folder: str
    config_template_path: str
    silverstack_csv_folder: str
    
    # Processing settings
    profile: ProcessingProfile = field(default_factory=ProcessingProfile)
    resume: bool = False
    
    # Image processing settings
    crop_left: int = 115
    crop_right: int = 115
    crop_top: int = 665
    crop_bottom: int = 665
    output_width: int = 3840
    output_height: int = 2160
    
    # Overlay settings
    font_path: str = "monarcha-regular.ttf"
    font_size_small: int = 35
    font_size_medium: int = 40
    font_size_large: int = 70
    
    # Logo settings
    logo_image: str = "logo_image.png"
    tool_image: str = "tool_image.png"
    logo_padding: int = 50
    logo_max_height: int = 200
    logo_spacing: int = 20
    
    # Cache settings
    cache_dir: str = ".stillgen_cache"
    max_cache_size_mb: int = 1000
    
    # Text overlay positions
    text_margin: int = 60
    text_columns: int = 6
    text_y_top: int = 30
    text_y_bottom: int = 200
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        # Ensure output folder exists
        Path(self.output_folder).mkdir(parents=True, exist_ok=True)
        
        # Create cache directory
        Path(self.cache_dir).mkdir(parents=True, exist_ok=True)
        
        # Validate required files exist
        self._validate_files()
    
    def _validate_files(self):
        """Validate that required files exist."""
        required_files = [
            (self.config_template_path, "OCIO config template"),
            (self.font_path, "Font file"),
            (self.logo_image, "Logo image"),
            (self.tool_image, "Tool image")
        ]
        
        for file_path, description in required_files:
            if not os.path.exists(file_path):
                logger.warning(f"{description} not found at: {file_path}")
    
    def load_from_file(self, config_file: str):
        """Load configuration from YAML or JSON file."""
        try:
            with open(config_file, 'r') as f:
                if config_file.endswith('.yaml') or config_file.endswith('.yml'):
                    config_data = yaml.safe_load(f)
                else:
                    config_data = json.load(f)
            
            # Update configuration with loaded values
            for key, value in config_data.items():
                if hasattr(self, key):
                    setattr(self, key, value)
            
            logger.info(f"Loaded configuration from {config_file}")
        except Exception as e:
            logger.error(f"Failed to load configuration file: {e}")
    
    def save_to_file(self, config_file: str):
        """Save configuration to YAML or JSON file."""
        config_data = {
            'input_folder': self.input_folder,
            'output_folder': self.output_folder,
            'lut_dir': self.lut_dir,
            'frame_csv_folder': self.frame_csv_folder,
            'lab_ale_folder': self.lab_ale_folder,
            'config_template_path': self.config_template_path,
            'silverstack_csv_folder': self.silverstack_csv_folder,
            'crop_left': self.crop_left,
            'crop_right': self.crop_right,
            'crop_top': self.crop_top,
            'crop_bottom': self.crop_bottom,
            'output_width': self.output_width,
            'output_height': self.output_height,
            'font_path': self.font_path,
            'font_size_small': self.font_size_small,
            'font_size_medium': self.font_size_medium,
            'font_size_large': self.font_size_large,
            'logo_image': self.logo_image,
            'tool_image': self.tool_image,
            'logo_padding': self.logo_padding,
            'logo_max_height': self.logo_max_height,
            'logo_spacing': self.logo_spacing
        }
        
        try:
            with open(config_file, 'w') as f:
                if config_file.endswith('.yaml') or config_file.endswith('.yml'):
                    yaml.dump(config_data, f, default_flow_style=False)
                else:
                    json.dump(config_data, f, indent=2)
            logger.info(f"Saved configuration to {config_file}")
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")
    
    def is_processed(self, input_path: str) -> bool:
        """Check if a file has already been processed (for resume functionality)."""
        if not self.resume:
            return False
        
        # Generate expected output filename
        from utils import extract_clip_info
        clip_name, tc_key = extract_clip_info(input_path)
        if not clip_name:
            return False
        
        # Check if any output file with this clip name exists
        output_pattern = f"{clip_name}*"
        output_files = list(Path(self.output_folder).glob(output_pattern))
        return len(output_files) > 0
    
    def save_processing_report(self, processed: int, errors: List[Tuple[str, str]]):
        """Save a processing report with statistics and errors."""
        report_path = Path(self.output_folder) / f"processing_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'processed_count': processed,
            'error_count': len(errors),
            'configuration': {
                'input_folder': self.input_folder,
                'output_folder': self.output_folder,
                'profile': self.profile.name
            },
            'errors': [{'file': f, 'error': e} for f, e in errors]
        }
        
        try:
            with open(report_path, 'w') as f:
                json.dump(report, f, indent=2)
            logger.info(f"Processing report saved to {report_path}")
        except Exception as e:
            logger.error(f"Failed to save processing report: {e}")
    
    def get_cache_path(self, key: str) -> Path:
        """Get path for cached item."""
        return Path(self.cache_dir) / key
    
    def clean_cache(self):
        """Clean up old cache files."""
        cache_path = Path(self.cache_dir)
        if not cache_path.exists():
            return
        
        # Get all cache files with modification times
        cache_files = [(f, f.stat().st_mtime) for f in cache_path.iterdir() if f.is_file()]
        
        # Sort by modification time (oldest first)
        cache_files.sort(key=lambda x: x[1])
        
        # Calculate total size
        total_size = sum(f[0].stat().st_size for f in cache_files) / (1024 * 1024)  # MB
        
        # Remove oldest files if over limit
        while total_size > self.max_cache_size_mb and cache_files:
            file_to_remove, _ = cache_files.pop(0)
            size_mb = file_to_remove.stat().st_size / (1024 * 1024)
            file_to_remove.unlink()
            total_size -= size_mb
            logger.debug(f"Removed cache file: {file_to_remove.name}")
