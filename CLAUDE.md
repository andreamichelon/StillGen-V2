# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

StillGen-V2 is a professional film still processing tool designed for high-performance batch processing of film stills with color grading, metadata overlays, and production workflow integration. It's a Python CLI application that processes TIFF images with industry-standard color management and metadata overlay generation.

## Architecture

### Core Components
- **stillgen.py**: Main entry point with multiprocessing orchestration and CLI interface
- **stillgen/**: Core Python package containing all processing modules
  - `config.py`: Configuration management and processing profiles
  - `parsers.py`: File format parsers (ALE, CSV, Silverstack exports)
  - `image_processor.py`: Core image processing pipeline
  - `cdl.py`: Color Decision List (CDL) handling for color grading
  - `overlay.py`: Text and logo overlay generation with production metadata
  - `el_zone.py`: EL Zone System analysis with vectorscope and histogram
  - `utils.py`: Utility functions and helpers
  - `dependencies.py`: External dependency validation

### Data Flow Architecture
1. **Input Processing**: TIFF files + metadata (CSV/ALE files)
2. **Color Grading**: Apply CDL/LUT transformations using OpenColorIO
3. **Overlay Generation**: Add production metadata, technical data, and logos
4. **EL Zone Analysis**: Optional 4-quadrant analysis with EL Zone System, vectorscope, and histogram
5. **Batch Processing**: Multiprocessing with caching for performance

### Professional Workflow Integration
- **Industry Formats**: ALE (Avid Log Exchange), CDL files, OCIO color management
- **Production Metadata**: Episode/scene/take tracking, crew information, camera metadata
- **Multi-Camera Support**: ARRI Alexa 35, RED cameras (R, U, F), with camera-specific processing
- **Post-Production Tools**: Integration with Silverstack, ARRI cameras, RED workflows, lab workflows

## Common Commands

### Running the Application
```bash
# Basic execution (uses default folder structure)
python stillgen.py

# With options
python stillgen.py --profile preview --workers 4 --resume

# Generate EL Zone System analysis
python stillgen.py --el-zone --el-zone-log logc4

# Using shell script (Unix/Mac)
./run-stillgen-sh.sh --preview --verbose --el-zone
```

### Development Commands
```bash
# Install dependencies
pip install -r requirements.txt

# Create virtual environment (handled by shell script)
python3 -m venv venv
source venv/bin/activate  # Unix/Mac
# venv\Scripts\activate   # Windows

# Check dependencies
python -c "from stillgen.dependencies import check_dependencies; check_dependencies()"
```

### Key CLI Options
- `--profile {preview,final}`: Processing quality profile
- `--workers N`: Parallel processing workers (default: CPU count)
- `--batch-size N`: Images per batch for processing
- `--resume`: Skip already processed files
- `--dry-run`: Preview what would be processed
- `--verbose`: Detailed logging output
- `--config-file`: Load YAML/JSON configuration
- `--el-zone`: Generate EL Zone System analysis (4-quadrant layout)
- `--el-zone-log`: Choose log format (logc4, slog3, apple_log, redlog3, linear)

## Project Structure

### Numbered Workflow Directories
- `01_INPUT_STILLS/`: Input TIFF files to process
- `02_DIT_CSV/`: Silverstack export CSV files
- `03_DIT_FbF/`: Frame-by-frame metadata CSV files
- `04_LAB_ALE/`: Lab ALE (Avid Log Exchange) files
- `05_OUTPUT_STILLS/`: Processed output images (created automatically)

### Static Resources
- `stillgen/static/`: Fonts, logos, LUTs, OCIO configuration templates
- `venv/`: Python virtual environment (included in repo)
- `stillgen.log`: Runtime log file

## Dependencies and External Tools

### Required External Dependencies
- **OpenImageIO** (`oiiotool` command): Professional image processing
  - macOS: `brew install openimageio`
  - Linux: `sudo apt-get install openimageio-tools`

### Python Dependencies (minimal)
- Pillow (image processing)
- numpy (numerical operations)
- tqdm (progress tracking)
- PyYAML (configuration files)
- Optional: matplotlib, scikit-image
- Optional for EL Zone: opencv-python, colour-science

## Development Notes

### Performance Considerations
- Uses multiprocessing for CPU-intensive image processing
- Implements smart caching for CDL files and images
- Memory-efficient handling of large TIFF files
- Batch processing reduces I/O overhead

### File Naming Conventions
- **Input**: `CLIPNAME-HH_MM_SS_FF.tiff` format supports multiple camera types:
  - ARRI Alexa: `A001_C002_0123AB-01_23_45_12.tiff`
  - RED cameras: `U001_C013_0623VB-16_59_50_07.tiff`, `F002_C001_0624CP-16_00_01_05.tiff`
- **Output**: Generated from metadata (e.g., `304-18-4-A_20240624_Day1_Main_DayExterior_9658.tiff`)

### Camera-Specific Processing
- **ARRI Alexa 35**: ARRI LogC4 color pipeline, extraction-based cropping from ALE
- **RED R Cameras**: REDLog3 input LUT color pipeline  
- **RED U Cameras**: REDLog3 input LUT + specific sensor cropping (6144x3240 → 2.39:1)
- **RED F Cameras**: REDLog3 input LUT + specific sensor cropping (5120x2700 → 2.39:1)

### Configuration
- Supports YAML/JSON configuration files
- Runtime configuration via command-line arguments
- Processing profiles for different quality/speed requirements

### Error Handling and Logging
- Comprehensive logging to `stillgen.log`
- Progress tracking with time estimates
- Resume capability for interrupted processing
- Dependency validation on startup

## Code Patterns

- Type hints used throughout for maintainability
- Single responsibility principle for modules
- Lazy loading of CSV data for memory efficiency
- Error handling with detailed logging
- Cross-platform compatibility (macOS, Linux, Windows)