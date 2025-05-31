# StillGen - Film Still Processing Tool

StillGen is a high-performance tool for processing film stills with color grading, metadata overlays, and batch processing capabilities.

## Features

- **Color Management**: Apply CDL (Color Decision List) and LUTs using OpenColorIO
- **Metadata Overlays**: Automatically add production information, technical data, and logos
- **Batch Processing**: Process multiple images in parallel using all CPU cores
- **Smart Caching**: Cache CDL files and images for improved performance
- **Resume Capability**: Skip already processed files when resuming interrupted jobs
- **Multiple Profiles**: Preview and final quality profiles for different use cases
- **Configuration Files**: YAML/JSON configuration support for easy setup

## Installation

### Prerequisites

1. **Python 3.6+**
2. **OpenImageIO** (for `oiiotool` command)
   - macOS: `brew install openimageio`
   - Linux: `sudo apt-get install openimageio-tools`
   - Windows: Download from [OpenImageIO releases](https://github.com/OpenImageIO/oiio/releases)

### Setup

1. Clone or download the StillGen files
2. Run the setup script to organize the folder structure:
   ```bash
   python setup_folders.py
   ```
3. Create a virtual environment (recommended):
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
4. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
5. Place required files in the appropriate locations:
   - OCIO config template → `stillgen/static/config_template.ocio`
   - Logo images → `stillgen/static/logo_image.png` and `tool_image.png`
   - Font file → `stillgen/static/fonts/monarcha-regular.ttf`
   - LUT files → `stillgen/static/lut_dir/`
6. Place your content in the numbered folders:
   - TIFF files → `01_INPUT_STILLS/`
   - Silverstack CSVs → `02_DIT_CSV/`
   - Frame CSVs → `03_DIT_FbF/`
   - ALE files → `04_LAB_ALE/`

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
- Input files: `CLIPNAME-HH_MM_SS_FF.tiff`
  - Example: `A001_C002_0123AB-01_23_45_12.tiff`
- Output files: Generated based on metadata
  - Example: `EP01_SC02_TK03_A_20240115_Day1_Main_DayExterior_4512.tiff`

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
