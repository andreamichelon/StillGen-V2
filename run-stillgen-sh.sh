#!/bin/bash
# StillGen Runner Script for Unix/Mac

# Colors for output (using printf for better compatibility)
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

printf "${GREEN}=== StillGen Film Still Processor ===${NC}\n"

# Check system dependencies
printf "${YELLOW}Checking system dependencies...${NC}\n"

# Check if Homebrew is installed
if ! command -v brew &> /dev/null; then
    printf "${RED}✗ Homebrew not found!${NC}\n"
    echo "Install Homebrew first: https://brew.sh/"
    echo '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
    exit 1
fi

# Check and install OpenImageIO
if ! command -v oiiotool &> /dev/null; then
    printf "${YELLOW}Installing OpenImageIO via Homebrew...${NC}\n"
    brew install openimageio
fi

# Check and install OpenColorIO (optional but recommended)
if ! brew list opencolorio &> /dev/null; then
    printf "${YELLOW}Installing OpenColorIO via Homebrew...${NC}\n"
    brew install opencolorio
fi

# Check if pipx is installed
if ! command -v pipx &> /dev/null; then
    printf "${YELLOW}Installing pipx via Homebrew...${NC}\n"
    brew install pipx
    pipx ensurepath
fi

# Install colour-science via pipx
if ! pipx list | grep -q colour-science; then
    printf "${YELLOW}Installing colour-science via pipx...${NC}\n"
    pipx install colour-science --include-deps
fi

# Check if virtual environment exists
if [ -d "venv" ]; then
    printf "${GREEN}✓ Virtual environment found${NC}\n"
    source venv/bin/activate
    
    # Check if required packages are installed
    python -c "import tqdm" 2>/dev/null
    if [ $? -ne 0 ]; then
        printf "${YELLOW}Installing required packages...${NC}\n"
        pip install -r requirements.txt
    fi
else
    printf "${YELLOW}⚠ Virtual environment not found${NC}\n"
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    echo "Installing required packages..."
    pip install -r requirements.txt
fi

# Check if stillgen package exists
if [ ! -d "stillgen" ]; then
    printf "${RED}✗ stillgen package directory not found!${NC}\n"
    echo "Run setup_folders.py first to organize the folder structure"
    exit 1
fi

# Default folders with new naming convention
INPUT_FOLDER="01_INPUT_STILLS"
OUTPUT_FOLDER="05_OUTPUT_STILLS"
FRAME_CSV_FOLDER="03_DIT_FbF"
LAB_ALE_FOLDER="04_LAB_ALE"
SILVERSTACK_CSV_FOLDER="02_DIT_CSV"

# Check if folders exist
for folder in "$INPUT_FOLDER" "$OUTPUT_FOLDER" "$FRAME_CSV_FOLDER" "$LAB_ALE_FOLDER" "$SILVERSTACK_CSV_FOLDER"; do
    if [ ! -d "$folder" ]; then
        printf "${YELLOW}Creating $folder/${NC}\n"
        mkdir -p "$folder"
    fi
done

# Parse command line options
EXTRA_ARGS=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --preview)
            EXTRA_ARGS="$EXTRA_ARGS --profile preview"
            shift
            ;;
        --resume)
            EXTRA_ARGS="$EXTRA_ARGS --resume"
            shift
            ;;
        --dry-run)
            EXTRA_ARGS="$EXTRA_ARGS --dry-run"
            shift
            ;;
        --verbose)
            EXTRA_ARGS="$EXTRA_ARGS --verbose"
            shift
            ;;
        --workers)
            EXTRA_ARGS="$EXTRA_ARGS --workers $2"
            shift 2
            ;;
        --batch-size)
            EXTRA_ARGS="$EXTRA_ARGS --batch-size $2"
            shift 2
            ;;
        --el-zone)
            EXTRA_ARGS="$EXTRA_ARGS --el-zone"
            shift
            ;;
        --el-zone-log)
            EXTRA_ARGS="$EXTRA_ARGS --el-zone-log $2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [options]"
            echo "Options:"
            echo "  --preview       Use preview profile for faster processing"
            echo "  --resume        Resume processing (skip existing files)"
            echo "  --dry-run       Show what would be processed without doing it"
            echo "  --verbose       Enable verbose logging"
            echo "  --workers N     Number of worker processes"
            echo "  --batch-size N  Images per batch"
            echo "  --el-zone       Generate EL Zone System analysis (4-quadrant layout)"
            echo "  --el-zone-log FORMAT  Log format (logc4, slog3, apple_log, linear)"
            echo "  --help          Show this help message"
            exit 0
            ;;
        *)
            printf "${RED}Unknown option: $1${NC}\n"
            exit 1
            ;;
    esac
done

# Check for input files
if [ -d "$INPUT_FOLDER" ]; then
    TIFF_COUNT=$(find "$INPUT_FOLDER" -type f \( -name "*.tiff" -o -name "*.tif" -o -name "*.TIFF" -o -name "*.TIF" \) 2>/dev/null | wc -l | tr -d ' ')
else
    TIFF_COUNT=0
fi

if [ -d "$LAB_ALE_FOLDER" ]; then
    ALE_COUNT=$(find "$LAB_ALE_FOLDER" -type f \( -name "*.ale" -o -name "*.ALE" \) 2>/dev/null | wc -l | tr -d ' ')
else
    ALE_COUNT=0
fi

printf "\nFile counts:\n"
printf "  TIFF files: ${GREEN}$TIFF_COUNT${NC} in $INPUT_FOLDER\n"
printf "  ALE files: ${GREEN}$ALE_COUNT${NC} in $LAB_ALE_FOLDER\n"

if [ "$TIFF_COUNT" -eq "0" ]; then
    printf "${YELLOW}⚠ No TIFF files found in $INPUT_FOLDER${NC}\n"
    echo "  Looking for: *.tiff, *.tif, *.TIFF, *.TIF"
fi

if [ "$ALE_COUNT" -eq "0" ]; then
    printf "${YELLOW}⚠ No ALE files found in $LAB_ALE_FOLDER${NC}\n"
    echo "  Looking for: *.ale, *.ALE"
    # List what's actually in the folder for debugging
    if [ -d "$LAB_ALE_FOLDER" ]; then
        FILE_COUNT=$(ls -1 "$LAB_ALE_FOLDER" 2>/dev/null | wc -l | tr -d ' ')
        if [ "$FILE_COUNT" -gt "0" ]; then
            echo "  Files in folder:"
            ls -la "$LAB_ALE_FOLDER" | head -10
        fi
    fi
fi

# Only exit if both are zero
if [ "$TIFF_COUNT" -eq "0" ] && [ "$ALE_COUNT" -eq "0" ]; then
    printf "${RED}✗ No input files found${NC}\n"
    exit 1
fi

# Run StillGen (no arguments needed with default folders)
printf "\n${GREEN}Starting StillGen processing...${NC}\n"
python stillgen.py $EXTRA_ARGS

# Check exit status
if [ $? -eq 0 ]; then
    printf "\n${GREEN}✓ Processing completed successfully!${NC}\n"
else
    printf "\n${RED}✗ Processing failed!${NC}\n"
    exit 1
fi
