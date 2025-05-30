# stillgen/__init__.py
"""
StillGen - Film Still Processing Tool
A high-performance tool for processing film stills with color grading and metadata overlays.
"""

__version__ = "2.0.0"
__author__ = "StillGen Team"
__description__ = "Film still processing with CDL color grading and metadata overlays"

# Package-level imports for convenience
from .config import Config, ProcessingProfile
from .parsers import parse_ale_files, parse_silverstack_files, LazyCSVLoader
from .image_processor import StillProcessor
from .utils import find_tiff_files, process_in_batches

__all__ = [
    'Config',
    'ProcessingProfile',
    'parse_ale_files',
    'parse_silverstack_files',
    'LazyCSVLoader',
    'StillProcessor',
    'find_tiff_files',
    'process_in_batches'
]
