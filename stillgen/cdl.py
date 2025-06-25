# cdl.py - Color Decision List handling
import re
import os
import tempfile
import hashlib
from typing import Tuple, Optional
import logging
from functools import lru_cache

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
    
    def __init__(self, cache_dir: str = None):
        # Store cache in the output directory or current directory
        if cache_dir is None:
            cache_dir = os.path.abspath(".stillgen_cache/cdl")
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)
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
            # Return absolute path
            abs_path = os.path.abspath(cache_path)
            self._memory_cache[cache_key] = abs_path
            return abs_path
        
        return None
    
    def save_cdl(self, asc_sop: str, asc_sat: str, content: str) -> str:
        """Save CDL content to cache and return absolute path."""
        cache_key = self._get_cache_key(asc_sop, asc_sat)
        cache_path = os.path.join(self.cache_dir, f"{cache_key}.cdl")
        
        with open(cache_path, 'w') as f:
            f.write(content)
        
        # Return absolute path
        abs_path = os.path.abspath(cache_path)
        self._memory_cache[cache_key] = abs_path
        return abs_path


# Global cache instance
_cdl_cache = None


def get_cdl_cache(cache_dir: Optional[str] = None) -> CDLCache:
    """Get global CDL cache instance."""
    global _cdl_cache
    if _cdl_cache is None:
        # Use cache directory in the current working directory
        if cache_dir is None:
            cache_dir = os.path.join(os.getcwd(), ".stillgen_cache", "cdl")
        _cdl_cache = CDLCache(cache_dir)
    return _cdl_cache


def create_cdl_file(asc_sop: str, asc_sat: str, use_cache: bool = False) -> str:
    """Create a CDL file and return its path."""
    if use_cache:
        # Try to get from cache first
        cache = get_cdl_cache()
        cached_path = cache.get_cdl_path(asc_sop, asc_sat)
        if cached_path:
            return cached_path
        
        # Generate content and save to cache
        content = generate_cdl_content(asc_sop, asc_sat)
        return cache.save_cdl(asc_sop, asc_sat, content)
    else:
        # Create temporary file
        content = generate_cdl_content(asc_sop, asc_sat)
        temp_dir = os.path.join(os.getcwd(), ".stillgen_cache", "cdl", "temp")
        os.makedirs(temp_dir, exist_ok=True)
        
        # Create temporary file with unique name
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.cdl',
            dir=temp_dir,
            delete=False
        ) as f:
            f.write(content)
            return f.name


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
    
    @classmethod
    def detect_colorspace(cls, clip_name: str, ale_entry: Optional[dict] = None) -> str:
        """Detect source colorspace from clip name or metadata."""
        camera_letter = clip_name[0] if clip_name else ''
        
        if camera_letter == 'R':
            return "REDLog3"
        elif camera_letter in ['U', 'F']:
            # U and F cameras use REDLog3 with input LUT
            return "REDLog3"
        else:
            # All other camera letters (A, B, C, etc.) are ARRI cameras
            return "Arri LogC4"
    
    @classmethod
    def uses_input_lut(cls, clip_name: str) -> bool:
        """Check if this camera letter requires input LUT processing."""
        camera_letter = clip_name[0] if clip_name else ''
        return camera_letter in ['U', 'F']


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
    """Manages temporary files for cleanup."""
    
    def __init__(self):
        self.temp_files = set()
        self.temp_dirs = set()
    
    def add_file(self, file_path: str):
        """Add a file to be cleaned up."""
        if file_path:
            self.temp_files.add(file_path)
            # Also track the directory if it's a temp directory
            temp_dir = os.path.join(os.getcwd(), ".stillgen_cache", "cdl", "temp")
            if os.path.dirname(file_path) == temp_dir:
                self.temp_dirs.add(temp_dir)
    
    def cleanup(self):
        """Clean up all temporary files and directories."""
        for file_path in self.temp_files:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                logger.warning(f"Failed to remove temporary file {file_path}: {e}")
        
        # Clean up temp directories
        for temp_dir in self.temp_dirs:
            try:
                if os.path.exists(temp_dir):
                    os.rmdir(temp_dir)
            except Exception as e:
                logger.warning(f"Failed to remove temporary directory {temp_dir}: {e}")
        
        self.temp_files.clear()
        self.temp_dirs.clear()