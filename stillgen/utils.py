# utils.py - Utility functions
import os
import re
import random
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Generator
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def find_tiff_files(input_folder: str) -> List[str]:
    """Recursively find all TIFF files in a folder."""
    tiff_files = []
    
    for root, _, files in os.walk(input_folder):
        for file in files:
            if file.lower().endswith(('.tiff', '.tif')):
                tiff_files.append(os.path.join(root, file))
    
    return tiff_files


def extract_clip_info(file_path: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract clip name and timecode from filename.
    
    Expected format: CLIPNAME-HH_MM_SS_FF.tiff
    Returns: (clip_name, timecode_key) or (None, None) if invalid
    """
    base_name = os.path.basename(file_path)
    base_name = os.path.splitext(base_name)[0]
    
    # Split by hyphen
    parts = base_name.split('-')
    if len(parts) != 2:
        logger.debug(f"Invalid filename format (no hyphen): {base_name}")
        return None, None
    
    clip_name = parts[0]
    tc_key = parts[1]
    
    # Validate timecode format (HH_MM_SS_FF)
    tc_pattern = r'^\d{2}_\d{2}_\d{2}_\d{2}$'
    if not re.match(tc_pattern, tc_key):
        logger.debug(f"Invalid timecode format: {tc_key}")
        return None, None
    
    return clip_name, tc_key


def transform_slate(slate_value: str) -> str:
    """Transform slate value according to specific rules.
    
    Rules:
    1. Remove the first character (always)
    2. Remove any P-Z characters
    3. If digits exist, put them first
    4. Add hyphen before any trailing letters
    
    Examples:
    - "143" → "43"
    - "143A" → "43-A"
    - "143AB" → "43-AB"
    - "1X43" → "43"
    - "1A43" → "43A"
    - "1A43B" → "43A-B"
    - "1XA43B" → "43A-B"
    """
    if not slate_value:
        return ''
    
    # Remove any leading/trailing spaces
    slate_value = slate_value.strip()
    
    # If empty after stripping, return empty string
    if not slate_value:
        return ''
    
    # Always remove the first character
    if len(slate_value) > 1:
        slate_value = slate_value[1:]
    else:
        return ''  # If only one character, nothing left after removal
    
    # Remove any P-Z characters from the string
    cleaned_slate = ''
    for char in slate_value:
        if char.upper() not in 'PQRSTUVWXYZ':
            cleaned_slate += char
    
    # If the cleaned slate is empty, return empty string
    if not cleaned_slate:
        return ''
    
    # Find the first digit position
    first_digit_pos = -1
    for i, char in enumerate(cleaned_slate):
        if char.isdigit():
            first_digit_pos = i
            break
    
    # If no digits found, return as is
    if first_digit_pos == -1:
        return cleaned_slate
    
    # Find where digits end
    last_digit_pos = first_digit_pos
    for i in range(first_digit_pos, len(cleaned_slate)):
        if cleaned_slate[i].isdigit():
            last_digit_pos = i
        else:
            break
    
    # Extract parts
    before_digits = cleaned_slate[:first_digit_pos]
    digits = cleaned_slate[first_digit_pos:last_digit_pos + 1]
    after_digits = cleaned_slate[last_digit_pos + 1:]
    
    # Construct result: digits first, then letters before (no hyphen), then letters after (with hyphen)
    result = digits
    if before_digits:
        result = digits + before_digits
    if after_digits:
        result = result + '-' + after_digits
    
    return result


def generate_output_filename(ale_entry: Dict, silverstack_entry: Optional[Dict], 
                           csv_entry: Optional[Dict]) -> str:
    """Generate output filename based on metadata."""
    # Import here to avoid circular import
    from .parsers import get_value_fuzzy
    
    # Extract base information
    episode = ale_entry.get('Episode', '').strip()
    slate = transform_slate(ale_entry.get('Slate', '').strip())  # Use Slate with transformation
    take = ale_entry.get('Take', '').strip()
    camera = ale_entry.get('Camera', '').strip()
    
    # Get additional metadata from silverstack
    shooting_date = get_value_fuzzy(silverstack_entry, 'Shoot Date') if silverstack_entry else ''
    shooting_day = get_value_fuzzy(silverstack_entry, 'Shooting Day') if silverstack_entry else ''
    crew_unit = get_value_fuzzy(silverstack_entry, 'Crew Unit') if silverstack_entry else ''
    look_name = get_value_fuzzy(silverstack_entry, 'Look Name') if silverstack_entry else ''
    
    # Format date if present
    if shooting_date and shooting_date != 'N/A':
        try:
            # Try to parse and reformat date
            date_obj = datetime.strptime(shooting_date, '%Y-%m-%d')
            shooting_date = date_obj.strftime('%Y%m%d')
        except:
            # Clean up date string - remove non-digits
            shooting_date = re.sub(r'[^\d]', '', shooting_date)
    
    # Get timecode suffix
    timecode_suffix = ''
    if csv_entry and 'Timecode' in csv_entry:
        timecode = csv_entry['Timecode']
        # Get last 5 characters and remove all separators
        timecode_suffix = timecode[-5:].replace(':', '').replace('/', '').replace('_', '')
    else:
        # Fallback to random digits
        timecode_suffix = ''.join(random.choices('0123456789', k=4))
    
    # Build filename using the specific format
    base_filename = f"{episode}-{slate}-{take}-{camera}_{shooting_date}_{shooting_day}_{crew_unit}_{look_name}_{timecode_suffix}"
    
    # Remove any remaining separators and clean up multiple underscores
    base_filename = re.sub(r'_+', '_', base_filename.replace('/', '').replace(':', '')).strip('_')
    
    # Additional cleanup - remove any empty segments that might create "--" or "__"
    base_filename = re.sub(r'-+', '-', base_filename)  # Replace multiple hyphens with single
    base_filename = re.sub(r'_+', '_', base_filename)  # Replace multiple underscores with single
    base_filename = base_filename.strip('-_')  # Remove leading/trailing separators
    
    # Ensure filename is not empty
    if not base_filename:
        base_filename = f"still_{timecode_suffix}"
    
    return base_filename


def process_in_batches(items: List, batch_size: int) -> Generator[List, None, None]:
    """Yield successive batches from items list."""
    for i in range(0, len(items), batch_size):
        yield items[i:i + batch_size]


def clean_path(path: str) -> str:
    """Clean and normalize a file path."""
    # Expand user home directory
    path = os.path.expanduser(path)
    
    # Convert to absolute path
    path = os.path.abspath(path)
    
    # Normalize path separators
    path = os.path.normpath(path)
    
    return path


def ensure_directory_exists(directory: str) -> bool:
    """Ensure a directory exists, create if necessary."""
    try:
        Path(directory).mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        logger.error(f"Failed to create directory {directory}: {e}")
        return False


def get_file_info(file_path: str) -> Dict[str, any]:
    """Get information about a file."""
    try:
        stat = os.stat(file_path)
        return {
            'path': file_path,
            'size': stat.st_size,
            'size_mb': stat.st_size / (1024 * 1024),
            'modified': datetime.fromtimestamp(stat.st_mtime),
            'created': datetime.fromtimestamp(stat.st_ctime)
        }
    except Exception as e:
        logger.error(f"Failed to get file info for {file_path}: {e}")
        return None


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def validate_image_file(file_path: str) -> Tuple[bool, Optional[str]]:
    """Validate that a file is a valid image file."""
    if not os.path.exists(file_path):
        return False, "File does not exist"
    
    if not os.path.isfile(file_path):
        return False, "Path is not a file"
    
    # Check file extension
    valid_extensions = {'.tiff', '.tif', '.png', '.jpg', '.jpeg'}
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in valid_extensions:
        return False, f"Invalid file extension: {ext}"
    
    # Check file size
    file_size = os.path.getsize(file_path)
    if file_size == 0:
        return False, "File is empty"
    
    # Check if file is readable
    try:
        with open(file_path, 'rb') as f:
            # Try to read first few bytes
            header = f.read(16)
            if not header:
                return False, "Cannot read file header"
    except Exception as e:
        return False, f"Cannot read file: {e}"
    
    return True, None


def create_backup(file_path: str, backup_dir: str = None) -> Optional[str]:
    """Create a backup of a file."""
    if not os.path.exists(file_path):
        logger.error(f"Cannot backup non-existent file: {file_path}")
        return None
    
    # Determine backup directory
    if backup_dir:
        ensure_directory_exists(backup_dir)
    else:
        backup_dir = os.path.dirname(file_path)
    
    # Generate backup filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    base_name = os.path.basename(file_path)
    name, ext = os.path.splitext(base_name)
    backup_name = f"{name}_backup_{timestamp}{ext}"
    backup_path = os.path.join(backup_dir, backup_name)
    
    try:
        import shutil
        shutil.copy2(file_path, backup_path)
        logger.info(f"Created backup: {backup_path}")
        return backup_path
    except Exception as e:
        logger.error(f"Failed to create backup: {e}")
        return None


def get_progress_percentage(current: int, total: int) -> float:
    """Calculate progress percentage."""
    if total == 0:
        return 0.0
    return (current / total) * 100


def estimate_time_remaining(processed: int, total: int, elapsed_seconds: float) -> str:
    """Estimate time remaining based on current progress."""
    if processed == 0:
        return "Unknown"
    
    rate = processed / elapsed_seconds  # items per second
    remaining = total - processed
    
    if rate == 0:
        return "Unknown"
    
    remaining_seconds = remaining / rate
    
    # Format time
    hours = int(remaining_seconds // 3600)
    minutes = int((remaining_seconds % 3600) // 60)
    seconds = int(remaining_seconds % 60)
    
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename to ensure it's valid across platforms."""
    # Remove or replace invalid characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    
    # Remove control characters
    filename = ''.join(char for char in filename if ord(char) >= 32)
    
    # Limit length (255 is typical max, but leave room for extensions)
    max_length = 200
    if len(filename) > max_length:
        filename = filename[:max_length]
    
    # Ensure filename is not empty
    if not filename:
        filename = "unnamed"
    
    return filename
