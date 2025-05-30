# cdl.py - Color Decision List handling
import re
import os
import tempfile
from typing import Tuple, Optional
import logging
from functools import lru_cache
import hashlib

logger = logging.getLogger(__name__)


def parse_asc_sop(asc_sop: str) -> Tuple[str, str, str]:
    """Parse ASC_SOP string into slope, offset, and power."""
    match = re.match(r'\(([^)]+)\)\(([^)]+)\)\(([^)]+)\)', asc_sop)
    if not match:
        raise ValueError(f"Invalid ASC_SOP format: {asc_sop}")
    
    slope = match.group(1).strip()
    offset = match.group(2).strip()
    power = match.group(3).strip()
    
    # Validate values are numeric
    for component in [slope, offset, power]:
        values = component.split()
        if len(values) != 3:
            raise ValueError(f"Invalid component format: {component}")
        for v in values:
            try:
                float(v)
            except ValueError:
                raise ValueError(f"Non-numeric value in component: {component}")
    
    return slope, offset, power


def generate_cdl_content(asc_sop: str, asc_sat: str) -> str:
    """Generate CDL XML content from ASC_SOP and ASC_SAT values."""
    slope, offset, power = parse_asc_sop(asc_sop)
    
    # Validate saturation value
    try:
        float(asc_sat)
    except ValueError:
        raise ValueError(f"Invalid ASC_SAT value: {asc_sat}")
    
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<ColorCorrection id="cc0001">
    <SOPNode>
        <Slope>{slope}</Slope>
        <Offset>{offset}</Offset>
        <Power>{power}</Power>
    </SOPNode>
    <SatNode>
        <Saturation>{asc_sat}</Saturation>
    </SatNode>
</ColorCorrection>"""


class CDLCache:
    """Cache for CDL files to avoid recreating identical ones."""
    
    def __init__(self, cache_dir: str = ".stillgen_cache/cdl"):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self._memory_cache = {}
    
    def _get_cache_key(self, asc_sop: str, asc_sat: str) -> str:
        """Generate cache key from CDL parameters."""
        content = f"{asc_sop}:{asc_sat}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def get_cdl_path(self, asc_sop: str, asc_sat: str) -> Optional[str]:
        """Get cached CDL file path if exists."""
        cache_key = self._get_cache_key(asc_sop, asc_sat)
        
        # Check memory cache first
        if cache_key in self._memory_cache:
            path = self._memory_cache[cache_key]
            if os.path.exists(path):
                return path
            else:
                del self._memory_cache[cache_key]
        
        # Check disk cache
        cache_path = os.path.join(self.cache_dir, f"{cache_key}.cdl")
        if os.path.exists(cache_path):
            self._memory_cache[cache_key] = cache_path
            return cache_path
        
        return None
    
    def save_cdl(self, asc_sop: str, asc_sat: str, content: str) -> str:
        """Save CDL content to cache and return path."""
        cache_key = self._get_cache_key(asc_sop, asc_sat)
        cache_path = os.path.join(self.cache_dir, f"{cache_key}.cdl")
        
        with open(cache_path, 'w') as f:
            f.write(content)
        
        self._memory_cache[cache_key] = cache_path
        return cache_path


# Global cache instance
_cdl_cache = None


def get_cdl_cache(cache_dir: Optional[str] = None) -> CDLCache:
    """Get global CDL cache instance."""
    global _cdl_cache
    if _cdl_cache is None:
        _cdl_cache = CDLCache(cache_dir or ".stillgen_cache/cdl")
    return _cdl_cache


def create_cdl_file(asc_sop: str, asc_sat: str, use_cache: bool = True) -> str:
    """Create a CDL file and return its path."""
    if use_cache:
        cache = get_cdl_cache()
        cached_path = cache.get_cdl_path(asc_sop, asc_sat)
        if cached_path:
            logger.debug(f"Using cached CDL: {cached_path}")
            return cached_path
    
    try:
        cdl_content = generate_cdl_content(asc_sop, asc_sat)
        
        if use_cache:
            path = cache.save_cdl(asc_sop, asc_sat, cdl_content)
            logger.debug(f"Created and cached CDL: {path}")
            return path
        else:
            # Create temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.cdl', delete=False) as f:
                f.write(cdl_content)
                return f.name
                
    except Exception as e:
        logger.error(f"Failed to create CDL file: {e}")
        raise


def update_ocio_config(template_path: str, cdl_path: str, lut_dir: str) -> str:
    """Update OCIO config with CDL path and return temporary config path."""
    try:
        with open(template_path, 'r') as f:
            config_data = f.read()
        
        # Replace placeholders
        config_data = config_data.replace("cd.cdl", cdl_path)
        config_data = config_data.replace("search_path: luts", f"search_path: {lut_dir}")
        
        # Create temporary config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ocio', delete=False) as f:
            f.write(config_data)
            return f.name
            
    except Exception as e:
        logger.error(f"Failed to update OCIO config: {e}")
        raise


class ColorspaceDetector:
    """Detect source colorspace based on camera metadata."""
    
    # Camera identifier to colorspace mapping
    CAMERA_COLORSPACES = {
        'R': 'REDLog3',          # RED cameras
        'A': 'ArriLogC3',        # ARRI cameras
        'S': 'SLog3',            # Sony cameras
        'C': 'CanonLog3',        # Canon cameras
        'B': 'BlackmagicFilm',   # Blackmagic cameras
        'P': 'PanasonicVLog',    # Panasonic cameras
    }
    
    @classmethod
    def detect_colorspace(cls, clip_name: str, ale_entry: Optional[dict] = None) -> str:
        """Detect source colorspace from clip name or metadata."""
        # Try to detect from clip name first letter
        if clip_name and clip_name[0].upper() in cls.CAMERA_COLORSPACES:
            return cls.CAMERA_COLORSPACES[clip_name[0].upper()]
        
        # Try to detect from ALE metadata
        if ale_entry:
            camera_type = ale_entry.get('Camera Type', '').upper()
            manufacturer = ale_entry.get('Manufacturer', '').upper()
            
            # Check various metadata fields
            if 'RED' in camera_type or 'RED' in manufacturer:
                return 'REDLog3'
            elif 'ARRI' in camera_type or 'ARRI' in manufacturer:
                return 'ArriLogC3'
            elif 'SONY' in camera_type or 'SONY' in manufacturer:
                return 'SLog3'
            elif 'CANON' in camera_type or 'CANON' in manufacturer:
                return 'CanonLog3'
            elif 'BLACKMAGIC' in camera_type or 'BLACKMAGIC' in manufacturer:
                return 'BlackmagicFilm'
            elif 'PANASONIC' in camera_type or 'PANASONIC' in manufacturer:
                return 'PanasonicVLog'
        
        # Default to raw if cannot detect
        logger.warning(f"Could not detect colorspace for {clip_name}, defaulting to 'raw'")
        return 'raw'


def validate_cdl_values(asc_sop: str, asc_sat: str) -> Tuple[bool, Optional[str]]:
    """Validate CDL values and return (is_valid, error_message)."""
    try:
        # Parse ASC_SOP
        slope, offset, power = parse_asc_sop(asc_sop)
        
        # Validate saturation
        sat_value = float(asc_sat)
        if sat_value < 0:
            return False, "Saturation value cannot be negative"
        
        # Check for extreme values that might indicate errors
        for component_name, component in [('slope', slope), ('offset', offset), ('power', power)]:
            values = [float(v) for v in component.split()]
            
            if component_name == 'slope' and any(v < 0 for v in values):
                return False, f"Negative slope value detected: {component}"
            
            if component_name == 'power' and any(v <= 0 for v in values):
                return False, f"Non-positive power value detected: {component}"
            
            # Warn about extreme values
            if any(abs(v) > 10 for v in values):
                logger.warning(f"Extreme {component_name} value detected: {component}")
        
        return True, None
        
    except Exception as e:
        return False, str(e)


class TempFileManager:
    """Manage temporary files and ensure cleanup."""
    
    def __init__(self):
        self.temp_files = []
    
    def add_file(self, filepath: str):
        """Add a file to be cleaned up."""
        self.temp_files.append(filepath)
    
    def cleanup(self):
        """Clean up all temporary files."""
        for filepath in self.temp_files:
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
                    logger.debug(f"Cleaned up temp file: {filepath}")
            except Exception as e:
                logger.error(f"Failed to clean up {filepath}: {e}")
        self.temp_files.clear()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()