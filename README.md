# StillGen - Film Still Processing Tool

StillGen is a high-performance tool for processing film stills with color grading, metadata overlays, and batch processing capabilities.

## Features

- **Color Management**: Apply CDL (Color Decision List) and LUTs using OpenColorIO
- **Multi-Camera Support**: ARRI Alexa 35, RED cameras (R, U, F) with camera-specific processing
- **Metadata Overlays**: Automatically add production information, technical data, and logos
- **EL Zone System**: Professional exposure analysis with 4-quadrant layout:
  - **EL Zone False Color**: Industry-standard exposure visualization
  - **Professional Vectorscope**: YUV color analysis with broadcast targets
  - **Luminance Waveform**: Log image monitoring with IRE scale
  - **Direct Image Correlation**: All tools scale to match source image dimensions
- **Batch Processing**: Process multiple images in parallel using all CPU cores
- **Smart Caching**: Cache CDL files and images for improved performance
- **Resume Capability**: Skip already processed files when resuming interrupted jobs
- **Multiple Profiles**: Preview and final quality profiles for different use cases
- **Configuration Files**: YAML/JSON configuration support for easy setup

## Installation

### Prerequisites

1. **Python 3.8+**
2. **Homebrew** (macOS) - Install from [brew.sh](https://brew.sh/)
3. **System Dependencies** (installed automatically by run script):
   - **OpenImageIO** (for `oiiotool` command): `brew install openimageio`
   - **OpenColorIO** (professional color management): `brew install opencolorio`
   - **pipx** (isolated Python app installs): `brew install pipx`

### Quick Setup (Recommended)

**For macOS/Linux users:**
```bash
# Clone or download StillGen files
# Navigate to the project directory
# Run the setup script (handles all dependencies automatically)
./run-stillgen-sh.sh --help
```

The `run-stillgen-sh.sh` script automatically:
- Checks for and installs Homebrew if needed
- Installs OpenImageIO and OpenColorIO via Homebrew
- Installs pipx for isolated Python environments
- Installs colour-science via pipx: `pipx install colour-science --include-deps`
- Creates and manages Python virtual environment
- Installs all required Python packages

### Manual Setup

1. **Install System Dependencies:**
   ```bash
   # Install Homebrew (if not already installed)
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   
   # Install required system packages
   brew install openimageio opencolorio pipx
   pipx ensurepath
   
   # Install colour-science for professional log decoding
   pipx install colour-science --include-deps
   ```

2. **Setup Python Environment:**
   ```bash
   # Create virtual environment
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   
   # Install Python dependencies
   pip install -r requirements.txt
   ```

3. **Verify Installation:**
   ```bash
   # Check if all tools are available
   oiiotool --help
   python -c "import colour; print('Colour-science:', colour.__version__)"
   python -c "import cv2; print('OpenCV:', cv2.__version__)"
   ```

### Professional Dependencies

**Required for EL Zone System:**
- **colour-science** - Official ARRI LogC4, Sony S-Log3 decoding
- **opencv-python** - Professional vectorscope and waveform generation
- **OpenColorIO** - Industry-standard color management (optional but recommended)

**Installation via pipx (recommended):**
```bash
pipx install colour-science --include-deps
```

This ensures colour-science is available system-wide and won't conflict with project dependencies.

## Usage

### Basic Usage

```bash
# Using default folder names (no arguments needed)
python stillgen.py

# Or specify custom folders
python stillgen.py 01_INPUT_STILLS 05_OUTPUT_STILLS 03_DIT_FbF 04_LAB_ALE 02_DIT_CSV
```

Note: The script automatically finds the OCIO config and LUT directory in `stillgen/static/`

### Advanced Usage with Options

```bash
# Preview mode with 4 workers (using default folders)
python stillgen.py --profile preview --workers 4

# Resume interrupted processing
python stillgen.py --resume

# Dry run to see what would be processed
python stillgen.py --dry-run

# Use configuration file
python stillgen.py --config-file stillgen_config.yaml
```

### Command Line Options

- `--profile {preview,final}`: Processing profile (default: final)
- `--workers N`: Number of worker processes (default: CPU count)
- `--batch-size N`: Images per batch (default: 10)
- `--resume`: Skip already processed files
- `--dry-run`: Show what would be processed without doing it
- `--verbose`: Enable detailed logging
- `--config-file`: Load settings from YAML/JSON file
- `--el-zone`: Generate EL Zone System analysis (4-quadrant layout)
- `--el-zone-log {logc4,slog3,apple_log,redlog3,linear}`: Log format for EL Zone processing

### EL Zone System Usage

Generate professional exposure analysis tools alongside your processed stills:

```bash
# Generate EL Zone analysis with LogC4 decoding
python stillgen.py --el-zone --el-zone-log logc4

# Using the shell script
./run-stillgen-sh.sh --el-zone --el-zone-log logc4
```

**EL Zone Output:**
- **File format**: JPEG (high quality, 95% compression)
- **Filename suffix**: `_exp_tool.jpg`
- **Layout**: 4-quadrant analysis (1920x1080)
  - Top-left: Original log image (scaled to width)
  - Top-right: EL Zone false color exposure map
  - Bottom-left: Professional vectorscope (YUV color analysis)
  - Bottom-right: Luminance waveform (log monitoring)

## Configuration

Create a `stillgen_config.yaml` file to customize settings:

```yaml
# See example_config.yaml for all options
output_width: 3840
output_height: 2160
font_size_medium: 40
logo_padding: 50
```

## Input File Structure

### Required Folder Structure
```
project/
├── stillgen.py            # Main script (root level)
├── 01_INPUT_STILLS/       # Input TIFF files to process
├── 02_DIT_CSV/            # Silverstack export CSV files
├── 03_DIT_FbF/            # Per-frame metadata CSV files
├── 04_LAB_ALE/            # ALE files from lab
├── 05_OUTPUT_STILLS/      # Processed output images (created automatically)
├── requirements.txt       # Python dependencies
├── example_config.yaml    # Example configuration
└── stillgen/             # Package directory
    ├── __init__.py
    ├── config.py
    ├── parsers.py
    ├── cdl.py
    ├── image_processor.py
    ├── overlay.py
    ├── utils.py
    ├── dependencies.py
    └── static/           # Static resources
        ├── config_template.ocio
        ├── lut_dir/      # Place LUT files here
        ├── logo_image.png
        ├── tool_image.png
        └── fonts/
            └── monarcha-regular.ttf
```

### File Naming Convention

**Input files:** `CLIPNAME-HH_MM_SS_FF.tiff` (supports multiple camera types)
- **ARRI Alexa**: `A001_C002_0123AB-01_23_45_12.tiff`
- **RED cameras**: `U001_C013_0623VB-16_59_50_07.tiff`, `F002_C001_0624CP-16_00_01_05.tiff`

**Output files:** Generated from metadata with consistent format
- Example: `304-18-4-A_20240624_Day1_Main_DayExterior_9658.tiff`

### Camera-Specific Processing

**ARRI Alexa 35:**
- Color pipeline: ARRI LogC4 → CDL → Output LUT
- Cropping: Extraction-based from ALE (e.g., `A35_4608x3164_SPH_2.39_95`)
- EL Zone: LogC4 log format recommended

**RED R Cameras:**
- Color pipeline: REDLog3 input LUT → CDL → Output LUT  
- EL Zone: REDLog3 log format recommended

**RED U Cameras:**
- Sensor: 6144x3240 → 2.39:1 aspect ratio (95% crop)
- Color pipeline: REDLog3 input LUT → CDL → Output LUT
- Cropping: Extraction-based from ALE (e.g., `RED_6144x3240_SPH_2.39_95`)

**RED F Cameras:**
- Sensor: 5120x2700 → 2.39:1 aspect ratio (100% crop)  
- Color pipeline: REDLog3 input LUT → CDL → Output LUT
- Cropping: Extraction-based from ALE (e.g., `RED_5120x2700_SPH_2.39_100`)

## Performance Optimization

### Caching
- CDL files are cached to avoid regeneration
- Logo images are cached in memory
- CSV data is loaded lazily on demand

### Multiprocessing
- Processes images in parallel using all CPU cores
- Batch processing reduces overhead
- Progress tracking with time estimates

### Memory Management
- Images are processed one at a time per worker
- Temporary files are cleaned up automatically
- Cache size limits prevent excessive disk usage

## Troubleshooting

### Common Issues

1. **"oiiotool not found"**
   - Install OpenImageIO for your platform
   - Ensure it's in your system PATH

2. **"Missing CDL values"**
   - Check ALE files contain ASC_SOP and ASC_SAT columns
   - Verify clip names match between files

3. **"Font file not found"**
   - Place `monarcha-regular.ttf` in the script directory
   - Or update `font_path` in configuration

4. **Memory errors with large batches**
   - Reduce `--batch-size` parameter
   - Use `--profile preview` for lower memory usage

### Debug Mode

Enable verbose logging for troubleshooting:
```bash
python stillgen.py [...] --verbose
```

Check `stillgen.log` for detailed processing information.

## Module Structure

- `stillgen.py` - Main entry point and orchestration
- `config.py` - Configuration management
- `parsers.py` - ALE, CSV, and Silverstack file parsing
- `cdl.py` - Color Decision List handling
- `image_processor.py` - Core image processing pipeline
- `overlay.py` - Text and logo overlay generation
- `utils.py` - Utility functions
- `dependencies.py` - Dependency checking and setup

## Contributing

To extend or modify StillGen:

1. Each module has a single responsibility
2. Add new features by extending existing modules
3. Use type hints for better code documentation
4. Follow the existing logging patterns
5. Update tests when adding features

## License

[Your license information here]

## Credits

Developed for professional film production workflows.
