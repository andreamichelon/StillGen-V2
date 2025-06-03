#!/usr/bin/env python3
"""
StillGen - Film Still Processing Tool
Main entry point
"""
import sys
import os
import argparse
import logging
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm
import multiprocessing

# Add the stillgen package to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stillgen.dependencies import check_dependencies
from stillgen.parsers import parse_ale_files, parse_silverstack_files, LazyCSVLoader
from stillgen.image_processor import StillProcessor
from stillgen.config import Config, ProcessingProfile
from stillgen.utils import find_tiff_files, process_in_batches

# Set up logging
def setup_logging(verbose=False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('stillgen.log'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='StillGen - Film Still Processing Tool')
    
    # Required arguments with new folder names
    parser.add_argument('input_folder', nargs='?', default='01_INPUT_STILLS',
                        help='Input folder containing TIFF files (default: 01_INPUT_STILLS)')
    parser.add_argument('output_folder', nargs='?', default='05_OUTPUT_STILLS',
                        help='Output folder for processed images (default: 05_OUTPUT_STILLS)')
    parser.add_argument('frame_csv_folder', nargs='?', default='03_DIT_FbF',
                        help='Folder containing per-frame CSV files (default: 03_DIT_FbF)')
    parser.add_argument('lab_ale_folder', nargs='?', default='04_LAB_ALE',
                        help='Folder containing lab ALE files (default: 04_LAB_ALE)')
    parser.add_argument('silverstack_csv_folder', nargs='?', default='02_DIT_CSV',
                        help='Folder containing Silverstack CSV files (default: 02_DIT_CSV)')
    
    # Optional arguments
    parser.add_argument('--profile', choices=['preview', 'final'], default='final',
                        help='Processing profile (preview for faster processing)')
    parser.add_argument('--workers', type=int, default=None,
                        help='Number of worker processes (default: CPU count)')
    parser.add_argument('--batch-size', type=int, default=10,
                        help='Batch size for processing (default: 10)')
    parser.add_argument('--resume', action='store_true',
                        help='Resume processing (skip existing files)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Perform a dry run without processing')
    parser.add_argument('--verbose', action='store_true',
                        help='Enable verbose logging')
    parser.add_argument('--config-file', help='Optional configuration file (YAML/JSON)')
    
    return parser.parse_args()


def get_static_paths():
    """Get paths to static resources in the stillgen package."""
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    static_dir = os.path.join(script_dir, 'stillgen', 'static')
    
    return {
        'config_template': os.path.join(static_dir, 'config_template.ocio'),
        'lut_dir': os.path.join(static_dir, 'lut_dir'),
        'logo_image': os.path.join(static_dir, 'logo_image.png'),
        'tool_image': os.path.join(static_dir, 'tool_image.png'),
        'font_path': os.path.join(static_dir, 'fonts', 'monarcha-regular.ttf')
    }


def process_batch(batch_args):
    """Process a batch of images. Used for multiprocessing."""
    batch_files, config, ale_data, silverstack_data, csv_loader = batch_args
    results = []
    
    # Create processor for this batch
    processor = StillProcessor(config, ale_data, silverstack_data, csv_loader)
    
    for file_path in batch_files:
        try:
            success = processor.process_image(file_path)
            # Clean up any temporary CDL files
            temp_cdl = os.path.join(os.path.dirname(file_path), f"tmp{os.path.basename(file_path)}.cdl")
            if os.path.exists(temp_cdl):
                os.remove(temp_cdl)
            results.append((file_path, success, None))
        except Exception as e:
            results.append((file_path, False, str(e)))
    
    return results


def main():
    args = parse_arguments()
    logger = setup_logging(args.verbose)
    
    logger.info("=== StillGen Processing Started ===")
    
    # Get static resource paths
    static_paths = get_static_paths()
    
    # Check that static resources exist
    for resource_name, resource_path in static_paths.items():
        if not os.path.exists(resource_path):
            logger.error(f"Required resource not found: {resource_name} at {resource_path}")
            logger.error("Please ensure the stillgen package is properly installed with all static files.")
            sys.exit(1)
    
    # Check dependencies
    if not args.dry_run:
        logger.info("Checking dependencies...")
        if not check_dependencies():
            logger.error("Dependency check failed. Please install missing dependencies.")
            sys.exit(1)
    
    # Create configuration with static paths
    config = Config(
        input_folder=args.input_folder,
        output_folder=args.output_folder,
        lut_dir=static_paths['lut_dir'],
        frame_csv_folder=args.frame_csv_folder,
        lab_ale_folder=args.lab_ale_folder,
        config_template_path=static_paths['config_template'],
        silverstack_csv_folder=args.silverstack_csv_folder,
        profile=ProcessingProfile(args.profile),
        resume=args.resume,
        # Override with static paths
        logo_image=static_paths['logo_image'],
        tool_image=static_paths['tool_image'],
        font_path=static_paths['font_path']
    )
    
    # Load configuration file if provided
    if args.config_file:
        config.load_from_file(args.config_file)
        # Ensure static paths are not overridden
        config.lut_dir = static_paths['lut_dir']
        config.config_template_path = static_paths['config_template']
        config.logo_image = static_paths['logo_image']
        config.tool_image = static_paths['tool_image']
        config.font_path = static_paths['font_path']
    
    # Load data
    logger.info("Loading ALE files...")
    ale_data = parse_ale_files(config.lab_ale_folder)
    if not ale_data:
        logger.error("No ALE data loaded. Check your ALE files.")
        sys.exit(1)
    logger.info(f"Loaded {len(ale_data)} clips from ALE files")
    
    logger.info("Loading Silverstack CSV files...")
    silverstack_data = parse_silverstack_files(config.silverstack_csv_folder)
    logger.info(f"Loaded {len(silverstack_data)} clips from Silverstack files")
    
    # Create lazy CSV loader
    csv_loader = LazyCSVLoader(config.frame_csv_folder)
    
    # Find all TIFF files
    logger.info("Scanning for TIFF files...")
    tiff_files = find_tiff_files(config.input_folder)
    
    if not tiff_files:
        logger.error(f"No TIFF files found in {config.input_folder}")
        sys.exit(1)
    
    # Filter out already processed files if resuming
    if config.resume:
        original_count = len(tiff_files)
        tiff_files = [f for f in tiff_files if not config.is_processed(f)]
        logger.info(f"Resuming: {len(tiff_files)} of {original_count} files remaining")
    else:
        logger.info(f"Found {len(tiff_files)} TIFF files to process")
    
    if args.dry_run:
        logger.info("DRY RUN - Files that would be processed:")
        for f in tiff_files[:10]:
            logger.info(f"  {f}")
        if len(tiff_files) > 10:
            logger.info(f"  ... and {len(tiff_files) - 10} more files")
        return
    
    # Process files
    processed = 0
    errors = []
    
    # Determine number of workers
    num_workers = args.workers or multiprocessing.cpu_count()
    logger.info(f"Using {num_workers} worker processes")
    
    # Process in batches
    batches = list(process_in_batches(tiff_files, args.batch_size))
    
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        # Prepare batch arguments
        batch_args = [
            (batch, config, ale_data, silverstack_data, csv_loader)
            for batch in batches
        ]
        
        # Submit all batches
        future_to_batch = {
            executor.submit(process_batch, args): i
            for i, args in enumerate(batch_args)
        }
        
        # Process results with progress bar
        with tqdm(total=len(tiff_files), desc="Processing images") as pbar:
            for future in as_completed(future_to_batch):
                batch_idx = future_to_batch[future]
                try:
                    results = future.result()
                    for file_path, success, error in results:
                        if success:
                            processed += 1
                        else:
                            errors.append((file_path, error))
                        pbar.update(1)
                except Exception as e:
                    logger.error(f"Batch {batch_idx} failed: {str(e)}")
                    # Update progress bar for failed batch
                    pbar.update(len(batches[batch_idx]))
    
    # Report results
    logger.info(f"\n=== Processing Complete ===")
    logger.info(f"Successfully processed: {processed}/{len(tiff_files)} files")
    
    # Clean up any remaining temporary CDL files
    for root, _, files in os.walk(config.input_folder):
        for file in files:
            if file.startswith('tmp') and file.endswith('.cdl'):
                try:
                    os.remove(os.path.join(root, file))
                except Exception as e:
                    logger.warning(f"Failed to remove temporary file {file}: {e}")
    
    if errors:
        logger.error(f"Errors encountered: {len(errors)}")
        for file_path, error in errors[:5]:
            logger.error(f"  {file_path}: {error}")
        if len(errors) > 5:
            logger.error(f"  ... and {len(errors) - 5} more errors")
    
    # Save processing report
    config.save_processing_report(processed, errors)


if __name__ == "__main__":
    main()