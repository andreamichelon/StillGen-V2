# parsers.py - File parsing utilities
import os
import csv
import re
import logging
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


def parse_ale_file(ale_path: str) -> Dict[str, Dict]:
    """Parse ALE file and return a dictionary of clip data, keyed by Tape column."""
    clip_data = {}
    current_section = None
    headers = []
    
    logger.debug(f"Reading ALE file: {ale_path}")
    
    try:
        with open(ale_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.rstrip('\n')
                if not line:
                    continue
                    
                if line == 'Heading':
                    current_section = 'heading'
                    continue
                elif line == 'Column':
                    current_section = 'column'
                    continue
                elif line == 'Data':
                    current_section = 'data'
                    continue
                    
                if current_section == 'column':
                    headers = [h.strip() for h in line.split('\t')]
                    logger.debug(f"Found {len(headers)} columns in ALE")
                elif current_section == 'data':
                    values = [v.strip() for v in line.split('\t')]
                    if len(values) < len(headers):
                        values.extend([''] * (len(headers) - len(values)))
                    
                    if len(values) == len(headers):
                        clip_dict = dict(zip(headers, values))
                        
                        # Use Tape as primary key, fallback to Name
                        tape_value = clip_dict.get('Tape', '').strip()
                        name_value = clip_dict.get('Name', '').strip()
                        
                        # Store by both Tape and Name for flexibility
                        if tape_value:
                            clip_data[tape_value] = clip_dict
                        if name_value and name_value != tape_value:
                            clip_data[name_value] = clip_dict
                            
    except Exception as e:
        logger.error(f"Error parsing ALE file {ale_path}: {str(e)}")
        
    return clip_data


def parse_ale_files(ale_folder: str) -> Dict[str, Dict]:
    """Parse all ALE files in a folder and return combined data."""
    combined_data = {}
    
    if not os.path.exists(ale_folder):
        logger.error(f"ALE folder not found: {ale_folder}")
        return combined_data
    
    # Look for .ale files (case insensitive)
    ale_files = []
    for file in os.listdir(ale_folder):
        if file.lower().endswith('.ale'):
            ale_files.append(file)
    
    if not ale_files:
        logger.warning(f"No ALE files found in {ale_folder}")
        # Debug: show what files are in the folder
        all_files = os.listdir(ale_folder)
        if all_files:
            logger.debug(f"Files in {ale_folder}: {', '.join(all_files[:5])}")
            if len(all_files) > 5:
                logger.debug(f"... and {len(all_files) - 5} more files")
        return combined_data
    
    logger.info(f"Found {len(ale_files)} ALE file(s) in {ale_folder}")
    
    for ale_file in ale_files:
        ale_path = os.path.join(ale_folder, ale_file)
        logger.info(f"Processing ALE file: {ale_file}")
        data = parse_ale_file(ale_path)
        combined_data.update(data)
        logger.debug(f"Loaded {len(data)} clips from {ale_file}")
    
    logger.info(f"Total clips loaded from ALE files: {len(combined_data)}")
    return combined_data


def parse_silverstack_csv(csv_path: str) -> Dict[str, Dict]:
    """Parse Silverstack CSV file and return a dictionary of clip data."""
    clip_data = {}
    
    try:
        with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get('Name', '').strip()
                if name:
                    # Create a dictionary with all available fields, using empty string as default
                    clip_dict = {}
                    for key, value in row.items():
                        # Only store non-empty values
                        if value and value.strip():
                            clip_dict[key.strip()] = value.strip()
                    
                    # Store the clip data
                    clip_data[name] = clip_dict
                    
    except Exception as e:
        logger.error(f"Error parsing Silverstack CSV {csv_path}: {str(e)}")
        
    return clip_data


def parse_silverstack_files(csv_folder: str) -> Dict[str, Dict]:
    """Parse all Silverstack CSV files in a folder."""
    combined_data = {}
    
    if not os.path.exists(csv_folder):
        logger.error(f"Silverstack CSV folder not found: {csv_folder}")
        return combined_data
    
    csv_files = [f for f in os.listdir(csv_folder) if f.lower().endswith('.csv')]
    
    if not csv_files:
        logger.warning(f"No CSV files found in {csv_folder}")
        return combined_data
    
    for csv_file in csv_files:
        csv_path = os.path.join(csv_folder, csv_file)
        logger.info(f"Processing Silverstack CSV: {csv_file}")
        data = parse_silverstack_csv(csv_path)
        combined_data.update(data)
        logger.debug(f"Loaded {len(data)} clips from {csv_file}")
    
    logger.info(f"Total clips loaded from Silverstack files: {len(combined_data)}")
    return combined_data


def parse_frame_csv(csv_path: str) -> Optional[Dict[str, Dict]]:
    """Parse per-frame CSV data and return a dictionary of timecode-indexed data."""
    frame_data = {}
    
    try:
        with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.DictReader(f)
            
            # Normalize header names by stripping whitespace
            if reader.fieldnames:
                reader.fieldnames = [name.strip() for name in reader.fieldnames]
            
            for row in reader:
                tc = row.get('Timecode', '').strip()
                if tc:
                    # Convert timecode to key format (HH_MM_SS_FF)
                    tc_parts = tc.split(':')
                    if len(tc_parts) == 4:
                        tc_key = f"{tc_parts[0]}_{tc_parts[1]}_{tc_parts[2]}_{tc_parts[3]}"
                        frame_data[tc_key] = {k.strip(): v.strip() for k, v in row.items()}
        
        return frame_data
    except FileNotFoundError:
        logger.debug(f"CSV file not found: {csv_path}")
        return None
    except Exception as e:
        logger.error(f"Error reading CSV file {csv_path}: {str(e)}")
        return None


class LazyCSVLoader:
    """Lazy loader for per-frame CSV files with caching."""
    
    def __init__(self, csv_folder: str, cache_size: int = 32):
        self.csv_folder = csv_folder
        self._cache = {}
        self._cache_size = cache_size
    
    def _load_csv(self, clip_name: str) -> Optional[Dict[str, Dict]]:
        """Load CSV data for a specific clip."""
        csv_path = os.path.join(self.csv_folder, f"{clip_name}.csv")
        return parse_frame_csv(csv_path)
    
    def get_data(self, clip_name: str) -> Optional[Dict[str, Dict]]:
        """Get CSV data for a clip, loading lazily if needed."""
        # Simple manual cache implementation instead of lru_cache
        if clip_name in self._cache:
            return self._cache[clip_name]
        
        # Load data
        data = self._load_csv(clip_name)
        
        # Add to cache if there's room
        if len(self._cache) < self._cache_size:
            self._cache[clip_name] = data
        
        return data
    
    def get_frame_data(self, clip_name: str, tc_key: str) -> Optional[Dict]:
        """Get data for a specific frame."""
        csv_data = self.get_data(clip_name)
        if csv_data and tc_key in csv_data:
            return csv_data[tc_key]
        return None
    
    def clear_cache(self):
        """Clear the cache."""
        self._cache.clear()


def get_value_fuzzy(data: Optional[Dict], *keys: List[str], default: str = '') -> str:
    """Get value from dictionary with fuzzy key matching.
    
    Args:
        data: Dictionary to search in
        *keys: List of possible keys to match
        default: Default value to return if no match is found
        
    Returns:
        The matched value or the default value if no match is found
    """
    if not data:
        return default
    
    # Try exact matches first
    for key in keys:
        if key in data:
            value = data[key]
            return value if value else default
    
    # Try case-insensitive matches
    data_lower = {k.lower(): v for k, v in data.items()}
    for key in keys:
        if key.lower() in data_lower:
            value = data_lower[key.lower()]
            return value if value else default
    
    # Try partial matches
    for key in keys:
        for data_key in data:
            if key.lower() in data_key.lower():
                value = data[data_key]
                return value if value else default
    
    return default


def parse_extraction_info(extraction: str) -> Optional[Dict]:
    """Parse extraction information from ALE data.
    
    Expected format: CAMERA_WIDTHxHEIGHT_FORMAT_ASPECT_CROP
    Examples:
    - A35_4608x3164_SPH_2.39_95
    - RED_6144x3240_SPH_2.39_95  
    - RED_5120x2700_SPH_2.39_100
    
    Returns:
        Dict with keys: camera_type, original_width, original_height, 
                       format, aspect_ratio, crop_percent
    """
    if not extraction:
        return None
    
    try:
        # Split the extraction string by underscores
        parts = extraction.split('_')
        if len(parts) < 5:
            logger.debug(f"Invalid extraction format (not enough parts): {extraction}")
            return None
        
        camera_type = parts[0]
        resolution = parts[1]  # e.g., "4608x3164"
        format_type = parts[2]  # e.g., "SPH"
        aspect_ratio = float(parts[3])  # e.g., "2.39"
        crop_percent = int(parts[4])  # e.g., "95"
        
        # Parse resolution
        if 'x' not in resolution:
            logger.debug(f"Invalid resolution format in extraction: {resolution}")
            return None
        
        width_str, height_str = resolution.split('x')
        original_width = int(width_str)
        original_height = int(height_str)
        
        return {
            'camera_type': camera_type,
            'original_width': original_width,
            'original_height': original_height,
            'format': format_type,
            'aspect_ratio': aspect_ratio,
            'crop_percent': crop_percent
        }
        
    except (ValueError, IndexError) as e:
        logger.debug(f"Error parsing extraction '{extraction}': {e}")
        return None


def calculate_crop_from_extraction(extraction_info: Dict) -> Optional[Dict]:
    """Calculate crop parameters from extraction information.
    
    Args:
        extraction_info: Dict from parse_extraction_info()
        
    Returns:
        Dict with keys: crop_left, crop_right, crop_top, crop_bottom
    """
    if not extraction_info:
        return None
    
    try:
        original_width = extraction_info['original_width']
        original_height = extraction_info['original_height']
        aspect_ratio = extraction_info['aspect_ratio']
        crop_percent = extraction_info['crop_percent']
        
        # Calculate cropped dimensions (crop_percent% of original)
        crop_factor = crop_percent / 100.0
        cropped_width = int(original_width * crop_factor)
        cropped_height = int(original_height * crop_factor)
        
        # Calculate target height for the given aspect ratio
        target_height = int(cropped_width / aspect_ratio)
        
        # Ensure target height doesn't exceed cropped height
        if target_height > cropped_height:
            # Adjust width to fit the height constraint
            target_width = int(cropped_height * aspect_ratio)
            final_width = target_width
            final_height = cropped_height
        else:
            final_width = cropped_width
            final_height = target_height
        
        # Calculate crop values
        # Horizontal crop (equal on both sides)
        horizontal_crop_total = original_width - final_width
        crop_left = horizontal_crop_total // 2
        crop_right = horizontal_crop_total - crop_left
        
        # Vertical crop (equal on both sides)
        vertical_crop_total = original_height - final_height
        crop_top = vertical_crop_total // 2
        crop_bottom = vertical_crop_total - crop_top
        
        logger.debug(f"Extraction crop calculation: {original_width}x{original_height} -> "
                    f"{final_width}x{final_height} (crop: L{crop_left} R{crop_right} T{crop_top} B{crop_bottom})")
        
        return {
            'crop_left': crop_left,
            'crop_right': crop_right,
            'crop_top': crop_top,
            'crop_bottom': crop_bottom,
            'final_width': final_width,
            'final_height': final_height
        }
        
    except (KeyError, ValueError, ZeroDivisionError) as e:
        logger.error(f"Error calculating crop from extraction: {e}")
        return None


def validate_clip_data(clip_data: Dict[str, Dict]) -> Dict[str, List[str]]:
    """Validate clip data and return any issues found."""
    issues = {}
    
    required_fields = ['ASC_SOP', 'ASC_SAT', 'Name', 'Tape']
    
    for clip_name, data in clip_data.items():
        clip_issues = []
        
        for field in required_fields:
            if field not in data or not data[field]:
                clip_issues.append(f"Missing required field: {field}")
        
        # Validate ASC_SOP format
        if 'ASC_SOP' in data and data['ASC_SOP']:
            asc_sop = data['ASC_SOP']
            if not re.match(r'\([^)]+\)\([^)]+\)\([^)]+\)', asc_sop):
                clip_issues.append(f"Invalid ASC_SOP format: {asc_sop}")
        
        if clip_issues:
            issues[clip_name] = clip_issues
    
    return issues