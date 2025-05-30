#!/usr/bin/env python3
"""
Setup script to create the proper folder structure for StillGen
"""
import os
import shutil
from pathlib import Path


def setup_stillgen_structure():
    """Create the StillGen folder structure."""
    print("Setting up StillGen folder structure...")
    
    # Define the folder structure with new naming convention
    folders = [
        '01_INPUT_STILLS',
        '02_DIT_CSV',
        '03_DIT_FbF',
        '04_LAB_ALE',
        '05_OUTPUT_STILLS',
        'stillgen',
        'stillgen/static',
        'stillgen/static/lut_dir',
        'stillgen/static/fonts',
    ]
    
    # Create folders
    for folder in folders:
        Path(folder).mkdir(parents=True, exist_ok=True)
        print(f"✓ Created {folder}/")
    
    # Define files to move/create
    package_files = {
        'stillgen/__init__.py': 'Package initialization',
        'stillgen/config.py': 'Configuration management',
        'stillgen/parsers.py': 'File parsers',
        'stillgen/cdl.py': 'Color management',
        'stillgen/image_processor.py': 'Image processing',
        'stillgen/overlay.py': 'Overlay generation',
        'stillgen/utils.py': 'Utilities',
        'stillgen/dependencies.py': 'Dependency checking',
    }
    
    static_files = {
        'stillgen/static/config_template.ocio': 'OCIO config template',
        'stillgen/static/logo_image.png': 'Logo image',
        'stillgen/static/tool_image.png': 'Tool image',
        'stillgen/static/fonts/monarcha-regular.ttf': 'Font file',
    }
    
    # Check for existing files to move
    existing_files = {
        'config.py': 'stillgen/config.py',
        'parsers.py': 'stillgen/parsers.py',
        'cdl.py': 'stillgen/cdl.py',
        'image_processor.py': 'stillgen/image_processor.py',
        'overlay.py': 'stillgen/overlay.py',
        'utils.py': 'stillgen/utils.py',
        'dependencies.py': 'stillgen/dependencies.py',
        'config_template.ocio': 'stillgen/static/config_template.ocio',
        'logo_image.png': 'stillgen/static/logo_image.png',
        'tool_image.png': 'stillgen/static/tool_image.png',
        'monarcha-regular.ttf': 'stillgen/static/fonts/monarcha-regular.ttf',
        'miso-regular.ttf': 'stillgen/static/fonts/monarcha-regular.ttf',  # Alternative font name
    }
    
    # Move existing files
    for src, dst in existing_files.items():
        if os.path.exists(src) and not os.path.exists(dst):
            try:
                shutil.move(src, dst)
                print(f"✓ Moved {src} -> {dst}")
            except Exception as e:
                print(f"✗ Failed to move {src}: {e}")
    
    # Move LUT files if lut_dir exists
    if os.path.exists('lut_dir') and os.path.isdir('lut_dir'):
        lut_files = os.listdir('lut_dir')
        if lut_files:
            for lut_file in lut_files:
                src = os.path.join('lut_dir', lut_file)
                dst = os.path.join('stillgen/static/lut_dir', lut_file)
                if os.path.isfile(src):
                    shutil.copy2(src, dst)
            print(f"✓ Copied {len(lut_files)} LUT files to stillgen/static/lut_dir/")
    
    # Create placeholder files if they don't exist
    for file_path, description in {**package_files, **static_files}.items():
        if not os.path.exists(file_path):
            print(f"⚠ Missing: {file_path} ({description})")
    
    # Update imports in moved files
    update_imports()
    
    print("\n✓ Folder structure setup complete!")
    print("\nUsage:")
    print("  python stillgen.py")
    print("\nOr with custom folders:")
    print("  python stillgen.py 01_INPUT_STILLS 05_OUTPUT_STILLS 03_DIT_FbF 04_LAB_ALE 02_DIT_CSV")
    print("\nNote: Place your files in the appropriate folders:")
    print("  - TIFF files -> 01_INPUT_STILLS/")
    print("  - Silverstack CSVs -> 02_DIT_CSV/")
    print("  - Frame CSVs -> 03_DIT_FbF/")
    print("  - ALE files -> 04_LAB_ALE/")
    print("  - LUT files -> stillgen/static/lut_dir/")


def update_imports():
    """Update import statements in moved files."""
    files_to_update = [
        'stillgen/config.py',
        'stillgen/parsers.py',
        'stillgen/cdl.py',
        'stillgen/image_processor.py',
        'stillgen/overlay.py',
        'stillgen/utils.py',
    ]
    
    import_replacements = {
        'from parsers import': 'from stillgen.parsers import',
        'from config import': 'from stillgen.config import',
        'from cdl import': 'from stillgen.cdl import',
        'from overlay import': 'from stillgen.overlay import',
        'from utils import': 'from stillgen.utils import',
        'from dependencies import': 'from stillgen.dependencies import',
        'import parsers': 'import stillgen.parsers as parsers',
        'import config': 'import stillgen.config as config',
        'import cdl': 'import stillgen.cdl as cdl',
        'import overlay': 'import stillgen.overlay as overlay',
        'import utils': 'import stillgen.utils as utils',
    }
    
    for file_path in files_to_update:
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r') as f:
                    content = f.read()
                
                # Check if file needs updating (avoid relative imports within package)
                if file_path.startswith('stillgen/'):
                    # For files within the package, use relative imports
                    for old, new in import_replacements.items():
                        if 'from stillgen.' in new:
                            # Convert to relative import
                            relative = new.replace('from stillgen.', 'from .')
                            content = content.replace(old, relative)
                        elif 'import stillgen.' in new:
                            # Convert to relative import
                            module = new.split(' as ')[1]
                            relative = f'from . import {module}'
                            content = content.replace(old, relative)
                
                with open(file_path, 'w') as f:
                    f.write(content)
                    
            except Exception as e:
                print(f"Failed to update imports in {file_path}: {e}")


if __name__ == "__main__":
    setup_stillgen_structure()
